import os
import requests
import instructor
from openai import OpenAI
from pydantic import BaseModel, Field
from src.retrieval.hybrid import hybrid_retriever
from src.database.supabase_client import supabase_manager
from langsmith import traceable

client = instructor.from_openai(OpenAI(
    api_key=os.environ.get("GROQ_API_KEY", ""),
    base_url="https://api.groq.com/openai/v1"
))

gen_client = OpenAI(
    api_key=os.environ.get("SARVAM_API_KEY", ""),
    base_url="https://api.sarvam.ai/v1"
)

# Create a separate instructor client specifically for Sarvam to handle structured Pydantic outputs
sarvam_instructor = instructor.from_openai(gen_client)

# Create a separate instructor client specifically for Sarvam to handle structured Pydantic outputs
sarvam_instructor = instructor.from_openai(gen_client)

class RouteDecision(BaseModel):
    intent: str = Field(description="Must be exactly 'greeting', 'faq', or 'technical_query'")

class GraderDecision(BaseModel):
    is_relevant: str = Field(description="Must be exactly 'yes' or 'no'")

class RewrittenQuery(BaseModel):
    new_query: str = Field(description="The reformulated question")


@traceable(name="route_query")
def route_query(state):
    print("--- ROUTING QUERY VIA SARVAM-105B ---")
    question = state["question"]
    try:
        decision = sarvam_instructor.chat.completions.create(
            model="sarvam-105b",
            response_model=RouteDecision,
            messages=[
                {"role": "system", "content": "Classify the intent of the user query. ONLY return 'greeting' or 'faq' for pure small talk (like 'hello', 'who are you'). ALL other queries asking about systems, compatibility, developers, features, or documents MUST be classified as 'technical_query'."},
                {"role": "user", "content": question}
            ]
        )
        route = decision.intent
    except Exception as e:
        print(f"Router failed: {e}. Defaulting to technical_query.")
        route = "technical_query"
        
    print(f"Decision: {route}")
    return {"route": route}

@traceable(name="retrieve_context")
def retrieve(state):
    print("--- HYBRID RETRIEVAL (BM25 + Vector + Graph + RRF) ---")
    question = state["question"]
    tenant_id = state["tenant_id"]
    
    docs = hybrid_retriever(tenant_id, question)
    return {"documents": docs}

@traceable(name="grade_documents")
def grade_documents(state):
    print("--- GRADING CONTEXT VIA JINA CROSS-ENCODER RERANKER ---")
    question = state["question"]
    documents = state["documents"]
    
    if documents == "No relevant context found.":
        return {"route": "no"}
        
    try:
        # Split documents back into a list of individual chunks
        chunks = documents.split("\n\n---\n\n")
        
        # Call Jina Reranker API
        headers = {
            "Authorization": f"Bearer {os.environ.get('JINA_API_KEY')}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "jina-reranker-v2-base-multilingual",
            "query": question,
            "documents": chunks,
            "top_n": len(chunks)
        }
        
        response = requests.post("https://api.jina.ai/v1/rerank", headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        filtered_chunks = []
        # Sort results by relevance score descending just in case
        sorted_results = sorted(data.get("results", []), key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        for result in sorted_results[:3]:  # Keep top 3, but enforce threshold
            if result.get("relevance_score", 0) >= 0.05:
                index = result.get("index")
                filtered_chunks.append(chunks[index])
                
        if not filtered_chunks:
            print("Decision: no (all chunks filtered out by Reranker)")
            return {"route": "no", "documents": "No relevant context found."}
            
        print(f"Decision: yes (kept {len(filtered_chunks)}/{len(chunks)} chunks)")
        return {"route": "yes", "documents": "\n\n---\n\n".join(filtered_chunks)}
        
    except Exception as e:
        print(f"Grader (Reranker) failed: {e}. Defaulting to yes.")
        return {"route": "yes"}

@traceable(name="generate_answer")
def generate(state):
    print("--- GENERATING FINAL ANSWER VIA SARVAM-105B ---")
    question = state["question"]
    documents = state["documents"]
    preferences = state.get("preferences", {})
    summary = state.get("summary", "")
    chat_history = state.get("chat_history", [])
    
    system_prompt = "You are an expert SaaS support assistant. Answer the user's question using ONLY the provided context. You must ONLY answer in English, regardless of the language the user speaks. If the context doesn't have the answer, say you don't know."
    
    if preferences:
        system_prompt += f"\n\nCRITICAL USER PREFERENCES YOU MUST FOLLOW:\n{preferences}"
        
    context_block = f"Context:\n{documents}"
    if summary:
        context_block += f"\n\nPrevious Conversation Summary:\n{summary}"
        
    # Inject Short-Term Memory Buffer
    if chat_history:
        # Keep up to the last 6 messages
        recent_history = chat_history[-6:]
        history_str = ""
        for msg in recent_history:
            role = "User" if msg["role"] == "user" else "Assistant"
            history_str += f"{role}: {msg['content']}\n"
        context_block += f"\n\nRecent Chat History:\n{history_str}"
    
    response = gen_client.chat.completions.create(
        model="sarvam-105b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{context_block}\n\nQuestion: {question}"}
        ]
    )
    return {"generation": response.choices[0].message.content}

