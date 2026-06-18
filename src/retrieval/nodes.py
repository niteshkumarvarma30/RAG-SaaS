import os
import requests
import instructor
from openai import OpenAI
from pydantic import BaseModel, Field
from src.retrieval.hybrid import hybrid_retriever
from src.database.supabase_client import supabase_manager
from langsmith import traceable
import google.generativeai as genai

genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))

client = instructor.from_openai(OpenAI(
    api_key=os.environ.get("GROQ_API_KEY", ""),
    base_url="https://api.groq.com/openai/v1"
))

gen_client = OpenAI(
    api_key=os.environ.get("SARVAM_API_KEY", ""),
    base_url="https://api.sarvam.ai/v1"
)

github_client = OpenAI(
    api_key=os.environ.get("GITHUB_TOKEN", ""),
    base_url="https://models.inference.ai.azure.com"
)

# Create a separate instructor client specifically for Sarvam to handle structured Pydantic outputs
sarvam_instructor = instructor.from_openai(gen_client)

# Create a separate instructor client specifically for Sarvam to handle structured Pydantic outputs
sarvam_instructor = instructor.from_openai(gen_client)

# Create the instructor client for Github Models (gpt-4o-mini)
instructor_client = instructor.from_openai(github_client)

class RouteDecision(BaseModel):
    intent: str = Field(description="Must be exactly 'greeting', 'faq', 'conversational', or 'technical_query'")

class GraderDecision(BaseModel):
    is_relevant: str = Field(description="Must be exactly 'yes' or 'no'")

from src.retrieval.hybrid import get_embedding
from src.retrieval.cache import LRUCache

response_cache = LRUCache(max_size=500)
memory_cache = LRUCache(max_size=200)

class RewrittenQuery(BaseModel):
    new_query: str = Field(description="The reformulated question")

class MemoryExtraction(BaseModel):
    facts: list[str] = Field(description="A list of standalone factual statements extracted from the latest interaction")
    preferences: dict[str, str] = Field(description="A dictionary mapping preference keys (e.g. 'formatting', 'language') to values (e.g. 'bullet points', 'Spanish') based on explicit user instructions.")


@traceable(name="embed_query")
def embed_query(state):
    print("--- EMBEDDING QUERY ---")
    question = state["question"]
    try:
        query_embedding = get_embedding(question)
        return {"query_embedding": query_embedding}
    except Exception as e:
        print(f"Failed to generate query embedding: {e}")
        return {"query_embedding": []}

@traceable(name="check_semantic_cache")
def check_cache(state):
    print("--- CHECKING SEMANTIC CACHE ---")
    question = state["question"]
    tenant_id = state["tenant_id"]
    user_id = state.get("user_id", "default_user")
    
    try:
        # 1. Check RAM Exact-Match Response Cache first (0ms)
        r_key = response_cache.generate_key(tenant_id, question)
        cached_ans = response_cache.get(r_key)
        if cached_ans:
            print("[Cache Hit] Exact match found in RAM response_cache")
            return {"route": "cached", "generation": cached_ans}

        # 2. Check Supabase Vector Semantic Cache (>95% similarity)
        query_embedding = state.get("query_embedding")
        if not query_embedding:
            return {"route": "not_cached"}
            
        db = supabase_manager.get_tenant_client(tenant_id)
        
        response = db.rpc("match_semantic_cache", {
            "p_query_embedding": query_embedding,
            "p_tenant_id": tenant_id,
            "p_user_id": user_id,
            "match_threshold": 0.95
        }).execute()
        
        if response.data and len(response.data) > 0:
            cached_answer = response.data[0]["response"]
            print(f"Cache Hit! Similarity: {response.data[0]['similarity']:.4f}")
            return {"route": "cached", "generation": cached_answer}
            
        print("Cache Miss.")
        return {"route": "not_cached"}
    except Exception as e:
        print(f"Semantic Cache check failed: {e}")
        return {"route": "not_cached"}


