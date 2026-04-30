# 01. Architecture & Core Logic

## Project Overview
This project is an **Autonomous Supply Chain & Inventory Risk SaaS**. It uses a **Hybrid ReAct Agent** architecture that combines deterministic Machine Learning (XGBoost) with Generative AI (LangGraph/LangChain) and an Orchestration layer (n8n).

## Core Components
1. **FastAPI Backend (`api/server.py`)**: The central brain. Hosts the LangGraph agent, the ML inference endpoints, and webhook listeners for n8n.
2. **ReAct Agent (`agent/graph.py` & `tools/inventory.py`)**: A LangGraph `create_react_agent` configured with `system_prompt.txt`. It acts as a Supply Chain Consultant. The agent uses tools to query inventory and calculate risk levels.
3. **Machine Learning (`scripts/train_model.py`)**: An XGBoost regressor that predicts 30-day cumulative demand based on historical lags (7, 14, 30 days).
4. **n8n Orchestration (`n8n/`)**: Executes cron jobs (Nightly Batch Scans, Weekly Retraining) and connects the FastAPI agent to Slack for interactive chatting and autonomous alerting.

## Key Design Principles (Context for LLMs)
- **Zero-Downtime ML**: The model can be retrained in the background (`/retrain`) using `subprocess`. The new `.pkl` is hot-reloaded into memory without dropping API requests.
- **Batch Scanning over Loop LLM**: Instead of making the LLM check 7,000 SKUs sequentially (which takes hours and massive tokens), the `GET /scan-inventory` endpoint uses vectorized Pandas operations to calculate risk for all items in ~100ms.
- **Graceful Degradation**: If the LangGraph recursion limit is reached or the LLM fails, the API catches the exception and returns a static JSON payload rather than crashing the server.
- **Boolean Alerting**: The n8n logic relies on a single `requires_alert: true/false` flag returned by the API, decoupling n8n from string-matching (`risk == "High"`).

## Memory & Context Window Management (Checkpointer)
The LangGraph agent is fully stateful and remembers previous conversations.
- **Persistence:** Enabled via `SqliteSaver` pointing to `agent_state.db` using the thread ID (user ID).
- **Context Bloat Prevention:** To prevent long chats from hitting the LLM's max token limit (and wasting money), we use LangChain's `trim_messages`.
- **Trimming Strategy:** The message history is strictly pruned to the **last 4000 tokens**. To avoid hitting the LLM Provider API limit with constant HTTP token-counting requests (Error 503), we use a **local `tiktoken` proxy counter**.

> **Instruction for Future LLMs:** 
> When modifying the Agent's logic, do NOT put heavy computational tasks (like scanning 1000 items) inside a LangChain Tool. Always use the FastAPI endpoints and Pandas for bulk data processing, reserving the LLM for chat and single-item deep analysis. When tweaking the prompt, be aware of the 4000 token sliding window.
