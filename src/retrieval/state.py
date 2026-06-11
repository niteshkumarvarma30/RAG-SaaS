from typing import TypedDict

class GraphState(TypedDict):
    """Represents the strictly typed state of our CRAG graph."""
    tenant_id: str
    question: str
    generation: str
    documents: str
    route: str
