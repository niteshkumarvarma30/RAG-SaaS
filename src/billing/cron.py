import os
import asyncio
from src.database.supabase_client import supabase_manager

async def run_billing_aggregation():
    """
    Mock Cron Job for Stripe Metered Billing.
    This would run nightly via Celery or AWS EventBridge.
    """
    print("\n[CRON] Starting Nightly Billing Aggregation...")
    
    db = supabase_manager.get_admin_client()
    
    # Fetch pending transactions
    response = db.table("transactions").select("*").eq("status", "pending_billing").execute()
    transactions = response.data
    
    if not transactions:
        print("[CRON] No pending transactions found. Exiting.")
        return
        
    print(f"[CRON] Found {len(transactions)} pending transactions.")
    
    # Aggregate tokens per tenant
    usage_per_tenant = {}
    transaction_ids = []
    
    for txn in transactions:
        t_id = txn["tenant_id"]
        usage_per_tenant[t_id] = usage_per_tenant.get(t_id, 0) + txn["tokens_used"]
        transaction_ids.append(txn["id"])
        
    # Push to Stripe Mock
    print("\n--- PUSHING TO STRIPE ---")
    for tenant_id, tokens in usage_per_tenant.items():
        print(f"Tenant {tenant_id}: {tokens} tokens used.")
        print(f"  -> [MOCK] Sending {tokens} usage record to Stripe API for meter_id_xxx...")
    print("-------------------------\n")
    
    # Mark as billed
    for txn_id in transaction_ids:
        db.table("transactions").update({"status": "billed"}).eq("id", txn_id).execute()
        
    print("[CRON] Billing Sync Complete! Transactions marked as 'billed'.")

if __name__ == "__main__":
    asyncio.run(run_billing_aggregation())
