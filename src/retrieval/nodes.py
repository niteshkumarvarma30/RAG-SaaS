import os
import instructor
from openai import OpenAI
from pydantic import BaseModel, Field
from src.retrieval.hybrid import hybrid_retriever

client = instructor.from_openai(OpenAI(
    api_key=os.environ.get("GROQ_API_KEY", ""),
    base_url="https://api.groq.com/openai/v1"
))

gen_client = OpenAI(
    api_key=os.environ.get("SARVAM_API_KEY", ""),
    base_url="https://api.sarvam.ai/v1"
)

class RouteDecision(BaseModel):
    intent: str = Field(description="Must be exactly 'greeting', 'faq', or 'technical_query'")

class GraderDecision(BaseModel):
    is_relevant: str = Field(description="Must be exactly 'yes' or 'no'")

class RewrittenQuery(BaseModel):
    new_query: str = Field(description="The reformulated question")


def route_query(state):
    print("--- ROUTING QUERY VIA GPT-4o-mini ---")
    question = state["question"]
    try:
        decision = client.chat.completions.create(
            model="llama-3.1-8b-instant",
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

def retrieve(state):
    print("--- HYBRID RETRIEVAL (BM25 + Vector + Graph + RRF) ---")
    question = state["question"]
    tenant_id = state["tenant_id"]
    
    docs = hybrid_retriever(tenant_id, question)
    return {"documents": docs}

def grade_documents(state):
    print("--- GRADING CONTEXT ---")
    question = state["question"]
    documents = state["documents"]
    
    if documents == "No relevant context found.":
        return {"route": "no"}
        
    try:
        decision = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            response_model=GraderDecision,
            messages=[
                {"role": "system", "content": "You are a strict grader. Does the document contain the answer to the question? Return 'yes' or 'no'."},
                {"role": "user", "content": f"Question: {question}\n\nDocuments: {documents}"}
            ]
        )
        is_relevant = decision.is_relevant.lower()
    except Exception as e:
        print(f"Grader failed: {e}. Defaulting to yes.")
        is_relevant = "yes"
        
    print(f"Decision: {is_relevant}")
    return {"route": is_relevant}

def generate(state):
    print("--- GENERATING FINAL ANSWER ---")
    question = state["question"]
    documents = state["documents"]
    
    response = gen_client.chat.completions.create(
        model="sarvam-30b",
        messages=[
            {"role": "system", "content": "You are an expert SaaS support assistant. Answer the user's question using ONLY the provided context. You must ONLY answer in English, regardless of the language the user speaks. If the context doesn't have the answer, say you don't know."},
            {"role": "user", "content": f"Context:\n{documents}\n\nQuestion: {question}"}
        ]
    )
    return {"generation": response.choices[0].message.content}

def rewrite(state):
    print("--- REWRITING QUERY ---")
    question = state["question"]
    try:
        decision = client.chat.completions.create(
            model="llama-3.1-8b-instant",
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
        
    print(f"New query: {new_q}")
    return {"question": new_q}

def generate_cached(state):
    print("--- GENERATING CACHED RESPONSE ---")
    return {"generation": "Hello! I am your AI Support Assistant. I'm ready to help you with technical questions about your infrastructure."}
