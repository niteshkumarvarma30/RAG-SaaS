from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from src.database.supabase_client import supabase_manager
from src.ingestion.parser import parse_pdf, chunk_text
from src.ingestion.vector_worker import process_vector_track_sync
from src.ingestion.graph_worker import process_graph_track_sync
from src.retrieval.graph import crag_app

from fastapi.responses import StreamingResponse
import json
import uuid

router = APIRouter()

def get_tenant_uuid(clerk_id: str) -> str:
    """Deterministically convert a Clerk string ID (e.g. user_2pkXY) into a valid Postgres UUID."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, clerk_id))

class ChatRequest(BaseModel):
    tenant_id: str
    user_id: Optional[str] = "default_user"
    message: str
    chat_history: Optional[List[Dict[str, Any]]] = []

@router.post("/api/v1/chat")
def chat_endpoint(request: ChatRequest):
    """Executes the full Hybrid CRAG loop and logs token usage for billing."""
    uuid_tenant = get_tenant_uuid(request.tenant_id)
    initial_state = {
        "tenant_id": uuid_tenant,
        "user_id": request.user_id,
        "question": request.message,
        "generation": "",
        "documents": "",
        "route": "",
        "chat_history": request.chat_history
    }
    
    # 1. Execute LangGraph
    final_state = crag_app.invoke(initial_state)
    answer = final_state["generation"]
    
    # Format the context from retrieved documents
    context_docs = final_state.get("documents", [])
    if isinstance(context_docs, str):
        context_string = context_docs
    else:
        context_string = "\n\n".join([doc.page_content for doc in context_docs if hasattr(doc, "page_content")])
    
    # 2. Phase 4 Usage Tracking (Mock Token Count)
    try:
        # Roughly estimate tokens: 1 word ~ 1.3 tokens
        estimated_tokens = int(len(answer.split()) * 1.3) + int(len(request.message.split()) * 1.3)
        
        # Use tenant client to write to transactions so the RLS RETURNING clause succeeds
        db = supabase_manager.get_tenant_client(uuid_tenant)
        db.table("transactions").insert({
            "tenant_id": uuid_tenant,
            "tokens_used": estimated_tokens
        }).execute()
        print(f"Logged {estimated_tokens} tokens for billing on Tenant {uuid_tenant}.")
    except Exception as e:
        print(f"Failed to log transaction: {e}")
    
    return {"answer": answer, "context": context_string}

@router.post("/api/v1/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """Executes the full Hybrid CRAG loop and streams the status of each LangGraph node."""
    uuid_tenant = get_tenant_uuid(request.tenant_id)
    initial_state = {
        "tenant_id": uuid_tenant,
        "user_id": request.user_id,
        "question": request.message,
        "generation": "",
        "documents": "",
        "route": "",
        "chat_history": request.chat_history
    }
    
    async def event_generator():
        full_state = {}
        answer = ""
        import asyncio
        
        async for mode, data in crag_app.astream(initial_state, stream_mode=["updates", "messages"]):
            if mode == "messages":
                msg, meta = data
                if msg.content and meta.get("langgraph_node") == "generate":
                    token = msg.content
                    answer += token
                    await asyncio.sleep(0.01)  # Add typing effect delay
                    yield f"data: {json.dumps({'token': token})}\n\n"
                    
            elif mode == "updates":
                node_name = list(data.keys())[0]
                update = data[node_name]
                if update:
                    full_state.update(update)
                    
                if node_name == "load_memory":
                    yield f"data: {json.dumps({'status': 'Loading user memory...'})}\n\n"
                elif node_name == "contextualize_query":
                    yield f"data: {json.dumps({'status': 'Contextualizing query...'})}\n\n"
                elif node_name == "check_cache":
                    yield f"data: {json.dumps({'status': 'Checking semantic cache...'})}\n\n"
                elif node_name == "route_query":
                    yield f"data: {json.dumps({'status': 'Routing query...'})}\n\n"
                elif node_name == "retrieve":
                    yield f"data: {json.dumps({'status': 'Retrieving from Vector & Graph...'})}\n\n"
                elif node_name == "grade_documents":
                    yield f"data: {json.dumps({'status': 'Reranking and validating chunks...'})}\n\n"
                elif node_name == "generate" or node_name == "generate_cached":
                    yield f"data: {json.dumps({'status': 'Synthesizing final answer...'})}\n\n"
                elif node_name == "rewrite":
                    yield f"data: {json.dumps({'status': 'Rewriting query for better results...'})}\n\n"
                    
        # Graph execution finished. Get final answer.
        final_answer = full_state.get("generation", answer)
        
        # Execute memory and caching functions asynchronously in a background thread
        from src.retrieval.nodes import get_embedding, save_memory
        def background_tasks(state, u_tenant, req_msg, ans):
            try:
                save_memory(state)
            except Exception as e:
                print(f"Failed to manually save episodic memory: {e}")
                
            try:
                query_embedding = get_embedding(req_msg)
                db = supabase_manager.get_tenant_client(u_tenant)
                db.table("semantic_cache").insert({
                    "tenant_id": u_tenant,
                    "query": req_msg,
                    "query_embedding": query_embedding,
                    "response": ans
                }).execute()
            except Exception as e:
                print(f"Failed to save semantic cache: {e}")
        
        if final_answer:
            import threading
            threading.Thread(target=background_tasks, args=(full_state, uuid_tenant, request.message, final_answer)).start()
            
        context_docs = full_state.get("documents", [])
        if isinstance(context_docs, str):
            context_string = context_docs
        else:
            context_string = "\n\n".join([doc.page_content for doc in context_docs if hasattr(doc, "page_content")])
            
        yield f"data: {json.dumps({'status': 'done', 'answer': final_answer, 'context': context_string})}\n\n"
        
    return StreamingResponse(event_generator(), media_type="text/event-stream")

def background_ingestion_pipeline(uuid_tenant: str, document_id: str, pdf_bytes: bytes):
    """Orchestrates the entire ingestion process asynchronously."""
    db = supabase_manager.get_tenant_client(uuid_tenant)
    try:
        text = parse_pdf(pdf_bytes)
        chunks = chunk_text(text)
        process_vector_track_sync(uuid_tenant, document_id, chunks)
        process_graph_track_sync(uuid_tenant, document_id, chunks)
        db.table("documents").update({"status": "completed"}).eq("id", document_id).execute()
        print(f"Successfully processed document {document_id}")
    except Exception as e:
        print(f"Pipeline failed for document {document_id}: {e}")
        db.table("documents").update({"status": "failed"}).eq("id", document_id).execute()


@router.post("/api/v1/ingest")
async def ingest_document(
    background_tasks: BackgroundTasks,
    tenant_id: str = Form(...),
    file: UploadFile = File(...)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    uuid_tenant = get_tenant_uuid(tenant_id)
    pdf_bytes = await file.read()
    
    admin_db = supabase_manager.get_admin_client()
    try:
        # Ensure the tenant exists in the Supabase `tenants` table. 
        # We use the admin_db to bypass the strict RLS policies on the `tenants` table.
        admin_db.table("tenants").upsert({
            "id": uuid_tenant,
            "name": f"Company {tenant_id}"
        }).execute()
        
        # Switch back to the strictly isolated tenant_client for the document insertion
        db = supabase_manager.get_tenant_client(uuid_tenant)
        response = db.table("documents").insert({
            "tenant_id": uuid_tenant,
            "filename": file.filename,
            "status": "pending"
        }).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=500, detail="Failed to insert document record into Supabase.")
            
        document_id = response.data[0]['id']
        background_tasks.add_task(background_ingestion_pipeline, uuid_tenant, document_id, pdf_bytes)
        
        return {"message": "Document ingestion successfully started in the background.", "document_id": document_id}
    except Exception as e:
        print(f"Insertion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/v1/billing/{tenant_id}")
def get_billing(tenant_id: str):
    """Calculates the total tokens used by a tenant and the estimated bill."""
    uuid_tenant = get_tenant_uuid(tenant_id)
    db = supabase_manager.get_tenant_client(uuid_tenant)
    try:
        response = db.table("transactions").select("tokens_used").eq("tenant_id", uuid_tenant).execute()
        total_tokens = sum(row.get("tokens_used", 0) for row in response.data)
        
        estimated_cost_usd = (total_tokens / 1000.0) * 0.001
        
        return {
            "tenant_id": tenant_id, # return the original clerk id to the frontend
            "total_tokens_used": total_tokens,
            "estimated_cost_usd": round(estimated_cost_usd, 6)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch billing data: {e}")

@router.get("/api/v1/documents/{tenant_id}")
def list_documents(tenant_id: str):
    uuid_tenant = get_tenant_uuid(tenant_id)
    db = supabase_manager.get_tenant_client(uuid_tenant)
    try:
        response = db.table("documents").select("*").eq("tenant_id", uuid_tenant).order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {e}")

@router.delete("/api/v1/documents/{tenant_id}/{document_id}")
def delete_document(tenant_id: str, document_id: str):
    uuid_tenant = get_tenant_uuid(tenant_id)
    db = supabase_manager.get_tenant_client(uuid_tenant)
    try:
        # Delete vectors to remove from RAG hybrid search context
        db.table("document_chunks").delete().eq("document_id", document_id).eq("tenant_id", uuid_tenant).execute()
        # Delete document record
        db.table("documents").delete().eq("id", document_id).eq("tenant_id", uuid_tenant).execute()
        
        # Safely delete from Neo4j Knowledge Graph
        from src.database.neo4j_client import neo4j_manager
        with neo4j_manager.driver.session() as session:
            session.run("""
                MATCH (d:Document {id: $doc_id, tenantId: $tenant_id})
                OPTIONAL MATCH (e:Entity)-[:FOUND_IN]->(d)
                // Detach and delete the Document node and its relationships
                DETACH DELETE d
                // Find Entities that were ONLY found in this document (they have no remaining FOUND_IN relationships)
                WITH e
                WHERE e IS NOT NULL AND NOT (e)-[:FOUND_IN]->()
                DETACH DELETE e
            """, doc_id=document_id, tenant_id=uuid_tenant)
            
        return {"message": "Document, Vectors, and Knowledge Graph nodes successfully deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {e}")
