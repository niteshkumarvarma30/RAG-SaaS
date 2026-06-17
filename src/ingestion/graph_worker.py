import os
import instructor
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List
from src.database.neo4j_client import neo4j_manager

client = OpenAI(
    api_key=os.environ.get("SARVAM_API_KEY", ""),
    base_url="https://api.sarvam.ai/v1"
)

# Define the precise JSON schema we want Claude/GPT to extract
class Entity(BaseModel):
    name: str = Field(description="Name of the entity in title case")
    type: str = Field(description="Type of the entity (e.g., Feature, Error, Register, Component, Concept)")

class Relationship(BaseModel):
    source_entity: str = Field(description="Name of the source entity")
    target_entity: str = Field(description="Name of the target entity")
    relation_type: str = Field(description="Type of relationship, ALL_CAPS (e.g., RELATES_TO, CAUSES, DEPENDS_ON)")

class GraphExtraction(BaseModel):
    entities: List[Entity]
    relationships: List[Relationship]

def extract_graph_from_chunk(chunk: str) -> GraphExtraction:
    import json
    response = client.chat.completions.create(
        model="sarvam-30b",
        messages=[
            {
                "role": "system", 
                "content": """You are a highly precise technical knowledge graph extractor. 
Extract core entities and their relationships from the provided text.
You MUST reply with ONLY raw JSON in this exact format. Do NOT wrap it in markdown block quotes (```json).
{
  "entities": [
    {"name": "Entity1", "type": "Component"}
  ],
  "relationships": [
    {"source_entity": "Entity1", "target_entity": "Entity2", "relation_type": "DEPENDS_ON"}
  ]
}"""
            },
            {
                "role": "user", 
                "content": f"Text:\n{chunk}"
            }
        ],
        temperature=0.1
    )
    
    raw_text = response.choices[0].message.content.strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:-3].strip()
    elif raw_text.startswith("```"):
        raw_text = raw_text[3:-3].strip()
        
    parsed = json.loads(raw_text)
    return GraphExtraction(**parsed)

def resolve_coreferences(chunk: str) -> str:
    """Uses LLM to replace pronouns with their actual entities before extraction."""
    response = client.chat.completions.create(
        model="sarvam-30b",
        messages=[
            {
                "role": "system",
                "content": "You are a precise technical editor. Rewrite the following text by replacing all pronouns (it, they, this, these, etc.) and vague references with the exact proper nouns or entities they refer to based on the context. Do not summarize or change the meaning. Return ONLY the rewritten text."
            },
            {
                "role": "user",
                "content": f"Text:\n{chunk}"
            }
        ],
        temperature=0.0
    )
    return response.choices[0].message.content

import concurrent.futures

def process_single_chunk(chunk: str, tenant_id: str, document_id: str):
    """Processes a single chunk in its own thread with its own Neo4j session."""
    try:
        print("    -> Resolving Coreferences...")
        resolved_chunk = resolve_coreferences(chunk)
        
        print("    -> Extracting Graph Entities...")
        graph_data = extract_graph_from_chunk(resolved_chunk)
        
        with neo4j_manager.driver.session() as session:
            # Merge Entities
            for ent in graph_data.entities:
                session.run("""
                    MERGE (e:Entity {name: $name, tenantId: $tenant_id})
                    ON CREATE SET e.type = $type
                    WITH e
                    MATCH (t:Tenant {id: $tenant_id})
                    MERGE (e)-[:BELONGS_TO]->(t)
                    WITH e
                    MATCH (d:Document {id: $doc_id})
                    MERGE (e)-[:FOUND_IN]->(d)
                """, name=ent.name, type=ent.type, tenant_id=tenant_id, doc_id=document_id)
            
            # Merge Relationships
            for rel in graph_data.relationships:
                session.run("""
                    MATCH (s:Entity {name: $source, tenantId: $tenant_id})
                    MATCH (t:Entity {name: $target, tenantId: $tenant_id})
                    MERGE (s)-[r:RELATION {type: $rel_type}]->(t)
                """, source=rel.source_entity, target=rel.target_entity, rel_type=rel.relation_type, tenant_id=tenant_id)
    except Exception as e:
        print(f"Failed to extract graph for a chunk: {e}")

def process_graph_track_sync(tenant_id: str, document_id: str, chunks: list[tuple[str, str]]):
    """Extracts entities/relationships via LLM and merges them into Neo4j securely using Multi-Threading."""
    with neo4j_manager.driver.session() as session:
        # First ensure the Tenant node exists
        session.run("MERGE (t:Tenant {id: $tenant_id})", tenant_id=tenant_id)
        
        # Ensure Document node exists and link to Tenant
        session.run("""
            MERGE (d:Document {id: $doc_id})
            ON CREATE SET d.tenantId = $tenant_id
            WITH d
            MATCH (t:Tenant {id: $tenant_id})
            MERGE (d)-[:BELONGS_TO]->(t)
        """, doc_id=document_id, tenant_id=tenant_id)

    # Extract unique parent chunks to avoid redundant LLM calls
    unique_parents = list(set([parent for parent, child in chunks]))
    
    print(f"Starting multi-threaded graph extraction for {len(unique_parents)} chunks...")
    
    # Process all chunks in parallel (max 10 threads)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_single_chunk, chunk, tenant_id, document_id) for chunk in unique_parents]
        concurrent.futures.wait(futures)
