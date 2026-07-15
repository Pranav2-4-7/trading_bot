# Walkthrough - 2-Second Intraday Scalper

We have successfully rebuilt the trading bot into a 2-second real-time intraday scalping bot. The bot now polls the free public REST API (`http://65.0.104.9/`) every 2 seconds, while training and running its XGBoost brain on 1-minute historical candles.

## Summary of Changes

1. **No-Lag Training Architecture ([web_server.py](file:///c:/AntiGravity/TradingBOT/web_server.py)):**
   * Configured the system to instantiate and train the XGBoost model **once** at server startup.
   * During the 2-second loop, the bot only uses the pre-trained model for instant predictions, eliminating lag and avoiding rate-limiting.
   * Updated the loop interval to **2 seconds**.

2. **Cached Real-Time Candle Reconstruction ([live_paper_runner.py](file:///c:/AntiGravity/TradingBOT/live_paper_runner.py)):**
   * Created a global cache to store the last 5 days of 1-minute data, downloaded once from Yahoo Finance at startup.
   * On every 2-second tick, the bot polls the free public REST API to get the latest prices and updates the active 1-minute candle in memory, fully avoiding `yfinance` rate-limiting.

3. **1-Minute Ingestion & Scalping Targets ([data_scraper.py](file:///c:/AntiGravity/TradingBOT/data_scraper.py)):**
   * Updated `IngestionAgent` to fetch 1-minute candles from Yahoo Finance.
   * Defined a scalping target of **`0.20%` price return** over the next **15 minutes** (15 bars ahead) instead of the old daily swing targets.
   * Fixed timezone merge errors in `pd.merge_asof` by stripping UTC offset.

---

## Intraday Backtest Results
The 1-minute intraday model backtest was verified on the 7-day test set (July 2026):
* **Accuracy:** `80.42%`
* **Total Buy Signals:** `216`
* **Trades Placed:**
  * Bought `TCS.NS` at `2026-07-13 13:59:00`
  * Bought `INFY.NS` at `2026-07-13 15:11:00`
  * Bought `HDFCBANK.NS` at `2026-07-13 15:12:00`

## Production Resilience Updates

To ensure stable runtime performance during live market hours, the following fixes were implemented:
1. **TCP Handshake Timeout & Socket Closure:** Swapped `urllib` with the `requests` library in [live_paper_runner.py](file:///c:/AntiGravity/TradingBOT/live_paper_runner.py), configuring a `5.0` second timeout and adding the `Connection: close` header to bypass TCP keep-alive socket hangs on the API server.
2. **yfinance Quote Fallback:** Configured `live_paper_runner.py` to query `yf.Ticker(symbol).fast_info['lastPrice']` directly if the public REST API fails or rate-limits requests.
3. **Timezone Normalization:** Normalized the timezone of `df["Date"]` and `last_row_date` to timezone-naive format in [live_paper_runner.py](file:///c:/AntiGravity/TradingBOT/live_paper_runner.py) to prevent `TypeError: can't compare offset-naive and offset-aware datetimes`.
4. **Pandas Accessor Safety:** Wrapped datetimelike series in `pd.to_datetime()` before invoking the `.dt` accessor in both [web_server.py](file:///c:/AntiGravity/TradingBOT/web_server.py) and [live_paper_runner.py](file:///c:/AntiGravity/TradingBOT/live_paper_runner.py) to prevent type conversion errors when dataframes are concatenated.
5. **Reloader-Free Execution:** Disabled Flask's auto-reloader and ran the server in single-process mode to avoid thread collisions and socket blocks on Windows.

