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

def process_graph_track_sync(tenant_id: str, document_id: str, chunks: list[str]):
    """Extracts entities/relationships via LLM and merges them into Neo4j securely."""
    session = neo4j_manager.get_session()
    
    try:
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

        for chunk in chunks:
            try:
                # 1. LLM Extraction
                graph_data = extract_graph_from_chunk(chunk)
                
                # 2. Merge Entities
                for ent in graph_data.entities:
                    session.run("""
                        MERGE (e:Entity {name: $name, tenantId: $tenant_id})
                        ON CREATE SET e.type = $type
                        WITH e
                        MATCH (t:Tenant {id: $tenant_id})
                        MERGE (e)-[:BELONGS_TO]->(t)
                    """, name=ent.name, type=ent.type, tenant_id=tenant_id)
                
                # 3. Merge Relationships
                for rel in graph_data.relationships:
                    session.run("""
                        MATCH (s:Entity {name: $source, tenantId: $tenant_id})
                        MATCH (t:Entity {name: $target, tenantId: $tenant_id})
                        MERGE (s)-[r:RELATION {type: $rel_type}]->(t)
                    """, source=rel.source_entity, target=rel.target_entity, rel_type=rel.relation_type, tenant_id=tenant_id)

            except Exception as e:
                print(f"Failed to extract graph for a chunk: {e}")

    finally:
        session.close()
