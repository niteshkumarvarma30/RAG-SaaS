# RAG SaaS implementation details

This document outlines the technical implementation of the RAG SaaS platform.

## 1. Core Architecture
Multi-Tenant Retrieval-Augmented Generation (RAG) platform, using FastAPI.

* **Backend Framework:** FastAPI (`uvicorn` server).
* **Multi-Tenancy:** Hard-coded Row Level Security (RLS) in PostgreSQL, isolating `document_chunks` and graphs per tenant ID.

## 2. Ingestion Pipeline
Documents are processed through two workers:

### Vector Worker (`vector_worker.py`)
* **Embedding Model:** Jina Embeddings (`jina-embeddings-v4`).
* **Vector Database:** Supabase (PostgreSQL with `pgvector`).
* **Dimensions:** 1536 (Truncated from Jina's 2048 natively).

### Graph Worker (`graph_worker.py`)
* **Purpose:** Extracts structured JSON nodes and relationships to build a semantic Knowledge Graph.
* **Graph Database:** Neo4j.
* **Current LLM Evaluated:** Sarvam-30B and Llama-3.

## 3. Hybrid Search Retrieval
The retrieval engine combines three search techniques using Reciprocal Rank Fusion (RRF).

1. **Vector Search:** Supabase RPC function `match_document_chunks` using Cosine Similarity.
2. **Keyword Search (BM25):** PostgreSQL Full Text Search (`text_search`). Boosted by 1.5x in RRF weighting.
3. **Graph Search:** Neo4j Cypher querying.

## 4. Agentic Workflow (LangGraph)
* **Router Node:** Evaluates intent using `llama-3.1-8b-instant` via Groq.
* **Grader Node:** `llama-3.1-8b-instant` evaluates if the retrieved documents successfully answer the user's question.
* **Generator Node:** Uses **Sarvam-30B** to generate a fluent response.

## 5. Deployment Instructions
1. Install requirements using `uv`.
2. Configure `.env` with Supabase, Neo4j, Groq, and Sarvam API keys.
3. Start backend: `uvicorn src.main:app --reload`
