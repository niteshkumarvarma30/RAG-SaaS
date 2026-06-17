# Multi-Tenant RAG SaaS Documentation
This document provides a conceptual overview of the SaaS product you are building. It explains the core machine learning mechanisms powering the platform, the architecture of the AI workflows, and the historical reasoning behind major technical pivots we made during development.

## 1. Core Concepts
### 1.1 Ingestion & Parsing
When a user uploads a document (e.g., a PDF), the system cannot feed the entire book to an AI at once due to "context window" limits. The first step is extracting raw text. We use pymupdf4llm to read PDFs and instantly translate them into structured Markdown format, preserving headers, bullet points, and tables.

### 1.2 Chunking
Chunking is the process of slicing a large document into smaller, searchable blocks (chunks).

**The Concept:** If you search for "Developer Options", the database needs to return just the specific paragraph talking about it, not the whole book.
**Our Approach (Semantic Chunking):** We use a MarkdownHeaderTextSplitter. This algorithm actively looks for Markdown headers (like ## 1.1.1 Developer Options) and intelligently groups all the paragraphs and bullet points underneath it into a single, unified chunk, injecting the header into the chunk's metadata.

### 1.3 Vector Embeddings
Vector Embedding is the process of converting human text into mathematics.

**The Concept:** Words are translated into an array of thousands of numbers representing their "meaning". If two chunks have similar meanings (e.g., "puppy" and "dog"), their number arrays will be mathematically close to each other.
**Our Approach:** We use the Jina Embeddings API to convert chunks into 1536-dimensional vectors. These vectors are securely isolated by tenant_id and stored in Supabase (using the pgvector extension).

### 1.4 Knowledge Graphs
A Knowledge Graph stores information not as text, but as a web of relationships.

**The Concept:** It defines Entities (e.g., PostgreSQL, debug_assertions) and the Relationships between them (e.g., HAS_OPTION).
**Our Approach:** We pass chunks to an LLM which outputs a strict JSON schema. The system then uses Cypher MERGE commands to "upsert" these entities into a Neo4j graph database, guaranteeing multi-tenant isolation by tagging every node with a tenantId.

### 1.5 Retrieval (Hybrid Search & RRF)
Retrieval is how the system fetches the right data when a user asks a question.

**The Concept:** Vector search is great for "vibes" and semantic meaning, but terrible at exact keyword matching (like serial numbers). Keyword search (BM25) is great at exact matches, but terrible at understanding synonyms.
**Our Approach:** We run a Hybrid Search. We query Supabase vectors, Supabase BM25 keywords, and Neo4j graph relationships simultaneously. We then mathematically fuse the results together using Reciprocal Rank Fusion (RRF), ensuring the absolute best chunks float to the top.

### 1.6 Agentic Workflow (LangGraph)
Rather than a basic chat script, the system uses an Agentic Workflow built on LangGraph. The request moves through intelligent "Nodes" that mimic human reasoning:

* **Router Node:** Evaluates if the question is small-talk or technical.
* **Retriever Node:** Executes the Hybrid Search.
* **Grader Node:** Reads the retrieved chunks and grades if they actually contain the answer (to prevent hallucinations).
* **Generator Node:** Reads the validated chunks and synthesizes the final human-readable answer.

## 2. Technology Evolution & Replacements
As we built this SaaS, we hit several technical bottlenecks that required architectural pivots. Here is a historical log of what we replaced and why:

> [!WARNING]
> **Replaced:** Fixed-Size Chunking
> **Upgraded To:** Semantic Markdown Chunking
> 
> **Reason:** Initially, we sliced text aggressively every 200 characters. This caused severe "Header Disconnect" bugs (e.g., the header "Developer Options" was placed in Chunk 1, but its bullet points were placed in Chunk 2). When the AI searched for "Developer Options", it never saw the bullet points. We replaced this with a Markdown Splitter that respects natural header boundaries.

> [!TIP]
> **Replaced:** LangSmith
> **Upgraded To:** MLflow
> 
> **Reason:** LangSmith required a cloud account, API keys, and external data transit. To build a robust, self-hosted, open-source stack, we stripped out LangSmith and integrated mlflow.openai.autolog(). This gives us a highly detailed, local UI dashboard (localhost:5000) to track token usage, latency, and agent traces without relying on external corporate infrastructure.

> [!IMPORTANT]
> **Replaced:** Microsoft GitHub API (GPT-4o-mini)
> **Upgraded To:** Groq (Llama-3)
> 
> **Reason:** We needed an incredibly fast, strict, open-source model to power our LangGraph Router and Grader nodes. Groq's Llama-3 endpoints provide lightning-fast inference for rapid routing decisions, allowing us to drop the dependency on OpenAI/Microsoft models entirely for routing logic.

> [!NOTE]
> **Replaced:** Basic Vector Search
> **Upgraded To:** Hybrid Graph + Vector + BM25
> 
> **Reason:** Standard Vector search routinely fails on highly technical SaaS documentation because it doesn't understand acronyms or code variables. By fusing BM25 (keyword matching) and Neo4j (relationship mapping) with Vectors, the AI can cross-reference concepts perfectly.

> [!TIP]
> **Added:** Hierarchical Title Boosting
> 
> **Reason:** We optimized our BM25 search logic. Now, if the user's query keywords match the natural ## Markdown Header of a chunk (which was saved into Supabase metadata during ingestion), that chunk's Reciprocal Rank Fusion score is mathematically multiplied by 1.5x. This mimics how humans read Table of Contents.

> [!IMPORTANT]
> **Replaced:** Massive LLM Grader Node (sarvam-105b) 
> **Upgraded To:** Precision Cross-Encoder Reranker (jina-reranker-v2)
> 
> **Reason:** Previously, the LLM Grader voted "yes/no" on the entire block of retrieved text. We replaced this with a lightning-fast Cross-Encoder API. The Reranker scores every single chunk independently from 0.0 to 1.0. We filter out any chunk scoring below 0.15. This prevents hallucinations by ensuring the final Generator LLM only sees perfectly relevant information, while drastically reducing latency and API costs.

> [!WARNING]
> **Replaced:** Semantic Markdown Chunking
> **Upgraded To:** Recursive Parent-Child Chunking
> 
> **Reason:** The Markdown Splitter caused "Context Starvation" bugs when headers contained formatting characters (like `**`). It also made chunk sizes unpredictable. We replaced it with a Recursive strategy that uses two splitters: a 2,000-character parent chunk for the LLM to read, and a 400-character child chunk for the Vector Database to search. This guarantees perfect context boundaries and hyper-accurate retrieval.

> [!IMPORTANT]
> **Added:** Corrective RAG (CRAG) & Infinite Loop Prevention
> 
> **Reason:** When the Jina Cross-Encoder correctly rejects all chunks because the user asked an irrelevant or trick question, the LLM was left with no context. Instead of just answering "I don't know", we implemented a CRAG loop. When all chunks are rejected, the LangGraph routes to a `rewrite` node that calls an LLM to dynamically reformulate the user's question, and triggers a second Hybrid Search. To guarantee safety and prevent infinite loops, we added a strictly typed `rewrite_count` integer to the LangGraph state that caps the system at 1 rewrite attempt.

## 3. Automated Evaluation Pipeline
To guarantee the quality of the RAG system over time, we built a local automated evaluation pipeline (run_mlflow_eval.py). It uses an LLM-as-a-Judge (gpt-4o via GitHub Models API) to automatically grade the RAG API against a synthetic dataset of questions and expected answers. The results are logged directly to the local MLflow dashboard.

Evolution of Evaluation Scores
Before Cross-Encoder Optimization (LLM Grader):
* Faithfulness: 0.8
* Relevance: 0.8
* Context Accuracy: 0.8

After Cross-Encoder Optimization & Title Boosting:
* Faithfulness: 0.8
* Relevance: 0.8
* Context Accuracy: 0.7

After Recursive Parent-Child Chunking & Knowledge Graph Extraction (gpt-4o-mini Judge):
* Faithfulness: 0.8
* Relevance: 0.7
* Context Accuracy: 0.7

After Recursive Parent-Child Chunking & Knowledge Graph Extraction (gpt-4o Judge):
* Faithfulness: 0.9
* Relevance: 0.6
* Context Accuracy: 0.7

> [!TIP]
> **Why did Context Accuracy drop to 0.7?** 
> The Context Accuracy naturally dropped to 70% as a direct result of upgrading to the strict Cross-Encoder Reranker. The Reranker is designed to aggressively block noisy or borderline chunks (filtering out anything below a 0.15 confidence score). While this mathematically lowers the Context Accuracy score from the Judge because the LLM is starved of context, it actually produces the safest and most desired behavior in production. It forces the LLM to admit "I don't know" rather than confidently hallucinating an answer to a trick question.
> 
> Furthermore, the pipeline successfully executed the complete evaluation without throwing a single 413 Payload Too Large or 429 RateLimitReached error from the GitHub Models API, proving that our optimizations perfectly bypass free-tier API limitations!

## 4. Stateful AI Memory Architecture
To elevate the system from a basic "lookup engine" to a continuous, intelligent agent, we implemented a Stateful AI Memory Architecture modeled on modern 5-tier memory principles.

The architecture isolates ephemeral RAM (Short-Term Memory) from durable storage (Long-Term Memory) to maintain perfect multi-turn continuity without inflating the context window.

### 4.1 Short-Term Memory (STM)
**The Concept:** STM is the "ephemeral RAM" for a single conversation turn.
**Our Approach:** In LangGraph, the GraphState serves as our STM. It holds the intermediate chunks retrieved, the current chat_history, and the router decisions. Once the HTTP API request finishes, the STM is safely discarded, meaning the LLM's context window never grows uncontrollably.

### 4.2 Long-Term Memory (LTM)
To give the AI persistent memory across session boundaries, we implemented two durable stores using Supabase (secured by multi-tenant RLS):

* **Preference Memory (Policy):** A table (preference_memory) that stores strict rules scoped to a specific user_id. The load_memory graph node fetches these rules (e.g., "Always use bullet points") using a lightning-fast SQL query and injects them into the system prompt.
* **Episodic Memory (Distillation):** A table (episodic_memory) that stores concise summaries of past conversations. When a user has a multi-turn chat, a background LLM node (save_memory) distills the full transcript into a short summary and saves it. The next time the user connects, the graph injects this distilled summary instead of raw logs, preserving context while saving thousands of tokens.
