import os
import sys
import pandas as pd
import yfinance as yf
import datetime
import urllib.request
import json
import xml.etree.ElementTree as ET
import re
import numpy as np

# Add current folder to path to allow importing adjacent modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_scraper import IngestionAgent
from model import StrategyAgent
from paper_broker import ExecutionAgent, RiskAgent

# Global cache to persist historical dataframes and avoid yfinance rate-limiting
LIVE_DATA_CACHE = {}

def fetch_batch_live_prices(tickers):
    """Fetches batch live prices for all tickers using yfinance in one fast request."""
    current_prices = {}
    try:
        data = yf.download(tickers, period="1d", interval="1m", progress=False)
        if not data.empty and "Close" in data.columns:
            close_df = data["Close"]
            if isinstance(close_df, pd.Series):
                t = tickers[0]
                series = close_df.dropna()
                if not series.empty:
                    current_prices[t] = float(series.iloc[-1])
            else:
                for t in tickers:
                    if t in close_df.columns:
                        series = close_df[t].dropna()
                        if not series.empty:
                            current_prices[t] = float(series.iloc[-1])
    except Exception as e:
        print(f"[Batch Quotes Error] yf.download failed: {e}")

    # Fallback to individual history if any missing
    for t in tickers:
        if t not in current_prices or np.isnan(current_prices[t]):
            try:
                hist = yf.Ticker(t).history(period="1d", interval="1m")
                if not hist.empty and "Close" in hist.columns:
                    current_prices[t] = float(hist["Close"].iloc[-1])
            except Exception as err:
                print(f"[Quote Fallback Error] {t}: {err}")
                
    return current_prices

def fetch_sentiment_score(ticker):
    """Fetches recent news for a ticker and calculates a simple keyword sentiment score."""
    search_ticker = ticker.split(".")[0]
    url = f"https://finance.yahoo.com/rss/headline?s={search_ticker}"
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            xml_data = response.read()
        
        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        
        titles = []
        for item in items:
            title_el = item.find("title")
            if title_el is not None and title_el.text:
                titles.append(title_el.text)
                
        if not titles:
            return 0.0
            
        pos_words = re.compile(r'\b(bullish|profit|growth|buy|upbeat|gain|success|positive|soar|climb|rise|rally|strong|outperform)\b', re.IGNORECASE)
        neg_words = re.compile(r'\b(bearish|loss|crash|fall|debt|decline|negative|drop|plunge|sell|worry|warn|weak|underperform)\b', re.IGNORECASE)
        
        total_score = 0.0
        match_count = 0
        for title in titles:
            pos_matches = len(pos_words.findall(title))
            neg_matches = len(neg_words.findall(title))
            if pos_matches + neg_matches > 0:
                total_score += (pos_matches - neg_matches) / (pos_matches + neg_matches)
                match_count += 1
                
        if match_count == 0:
            return 0.0
            
        avg_score = total_score / match_count
        return float(np.clip(avg_score, -1.0, 1.0))
        
    except Exception as e:
        print(f"  [Sentiment Error] Failed to fetch sentiment for {ticker}: {e}")
        return 0.0

DAILY_SMA50_CACHE = {}

def get_daily_sma50(ticker):
    """Fetches Daily 50 SMA for the ticker and caches it."""
    global DAILY_SMA50_CACHE
    if ticker in DAILY_SMA50_CACHE:
        return DAILY_SMA50_CACHE[ticker]
    
    try:
        print(f"Fetching daily 50 SMA for {ticker}...")
        daily_df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if isinstance(daily_df.columns, pd.MultiIndex):
            daily_df.columns = daily_df.columns.get_level_values(0)
            
        daily_df["SMA50"] = daily_df["Close"].rolling(window=50).mean()
        sma50 = float(daily_df["SMA50"].iloc[-1])
        DAILY_SMA50_CACHE[ticker] = sma50
        print(f"  [Daily Filter] {ticker} SMA50: INR {sma50:.2f}")
        return sma50
    except Exception as e:
        print(f"Error fetching daily SMA for {ticker}: {e}")
        return None

