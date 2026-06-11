from src.retrieval.hybrid import vector_search, keyword_search, graph_search
from src.retrieval.nodes import route_query

tenant_id = "619f50ab-df74-4057-9305-05a70fdc2474"
query = "Platform and Client Compatibility"

with open("search_results.txt", "w", encoding="utf-8") as f:
    f.write("Vector Search:\n")
    try:
        f.write(str(vector_search(tenant_id, query)))
    except Exception as e:
        f.write("Vector Error: " + str(e))

    f.write("\n\nKeyword Search:\n")
    try:
        f.write(str(keyword_search(tenant_id, query)))
    except Exception as e:
        f.write("Keyword Error: " + str(e))

    f.write("\n\nGraph Search:\n")
    try:
        f.write(str(graph_search(tenant_id, query)))
    except Exception as e:
        f.write("Graph Error: " + str(e))