@traceable(name="load_memory")
def load_memory(state):
    print("--- LOADING LTM (PREFERENCES & EPISODIC) ---")
    tenant_id = state["tenant_id"]
    user_id = state.get("user_id", "default_user")
    
    db = supabase_manager.get_tenant_client(tenant_id)
    
    # 1. Load Preferences
    preferences = {}
    try:
        pref_res = db.table("preference_memory").select("pref_key, pref_value").eq("tenant_id", tenant_id).eq("user_id", user_id).execute()
        for row in pref_res.data:
            preferences[row["pref_key"]] = row["pref_value"]
    except Exception as e:
        print(f"Failed to load preferences: {e}")
        
    # 2. Load latest episodic summary
    summary = ""
    try:
        # Get the most recent summary
        sum_res = db.table("episodic_memory").select("summary").eq("tenant_id", tenant_id).eq("user_id", user_id).order("completed_at", desc=True).limit(1).execute()
        if sum_res.data:
            summary = sum_res.data[0]["summary"]
    except Exception as e:
        print(f"Failed to load summary: {e}")
        
    print(f"Loaded {len(preferences)} preferences and summary length {len(summary)}")
    return {"preferences": preferences, "summary": summary}

@traceable(name="save_memory")
def save_memory(state):
    print("--- SAVING LTM (EPISODIC DISTILLATION) ---")
    tenant_id = state["tenant_id"]
    user_id = state.get("user_id", "default_user")
    chat_history = state.get("chat_history", [])
    current_summary = state.get("summary", "")
    
    try:
        history_str = ""
        for msg in chat_history:
            role = "User" if msg["role"] == "user" else "Assistant"
            history_str += f"{role}: {msg['content']}\n"
            
        # Append the current interaction!
        current_q = state.get("question", "")
        current_a = state.get("generation", "")
        if current_q and current_a:
            history_str += f"User: {current_q}\nAssistant: {current_a}\n"
            
        if not history_str.strip():
            return {}
            
        system_prompt = "You are a memory distillation AI. Given an existing summary and a new chat transcript, generate an updated, concise summary of the entire interaction. Focus on key facts, decisions, and context. Do NOT answer the user."
        prompt = f"Existing Summary: {current_summary}\n\nNew Transcript:\n{history_str}"
        
        response = gen_client.chat.completions.create(
            model="sarvam-105b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        )
        new_summary = response.choices[0].message.content
        
        # Save to DB
        db = supabase_manager.get_tenant_client(tenant_id)
        db.table("episodic_memory").insert({
            "tenant_id": tenant_id,
            "user_id": user_id,
            "summary": new_summary
        }).execute()
        
        print(f"Distilled new summary: {new_summary[:50]}...")
        return {"summary": new_summary}
    except Exception as e:
        print(f"Failed to save episodic memory: {e}")
        return {}

@traceable(name="rewrite_query")
def rewrite(state):
    print("--- REWRITING QUERY VIA SARVAM-105B ---")
    question = state["question"]
    rewrite_count = state.get("rewrite_count", 0) + 1
    try:
        decision = sarvam_instructor.chat.completions.create(
            model="sarvam-105b",
            response_model=RewrittenQuery,
            messages=[
                {"role": "system", "content": "Reformulate this question to be highly specific for vector database search."},
                {"role": "user", "content": question}
            ]
        )
        new_q = decision.new_query
    except Exception as e:
        print("Rewrite failed, using original.")
        new_q = question
        
    print(f"New query: {new_q} (Rewrite #{rewrite_count})")
    return {"question": new_q, "rewrite_count": rewrite_count}

def generate_cached(state):
    print("--- GENERATING CACHED RESPONSE ---")
    return {"generation": "Hello! I am your AI Support Assistant. I'm ready to help you with technical questions about your infrastructure."}

@traceable(name="contextualize_query")
def contextualize_query(state):
    print("--- CONTEXTUALIZING QUERY ---")
    question = state["question"]
    chat_history = state.get("chat_history", [])
    
    if not chat_history:
        return {"question": question}
        
    try:
        # Construct the conversation string
        history_str = ""
        for msg in chat_history:
            role = "User" if msg["role"] == "user" else "Assistant"
            history_str += f"{role}: {msg['content']}\n"
            
        decision = sarvam_instructor.chat.completions.create(
            model="sarvam-105b",
            response_model=RewrittenQuery,
            messages=[
                {"role": "system", "content": "You are a query contextualizer. Given a conversation history and the latest user query, rewrite the user query to be a standalone question that can be understood without the history. Do NOT answer the question, just reformulate it."},
                {"role": "user", "content": f"Chat History:\n{history_str}\n\nLatest Query: {question}"}
            ]
        )
        new_q = decision.new_query
        print(f"Contextualized Query: {new_q}")
        return {"question": new_q}
    except Exception as e:
        print(f"Contextualize failed, using original: {e}")
        return {"question": question}
