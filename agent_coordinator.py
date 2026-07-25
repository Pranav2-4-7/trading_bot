import os
import sys
import gc
import pandas as pd
import yfinance as yf

# Add current folder to path to allow importing adjacent modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_scraper import IngestionAgent
from model import StrategyAgent
from paper_broker import ExecutionAgent, RiskAgent


def load_all_hybrid_data(data_dir="data", tickers=None):
    """
    Loads and combines all hybrid feature CSV files for specified tickers into a single DataFrame.
    """
    if tickers is None:
        tickers = [
            "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", 
            "ICICIBANK.NS", "SBIN.NS", "ITC.NS", "LT.NS", 
            "BHARTIARTL.NS", "WIPRO.NS"
        ]
    
    combined_df = pd.DataFrame()
    for ticker in tickers:
        file_path = os.path.join(data_dir, f"{ticker}_hybrid_features.csv")
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            df["Ticker"] = ticker
            combined_df = pd.concat([combined_df, df], axis=0)
        else:
            print(f"Warning: Hybrid feature file for {ticker} not found at {file_path}")
            
    if combined_df.empty:
        raise ValueError("No feature data loaded. Please run data_scraper.py first.")
        
    return combined_df


def walk_forward_optimization(data, train_months=24, test_months=1):
    """
    Executes a Walk-Forward Optimization (WFO) rolling window loop over historical data.
    
    Args:
        data (pd.DataFrame): Combined historical dataset containing a 'Date' column.
        train_months (int): Rolling training window duration in months (Default: 24).
        test_months (int): Out-of-sample testing window duration in months (Default: 1).
        
    Returns:
        list: Summary log of WFO iterations and window boundaries.
    """
    # 1. Ensure Date column is datetime format and sort chronologically
    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    min_date = df["Date"].min()
    max_date = df["Date"].max()

    current_train_start = min_date
    wfo_summary = []
    iteration = 1

    train_df = None
    test_df = None

    print("\n==================================================")
    print("STARTING WALK-FORWARD OPTIMIZATION (WFO) LOOP")
    print(f"Data Range: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}")
    print(f"Config: Train Window = {train_months} Months | Test Window = {test_months} Month(s)")
    print("==================================================\n")

    # 2. Rolling Walk-Forward Optimization Loop
    while True:
        train_end = current_train_start + pd.DateOffset(months=train_months)
        test_end = train_end + pd.DateOffset(months=test_months)

        # Stop when training window exceeds available data boundary
        if train_end >= max_date:
            print(f"\n[WFO Complete] Final training window reached dataset boundary ({train_end.strftime('%Y-%m')} >= {max_date.strftime('%Y-%m')}).")
            break

        # Explicitly release memory from previous loop iteration (16GB RAM Protection)
        if train_df is not None:
            del train_df
        if test_df is not None:
            del test_df
        gc.collect()

        # Slice current 24-month training window and 1-month testing window
        train_df = df[(df["Date"] >= current_train_start) & (df["Date"] < train_end)].copy()
        test_df = df[(df["Date"] >= train_end) & (df["Date"] < test_end)].copy()

        if train_df.empty or test_df.empty:
            print(f"[WFO Iteration {iteration:02d}] Empty window encountered. Skipping.")
        else:
            print(f"[WFO Iteration {iteration:02d}]")
            print(f"  Train Window: {current_train_start.strftime('%Y-%m-%d')} -> {train_end.strftime('%Y-%m-%d')} ({len(train_df):>6} rows)")
            print(f"  Test Window:  {train_end.strftime('%Y-%m-%d')} -> {test_end.strftime('%Y-%m-%d')} ({len(test_df):>6} rows)")

            wfo_summary.append({
                "iteration": iteration,
                "train_start": current_train_start.strftime('%Y-%m-%d'),
                "train_end": train_end.strftime('%Y-%m-%d'),
                "test_start": train_end.strftime('%Y-%m-%d'),
                "test_end": test_end.strftime('%Y-%m-%d'),
                "train_rows": len(train_df),
                "test_rows": len(test_df)
            })

        # Shift training window start forward by test_months
        current_train_start = current_train_start + pd.DateOffset(months=test_months)
        iteration += 1

    # Final cleanup of iteration references
    if train_df is not None:
        del train_df
    if test_df is not None:
        del test_df
    gc.collect()

    print(f"\n[WFO Summary] Completed {len(wfo_summary)} rolling Walk-Forward iterations.")
    return wfo_summary


def run_agent_simulation():
    """Coordinates standard backtest run."""
    print("Loading combined dataset for WFO verification...")
    combined_data = load_all_hybrid_data()
    walk_forward_optimization(combined_data, train_months=24, test_months=1)


if __name__ == "__main__":
    run_agent_simulation()
