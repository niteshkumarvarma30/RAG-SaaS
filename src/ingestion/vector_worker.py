import os
import openai
from src.database.supabase_client import supabase_manager

def process_vector_track_sync(tenant_id: str, document_id: str, chunks: list[str]):
    """Generates embeddings and bulk inserts them into Supabase."""
    oai_client = openai.OpenAI(
        api_key=os.environ.get("JINA_API_KEY", ""), 
        base_url="https://api.jina.ai/v1"
    )
    
    # Request embeddings from Jina API
    embeddings_data = oai_client.embeddings.create(
        input=chunks,
        model="jina-embeddings-v4",
        dimensions=1536 # Matryoshka dimension constraint truncates 2048 to 1536
    )
    
    # Get the securely isolated tenant client
    db = supabase_manager.get_tenant_client(tenant_id)
    
    records = []
    for i, chunk in enumerate(chunks):
        records.append({
            "document_id": document_id,
            "tenant_id": tenant_id,
            "content": chunk,
            "embedding": embeddings_data.data[i].embedding
        })
        
    # Bulk insert into pgvector
    db.table("document_chunks").insert(records).execute()
