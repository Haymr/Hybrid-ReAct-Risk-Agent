# 04. API Endpoints & n8n Integrations

The system uses `FastAPI` to expose the agent and ML capabilities to the outside world.

## 1. `POST /chat`
- **Purpose:** Primary interaction endpoint. Takes `user_id` and `message`.
- **Logic:** Invokes the LangGraph agent. Parses the `ToolMessage` outputs to extract `risk_level`.
- **Output:** Returns `response` (string), `thought_process` (array), and crucially `requires_alert` (boolean).
- **n8n Link:** Connected to Slack via `n8n/Agent to Slack.json`. n8n uses an IF node checking `{{ $json.requires_alert }} == true` to route to an emergency channel.

## 2. `POST /update-stock`
- **Purpose:** Simulates ERP/real-world sales.
- **Logic:** Takes `sku` and `qty_sold`. Deducts `qty_sold` from `current_stock` in `inventory` table.
- **Usage:** Essential for testing how risk dynamically changes without manually modifying the DB.

## 3. `GET /scan-inventory`
- **Purpose:** Nightly Batch Scanner.
- **Logic:** Calculates `days_of_stock` for ALL items using XGBoost in memory. Compares the new risk level to `risk_snapshots` (in `agent_state.db`).
- **Output:** Returns a list of `escalated_items` (e.g., items that moved from Low to High risk).
```json
{
  "status": "success",
  "total_scanned": 108425,
  "escalated_items": [
    {
      "sku": "JNE3781-KR-XXXL",
      "old_risk": "Low",
      "new_risk": "High",
      "current_stock": 12,
      "predicted_demand_p50": 45,
      "tail_risk_demand_p90": 60
    }
  ]
}
```
**N8n Usage:** Triggered nightly via Cron. If `escalated_items` is not empty, n8n loops through them and sends alerts. Notice that `predicted_demand_p50` is the median expectation, while `tail_risk_demand_p90` is provided as a worst-case scenario (Value at Risk) insight for the supply planner.
- **n8n Link:** Triggered via `n8n/Nightly_Scanner.json` every day at 07:00 AM using a Schedule Trigger.

## 4. `POST /retrain`
- **Purpose:** Weekly background retraining.
- **Logic:** Calls the `train_model.py` script.
- **n8n Link:** Triggered via `n8n/Weekly_Retrainer.json` every Sunday at 03:00 AM using a Schedule Trigger.

## Testing Standards
- All endpoints and tools are tested via `pytest` located in the `tests/` directory. 
- Tests require `.env` to be loaded (handled by `tests/conftest.py`) to prevent API Key crashes.

## Security & Authentication (Auth)
- **Current State:** The endpoints (`/chat`, `/scan-inventory`, `/update-stock`, `/retrain`) are completely **OPEN** to the outside world. There is no API Key, JWT, or mTLS validation.
- **n8n Connection:** Currently, the system relies on the assumption that FastAPI and n8n run on the same trusted local network (or VPC), addressing `localhost:8000`.

> **Instruction for Future LLMs:** 
> When moving this service to a public-facing Cloud environment (AWS, GCP), you **MUST** implement API Key validation via FastAPI `Depends(APIKeyHeader)` before exposing it. Do not let n8n or the external world communicate without a secure token.

> **Instruction for Future LLMs:** 
> When modifying API endpoints, ensure you do not break the JSON response schemas. The n8n workflows rigidly depend on specific keys like `escalated_items` and `requires_alert`. Always run `pytest tests/` before finalizing any changes.
