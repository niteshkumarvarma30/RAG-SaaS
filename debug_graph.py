import sys
import os

# Add the project root to the python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.retrieval.graph import crag_app

initial_state = {
    "tenant_id": "619f50ab-df74-4057-9305-05a70fdc2474",
    "question": "How do I setup Postgres replication?",
    "generation": "",
    "documents": "",
    "route": ""
}

try:
    final_state = crag_app.invoke(initial_state)
    print("Success:", final_state)
except Exception as e:
    import traceback
    traceback.print_exc()
