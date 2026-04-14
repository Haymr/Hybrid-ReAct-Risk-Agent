from fastapi import FastAPI
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from api.server import router as chat_router

app = FastAPI(
    title="Hybrid ReAct Agent API",
    description="FastAPI server for the LangGraph-based inventory risk analysis agent.",
    version="1.0.0"
)

app.include_router(chat_router)

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Agent API is running."}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)