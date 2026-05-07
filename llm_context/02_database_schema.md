# 02. Database Schema & State Management

The project strictly separates raw operational data from the agent's memory/state.

## 1. `database/amazon_sales.db` (Operational Data)
This is a Read/Write SQLite database holding historical sales and synthetic inventory.

### Table: `sales_history`
Contains historical Amazon sales data.
- **Columns**: `order_id`, `date`, `status`, `sku`, `category`, `qty`, `amount`, etc.
- **Usage**: Used to calculate historical lags (Lag 7, Lag 14, Lag 30) for the XGBoost model.

### Table: `inventory`
Contains the current stock, critical thresholds, and supplier lead times per SKU.
- **Columns**: 
  - `sku` (TEXT, PRIMARY KEY)
  - `current_stock` (INTEGER)
  - `critical_threshold` (INTEGER) - Dynamically generated based on product-specific lead time and safety factor.
  - `lead_time_days` (INTEGER, DEFAULT 7) - Supplier lead time categorized by sales velocity: high-volume SKUs get 3 days, medium-volume 7 days, low-volume 14 days.
- **Usage**: Used by `GET /scan-inventory` and updated by `POST /update-stock` (to simulate sales deductions). The `lead_time_days` field drives the dynamic risk thresholds (`High` = `days_of_stock < lead_time_days`).

## 2. `database/agent_state.db` (Agent Memory & Output)
This database holds the memory of the LangGraph agent and historical snapshots for alerting.

### Table: `risk_snapshots`
Stores the risk level of every SKU from the previous nightly scan.
- **Columns**: 
  - `sku` (TEXT, PRIMARY KEY)
  - `last_risk_level` (TEXT)
- **Usage**: During the `GET /scan-inventory` batch process, the system compares today's calculated risk to `last_risk_level`. If the rank increases (e.g., Low -> Medium, or Medium -> Critical), the item is flagged for a Slack alert.
- **Architecture Note**: We use an `UPSERT` (`ON CONFLICT DO UPDATE`) loop via `sqlite3` instead of `pandas.to_sql(replace)` to preserve the `PRIMARY KEY` constraint and avoid duplicate entries.

## 3. Database Concurrency & Locking
SQLite is notorious for the `database is locked` error when concurrent reads and writes occur (e.g., a massive `GET /scan-inventory` read while a `POST /update-stock` write happens).
- **`agent_state.db`**: Protected. We explicitly enable **WAL (Write-Ahead Logging)** mode via `PRAGMA journal_mode=WAL;` in `agent/graph.py` to allow concurrent readers and writers without blocking.
- **`amazon_sales.db`**: Currently uses standard journal mode. 

> **Instruction for Future LLMs:** 
> If the `amazon_sales.db` starts throwing `database is locked` errors during heavy `update-stock` operations, enable `PRAGMA journal_mode=WAL;` on its connection object immediately. Never mix `amazon_sales.db` logic with `agent_state.db`. If adding memory features, use `agent_state.db`. If adding product data, use `amazon_sales.db`. Always use parameterized queries `(?, ?)` to prevent SQL injection.
