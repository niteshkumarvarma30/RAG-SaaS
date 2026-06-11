from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from src.api.routes import router
import os

app = FastAPI(title="Hybrid RAG SaaS API")

# Add CORS so the widget can be embedded on any external customer domain securely
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Hybrid RAG SaaS"}

# Mount public directory for serving the widget locally
os.makedirs("src/public", exist_ok=True)
app.mount("/", StaticFiles(directory="src/public", html=True), name="public")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