@traceable(name="route_query")
def route_query(state):
    print("--- ROUTING QUERY VIA SARVAM-105B ---")
    question = state["question"]
    try:
        decision = instructor_client.chat.completions.create(
            model="gpt-4o-mini",
            response_model=RouteDecision,
            messages=[
                {"role": "system", "content": "Classify the intent of the user query. ONLY return 'greeting' or 'faq' for pure small talk (like 'hello', 'who are you'). Return 'conversational' if the user asks about the conversation history itself (like 'what did we talk about', 'summarize our chat'). ALL other queries asking about technical systems, features, or documents MUST be classified as 'technical_query'."},
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
    
    user_id = state.get("user_id", "default_user")
    query_embedding = state.get("query_embedding", [])
    
    docs = hybrid_retriever(tenant_id, user_id, question, query_embedding, top_k=10)
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
        import requests, os
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
        
        for result in sorted_results[:5]:  # Keep top 5, but enforce threshold
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
def generate(state, config):
    print("--- GENERATING FINAL ANSWER VIA SARVAM-30B ---")
    question = state["question"]
    documents = state["documents"]
    preferences = state.get("preferences", {})
    rolling_context = state.get("rolling_context", "")
    user_facts = state.get("user_facts", "")
    chat_history = state.get("chat_history", [])
    
    system_prompt = (
        "You are an expert SaaS support assistant. "
        "Answer the user's question using the provided Context, Relevant User Facts, Rolling Context, and Recent Chat History. "
        "If the user asks about the conversation itself, answer using the Recent Chat History. "
        "You must ONLY answer in English. If the answer cannot be found in ANY of the provided information, say exactly 'I don't know.'"
    )
    
    if preferences:
        system_prompt += f"\n\nCRITICAL USER PREFERENCES YOU MUST FOLLOW:\n{preferences}"
        
    context_block = f"Context:\n{documents}"
    if user_facts:
        context_block += f"\n\nRelevant User Facts:\n{user_facts}"
    if rolling_context:
        context_block += f"\n\nRolling Conversation Context:\n{rolling_context}"
        
    # Inject Short-Term Memory Buffer
    if chat_history:
        # Keep up to the last 4 messages (2 turns) since older ones are rolled up
        recent_history = chat_history[-4:]
        history_str = ""
        for msg in recent_history:
            role = "User" if msg["role"] == "user" else "Assistant"
            history_str += f"{role}: {msg['content']}\n"
        context_block += f"\n\nRecent Chat History:\n{history_str}"
    
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage
    import os
    
    llm = ChatOpenAI(
        model="sarvam-30b",
        temperature=0,
        base_url="https://api.sarvam.ai/v1",
        api_key=os.environ.get("SARVAM_API_KEY"),
        streaming=True
    )
    
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"{context_block}\n\nQuestion: {question}")
    ], config=config)
    
    return {"generation": response.content, "system_prompt": system_prompt, "context_block": context_block}

@traceable(name="load_memory")
def load_memory(state):
    print("--- LOADING LTM (FACTS, PREFS & ROLLING CONTEXT) ---")
    tenant_id = state["tenant_id"]
    user_id = state.get("user_id", "default_user")
    question = state.get("question", "")
    
    # 1. Check RAM Memory Cache for active users (0ms)
    mem_key = memory_cache.generate_key(tenant_id, user_id)
    cached_mem = memory_cache.get(mem_key)
    if cached_mem:
        print("[Cache Hit] Loaded LTM preferences and rolling context from RAM")
        # We must re-fetch facts since the question changed, but we keep the cached preferences/rolling
        preferences = cached_mem["preferences"]
        rolling = cached_mem["rolling_context"]
        db = supabase_manager.get_tenant_client(tenant_id)
    else:
        db = supabase_manager.get_tenant_client(tenant_id)
        
        # 1. Load Preferences
        preferences = {}
        try:
            pref_res = db.table("preference_memory").select("pref_key, pref_value").eq("tenant_id", tenant_id).eq("user_id", user_id).execute()
            for row in pref_res.data:
                preferences[row["pref_key"]] = row["pref_value"]
        except Exception as e:
            print(f"Failed to load preferences: {e}")
            
        # 2. Load latest rolling context
        rolling = ""
        try:
            sum_res = db.table("episodic_memory").select("summary").eq("tenant_id", tenant_id).eq("user_id", user_id).order("completed_at", desc=True).limit(1).execute()
            if sum_res.data:
                rolling = sum_res.data[0]["summary"]
        except Exception as e:
            print(f"Failed to load rolling context: {e}")
            
        # Cache preferences and rolling context for 5 minutes
        memory_cache.put(mem_key, {"preferences": preferences, "rolling_context": rolling}, ttl_seconds=300)
        
    # 3. Load User Facts via RPC
    user_facts = ""
    try:
        if question:
            query_embedding = state.get("query_embedding")
            if not query_embedding:
                query_embedding = get_embedding(question)
            fact_res = db.rpc("match_user_facts", {
                "p_query_embedding": query_embedding,
                "p_tenant_id": tenant_id,
                "p_user_id": user_id,
                "match_threshold": 0.5,
                "match_count": 3
            }).execute()
            if fact_res.data:
                user_facts = "\n".join([f"- {row['fact']}" for row in fact_res.data])
    except Exception as e:
        print(f"Failed to load user facts: {e}")
        
    print(f"Loaded {len(preferences)} preferences, {len(user_facts)} facts, and rolling context length {len(rolling)}")
    return {"preferences": preferences, "rolling_context": rolling, "user_facts": user_facts}

