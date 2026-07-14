import os 
import pandas as pd
import yfinance as yf
import numpy as np

class IngestionAgent:
    """Agent responsible for fetching and preparing price and fundamental data."""
    def __init__(self, output_dir="data"):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def download_historical_data(self, tickers, start_date, end_date):
        """Downloads daily historical data and saves to raw CSV files."""
        for ticker in tickers:
            print(f"Downloading data for {ticker}...")
            try:
                df = yf.download(ticker, start=start_date, end=end_date)

                if df.empty:
                    print(f"No data found for {ticker}")
                    continue 

                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                df = df.reset_index()

                raw_path = os.path.join(self.output_dir, f"{ticker}_raw.csv")
                df.to_csv(raw_path, index=False)
                print(f"Saved raw data to {raw_path}")

            except Exception as e:
                print(f"Failed to download {ticker}: {e}")

    def compute_technical_features(self, ticker):
        """Calculates indicators like MA, RSI, Volume Ratio, and Target labels."""
        raw_path = os.path.join(self.output_dir, f"{ticker}_raw.csv")
        df = pd.read_csv(raw_path)

        # Ensure data is sorted chronologically
        df = df.sort_values("Date").reset_index(drop=True)

        print(f"Engineering technical features for {ticker}...")

        # 1. Moving Averages (50 DMA and 200 DMA)
        df["MA50"] = df["Close"].rolling(window=50).mean()
        df["MA200"] = df["Close"].rolling(window=200).mean()

        # 2. Price Momentum (Relative Strength Index - RSI)
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()

        # Prevent division by zero
        rs = avg_gain / avg_loss.replace(0, 0.001)
        df["RSI14"] = 100 - (100 / (1 + rs))

        # 3. Volume Feature (Ratio of current volume to 20-day average volume)
        df["Volume_Ratio"] = df["Volume"] / df["Volume"].rolling(window=20).mean()

        # 4. MACD (Moving Average Convergence Divergence)
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
        df["BB_Upper_Dist"] = (df["Close"] - upper_bb) / upper_bb
        df["BB_Lower_Dist"] = (df["Close"] - lower_bb) / lower_bb
        df["BB_Width"] = (upper_bb - lower_bb) / sma20

        # 6. ATR (Average True Range)
        tr1 = df["High"] - df["Low"]
        tr2 = (df["High"] - df["Close"].shift(1)).abs()
        tr3 = (df["Low"] - df["Close"].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["ATR"] = tr.rolling(window=14).mean()
        df["ATR_Ratio"] = df["ATR"] / df["Close"]

        # 7. Distance from MAs
        df["Dist_MA50"] = (df["Close"] - df["MA50"]) / df["MA50"]
        df["Dist_MA200"] = (df["Close"] - df["MA200"]) / df["MA200"]

        # 8. Momentum (Rate of Change)
        df["ROC_10"] = (df["Close"] - df["Close"].shift(10)) / df["Close"].shift(10).replace(0, 0.001)

        # 9. Target Variable: 1 if price goes up > 5% in the next 30 days, else 0
        future_return = (df["Close"].shift(-30) - df["Close"]) / df["Close"]
        df["Target"] = (future_return >= 0.05).astype(int)

        # Drop rows where indicators or target couldn't be calculated (edges of data)
        df = df.dropna(subset=["MA200", "RSI14", "ATR", "ROC_10"])

        # Save feature-engineered data
        feature_path = os.path.join(self.output_dir, f"{ticker}_features.csv")
        df.to_csv(feature_path, index=False)
        print(f"Saved engineered features to {feature_path}\n")
        return df

    def fetch_historical_fundamentals(self, ticker):
        """Fetches quarterly and annual balance sheets/financials to compute margins and ratios."""
        t = yf.Ticker(ticker)
        fundamental_data = []

        def extract_from_df(df):
            if df is None or df.empty:
                return
            df.index = df.index.astype(str)
            net_income_keys = ['Net Income', 'Net Income Common Stockholders']
            revenue_keys = ['Total Revenue', 'Operating Revenue']
            debt_keys = ['Total Debt', 'Long Term Debt']
            equity_keys = ['Stockholders Equity', 'Common Stock Equity', 'Total Equity Gross Minority Interest']

            net_income_row = next((df.loc[k] for k in net_income_keys if k in df.index), None)
            revenue_row = next((df.loc[k] for k in revenue_keys if k in df.index), None)
            debt_row = next((df.loc[k] for k in debt_keys if k in df.index), None)
            equity_row = next((df.loc[k] for k in equity_keys if k in df.index), None)

            for col in df.columns:
                date_str = str(col).split(' ')[0]
                net_income = net_income_row[col] if net_income_row is not None else np.nan
                revenue = revenue_row[col] if revenue_row is not None else np.nan
                debt = debt_row[col] if debt_row is not None else np.nan
                equity = equity_row[col] if equity_row is not None else np.nan
                fundamental_data.append({
                    'Date': date_str,
                    'Net_Income': net_income,
                    'Total_Revenue': revenue,
                    'Total_Debt': debt,
                    'Stockholders_Equity': equity
                })

        extract_from_df(t.quarterly_financials)
        extract_from_df(t.quarterly_balance_sheet)
        extract_from_df(t.financials)
        extract_from_df(t.balance_sheet)
        
        if not fundamental_data:
            return pd.DataFrame(columns=['Date', 'Net_Profit_Margin', 'Debt_to_Equity'])
            
        fund_df = pd.DataFrame(fundamental_data)
        fund_df = fund_df.groupby('Date').first().reset_index()
        fund_df['Net_Profit_Margin'] = fund_df['Net_Income'] / fund_df['Total_Revenue']
        fund_df['Debt_to_Equity'] = fund_df['Total_Debt'] / fund_df['Stockholders_Equity']
        fund_df = fund_df[['Date', 'Net_Profit_Margin', 'Debt_to_Equity']]
        fund_df = fund_df.dropna(how='all', subset=['Net_Profit_Margin', 'Debt_to_Equity'])
        return fund_df

    def merge_price_and_fundamental_data(self, ticker):
        """Aligns fundamentals to daily price data cleanly without look-ahead bias."""
        tech_path = os.path.join(self.output_dir, f"{ticker}_features.csv")
        if not os.path.exists(tech_path):
            print(f"Technical features file not found for {ticker}")
            return
            
        tech_df = pd.read_csv(tech_path)
        fund_df = self.fetch_historical_fundamentals(ticker)
        
        if fund_df.empty:
            tech_df['Net_Profit_Margin'] = 0.0
            tech_df['Debt_to_Equity'] = 0.0
        else:
            tech_df['Date'] = pd.to_datetime(tech_df['Date'])
            fund_df['Date'] = pd.to_datetime(fund_df['Date'])
            
            tech_df = tech_df.sort_values('Date')
            fund_df = fund_df.sort_values('Date')
            
            # Merge on closest prior date
            merged_df = pd.merge_asof(tech_df, fund_df, on='Date', direction='backward')
            
            merged_df['Net_Profit_Margin'] = merged_df['Net_Profit_Margin'].ffill().bfill().fillna(0.0)
            merged_df['Debt_to_Equity'] = merged_df['Debt_to_Equity'].ffill().bfill().fillna(0.0)
            
            merged_df['Date'] = merged_df['Date'].dt.strftime('%Y-%m-%d')
            tech_df = merged_df
            
        hybrid_path = os.path.join(self.output_dir, f"{ticker}_hybrid_features.csv")
        tech_df.to_csv(hybrid_path, index=False)
        print(f"Saved hybrid features to {hybrid_path}")


if __name__ == "__main__":
    target_tickers = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"]
    start = "2021-01-01"
    end = "2026-06-25"

    agent = IngestionAgent()

    # 1. Get raw price data
    agent.download_historical_data(target_tickers, start_date=start, end_date=end)

    # 2. Calculate technicals
    for ticker in target_tickers:
        agent.compute_technical_features(ticker)
        
    # 3. Fetch fundamentals and merge them
    for ticker in target_tickers:
        agent.merge_price_and_fundamental_data(ticker)