import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class Neo4jManager:
    def __init__(self):
        uri = os.environ.get("NEO4J_URI", "")
        user = os.environ.get("NEO4J_USERNAME", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD", "")
        
        if not uri or not password:
            raise ValueError("NEO4J_URI and NEO4J_PASSWORD must be provided.")
            
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def get_session(self):
        return self.driver.session()

neo4j_manager = Neo4jManager()
