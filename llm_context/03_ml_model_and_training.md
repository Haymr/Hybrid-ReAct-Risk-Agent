# 03. Machine Learning Model & Training

### Why XGBoost instead of Deep Learning (LSTM / TimesFM)?
1. **Speed & Resource Efficiency:** The agent calculates 30-day demand in sub-milliseconds on CPU without needing heavy PyTorch/CUDA dependencies.
2. **Quantile Regression Support (v3.2.0):** Instead of using a scalar point forecast, XGBoost generates probabilistic bounds (P10, P50, P90) natively using `objective='reg:quantileerror'`.
3. **Robustness to Sparse Data:** E-commerce sales are often "intermittent" (days with 0 sales). Deep learning models struggle here, but tree-based models excel.

## Feature Engineering
The model uses lag-based features (autoregressive strategy):
* `lag_7`: Sales in the last 7 days.
* `lag_14`: Sales in the last 14 days.
* `lag_30`: Sales in the last 30 days.
* `velocity_ratio`: `lag_7 / (lag_30 + 1)`. Identifies sudden sales spikes or drops.
* `is_no_history`: Boolean flag marking sparse data (if `lag_30 == 0`).

## The `target_30d` Variable
Instead of predicting the next 1 day, the model predicts the **SUM of sales for the upcoming 30 days**. This acts as a smoothing mechanism that significantly improves accuracy and reduces alert noise (essential for supply chain stability).

> **Training Integrity Note:** The `FixedForwardWindowIndexer` uses `min_periods=30`, ensuring only rows with a full 30-day future window contribute to training. The last 29 days of each SKU's history are excluded via `dropna`, preventing the model from learning from artificially low partial-window targets.

## Probabilistic Forecasting (Quantiles)
The model outputs a 2D array of shape `(N, 3)` corresponding to three quantiles:
* **P10 (Optimistic):** Worst-case scenario for revenue (low sales).
* **P50 (Median):** The most likely scenario. Used as the main threshold for risk classification.
* **P90 (Conservative/Tail Risk):** Worst-case scenario for inventory (high sales). Used as a Value-at-Risk (VaR) insight to prevent stockouts.

## Dynamic Risk Thresholds
Risk levels are **not** calculated against hardcoded day values. They are based on each product's `lead_time_days` column from the `inventory` table:
- `Critical`: `current_stock <= critical_threshold`
- `High`: `days_of_stock < lead_time_days` — stock will run out before the supplier can even replenish
- `Medium`: `days_of_stock < lead_time_days * 2` — safety margin is thin
- `Low`: all other cases

The `calculate_inventory_risk` tool now returns `lead_time_days` and `days_of_stock` in its JSON output so the LLM can reason about supply chain context explicitly.

## Model Evaluation (`evaluate_model.ipynb`)
Evaluations are kept in a Jupyter Notebook to visualize distributions (like Fill Rate). The metrics used:
* **RMSE:** Captures heavy deviations (spikes).
* **MASE (Mean Absolute Scaled Error):** The primary benchmark. Uses the previous 30 days as a Naive baseline. Our model achieves a MASE of ~0.75 (25% better than naive).
* **Fill Rate:** A business metric measuring what percentage of demand is fulfilled if we stock up to the P90 forecast.
* **Lost Sales Rate:** 1 - Fill Rate.

## The Retraining Pipeline (`POST /retrain`)
- **Execution:** Triggered via HTTP. It uses `subprocess.run(..., timeout=120)` to execute `scripts/train_model.py` in a separate thread.
- **Zero-Downtime:** While the model trains, the FastAPI server continues answering `/chat` and `/scan-inventory` requests using the old model in memory.
- **Reloading:** Once training finishes, the new `xgboost_model.pkl` is saved to disk, and `reload_model()` is called to flush the cached `_model` global variable, forcing the API to load the fresh weights on the very next inference.

> **Instruction for Future LLMs:** 
> Do not attempt to refactor this into an LSTM or TCN. Deep Learning models are overengineering for this use case and will break the lightweight MLOps pipeline. If you want to improve model accuracy, add features like `day_of_week`, `is_weekend`, or `month` to the lag calculation. Do NOT change `min_periods` back to 1 — this would reintroduce partial-window target leakage.
