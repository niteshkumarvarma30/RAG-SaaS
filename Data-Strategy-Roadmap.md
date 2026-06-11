## 2. Data Strategy
Strict separation between the "Textbook" (Knowledge Base) and the "Exam" (Evaluation Dataset) is required to prevent data leakage and ensure fair benchmarking.

### A. The Knowledge Base (The Textbooks)
Used to populate vector and graph databases. Ideal for stress-testing complex architectural relationships.

* **Database Manuals (e.g., PostgreSQL docs):** Tests graph extraction of relational concepts (DDL commands, normal forms).
* **Hardware Architecture Specs (e.g., Intel datasheets):** Tests ingestion of dense logic and timing diagrams without context loss.
* **API Documentation (e.g., Stripe/AWS markdown):** Tests standard software troubleshooting workflows.

### B. The Evaluation Dataset (The Exam)
Used as an automated grading script to benchmark retrieval accuracy in the development environment.

* **IBM TechQA:** Real developer questions paired with correct technical documentation chunks.
* **Bitext Customer Support Dataset:** Realistic, messy end-user queries (available on Hugging Face) to test intent recognition.

## 3. Implementation Roadmap
Follow these phases sequentially. Do not build the frontend widget until Phase 3 and Phase 5 are validated in the terminal.

### Phase 1: Storage & Security Schema (Weeks 1-2)
**Goal:** Ensure multi-tenant security so Company A cannot access Company B's data.

1.  **Initialize Supabase:** Create tenants, documents, and document_chunks tables. Enable pgvector extension.
2.  **Enforce RLS (Row Level Security):** Write SQL policies to strictly isolate vector chunks based on the tenant_id present in the JWT/auth token.
3.  **Initialize Neo4j:** Set up the graph schema. Ensure every Node and Edge creation query requires and indexes a tenantId property.

> [!IMPORTANT]
> Failure to implement RLS properly at this stage can result in catastrophic data breaches between SaaS tenants. Validate security policies rigorously.

### Phase 2: The ML-Optimized Ingestion Pipeline (Weeks 2-3)
**Goal:** Build background workers to convert uploaded PDFs into searchable, structured data while minimizing future storage costs.

1.  **Document Parsing:** Create a FastAPI background task that accepts a PDF and strips formatting.
2.  **Semantic Chunking (DL Integration):** Use a local NLP model to chunk the text based on topic shifts rather than arbitrary character counts.
3.  **Vector Track:** Pass chunks to an embedding model, apply Matryoshka Compression (reducing dimensionality), and execute a bulk insert into Supabase.
4.  **Graph Track:** Pass chunks to Claude 3.5 Sonnet using a strict JSON extraction prompt to pull entities (features, errors, registers) and relationships, then insert them into Neo4j.

### Phase 3: Hybrid Retrieval & CRAG Logic (Weeks 4-5)
**Goal:** Build the brain of the application utilizing Corrective RAG (CRAG) and deep learning filters.

1.  **Intent Routing:** Deploy a local DistilBERT classifier before retrieval. Route simple queries to a cache.
2.  **Vector + Graph Fusion:** Write a retrieval function executing semantic search in Supabase and node-traversal search in Neo4j simultaneously.
3.  **Cascaded Reranking (DL Integration):** Pass the broad search results through a local Cross-Encoder (e.g., bge-reranker-base) to violently filter the payload down to the top 3 chunks.
4.  **LangGraph Orchestration:**
    * Pass the filtered data to a Grader agent (using a cheaper, quantized model).
    * If the Grader fails the data (irrelevant), route to a Rewriter agent to adjust search terms and loop back to retrieval.
5.  **Synthesizer:** Pass the finalized, approved context to the generator (heavy LLM) to formulate the final answer.

### Phase 4: Observability Integration (Week 5)
**Goal:** Implement tracing before interacting with the frontend to monitor agent behavior and token costs.

1.  **Enable LangSmith:** Configure API keys in .env.
2.  **Metadata Tagging:** Ensure every LangGraph invocation includes the tenant_id in its config metadata to filter traces by specific clients.
3.  **Custom Span Decorators:** Add @traceable to Neo4j, Supabase lookup functions, and local ML models to monitor precise latency and pinpoint bottlenecks.

### Phase 5: Automated Evaluation & Benchmarking (Weeks 5-6)
**Goal:** Benchmark the system using the Evaluation Dataset via Ragas or TruLens before going live.

#### The Evaluation Workflow
**The Automated Batch Run (Taking the Exam):**
* A Python script iterates through the evaluation dataset (e.g., IBM TechQA).
* Captures User Query, Retrieved Context (chunks/nodes), and Generated Answer.

**LLM-as-a-Judge (Grading the Exam):**
* Feed Query, Ground Truth, Retrieved Context, and Generated Answer to a judge LLM (e.g., GPT-4o).

**Measuring Core Metrics:**
* **Context Precision:** Did the system retrieve relevant facts? (Vector/Graph tuning).
* **Answer Faithfulness:** Did the LLM hallucinate? (Prompt tuning).
* **Answer Relevance:** Did the system directly answer the user's question?

**Iteration:** Tweak chunk sizes, graph prompts, and retrieval weights based on these metrics until scores hit target thresholds.

> [!CAUTION]
> Do NOT skip automated evaluation. It is the only mathematical proof that your hybrid retrieval is actually outperforming a basic vector search.

### Phase 6: The Embeddable Widget & Billing (Weeks 6-7)
**Goal:** Expose the system securely to clients and implement monetization.

1.  **The JavaScript Snippet:** Write a Vanilla JS script that injects a floating chat icon utilizing a Shadow DOM. Establish a WebSocket or HTTP polling connection to the FastAPI backend.
2.  **Usage Tracking:** Upon successful generation of an answer, log token consumption and tenant_id to a transactions table in Supabase.
3.  **Stripe Metering:** Implement a nightly cron job (e.g., via Celery or AWS EventBridge) to aggregate daily transactions and push the total usage count to Stripe for metered monthly billing.