def run_live_paper_trading(strategy=None, profile_id="macro"):
    global LIVE_DATA_CACHE
    tickers = [
        "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", 
        "ICICIBANK.NS", "SBIN.NS", "ITC.NS", "LT.NS", 
        "BHARTIARTL.NS", "WIPRO.NS"
    ]
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    portfolio_filename = f"live_paper_portfolio_{profile_id}.json"
    portfolio_file = os.path.abspath(os.path.join(base_dir, "..", "data", portfolio_filename))
    if not os.path.exists(portfolio_file) and profile_id == "legacy":
        portfolio_file = os.path.abspath(os.path.join(base_dir, "..", "data", "live_paper_portfolio.json"))
        
    data_dir = os.path.abspath(os.path.join(base_dir, "..", "data"))

    print("==================================================")
    print(f"LIVE PAPER TRADING BOT RUNNER (PROFILE: {profile_id.upper()})")
    print("==================================================")

    # 1. Initialize execution and risk agents, load portfolio state based on profile_id
    execution = ExecutionAgent(initial_capital=100000.0)
    execution.load_state(portfolio_file)

    if profile_id == "ultra":
        target_buy_threshold = 0.68
        risk = RiskAgent(stop_loss_pct=0.03, take_profit_pct=0.04, max_allocation_pct=0.10, trailing_stop_loss_pct=0.03)
        max_rsi_allowed = 58.0
    else:
        target_buy_threshold = getattr(strategy, 'buy_threshold', 0.57) if strategy else 0.57
        risk = RiskAgent(stop_loss_pct=0.05, take_profit_pct=0.05, max_allocation_pct=0.10, trailing_stop_loss_pct=0.05)
        max_rsi_allowed = 65.0

    # 2. Fallback/Safety model training
    if strategy is None:
        print("Initializing Strategy Agent (ML Brain) in fallback mode...")
        strategy = StrategyAgent(tickers, data_dir=data_dir)
        strategy.train_model()

    # 3. Fetch latest quotes in one fast batch request for all 10 tickers
    current_prices = fetch_batch_live_prices(tickers)

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

            # 4. MACD
            ema12 = df["Close"].ewm(span=12, adjust=False).mean()
            ema26 = df["Close"].ewm(span=26, adjust=False).mean()
            df["MACD"] = ema12 - ema26
            df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
            df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

            # 5. Bollinger Bands
            sma20 = df["Close"].rolling(window=20).mean()
            std20 = df["Close"].rolling(window=20).std()
            upper_bb = sma20 + 2 * std20
            lower_bb = sma20 - 2 * std20
            df["BB_Upper_Dist"] = (df["Close"] - upper_bb) / upper_bb.replace(0, 0.001)
            df["BB_Lower_Dist"] = (df["Close"] - lower_bb) / lower_bb.replace(0, 0.001)
            df["BB_Width"] = (upper_bb - lower_bb) / sma20.replace(0, 0.001)

            # 6. ATR
            tr1 = df["High"] - df["Low"]
            tr2 = (df["High"] - df["Close"].shift(1)).abs()
            tr3 = (df["Low"] - df["Close"].shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df["ATR"] = tr.rolling(window=14).mean()
            df["ATR_Ratio"] = df["ATR"] / df["Close"].replace(0, 0.001)

            # 7. Distance from MAs
            df["Dist_MA50"] = (df["Close"] - df["MA50"]) / df["MA50"].replace(0, 0.001)
            df["Dist_MA200"] = (df["Close"] - df["MA200"]) / df["MA200"].replace(0, 0.001)

            # 8. Momentum (Rate of Change)
            df["ROC_10"] = (df["Close"] - df["Close"].shift(10)) / df["Close"].shift(10).replace(0, 0.001)

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
            
            # Initialize or update peak price
            entry_price = position["entry_price"]
            peak_price = position.get("peak_price", entry_price)
            if current_price > peak_price:
                position["peak_price"] = current_price
                peak_price = current_price
                print(f"  [Risk Check] Updated peak price for {ticker}: INR {peak_price:.2f}")
                
            should_sell, reason = risk.check_position_risk(
                ticker, current_price, entry_price, peak_price=peak_price
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

            # Check Daily 50 SMA trend filter and Intraday Micro-Dip filter
            if can_buy:
                sma50 = get_daily_sma50(ticker)
                if sma50 and current_price < sma50:
                    print(f"  [Trend Filter] Blocked BUY/AVG-DOWN for {ticker}: Price (INR {current_price:.2f}) is below Daily 50 SMA (INR {sma50:.2f})")
                    can_buy = False

                # Intraday Micro-Dip check: Avoid buying at the peak of a 1-minute overbought spike (RSI > max_rsi_allowed)
                if can_buy and "RSI14" in df.columns:
                    intraday_rsi = df["RSI14"].iloc[-1] if not pd.isna(df["RSI14"].iloc[-1]) else 50.0
                    if intraday_rsi > max_rsi_allowed:
                        print(f"  [Micro-Dip Filter] Blocked BUY for {ticker}: 1-min RSI ({intraday_rsi:.1f}) exceeds profile max ({max_rsi_allowed:.1f})")
                        can_buy = False

            print(f"  [DEBUG BUY] ticker={ticker} | signal_val={signal_val} | confidence={confidence:.4f} | threshold={target_buy_threshold:.4f} | can_buy={can_buy} | is_averaging_down={is_averaging_down}")
            
            if signal_val == 1 and confidence >= target_buy_threshold and can_buy:
                # Run Live Sentiment override check
                sentiment_score = fetch_sentiment_score(ticker)
                print(f"  [Sentiment Agent] Ticker: {ticker} | Sentiment: {sentiment_score:+.2f}")
                if sentiment_score < -0.2:
                    print(f"  [Sentiment Block] Blocked BUY signal for {ticker} due to bearish news sentiment ({sentiment_score:+.2f})")
                else:
                    is_cooldown = execution.is_in_cooldown(ticker, today_str, cooldown_days=2)
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
