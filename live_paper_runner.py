import os
import sys
import pandas as pd
import yfinance as yf
import datetime
import urllib.request
import json

# Add current folder to path to allow importing adjacent modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_scraper import IngestionAgent
from model import StrategyAgent
from paper_broker import ExecutionAgent, RiskAgent

# Global cache to persist historical dataframes and avoid yfinance rate-limiting
LIVE_DATA_CACHE = {}

def run_live_paper_trading(strategy=None):
    global LIVE_DATA_CACHE
    tickers = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"]
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    portfolio_file = os.path.abspath(os.path.join(base_dir, "..", "data", "live_paper_portfolio.json"))
    data_dir = os.path.abspath(os.path.join(base_dir, "..", "data"))

    print("==================================================")
    print("LIVE PAPER TRADING BOT RUNNER (2-SEC SCALPER)")
    print("==================================================")

    # 1. Initialize execution and risk agents, load portfolio state
    execution = ExecutionAgent(initial_capital=100000.0)
    execution.load_state(portfolio_file)
    risk = RiskAgent(stop_loss_pct=0.02, take_profit_pct=0.05, max_allocation_pct=0.20)

    # 2. Fallback/Safety model training
    if strategy is None:
        print("Initializing Strategy Agent (ML Brain) in fallback mode...")
        strategy = StrategyAgent(tickers, data_dir=data_dir)
        strategy.train_model()

    # 3. Fetch latest quotes from the public REST API in one batch request
    current_prices = {}
    try:
        import requests
        url = "http://65.0.104.9/stock/list?symbols=RELIANCE,TCS,INFY,HDFCBANK&res=num"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0', 'Connection': 'close'}, timeout=5.0)
        if response.status_code == 200:
            res_data = response.json()
            if res_data.get("status") == "success":
                for stock_info in res_data.get("stocks", []):
                    sym = stock_info["symbol"]
                    ticker = f"{sym}.NS"
                    current_prices[ticker] = float(stock_info["last_price"])
    except Exception as e:
        print(f"Error fetching batch quotes from public REST API: {e}")

    # Fallback to yfinance if the REST API fails
    if not current_prices:
        print("Falling back to yfinance for live quotes...")
        for ticker in tickers:
            try:
                t = yf.Ticker(ticker)
                current_prices[ticker] = float(t.fast_info['lastPrice'])
            except Exception as yf_err:
                print(f"Failed to fetch live quote for {ticker} from yfinance: {yf_err}")

    if not current_prices:
        print("Warning: No quotes available. Skipping this tick.")
        return

    # Use current datetime stamp for trade logs
    today_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    current_minute = datetime.datetime.now().replace(second=0, microsecond=0)

    # Ingestion Agent for fundamental fetching
    ingestion = IngestionAgent(output_dir=data_dir)
    today_features = {}

    # 4. Update dataframes and compute technicals using the global cache
    for ticker in tickers:
        try:
            # Step A: Download historical 1m data once if not cached
            if ticker not in LIVE_DATA_CACHE:
                print(f"Downloading historical 1-minute data for {ticker} to seed cache...")
                # Download last 5 days of 1-minute data
                df = yf.download(ticker, period="5d", interval="1m")
                if df.empty:
                    print(f"Failed to seed cache for {ticker}")
                    continue
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = df.reset_index()
                if "Datetime" in df.columns:
                    df = df.rename(columns={"Datetime": "Date"})
                df["Date"] = pd.to_datetime(df["Date"])
                if df["Date"].dt.tz is not None:
                    df["Date"] = df["Date"].dt.tz_localize(None)
                df["Ticker"] = ticker
                LIVE_DATA_CACHE[ticker] = df

            # Step B: Get cached dataframe
            df = LIVE_DATA_CACHE[ticker].copy()

            # Step C: Update the dataframe with the latest tick
            live_price = current_prices[ticker]
            last_row_date = df["Date"].iloc[-1]
            if hasattr(last_row_date, "tzinfo") and last_row_date.tzinfo is not None:
                last_row_date = last_row_date.tz_localize(None)
            
            # If the current minute is newer than the last row, append a new row
            if current_minute > last_row_date:
                new_row = {
                    "Date": current_minute,
                    "Open": live_price,
                    "High": live_price,
                    "Low": live_price,
                    "Close": live_price,
                    "Volume": 0, # We will accumulate volume in future iterations if needed
                    "Ticker": ticker
                }
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            else:
                # Still in the same minute, update the last row's Close, High, Low
                idx = df.index[-1]
                df.at[idx, "Close"] = live_price
                if live_price > df.at[idx, "High"]:
                    df.at[idx, "High"] = live_price
                if live_price < df.at[idx, "Low"]:
                    df.at[idx, "Low"] = live_price

            # Save the updated dataframe back to cache
            LIVE_DATA_CACHE[ticker] = df

            # Step D: Compute technical indicators on the updated dataframe
            df["MA50"] = df["Close"].rolling(window=50).mean()
            df["MA200"] = df["Close"].rolling(window=200).mean()

            delta = df["Close"].diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            avg_gain = gain.rolling(window=14).mean()
            avg_loss = loss.rolling(window=14).mean()
            rs = avg_gain / avg_loss.replace(0, 0.001)
            df["RSI14"] = 100 - (100 / (1 + rs))

            df["Volume_Ratio"] = df["Volume"] / df["Volume"].rolling(window=20).mean().replace(0, 1.0)

            # Today's technical row (last row of calculated features)
            tech_row = df.iloc[-1:].copy()

            # Fetch fundamentals
            fund_df = ingestion.fetch_historical_fundamentals(ticker)
            if not fund_df.empty:
                latest_fund = fund_df.sort_values("Date").iloc[-1]
                net_profit_margin = latest_fund["Net_Profit_Margin"]
                debt_to_equity = latest_fund["Debt_to_Equity"]
            else:
                net_profit_margin = 0.0
                debt_to_equity = 0.0

            tech_row["Net_Profit_Margin"] = net_profit_margin
            tech_row["Debt_to_Equity"] = debt_to_equity

            # Format Date column back to string format for StrategyAgent
            tech_row["Date"] = pd.to_datetime(tech_row["Date"]).dt.strftime('%Y-%m-%d %H:%M:%S')

            today_features[ticker] = tech_row
            print(f"Current price for {ticker}: INR {live_price:.2f}")

        except Exception as e:
            print(f"Error processing live data for {ticker}: {e}")

    # 5. Risk Agent Check: Evaluate active positions first
    print("\n[Risk Check] Evaluating active positions...")
    for ticker in list(execution.active_positions.keys()):
        if ticker in current_prices:
            position = execution.active_positions[ticker]
            current_price = current_prices[ticker]
            
            should_sell, reason = risk.check_position_risk(
                ticker, current_price, position["entry_price"]
            )
            if should_sell:
                execution.sell_asset(ticker, today_str, current_price, reason=reason)

    # 6. Strategy & Decision Execution: Process signals
    print("\n[Strategy Check] Evaluating model signals...")
    for ticker in tickers:
        if ticker not in today_features or ticker not in current_prices:
            continue
            
        features_df = today_features[ticker]
        current_price = current_prices[ticker]

        try:
            signal, proba = strategy.predict_signal(features_df)
            signal_val = int(signal[0])
            confidence = float(proba[0])
            print(f"{ticker} | Signal: {signal_val} | Confidence: {confidence:.2%}")

            # BUY Decision
            is_active = ticker in execution.active_positions
            position = execution.active_positions.get(ticker) if is_active else None
            buy_count = position.get("buy_count", 1) if position else 0

            # Conditions to buy:
            # Case 1: Ticker is not currently active
            # Case 2: Ticker is active, but we have bought it only once (buy_count < 2), and current price is >= 1.0% lower than entry price
            can_buy = False
            is_averaging_down = False
            if not is_active:
                can_buy = True
            elif buy_count < 2:
                entry_price = position["entry_price"]
                price_drop_pct = (entry_price - current_price) / entry_price
                if price_drop_pct >= 0.003: # at least 0.3% drop
                    can_buy = True
                    is_averaging_down = True
                    print(f"  [Average Down] {ticker} qualifies for averaging down! Price drop: {price_drop_pct:.2%}")

            print(f"  [DEBUG BUY] ticker={ticker} | signal_val={signal_val} | confidence={confidence:.4f} | threshold={strategy.buy_threshold:.4f} | can_buy={can_buy} | is_averaging_down={is_averaging_down}")
            
            if signal_val == 1 and confidence >= strategy.buy_threshold and can_buy:
                is_cooldown = execution.is_in_cooldown(ticker, today_str, cooldown_days=0)
                print(f"  [DEBUG BUY] cooldown={is_cooldown}")
                if not is_cooldown:
                    allocation = risk.calculate_buy_allocation(
                        execution.initial_capital, execution.current_cash
                    )
                    print(f"  [DEBUG BUY] allocation={allocation} | current_cash={execution.current_cash}")
                    if allocation > 0:
                        execution.buy_asset(ticker, today_str, current_price, allocation)
                else:
                    print(f"  Buy signal ignored: {ticker} is in cooldown block.")

        except Exception as e:
            print(f"Error predicting signal for {ticker}: {e}")

    # 7. Save State
    execution.save_state(portfolio_file)

    # 8. Print Console Dashboard
    current_portfolio_value = execution.get_portfolio_value(current_prices)
    net_return = ((current_portfolio_value - execution.initial_capital) / execution.initial_capital) * 100

    print("\n================ LIVE PORTFOLIO DASHBOARD ================")
    print(f"Cash Balance:          INR {execution.current_cash:,.2f}")
    print(f"Active Holdings Value: INR {(current_portfolio_value - execution.current_cash):,.2f}")
    print(f"Total Valuation:       INR {current_portfolio_value:,.2f}")
    print(f"Net Return:            {net_return:+.2%}")
    print(f"Active Positions:      {list(execution.active_positions.keys())}")
    print(f"Active Cooldowns:      {execution.cooldowns}")
    print("==========================================================")


if __name__ == "__main__":
    run_live_paper_trading()
