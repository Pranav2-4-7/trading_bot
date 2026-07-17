# TradingBOT - Premium Multi-Agent Terminal & Real-Time Scalper

A professional, real-time intraday scalping bot and interactive web dashboard built to trade Indian Equities (RELIANCE, TCS, INFY, HDFCBANK). The project combines an advanced XGBoost machine learning brain, dynamic risk management, and a live financial news sentiment analysis filter.

---

## Features

- **Live 2-Second Scalping Scheduler**: Periodically polls live market quotes and runs real-time predictions in under 1ms.
- **Premium Web Dashboard**: A responsive Flask-based web interface at `http://127.0.0.1:5000` showing:
  - Account equity curve and cash balances.
  - Active positions table with dynamic PnL tracking.
  - Closed transactions ledger showing exit reasons.
  - Real-time terminal log outputs.
- **XGBoost ML Brain (18 Features)**: Pre-trained on 1-minute historical candles from Yahoo Finance. Features include:
  - *Core Trend:* 50/200 period Moving Averages, distance from MAs.
  - *Momentum:* RSI14, MACD (Signal/Hist), Rate of Change (ROC_10).
  - *Volatility:* Bollinger Bands (Width, Upper/Lower distances), ATR, ATR_Ratio.
  - *Base:* Close, Volume, Volume Ratio.
  - *Fundamentals:* Net Profit Margin, Debt-to-Equity.
- **Live RSS News Sentiment Agent**: Scraping recent Yahoo Finance news headlines via built-in XML parsing. Overrides and blocks buy orders if stock sentiment is bearish (`< -0.2`).
- **Dynamic Profit Locking (Trailing Stop-Loss)**: Tracks the highest peak price reached for all open positions and triggers automatic exit orders if the price drops `2.0%` from its peak.
- **Smart Averaging Down**: Allows buying more shares to lower average cost if price drops by `0.3%` or more, capped at 2 entries max per position.

---

## Project Structure

```text
TradingBOT/
  static/
    app.js              # Frontend dashboard client logic
    style.css           # Terminal styles and layout
  templates/
    index.html          # Web dashboard markup
  agent_coordinator.py  # Historical backtesting simulation coordinator
  data_scraper.py      # Technical feature engineering and data ingestion
  live_paper_runner.py  # 2-second scalper execution runner & sentiment agent
  model.py              # XGBoost ML Brain classifier and training script
  paper_broker.py       # Simulated broker with averaging down & trailing SL
  web_server.py         # Flask dashboard API and scan scheduler
```

---

## Setup & Running the Bot

### 1. Initialize Virtual Environment
Ensure you have Python 3.10+ installed. Initialize the virtual environment and install dependencies:

```bash
# Create and activate environment
python -m venv .venv
.venv\Scripts\activate

# Install required packages
pip install requests yfinance pandas xgboost scikit-learn Flask beautifulsoup4
```

### 2. Start the Live Scalper & Dashboard
Run the web server. This will pre-train the XGBoost brain on startup and kick off the 2-second background scheduler thread:

```bash
python TradingBOT/web_server.py
```

Open **`http://127.0.0.1:5000`** in your browser to view the active terminal, logs, and portfolio metrics.

---

## Model Evaluation & Performance

You can evaluate the XGBoost Strategy Agent's standalone accuracy and classification metrics directly:

```bash
python TradingBOT/model.py
```

**Latest Brain Accuracy Report:**
* **Accuracy Score**: `59.82%`
* **Buy Signal Precision**: `17%`
* **Positive F1-Score**: `0.26`

---

## Simulation Backtests

To run a historical paper trading simulation to verify your parameters (thresholds, stop losses, etc.):

```bash
python TradingBOT/agent_coordinator.py
```
