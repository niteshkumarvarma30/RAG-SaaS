from src.database.supabase_client import supabase_manager
from src.database.neo4j_client import neo4j_manager
from src.ingestion.graph_worker import process_graph_track_sync

print("Wiping Neo4j Graph Data...")
session = neo4j_manager.get_session()
session.run("MATCH (n) DETACH DELETE n")
session.close()
print("Neo4j wiped.")

print("Fetching chunks from Supabase...")
tenants = [
    "619f50ab-df74-4057-9305-05a70fdc2474",
    "3780bb27-250a-4a2c-be4b-9252b8e8ce9a",
    "a7f179d0-83b7-4960-843f-3cac536797f3"
]

chunks_by_doc = {}
tenant_by_doc = {}

for t in tenants:
    db = supabase_manager.get_tenant_client(t)
    res = db.table("document_chunks").select("tenant_id, document_id, content").eq("tenant_id", t).execute()
    for row in res.data:
        doc_id = row['document_id']
        text = row['content']
        
        if doc_id not in chunks_by_doc:
            chunks_by_doc[doc_id] = []
            tenant_by_doc[doc_id] = t
            
        chunks_by_doc[doc_id].append(text)

print(f"Found {len(chunks_by_doc)} documents to process.")

for doc_id, chunks in chunks_by_doc.items():
    tenant_id = tenant_by_doc[doc_id]
    print(f"Processing Document {doc_id} with {len(chunks)} chunks for tenant {tenant_id}...")
    process_graph_track_sync(tenant_id, doc_id, chunks)

print("Done! Neo4j is now populated.")
