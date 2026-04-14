# Hybrid ReAct Agent Architecture

A production-grade, closed-loop AI agent pipeline built with **LangGraph**, **FastAPI**, and **n8n**. This project demonstrates a hybrid reasoning and acting (ReAct) architecture specifically designed for supply chain and inventory risk analysis.

## 🚀 Key Features

* **LangGraph Cognitive Core:** Implements deterministic tool usage with strong system prompt guardrails.
* **Persistent Memory:** Utilizes `SqliteSaver` in WAL mode to handle concurrent conversation state management efficiently.
* **Token Bloat Protection:** Employs `trim_messages` to ensure the context window remains optimized (safely trimming at 4,000 tokens limit).
* **Robust API Layer:** Exposes the Agent via an asynchronous FastAPI endpoint, wrapped with `Tenacity` for automatic retry and exponential backoff mechanisms against external failures.
* **n8n Ready:** Specifically optimized JSON responses (exposing `tool_used`, `risk_level`) to act as a seamless HTTP Webhook backend for an n8n orchestration flow.
* **Mock Database Included:** Pre-populated dynamic SQLite database implementation for functional inventory queries right out of the box.

## 📂 Project Structure

```text
hybrid_react_agent/
├── .env                 # Environment variables (OpenAI API Keys)
├── requirements.txt     # Python dependencies
├── database/            # SQLite setup scripts and raw DB files
│   └── database.db      # Automatically populated mock storage limit
├── tools/               # ReAct tools (Inventory Analyzer with Pydantic Validation)
├── agent/               # LangGraph Engine (State, Nodes, Edges, Memory)
├── api/                 # FastAPI Router and Endpoint configurations
└── main.py              # Uvicorn entry point
```

## 🛠️ Quick Start

**1. Clone and Setup Environment**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Initialize the Mock Database**
Creates the mock database with standard `Products` data.
```bash
python3 database/db_setup.py
```

**3. Configure Environment Variables**
Edit the `.env` file to select your provider and include the respective API keys. By default, the provider is set to `openai`, but you can easily switch it to `gemini`.
```env
# Choose your provider: 'openai' or 'gemini'
LLM_PROVIDER=gemini

# Provider specific keys
GEMINI_API_KEY=your-gemini-key-here
OPENAI_API_KEY=sk-your-openai-key-here
```

**4. Run the Server**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
You can now access the interactive swagger docs at `http://localhost:8000/docs`.

## 🤖 API Interface / Endpoint

**POST `/chat`**

Request Payload:
```json
{
  "user_id": "unique-session-id-1234",
  "message": "What is the stock risk for Laptop Pro X?"
}
```

Response format precisely tailored for n8n Conditional logic integration:
```json
{
  "response": "The current stock for Laptop Pro X is critically low. Immediate supplier contact is required.",
  "thought_process": [
    {
       "type": "AIMessage",
       "content": "",
       "tool_calls": [{"name": "calculate_inventory_risk"}]
    }
  ],
  "tool_used": "calculate_inventory_risk",
  "risk_level": "High"
}
```
