from src.database.supabase_client import supabase_manager
from src.database.neo4j_client import neo4j_manager

tenants = [
    "619f50ab-df74-4057-9305-05a70fdc2474",
    "3780bb27-250a-4a2c-be4b-9252b8e8ce9a",
    "a7f179d0-83b7-4960-843f-3cac536797f3"
]

print("========================================")
print("     Wiping Old OpenAI Embeddings")
print("========================================")

for t in tenants:
    print(f"Clearing Supabase Data for Tenant: {t}...")
    try:
        db = supabase_manager.get_tenant_client(t)
        # We delete from chunks first, then documents, then billing
        db.table("document_chunks").delete().eq("tenant_id", t).execute()
        db.table("documents").delete().eq("tenant_id", t).execute()
        db.table("transactions").delete().eq("tenant_id", t).execute()
    except Exception as e:
        print(f"Error clearing Supabase for {t}: {e}")

print("\nClearing Neo4j Graph Data...")
try:
    session = neo4j_manager.get_session()
    session.run("MATCH (n) DETACH DELETE n")
    session.close()
    print("Graph Data wiped successfully.")
except Exception as e:
    print(f"Error clearing Neo4j: {e}")

print("\nAll Clear! Ready to run test_upload.py with Jina!")
