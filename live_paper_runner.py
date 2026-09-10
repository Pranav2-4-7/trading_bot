import os
import sys
import time
import pandas as pd
import yfinance as yf
try:
    yf.set_tz_cache_location("C:\\AntiGravity\\data\\yf_cache")
except Exception:
    pass
import yfinance.utils as yf_utils
yf_utils._sys.stderr = sys.stderr
import datetime
import urllib.request
import json
import xml.etree.ElementTree as ET
import re
import numpy as np

# Add current folder to path to allow importing adjacent modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_scraper import IngestionAgent, WATCHLIST, COMPANY_NAME_MAP
from model import StrategyAgent
from paper_broker import (
    ExecutionAgent, 
    RiskAgent, 
    PortfolioRiskAgent, 
    TICKER_SECTORS, 
    compute_60d_correlation_matrix,
    check_exits
)
from news_ingestor import GlobalNewsIngestor
from sentiment_analyzer import FinBERTSentimentAnalyzer

# Instantiate globally
news_ingestor = GlobalNewsIngestor()
sentiment_analyzer = FinBERTSentimentAnalyzer()
SENTIMENT_CACHE = {}

# Global cache to persist historical dataframes and avoid yfinance rate-limiting
LIVE_DATA_CACHE = {}

# Dead man's switch tracking
LAST_SUCCESSFUL_FETCH_TIMESTAMP = None
CONSECUTIVE_FETCH_FAILURES = 0

# Daily drawdown circuit breaker tracking: {profile_id: {'date': 'YYYY-MM-DD', 'start_val': float}}
PORTFOLIO_DAY_START_TRACKER = {}

# Cached 60-day correlation matrix
CORRELATION_MATRIX_CACHE = None

def fetch_batch_live_prices(tickers):
    """Fetches batch live prices for all tickers using yfinance in one fast request with dead man's switch tracking."""
    global LAST_SUCCESSFUL_FETCH_TIMESTAMP, CONSECUTIVE_FETCH_FAILURES
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

    if current_prices and len(current_prices) > 0:
        LAST_SUCCESSFUL_FETCH_TIMESTAMP = time.time()
        CONSECUTIVE_FETCH_FAILURES = 0
    else:
        CONSECUTIVE_FETCH_FAILURES += 1
        print(f"[Fetch Warning] Price fetch failed. Consecutive failures: {CONSECUTIVE_FETCH_FAILURES}")
                
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

BENCHMARK_CACHE = {}

