import os
from src.database.supabase_client import supabase_manager
from src.database.neo4j_client import neo4j_manager
import openai

oai_client = openai.OpenAI(
    api_key=os.environ.get("JINA_API_KEY", ""),
    base_url="https://api.jina.ai/v1"
)

def get_embedding(text: str) -> list[float]:
    response = oai_client.embeddings.create(
        input=text, model="jina-embeddings-v4", dimensions=1536
    )
    return response.data[0].embedding

def vector_search(tenant_id: str, query: str, top_k: int = 10) -> list[dict]:
    """Cosine Similarity search using pgvector via custom RPC."""
    db = supabase_manager.get_tenant_client(tenant_id)
    try:
        query_embedding = get_embedding(query)
        response = db.rpc("match_document_chunks", {
            "query_embedding": query_embedding,
            "match_count": top_k,
            "p_tenant_id": tenant_id
        }).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"Vector search failed: {e}")
        return []

def keyword_search(tenant_id: str, query: str, top_k: int = 10) -> list[dict]:
    """BM25 equivalent using Postgres Full Text Search."""
    db = supabase_manager.get_tenant_client(tenant_id)
    # Basic Postgres FTS uses '&' for AND logic. 
    fts_query = " & ".join([word for word in query.replace("?", "").split() if word])
    try:
        response = db.table("document_chunks") \
            .select("id, content") \
            .eq("tenant_id", tenant_id) \
            .text_search("content", fts_query) \
            .execute()
        return response.data[:top_k] if response.data else []
    except Exception as e:
        print(f"Keyword search failed: {e}")
        return []

def graph_search(tenant_id: str, query: str, top_k: int = 10) -> list[dict]:
    """Neo4j search matching query words to entities and pulling relationships."""
    results = []
    try:
        session = neo4j_manager.get_session()
        words = [word.lower() for word in query.replace("?", "").split() if len(word) > 2]
        query_str = """
        MATCH (e1:Entity)-[r:RELATION]->(e2:Entity)
        WHERE e1.tenantId = $tenant_id
        AND ANY(word IN $words WHERE toLower(e1.name) CONTAINS word OR toLower(e2.name) CONTAINS word)
        RETURN e1.name + ' ' + r.type + ' ' + e2.name AS content
        LIMIT $top_k
        """
        res = session.run(query_str, tenant_id=tenant_id, words=words, top_k=top_k)
        for record in res:
            results.append({"content": record["content"]})
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
    
    def add_to_scores(results, weight=1.0):
        for rank, res in enumerate(results):
            content = res.get("content", "")
            if not content:
                continue
            if content not in scores:
                scores[content] = 0.0
            scores[content] += weight * (1.0 / (k + rank + 1))
            
    add_to_scores(vector_res, weight=1.0)
    add_to_scores(keyword_res, weight=1.5)  # Boost exact keyword matches
    add_to_scores(graph_res, weight=1.0)
    
    # Sort descending by RRF score
    sorted_contents = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    return sorted_contents

def hybrid_retriever(tenant_id: str, query: str, top_k: int = 15) -> str:
    """Executes all 3 searches and fuses them with RRF."""
    print("  -> Running Vector Search (Cosine)...")
    v_res = vector_search(tenant_id, query)
    
    print("  -> Running Keyword Search (BM25)...")
    k_res = keyword_search(tenant_id, query)
    
    print("  -> Running Graph Search (Neo4j Cypher)...")
    g_res = graph_search(tenant_id, query)
    
    print("  -> Applying Reciprocal Rank Fusion (RRF)...")
    fused_docs = compute_rrf(v_res, k_res, g_res)
    
    top_contexts = fused_docs[:top_k]
    if not top_contexts:
        return "No relevant context found."
        
    return "\n\n---\n\n".join(top_contexts)
