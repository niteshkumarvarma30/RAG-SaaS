# Multi-Tenant RAG SaaS Platform

This is a Retrieval-Augmented Generation (RAG) platform with strict Multi-Tenancy isolation. It allows users to upload documents and query them using an Agentic LLM workflow.

## Features
- **Multi-Tenant Isolation:** Supabase Row Level Security (RLS) ensures chunks are completely isolated.
- **Hybrid Search (RRF):** Fuses Vector Search (Jina Embeddings in pgvector), Keyword Search (Postgres FTS), and Graph Search (Neo4j Cypher).
- **Agentic Routing:** Uses LangGraph and Groq (`llama-3.1-8b-instant`) to classify user intents (Greeting vs Technical), grade documents, and rewrite bad queries.
- **Generative Chat:** Uses Sarvam-30B to synthesize answers seamlessly.

## Workflow Diagram

```mermaid
graph TD
    User(["User Query"]) --> Router{"Router<br/>(Groq/Llama-3)"}
    
    %% Routing Logic
    Router -->|Greeting / FAQ| Cache["Static Response Cache"]
    Cache --> Output(["Final Answer"])
    
    Router -->|Technical Query| Hybrid["Hybrid Search Engine"]
    
    %% Retrieval
    subgraph Retrieval Phase
        Hybrid --> VS[("Supabase pgvector<br/>Cosine Similarity")]
        Hybrid --> KS[("Supabase FTS<br/>BM25 Keyword")]
        Hybrid --> GS[("Neo4j Graph<br/>Cypher Queries")]
        VS & KS & GS --> RRF["Reciprocal Rank Fusion<br/>Top 10 Chunks"]
    end
    
    %% Evaluation & Corrective RAG
    RRF --> Grader{"Jina Cross-Encoder<br/>Reranker Threshold"}
    
    Grader -->|Score >= 0.05| Generator["Response Generator<br/>(Sarvam-30B)"]
    Grader -->|Score < 0.05| Rewriter{"CRAG Rewrite Node<br/>(Rewrite Count < 1?)"}
    
    Rewriter -->|Yes| RewriteLLM["Query Rewriter<br/>(Sarvam-105B)"]
    RewriteLLM --> Hybrid
    
    Rewriter -->|No| Generator
    Generator --> Output
```
## Getting Started

1. Clone the repository.
2. Install dependencies via `uv`.
3. Set up your `.env` file (see `implementation.md` for details).
4. Run the FastAPI server: `uvicorn src.main:app --reload`
5. Visit `http://localhost:8000` to interact with the API or Web UI.

See `implementation.md` for a full breakdown of the architecture and database schema details.