def get_benchmark_dataframe(benchmark_symbol="^NSEI", period="1y", interval="1d"):
    """Fetches benchmark OHLCV data (e.g. NIFTY 50) and computes 200 MA and ATR Ratio."""
    global BENCHMARK_CACHE
    if benchmark_symbol in BENCHMARK_CACHE:
        return BENCHMARK_CACHE[benchmark_symbol]
        
    try:
        df = yf.download(benchmark_symbol, period=period, interval=interval, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        if not df.empty and "Close" in df.columns:
            # 200 DMA
            df["MA200"] = df["Close"].rolling(window=200, min_periods=1).mean()
            
            # ATR (14-period)
            high_low = df["High"] - df["Low"]
            high_close = (df["High"] - df["Close"].shift(1)).abs()
            low_close = (df["Low"] - df["Close"].shift(1)).abs()
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df["ATR"] = true_range.rolling(window=14, min_periods=1).mean()
            df["ATR_Ratio"] = df["ATR"] / df["Close"]
            
            BENCHMARK_CACHE[benchmark_symbol] = df
            return df
    except Exception as e:
        print(f"[Benchmark Fetch Error] {e}")
        
    return None

def get_market_regime(benchmark_df=None, watchlist_dfs=None):
    """
    Tri-factor majority-vote market regime classifier.
    
    Signals:
      1. Trend: benchmark_close > benchmark_ma200
      2. Volatility: benchmark_atr_ratio < rolling_mean(benchmark_atr_ratio, 60)
      3. Breadth: Percentage of watchlist stocks trading above individual 200 DMAs > 0.50
      
    Returns:
      str: 'RISK_ON' if at least 2 of 3 signals are True; otherwise 'RISK_OFF'.
    """
    # Signal 1 (Trend) & Signal 2 (Volatility) defaults
    signal_1 = True
    signal_2 = True
    
    if benchmark_df is None or (isinstance(benchmark_df, pd.DataFrame) and benchmark_df.empty):
        benchmark_df = get_benchmark_dataframe()
        
    if benchmark_df is not None and isinstance(benchmark_df, pd.DataFrame) and not benchmark_df.empty and "Close" in benchmark_df.columns:
        # Signal 1: Trend
        b_close = float(benchmark_df["Close"].iloc[-1])
        if "MA200" in benchmark_df.columns and not pd.isna(benchmark_df["MA200"].iloc[-1]):
            b_ma200 = float(benchmark_df["MA200"].iloc[-1])
        else:
            b_ma200 = float(benchmark_df["Close"].rolling(window=200, min_periods=1).mean().iloc[-1])
        signal_1 = bool(b_close > b_ma200)

        # Signal 2: Volatility
        if "ATR_Ratio" in benchmark_df.columns:
            atr_ratio_series = benchmark_df["ATR_Ratio"].dropna()
        elif "ATR" in benchmark_df.columns:
            atr_ratio_series = (benchmark_df["ATR"] / benchmark_df["Close"]).dropna()
        else:
            high_low = benchmark_df["High"] - benchmark_df["Low"]
            high_close = (benchmark_df["High"] - benchmark_df["Close"].shift(1)).abs()
            low_close = (benchmark_df["Low"] - benchmark_df["Close"].shift(1)).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(window=14, min_periods=1).mean()
            atr_ratio_series = (atr / benchmark_df["Close"]).dropna()

        if not atr_ratio_series.empty:
            curr_atr_ratio = float(atr_ratio_series.iloc[-1])
            rolling_window = min(60, len(atr_ratio_series))
            rolling_atr_mean = float(atr_ratio_series.rolling(window=rolling_window, min_periods=1).mean().iloc[-1])
            signal_2 = bool(curr_atr_ratio < rolling_atr_mean)

    # Signal 3 (Breadth): % of watchlist stocks above their individual 200 DMAs > 0.50
    signal_3 = True
    if watchlist_dfs is not None:
        above_count = 0
        total_valid = 0
        
        dfs_iter = watchlist_dfs.values() if isinstance(watchlist_dfs, dict) else watchlist_dfs
        for item in dfs_iter:
            if isinstance(item, pd.DataFrame) and not item.empty and "Close" in item.columns:
                c_price = float(item["Close"].iloc[-1])
                if "MA200" in item.columns and not pd.isna(item["MA200"].iloc[-1]):
                    c_ma200 = float(item["MA200"].iloc[-1])
                else:
                    c_ma200 = float(item["Close"].rolling(window=200, min_periods=1).mean().iloc[-1])
                if c_price > c_ma200:
                    above_count += 1
                total_valid += 1

        if total_valid > 0:
            breadth_ratio = above_count / total_valid
            signal_3 = bool(breadth_ratio > 0.50)
            print(f"  [Regime Breadth] {above_count}/{total_valid} ({breadth_ratio:.1%}) stocks above 200 DMA.")

    # Majority vote
    votes = sum([int(signal_1), int(signal_2), int(signal_3)])
    regime = "RISK_ON" if votes >= 2 else "RISK_OFF"
    print(f"  [Market Regime Classifier] Signals -> Trend: {signal_1}, Volatility: {signal_2}, Breadth: {signal_3} | Votes: {votes}/3 => Regime: {regime}")
    return regime

def calculate_dynamic_threshold(current_price, dma_200, base_threshold, regime="RISK_ON"):
    """Calculates dynamic confidence threshold based on the 200 DMA drop and market regime."""
    if dma_200 is None or pd.isna(dma_200) or dma_200 <= 0:
        dynamic_threshold = base_threshold
    elif current_price >= dma_200:
        dynamic_threshold = base_threshold
    else:
        drop_pct = (dma_200 - current_price) / dma_200
        dynamic_threshold = base_threshold + (drop_pct * 1.5)
        print(f"  [MACRO FILTER] Stock below 200 DMA. Base: {base_threshold:.2f} | 200 DMA Adjusted: {dynamic_threshold:.2f}")

    # When 'RISK_OFF', apply a 1.25x scaling multiplier to the dynamic entry confidence threshold
    if regime == "RISK_OFF":
        dynamic_threshold = dynamic_threshold * 1.25
        print(f"  [REGIME FILTER: RISK_OFF] Applied 1.25x scaling multiplier -> Dynamic Threshold: {dynamic_threshold:.2f}")

    dynamic_threshold = min(dynamic_threshold, 0.85)
    return dynamic_threshold

def run_live_paper_trading(strategy=None, profile_id="macro"):
    global LIVE_DATA_CACHE
    tickers = WATCHLIST
    
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

    # Load daily Gemini sentiment bias scores
    daily_gemini_bias = {}
    bias_file = os.path.abspath(os.path.join(base_dir, "..", "data", "daily_gemini_bias.json"))
    if os.path.exists(bias_file):
        try:
            with open(bias_file, "r") as bf:
                daily_gemini_bias = json.load(bf)
            print(f"Loaded daily Gemini sentiment bias scores from {bias_file}")
        except Exception as e:
            print(f"Error loading daily Gemini sentiment bias: {e}")

    if profile_id == "ultra":
        target_buy_threshold = 0.68
        risk = RiskAgent(stop_loss_pct=0.03, take_profit_pct=0.04, max_allocation_pct=0.10, trailing_stop_loss_pct=0.03)
        max_rsi_allowed = 58.0
    else:
        target_buy_threshold = getattr(strategy, 'buy_threshold', 0.57) if strategy else 0.57
        risk = RiskAgent(stop_loss_pct=0.05, take_profit_pct=0.05, max_allocation_pct=0.10, trailing_stop_loss_pct=0.05)
        max_rsi_allowed = 65.0

    # Initialize PortfolioRiskAgent (gating sector concentration & correlation exposure)
    portfolio_risk = PortfolioRiskAgent(max_sector_exposure=0.35, max_correlated_exposure=0.05)

    # Preload / Cache 60-day correlation matrix
    global CORRELATION_MATRIX_CACHE
    if CORRELATION_MATRIX_CACHE is None or (isinstance(CORRELATION_MATRIX_CACHE, pd.DataFrame) and CORRELATION_MATRIX_CACHE.empty):
        try:
            CORRELATION_MATRIX_CACHE = compute_60d_correlation_matrix(tickers, data_dir=data_dir)
            if not CORRELATION_MATRIX_CACHE.empty:
                print(f"  [Correlation Matrix] Preloaded 60-day correlation matrix ({len(CORRELATION_MATRIX_CACHE)} tickers).")
        except Exception as err:
            print(f"  [Correlation Matrix Error] {err}")
            CORRELATION_MATRIX_CACHE = pd.DataFrame()

    # 2. Fallback/Safety model training
    if strategy is None:
        print("Initializing Strategy Agent (ML Brain) in fallback mode...")
        strategy = StrategyAgent(tickers, data_dir=data_dir)
        strategy.train_model()

    # 3. Fetch latest quotes in one fast batch request for all tickers
    current_prices = fetch_batch_live_prices(tickers)

    if not current_prices:
        print("Warning: No quotes available. Skipping this tick.")
        return

    # Unconditional exit evaluation: executed on every live scan iteration
    # independent of available liquidity, new buy evaluations, or circuit breakers
    execution.check_exits(current_prices)

    # Dead Man's Switch Check: Stale data or consecutive fetch failures
    is_stale_data = False
    now_ts = time.time()
    if LAST_SUCCESSFUL_FETCH_TIMESTAMP is not None:
        time_since_fetch = now_ts - LAST_SUCCESSFUL_FETCH_TIMESTAMP
        if time_since_fetch > 300 or CONSECUTIVE_FETCH_FAILURES >= 5:
            is_stale_data = True
            print(f"[FAILSAFE ACTIVATED: Stale Data] Consecutive fetch failures ({CONSECUTIVE_FETCH_FAILURES}) or staleness ({time_since_fetch:.1f}s) exceeded 300 seconds. Blocking order execution.")
    elif CONSECUTIVE_FETCH_FAILURES >= 5:
        is_stale_data = True
        print(f"[FAILSAFE ACTIVATED: Stale Data] Consecutive fetch failures ({CONSECUTIVE_FETCH_FAILURES}) exceeded threshold. Blocking order execution.")

    # Aggregate Daily Drawdown Circuit Breaker Tracking
    today_date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    current_portfolio_value = execution.get_total_portfolio_value(current_prices)
    
    if profile_id not in PORTFOLIO_DAY_START_TRACKER or PORTFOLIO_DAY_START_TRACKER[profile_id].get("date") != today_date_str:
        PORTFOLIO_DAY_START_TRACKER[profile_id] = {
            "date": today_date_str,
            "start_val": current_portfolio_value
        }
        print(f"  [Circuit Breaker Baseline] Recorded session_start_portfolio_value for {profile_id}: INR {current_portfolio_value:,.2f}")

    session_start_portfolio_value = PORTFOLIO_DAY_START_TRACKER[profile_id]["start_val"]
    session_drawdown = (current_portfolio_value - session_start_portfolio_value) / session_start_portfolio_value if session_start_portfolio_value > 0 else 0.0

    halt_new_entries_for_session = False
    if session_drawdown <= -0.05:
        halt_new_entries_for_session = True
        print(f"⚠️ [CIRCUIT BREAKER TRIGGERED] Portfolio down {session_drawdown:.2%}. Halting all new buy orders for remainder of the session.")

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

            # 6. ATR & 20-period Average Volume
            tr1 = df["High"] - df["Low"]
            tr2 = (df["High"] - df["Close"].shift(1)).abs()
            tr3 = (df["Low"] - df["Close"].shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df["ATR"] = tr.rolling(window=14).mean()
            df["ATR_Ratio"] = df["ATR"] / df["Close"].replace(0, 0.001)
            df["Volume_20SMA"] = df["Volume"].rolling(window=20).mean()

            # 7. Distance from MAs
            df["Dist_MA50"] = (df["Close"] - df["MA50"]) / df["MA50"].replace(0, 0.001)
            df["Dist_MA200"] = (df["Close"] - df["MA200"]) / df["MA200"].replace(0, 0.001)

            # 8. Momentum (Rate of Change)
            df["ROC_10"] = (df["Close"] - df["Close"].shift(10)) / df["Close"].shift(10).replace(0, 0.001)

            # 9. Floor Pivot Points
            prev_high = df["High"].shift(1)
            prev_low = df["Low"].shift(1)
            prev_close = df["Close"].shift(1)

            p_level = (prev_high + prev_low + prev_close) / 3.0
            r1_level = (2.0 * p_level) - prev_low
            r2_level = p_level + (prev_high - prev_low)
            s1_level = (2.0 * p_level) - prev_high
            s2_level = p_level - (prev_high - prev_low)

            df["Dist_P"] = (df["Close"] - p_level) / p_level.replace(0, 0.001)
            df["Dist_R1"] = (df["Close"] - r1_level) / r1_level.replace(0, 0.001)
            df["Dist_R2"] = (df["Close"] - r2_level) / r2_level.replace(0, 0.001)
            df["Dist_S1"] = (df["Close"] - s1_level) / s1_level.replace(0, 0.001)
            df["Dist_S2"] = (df["Close"] - s2_level) / s2_level.replace(0, 0.001)
            
            df[["Dist_P", "Dist_R1", "Dist_R2", "Dist_S1", "Dist_S2"]] = df[["Dist_P", "Dist_R1", "Dist_R2", "Dist_S1", "Dist_S2"]].ffill().bfill()

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

            # Fetch global sentiment using cached GDELT and FinBERT scores (15-min cache lifetime)
            import time
            global_sentiment = 0.0
            now = time.time()
            if ticker in SENTIMENT_CACHE and (now - SENTIMENT_CACHE[ticker][0]) < 900:
                global_sentiment = SENTIMENT_CACHE[ticker][1]
                print(f"  [HYBRID SENTIMENT] {ticker} (CACHED) | Blended Score: {global_sentiment:+.2f}")
            else:
                try:
                    company_name = COMPANY_NAME_MAP.get(ticker, ticker.split(".")[0])
                    headlines = news_ingestor.fetch_recent_news(company_name, days_back=1)
                    
                    realtime_score = 0.0
                    if headlines:
                        realtime_score = sentiment_analyzer.score_headlines(headlines)
                    
                    daily_bias = daily_gemini_bias.get(ticker, 0.0)
                    global_sentiment = 0.7 * daily_bias + 0.3 * realtime_score
                    SENTIMENT_CACHE[ticker] = (now, global_sentiment)
                    print(f"  [HYBRID SENTIMENT] {ticker} | Daily Bias (Gemini): {daily_bias:+.2f} | Real-time (FinBERT): {realtime_score:+.2f} | Blended Score: {global_sentiment:+.2f}")
                except Exception as e:
                    print(f"  [Sentiment Error] Failed to calculate GDELT/FinBERT sentiment for {ticker}: {e}")
                    if ticker in SENTIMENT_CACHE:
                        global_sentiment = SENTIMENT_CACHE[ticker][1]
                    else:
                        global_sentiment = 0.0
                
            tech_row["Global_Sentiment_Score"] = global_sentiment

            # Format Date column back to string format for StrategyAgent
            tech_row["Date"] = pd.to_datetime(tech_row["Date"]).dt.strftime('%Y-%m-%d %H:%M:%S')

            today_features[ticker] = tech_row
            print(f"Current price for {ticker}: INR {live_price:.2f}")

        except Exception as e:
            import traceback
            print(f"Error processing live data for {ticker}: {e}")
            print(traceback.format_exc())

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
                t_row = today_features.get(ticker)
                atr_val = float(t_row["ATR"].iloc[-1]) if (t_row is not None and "ATR" in t_row.columns and not pd.isna(t_row["ATR"].iloc[-1])) else (0.015 * current_price)
                vol_val = float(t_row["Volume_20SMA"].iloc[-1]) if (t_row is not None and "Volume_20SMA" in t_row.columns and not pd.isna(t_row["Volume_20SMA"].iloc[-1])) else 1000000.0
                execution.sell_asset(ticker, today_str, current_price, reason=reason, atr_14=atr_val, avg_volume_20=vol_val)

    # 6. Strategy & Decision Execution: Process signals
    print("\n[Strategy Check] Evaluating model signals...")
    market_regime = get_market_regime(watchlist_dfs=today_features)

    for ticker in tickers:
        if ticker not in today_features or ticker not in current_prices:
            continue
            
        features_df = today_features[ticker]
        current_price = current_prices[ticker]

        try:
            dma_200 = float(features_df["MA200"].iloc[-1]) if "MA200" in features_df.columns else None
            required_threshold = calculate_dynamic_threshold(current_price, dma_200, target_buy_threshold, regime=market_regime)

            signal, proba = strategy.predict_signal(features_df)
            confidence = float(proba[0])
            signal_val = 1 if confidence >= required_threshold else 0
            print(f"{ticker} | Signal: {signal_val} | Confidence: {confidence:.2%} (Required: {required_threshold:.2%})")

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

            print(f"  [DEBUG BUY] ticker={ticker} | signal_val={signal_val} | confidence={confidence:.4f} | threshold={required_threshold:.4f} | can_buy={can_buy} | is_averaging_down={is_averaging_down}")
            
            if signal_val == 1 and confidence >= required_threshold and can_buy:
                if is_stale_data:
                    print(f"  [Dead Man's Switch Block] BUY signal for {ticker} blocked: [FAILSAFE ACTIVATED: Stale Data]")
                elif halt_new_entries_for_session:
                    print(f"  [Circuit Breaker Block] [CIRCUIT BREAKER TRIGGERED] Portfolio down {session_drawdown:.2%}. Halting all new buy orders for remainder of the session. Bypassing buy signal for {ticker}.")
                else:
                    # Run Live Sentiment override check
                    sentiment_score = fetch_sentiment_score(ticker)
                    print(f"  [Sentiment Agent] Ticker: {ticker} | Sentiment: {sentiment_score:+.2f}")
                    if sentiment_score < -0.2:
                        print(f"  [Sentiment Block] Blocked BUY signal for {ticker} due to bearish news sentiment ({sentiment_score:+.2f})")
                    else:
                        is_cooldown = execution.is_in_cooldown(ticker, today_str, cooldown_days=2)
                        print(f"  [DEBUG BUY] cooldown={is_cooldown}")
                        if not is_cooldown:
                            total_port_val = execution.get_portfolio_value(current_prices)
                            
                            b = risk.take_profit_pct / max(risk.trailing_stop_loss_pct, 0.001)
                            f = confidence - (1.0 - confidence) / b
                            f_kelly = max(0.02, min(0.5 * f, 0.20))
                            proposed_trade_val = total_port_val * f_kelly
                            trade_sector = TICKER_SECTORS.get(ticker, "Other")

                            # Gate trade allocation with PortfolioRiskAgent BEFORE calculate_kelly_allocation
                            is_port_safe, port_reject_reason = portfolio_risk.check_portfolio_risk(
                                open_positions=execution.active_positions,
                                new_trade_ticker=ticker,
                                new_trade_sector=trade_sector,
                                new_trade_value=proposed_trade_val,
                                total_portfolio_value=total_port_val,
                                correlation_matrix=CORRELATION_MATRIX_CACHE,
                                current_prices=current_prices
                            )

                            if not is_port_safe:
                                print(f"  [PortfolioRiskAgent Block] Trade rejected for {ticker}: {port_reject_reason}")
                            else:
                                # Active liquidity recovery check for cash-exhausted states
                                if execution.current_cash < 5000 or (total_port_val > 0 and execution.current_cash < 0.05 * total_port_val):
                                    risk.prune_worst_position(
                                        open_positions=execution.active_positions,
                                        incoming_candidate_confidence=confidence,
                                        available_cash=execution.current_cash,
                                        total_portfolio_value=total_port_val,
                                        current_prices=current_prices,
                                        execution_agent=execution,
                                        portfolio=execution.portfolio,
                                        date=today_str
                                    )

                                allocation = risk.calculate_kelly_allocation(
                                    confidence,
                                    tp_pct=risk.take_profit_pct,
                                    sl_pct=risk.trailing_stop_loss_pct,
                                    total_portfolio_value=total_port_val,
                                    available_cash=execution.current_cash
                                )
                                print(f"  [KELLY SIZING] Confidence: {confidence:.1%} | Kelly Fraction: {f_kelly:.1%} | Target Allocation: INR {allocation:,.2f}")
                                if allocation > 0:
                                    t_row = features_df
                                    atr_val = float(t_row["ATR"].iloc[-1]) if ("ATR" in t_row.columns and not pd.isna(t_row["ATR"].iloc[-1])) else (0.015 * current_price)
                                    vol_val = float(t_row["Volume_20SMA"].iloc[-1]) if ("Volume_20SMA" in t_row.columns and not pd.isna(t_row["Volume_20SMA"].iloc[-1])) else 1000000.0
                                    execution.buy_asset(
                                        ticker, 
                                        today_str, 
                                        current_price, 
                                        allocation, 
                                        atr_14=atr_val, 
                                        avg_volume_20=vol_val,
                                        kelly_fraction=f_kelly,
                                        confidence_score=confidence
                                    )
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
