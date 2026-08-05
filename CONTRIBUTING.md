# Contributing to TradingBOT

Welcome! This guide outlines how to maintain and extend the MLOps trading engine.

## 📁 Repository Directory Map
- `/reports` - Daily and weekly performance summaries.
- `config.json` - Settings for profiles, thresholds, and target symbols.
- `daily_reporter.py` - Audits daily performance and updates `README.md`.
- `weekly_stats.py` - Compiles weekly metrics.
- `run_pipeline.py` - CLI coordinator utility.

## 🛠️ Operational Tasks
1. **Run Target Scans:** `python TradingBOT/web_server.py`
2. **Launch MLflow Tracking Server:** `python -m mlflow ui --port 5001`
3. **Generate Daily Report:** `python TradingBOT/daily_reporter.py`
4. **Compile Weekly Stats:** `python TradingBOT/weekly_stats.py`
