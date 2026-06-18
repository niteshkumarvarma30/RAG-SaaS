import os
from src.database.supabase_client import supabase_manager
from src.database.neo4j_client import neo4j_manager
from src.retrieval.cache import LRUCache
import openai

oai_client = openai.OpenAI(
    api_key=os.environ.get("JINA_API_KEY", ""),
    base_url="https://api.jina.ai/v1"
)

embedding_cache = LRUCache(max_size=1000)

def get_embedding(text: str) -> list[float]:
    key = embedding_cache.generate_key(text)
    cached = embedding_cache.get(key)
    if cached is not None:
        print("[Cache Hit] Fetched embedding from local LRU cache in 0ms")
        return cached

    print("[Cache Miss] Fetching embedding from Jina API...")
    response = oai_client.embeddings.create(
        input=text, model="jina-embeddings-v4", dimensions=1536
    )
    vec = response.data[0].embedding
    embedding_cache.put(key, vec, ttl_seconds=3600)  # Cache for 1 hour
    return vec

def vector_search(tenant_id: str, query: str, query_embedding: list[float], top_k: int = 20) -> list[dict]:
    """Cosine Similarity search using pgvector via custom RPC."""
    db = supabase_manager.get_tenant_client(tenant_id)
    try:
        response = db.rpc("match_document_chunks", {
            "query_embedding": query_embedding,
            "match_count": top_k,
            "p_tenant_id": tenant_id
        }).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"Vector search failed: {e}")
        return []

def keyword_search(tenant_id: str, query: str, top_k: int = 20) -> list[dict]:
    """BM25 equivalent using Postgres Full Text Search."""
    db = supabase_manager.get_tenant_client(tenant_id)
    try:
        # The python client does not support type='websearch', so we manually build an OR query
        words = [word.lower() for word in query.replace("?", "").replace(",", "").split() if len(word) > 3]
        if not words:
            return []
        fts_query = " | ".join(words)
        
        response = db.table("document_chunks") \
            .select("id, content") \
            .eq("tenant_id", tenant_id) \
            .text_search("content", fts_query) \
            .execute()
            
        results = []
        if response.data:
            for row in response.data[:top_k]:
                row["boost_factor"] = 1.0
                results.append(row)
        return results
    except Exception as e:
        print(f"Keyword search failed: {e}")
        return []

def graph_search(tenant_id: str, user_id: str, query: str, top_k: int = 20) -> list[dict]:
    """Neo4j search matching query words to entities and pulling relationships."""
    results = []
    try:
        session = neo4j_manager.get_session()
        words = [word.lower() for word in query.replace("?", "").split() if len(word) > 2]
        def _read_tx(tx, t_id, u_id, wds, tk):
            q_str1 = """
            MATCH (e1:Entity)-[r:RELATION]->(e2:Entity)
            WHERE e1.tenantId = $tenant_id
            AND ANY(word IN $words WHERE toLower(e1.name) CONTAINS word OR toLower(e2.name) CONTAINS word)
            RETURN e1.name + ' has the following relationship: ' + r.type + ' with ' + e2.name AS content
            LIMIT $top_k
            """
            q_str2 = """
            MATCH (u:User {id: $u_id, tenantId: $tenant_id})-[r]->(e:Entity)
            WHERE ANY(word IN $words WHERE toLower(e.name) CONTAINS word)
            RETURN 'User has previously interacted with the topic: ' + e.name AS content
            LIMIT $top_k
            """
            res1 = [record["content"] for record in tx.run(q_str1, tenant_id=t_id, words=wds, top_k=tk)]
            res2 = [record["content"] for record in tx.run(q_str2, tenant_id=t_id, u_id=u_id, words=wds, top_k=tk)]
            return res1 + res2
            
        res = session.execute_read(_read_tx, tenant_id, user_id, words, top_k)
        for content in res:
            results.append({"content": content})
        session.close()
    except Exception as e:
        print(f"Graph search failed: {e}")
    return results

def compute_rrf(vector_res, keyword_res, graph_res, k=60):
    """
    Fuses results mathematically using Reciprocal Rank Fusion.
    score = 1 / (k + rank)
    """
    scores = {}
    
    def add_to_scores(results, base_weight=1.0):
        for rank, res in enumerate(results):
            content = res.get("content", "")
            if not content:
                continue
                
            # Apply dynamic title boost factor if it exists
            boost = res.get("boost_factor", 1.0)
            final_weight = base_weight * boost
            
            if content not in scores:
                scores[content] = 0.0
            scores[content] += final_weight * (1.0 / (k + rank + 1))
            
    add_to_scores(vector_res, base_weight=2.0)  # Boost vector semantics
    add_to_scores(keyword_res, base_weight=1.5) # Re-boost keyword for exact matches like im4gn.4xlarge
    add_to_scores(graph_res, base_weight=0.3)
    
    # Sort descending by RRF score
    sorted_contents = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    return sorted_contents

import concurrent.futures

def hybrid_retriever(tenant_id: str, user_id: str, query: str, query_embedding: list[float], top_k: int = 5) -> str:
    """Executes all 3 searches in parallel and fuses them with RRF."""
    print("  -> Running Hybrid Search (Vector + Keyword + Graph) in Parallel...")
    
    v_res, k_res, g_res = [], [], []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_v = executor.submit(vector_search, tenant_id, query, query_embedding)
        future_k = executor.submit(keyword_search, tenant_id, query)
        future_g = executor.submit(graph_search, tenant_id, user_id, query)
        
        v_res = future_v.result()
        k_res = future_k.result()
        g_res = future_g.result()
    
    print("  -> Applying Reciprocal Rank Fusion (RRF)...")
    fused_docs = compute_rrf(v_res, k_res, g_res)
    
    # DYNAMIC TOKEN BUDGETING
    # Sarvam-30B context window is 8192 tokens. Let's aim for max 6000 tokens for context to leave room for system prompt, history, and generation.
    # 1 token ~= 4 characters roughly. So max_chars = 24000.
    max_chars = 24000
    current_chars = len(query) # base query length
    
    top_contexts = []
    for doc in fused_docs:
        doc_chars = len(doc)
        if current_chars + doc_chars > max_chars:
            print("  -> Token Budget Reached. Stopping retrieval to prevent context overflow.")
            break
        top_contexts.append(doc)
        current_chars += doc_chars
        # To prevent too many chunks from confusing the LLM even if they fit, cap at 15
        if len(top_contexts) >= 15:
            break
            
    print(f"  -> Dynamic Budgeting allocated {len(top_contexts)} chunks using approx {current_chars//4} tokens.")
    
    if not top_contexts:
        return "No relevant context found."
        
    return "\n\n---\n\n".join(top_contexts)