@traceable(name="save_memory")
def save_memory(state):
    print("--- SAVING LTM (FACT EXTRACTION & ROLLING SUMMARY) ---")
    tenant_id = state["tenant_id"]
    user_id = state.get("user_id", "default_user")
    chat_history = state.get("chat_history", [])
    current_rolling = state.get("rolling_context", "")
    current_q = state.get("question", "")
    current_a = state.get("generation", "")
    
    if not current_q or not current_a or "I don't know" in current_a:
        return {}
        
    # Cache the final response for exact-match hits
    r_key = response_cache.generate_key(tenant_id, current_q)
    response_cache.put(r_key, current_a, ttl_seconds=3600)
        
    db = supabase_manager.get_tenant_client(tenant_id)
    
    # 1. Fact & Preference Extraction
    interaction = f"User: {current_q}\nAssistant: {current_a}"
    try:
        decision = sarvam_instructor.chat.completions.create(
            model="sarvam-30b",
            response_model=MemoryExtraction,
            mode=instructor.Mode.JSON,
            messages=[
                {"role": "system", "content": "Extract highly specific, discrete facts about the user's setup, and ALSO extract any explicit rules or preferences they want the assistant to follow (like 'always reply in Spanish' or 'use bullet points'). If there are no new facts or preferences, return empty lists/dicts."},
                {"role": "user", "content": interaction}
            ]
        )
        
        # Save Facts
        for fact in decision.facts:
            fact_emb = get_embedding(fact)
            db.table("user_facts").insert({
                "tenant_id": tenant_id,
                "user_id": user_id,
                "fact": fact,
                "embedding": fact_emb
            }).execute()
            print(f"Extracted Fact: {fact}")
            
        # Save Preferences
        for pref_key, pref_val in decision.preferences.items():
            db.table("preference_memory").upsert({
                "tenant_id": tenant_id,
                "user_id": user_id,
                "pref_key": pref_key,
                "pref_value": pref_val
            }).execute()
            print(f"Extracted Preference: {pref_key} = {pref_val}")
            
    except Exception as e:
        print(f"Extraction failed: {e}")

    # 2. Graph Update
    try:
        from src.database.neo4j_client import neo4j_manager
        session = neo4j_manager.get_session()
        def _update_graph(tx, t_id, u_id, text):
            words = [word.lower() for word in text.replace("?", "").split() if len(word) > 2]
            if not words: return
            q_str = """
            MATCH (e:Entity)
            WHERE e.tenantId = $t_id AND ANY(word IN $words WHERE toLower(e.name) CONTAINS word)
            MERGE (u:User {id: $u_id, tenantId: $t_id})
            MERGE (u)-[:ASKED_ABOUT]->(e)
            """
            tx.run(q_str, t_id=t_id, u_id=u_id, words=words)
        session.execute_write(_update_graph, tenant_id, user_id, current_q)
        session.close()
        print("Graph user memory updated.")
    except Exception as e:
        print(f"Graph update failed: {e}")
        
    # 3. Rolling Chat Summarization
    total_messages = len(chat_history) + 2 
    new_summary = current_rolling
    
    if total_messages > 8: # More than 4 complete turns
        old_messages = chat_history[:-4]
        history_str = ""
        for msg in old_messages:
            role = "User" if msg["role"] == "user" else "Assistant"
            history_str += f"{role}: {msg['content']}\n"
            
        system_prompt = "You are a memory distillation AI. Given an existing background context and some old chat messages, generate an updated, concise running context. Focus on key decisions."
        prompt = f"Existing Context: {current_rolling}\n\nOld Messages:\n{history_str}"
        try:
            response = github_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )
            new_summary = response.choices[0].message.content
        except Exception as e:
            print(f"Rolling summary failed: {e}")
            
    # Save the rolling context to episodic_memory ONLY if it was newly generated
    if new_summary != current_rolling and new_summary.strip():
        try:
            db.table("episodic_memory").insert({
                "tenant_id": tenant_id,
                "user_id": user_id,
                "summary": new_summary
            }).execute()
            print(f"Updated rolling context.")
        except Exception as e:
            print(f"Failed to save rolling context: {e}")

    return {"rolling_context": new_summary}

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
            
        system_prompt = (
            "Given a chat history and the latest user question "
            "which might reference context in the chat history, formulate a standalone question "
            "which can be understood without the chat history. Do NOT answer the question, "
            "just reformulate it if needed and otherwise return it as is. "
            "CRITICAL: Do NOT add generic phrases like 'in software development'. Maintain strict focus on the actual entities (like PostgreSQL) mentioned."
        )
            
        decision = instructor_client.chat.completions.create(
            model="gpt-4o-mini",
            response_model=RewrittenQuery,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Chat History:\n{history_str}\n\nLatest Query: {question}"}
            ]
        )
        new_q = decision.new_query
        print(f"Contextualized Query: {new_q}")
        return {"question": new_q}
    except Exception as e:
        print(f"Contextualize failed, using original: {e}")
        return {"question": question}
