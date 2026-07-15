import os
import sys
import io
import time
import threading
import numpy as np
import pandas as pd
import yfinance as yf
from flask import Flask, jsonify, render_template

# Add current folder to path to allow importing adjacent modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from live_paper_runner import run_live_paper_trading

# Define templates and static folder paths relative to this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
    static_url_path="/static"
)

PORTFOLIO_FILE = os.path.join(BASE_DIR, "..", "data", "live_paper_portfolio.json")
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
LOG_FILE = os.path.join(DATA_DIR, "live_agent_log.txt")

# Set up Dual Writer to mirror print statements to both stdout and a log file
class DualWriter:
    def __init__(self, stdout, file_handle):
        self.stdout = stdout
        self.file_handle = file_handle

    def write(self, message):
        self.stdout.write(message)
        self.file_handle.write(message)
        self.file_handle.flush()

    def flush(self):
        self.stdout.flush()
        self.file_handle.flush()

# Initialize log mirroring
os.makedirs(DATA_DIR, exist_ok=True)
log_file_handle = open(LOG_FILE, "a", encoding="utf-8")
sys.stdout = DualWriter(sys.stdout, log_file_handle)
sys.stderr = DualWriter(sys.stderr, log_file_handle)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/portfolio")
def get_portfolio():
    import json
    if not os.path.exists(PORTFOLIO_FILE):
        return jsonify({"error": "Portfolio file not found. Run the bot first."}), 404
        
    with open(PORTFOLIO_FILE, "r") as f:
        data = json.load(f)
    return jsonify(data)

@app.route("/api/ticker/<ticker>")
def get_ticker_data(ticker):
    try:
        # 1. Fetch latest 250 days directly from Yahoo Finance
        df = yf.download(ticker, period="250d", interval="1d")
        if df.empty:
            return jsonify({"error": f"Failed to download live data for {ticker}"}), 500
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()
        df = df.sort_values("Date").reset_index(drop=True)
        
        # Format Date column as string YYYY-MM-DD
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

        # 2. Compute Technical Indicators (50 DMA and 200 DMA)
        df["MA50"] = df["Close"].rolling(window=50).mean()
        df["MA200"] = df["Close"].rolling(window=200).mean()

        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss.replace(0, 0.001)
        df["RSI14"] = 100 - (100 / (1 + rs))

        df["Volume_Ratio"] = df["Volume"] / df["Volume"].rolling(window=20).mean()

        # 3. Merge latest fundamentals
        from data_scraper import IngestionAgent
        ingestion = IngestionAgent(output_dir=DATA_DIR)
        fund_df = ingestion.fetch_historical_fundamentals(ticker)
        if not fund_df.empty:
            fund_df = fund_df.sort_values("Date").reset_index(drop=True)
            df["Net_Profit_Margin"] = 0.0
            df["Debt_to_Equity"] = 0.0
            
            # Match fundamentals dynamically by date
            for idx, row in df.iterrows():
                row_date = row["Date"]
                past_funds = fund_df[fund_df["Date"] <= row_date]
                if not past_funds.empty:
                    latest_fund = past_funds.iloc[-1]
                    df.at[idx, "Net_Profit_Margin"] = latest_fund["Net_Profit_Margin"]
                    df.at[idx, "Debt_to_Equity"] = latest_fund["Debt_to_Equity"]
        else:
            df["Net_Profit_Margin"] = 0.0
            df["Debt_to_Equity"] = 0.0

        # Replace NaNs with None/null for JSON conversion
        df = df.replace({np.nan: None})

        records = df.to_dict(orient="records")
        return jsonify(records)
        
    except Exception as e:
        print(f"Error fetching live ticker data for {ticker}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/logs")
def get_logs():
    if not os.path.exists(LOG_FILE):
        return jsonify({"logs": ""})
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            # Read last 15KB of log output
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 15000))
            logs = f.read()
        return jsonify({"logs": logs})
    except Exception as e:
        return jsonify({"logs": f"Error reading logs: {e}"})

# Global Strategy Agent instance
global_strategy = None

@app.route("/api/run_bot", methods=["POST"])
def trigger_bot_run():
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    try:
        run_live_paper_trading(strategy=global_strategy)
        logs = buffer.getvalue()
        return jsonify({"status": "success", "logs": logs})
    except Exception as e:
        logs = buffer.getvalue()
        return jsonify({"status": "error", "message": str(e), "logs": logs})
    finally:
        sys.stdout = old_stdout

def background_scheduler():
    """Background daemon thread to execute live paper trading scan cycles every 2 seconds."""
    global global_strategy
    print("Pre-training Strategy Agent (ML Brain) on startup...")
    tickers = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"]
    from model import StrategyAgent
    global_strategy = StrategyAgent(tickers, data_dir=DATA_DIR)
    global_strategy.train_model()

    print("[Scheduler] Background agent scheduler thread active. Scanning every 2 seconds.")
    # Run once at startup (sleep a few seconds first to let flask bind)
    time.sleep(5)
    while True:
        try:
            print(f"\n[Scheduler] Triggering automatic market scan at {time.strftime('%Y-%m-%d %H:%M:%S')}...")
            run_live_paper_trading(strategy=global_strategy)
            print("[Scheduler] Automatic market scan completed successfully.")
        except Exception as e:
            print(f"[Scheduler Error] Auto scan failed: {e}")
        # Sleep for 2 seconds
        time.sleep(2)

if __name__ == "__main__":
    os.makedirs(os.path.join(BASE_DIR, "templates"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "static"), exist_ok=True)
    
    # Start the scheduler thread (handles reloader re-execution safe)
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        scheduler_thread = threading.Thread(target=background_scheduler, daemon=True)
        scheduler_thread.start()

    print("Starting TradingBOT Web Dashboard server...")
    print("Access the dashboard at http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
