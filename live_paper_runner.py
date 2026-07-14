import os
import sys
import pandas as pd
import yfinance as yf
import datetime

# Add current folder to path to allow importing adjacent modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_scraper import IngestionAgent
from model import StrategyAgent
from paper_broker import ExecutionAgent, RiskAgent

def run_live_paper_trading():
    """Fetches real-time/live market metrics, evaluates risk, runs model predictions, and records paper trades."""
    tickers = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"]
    portfolio_file = "data/live_paper_portfolio.json"

    print("==================================================")
    print("LIVE PAPER TRADING BOT RUNNER")
    print("==================================================")

    # 1. Initialize execution and risk agents, load portfolio state
    execution = ExecutionAgent(initial_capital=100000.0)
    execution.load_state(portfolio_file)
    risk = RiskAgent(stop_loss_pct=0.02, take_profit_pct=0.05, max_allocation_pct=0.20)

    # 2. Initialize and train Strategy Agent on existing historical data
    print("Initializing Strategy Agent (ML Brain)...")
    strategy = StrategyAgent(tickers, data_dir="data")
    strategy.train_model()

    # Ingestion Agent for fundamental fetching
    ingestion = IngestionAgent(output_dir="data")

    # Get today's date in YYYY-MM-DD
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    print(f"\nProcessing Today's Market Tick: {today_str}")

    # Store today's live prices and features for checking risk / new signals
    current_prices = {}
    today_features = {}

    # 3. Fetch latest live prices & fundamentals, build current feature rows
    for ticker in tickers:
        print(f"\nFetching live data for {ticker}...")
        try:
            # Fetch last 250 days of daily data to have enough rows for rolling 200 DMA calculations
            df = yf.download(ticker, period="250d", interval="1d")
            if df.empty:
                print(f"Failed to fetch live prices for {ticker}")
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.reset_index()
            df = df.sort_values("Date").reset_index(drop=True)
            
            # Today's close price (or last active trading session's close)
            latest_row = df.iloc[-1]
            current_price = float(latest_row["Close"])
            current_prices[ticker] = current_price
            
            # Compute technical features (50 DMA and 200 DMA)
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

            # MACD
            ema12 = df["Close"].ewm(span=12, adjust=False).mean()
            ema26 = df["Close"].ewm(span=26, adjust=False).mean()
            df["MACD"] = ema12 - ema26
            df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
            df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

            # Bollinger Bands
            sma20 = df["Close"].rolling(window=20).mean()
            std20 = df["Close"].rolling(window=20).std()
            upper_bb = sma20 + 2 * std20
            lower_bb = sma20 - 2 * std20
            df["BB_Upper_Dist"] = (df["Close"] - upper_bb) / upper_bb
            df["BB_Lower_Dist"] = (df["Close"] - lower_bb) / lower_bb
            df["BB_Width"] = (upper_bb - lower_bb) / sma20

            # ATR
            tr1 = df["High"] - df["Low"]
            tr2 = (df["High"] - df["Close"].shift(1)).abs()
            tr3 = (df["Low"] - df["Close"].shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df["ATR"] = tr.rolling(window=14).mean()
            df["ATR_Ratio"] = df["ATR"] / df["Close"]

            # Distance from MAs
            df["Dist_MA50"] = (df["Close"] - df["MA50"]) / df["MA50"]
            df["Dist_MA200"] = (df["Close"] - df["MA200"]) / df["MA200"]

            # Momentum ROC
            df["ROC_10"] = (df["Close"] - df["Close"].shift(10)) / df["Close"].shift(10).replace(0, 0.001)

            # Today's technical row
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

            today_features[ticker] = tech_row
            print(f"Current price for {ticker}: INR {current_price:.2f}")

        except Exception as e:
            print(f"Error fetching live data for {ticker}: {e}")

    # 4. Risk Agent Check: Evaluate active positions first
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

    # 5. Strategy & Decision Execution: Process signals
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
            if signal_val == 1 and confidence >= strategy.buy_threshold and ticker not in execution.active_positions:
                if not execution.is_in_cooldown(ticker, today_str, cooldown_days=10):
                    allocation = risk.calculate_buy_allocation(
                        execution.initial_capital, execution.current_cash
                    )
                    if allocation > 0:
                        execution.buy_asset(ticker, today_str, current_price, allocation)
                else:
                    print(f"  Buy signal ignored: {ticker} is in 10-day cooldown block.")


        except Exception as e:
            print(f"Error predicting signal for {ticker}: {e}")

    # 6. Save State
    execution.save_state(portfolio_file)

    # 7. Print Console Dashboard
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
