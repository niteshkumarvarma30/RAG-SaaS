from src.database.supabase_client import supabase_manager
import json

db = supabase_manager.get_admin_client()
res = db.table("document_chunks").select("content").ilike("content", "%Developer Options%").execute()
for i, row in enumerate(res.data):
    print(f"--- Chunk {i} ---")
    print(row['content'])

print("\n\nChecking for debug_assertions...")
res = db.table("document_chunks").select("content").ilike("content", "%debug_assertions%").execute()
for i, row in enumerate(res.data):
    print(f"--- Chunk {i} ---")
    print(row['content'])
