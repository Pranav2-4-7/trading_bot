import os
import sys
import gc
import pandas as pd
import yfinance as yf
import mlflow
import mlflow.xgboost

# Add current folder to path to allow importing adjacent modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_scraper import IngestionAgent, WATCHLIST
from model import StrategyAgent, UltraStrategyAgent
from paper_broker import ExecutionAgent, RiskAgent


def load_all_hybrid_data(data_dir="data", tickers=None):
    """
    Loads and combines all hybrid feature CSV files for specified tickers into a single DataFrame.
    """
    if tickers is None:
        tickers = WATCHLIST
    
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


def walk_forward_optimization(data, train_months=24, test_months=1, tickers=None):
    """
    Executes a Walk-Forward Optimization (WFO) rolling window loop over historical data
    integrated with StrategyAgent (0.57 threshold) and UltraStrategyAgent (0.68 threshold).
    
    Args:
        data (pd.DataFrame): Combined historical dataset containing a 'Date' column.
        train_months (int): Rolling training window duration in months (Default: 24).
        test_months (int): Out-of-sample testing window duration in months (Default: 1).
        tickers (list): List of ticker symbols (Optional).
        
    Returns:
        list: Summary log of WFO iterations, metrics, and window boundaries.
    """
    if tickers is None:
        tickers = [
            "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", 
            "ICICIBANK.NS", "SBIN.NS", "ITC.NS", "LT.NS", 
            "BHARTIARTL.NS", "WIPRO.NS"
        ]

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

    # Set MLflow experiment name before entering WFO loop
    try:
        mlflow.set_experiment("Nifty50_Walk_Forward_Optimization")
    except Exception as exp_err:
        print(f"[MLflow Warning] Could not set experiment: {exp_err}")

    print("\n==================================================")
    print("STARTING WALK-FORWARD OPTIMIZATION (WFO) LOOP WITH ML AGENTS")
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

            fold_run_name = f"Fold_{train_end.date()}"
            with mlflow.start_run(run_name=fold_run_name, nested=True):
                # Log slice parameters to MLflow
                mlflow.log_params({
                    "train_start": current_train_start.strftime('%Y-%m-%d'),
                    "train_end": train_end.strftime('%Y-%m-%d'),
                    "test_start": train_end.strftime('%Y-%m-%d'),
                    "test_end": test_end.strftime('%Y-%m-%d'),
                    "train_rows": len(train_df),
                    "test_rows": len(test_df),
                    "iteration": iteration
                })

                # Instantiate StrategyAgent and UltraStrategyAgent for this slice
                strategy_agent = StrategyAgent(tickers=tickers, data_dir="data")
                ultra_agent = UltraStrategyAgent(tickers=tickers, data_dir="data")

                # Train both models on the rolling 24-month train_df
                strategy_agent.train_on_slice(train_df)
                ultra_agent.train_on_slice(train_df)

                # Evaluate predictions on the unseen 1-month test_df
                strat_metrics = strategy_agent.evaluate_on_slice(test_df, target_col="Target")
                ultra_metrics = ultra_agent.evaluate_on_slice(test_df, target_col="Target_Ultra")

                # Log metrics to MLflow for this fold
                mlflow.log_metrics({
                    "standard_test_f1": float(strat_metrics['f1_score']),
                    "standard_test_acc": float(strat_metrics['accuracy']),
                    "standard_test_prec": float(strat_metrics['precision']),
                    "standard_buy_signals": float(strat_metrics['buy_signals']),
                    "ultra_test_f1": float(ultra_metrics['f1_score']),
                    "ultra_test_acc": float(ultra_metrics['accuracy']),
                    "ultra_test_prec": float(ultra_metrics['precision']),
                    "ultra_buy_signals": float(ultra_metrics['buy_signals'])
                })

                # Log metrics to console for this specific rolling window
                print(f"  |- Standard Brain (0.57 Threshold) | Acc: {strat_metrics['accuracy']:.2%} | F1: {strat_metrics['f1_score']:.2%} | Prec: {strat_metrics['precision']:.2%} | Buy Signals: {strat_metrics['buy_signals']}")
                print(f"  |- Ultra Brain    (0.68 Threshold) | Acc: {ultra_metrics['accuracy']:.2%} | F1: {ultra_metrics['f1_score']:.2%} | Prec: {ultra_metrics['precision']:.2%} | Buy Signals: {ultra_metrics['buy_signals']}")

                # Model Registry Promotion Gating (F1 > 0.60)
                if strat_metrics['f1_score'] > 0.60:
                    print(f"  |- [Model Registry] Standard Brain F1 ({strat_metrics['f1_score']:.2%}) > 60%! Registering model...")
                    try:
                        mlflow.xgboost.log_model(
                            strategy_agent.model,
                            artifact_path="standard_model",
                            registered_model_name="TradingBOT_XGBoost_Production"
                        )
                    except Exception as reg_err:
                        print(f"  |- [Model Registry Warning] {reg_err}")

                if ultra_metrics['f1_score'] > 0.60:
                    print(f"  |- [Model Registry] Ultra Brain F1 ({ultra_metrics['f1_score']:.2%}) > 60%! Registering model...")
                    try:
                        mlflow.xgboost.log_model(
                            ultra_agent.model,
                            artifact_path="ultra_model",
                            registered_model_name="TradingBOT_XGBoost_Production"
                        )
                    except Exception as reg_err:
                        print(f"  |- [Model Registry Warning] {reg_err}")

            wfo_summary.append({
                "iteration": iteration,
                "train_start": current_train_start.strftime('%Y-%m-%d'),
                "train_end": train_end.strftime('%Y-%m-%d'),
                "test_start": train_end.strftime('%Y-%m-%d'),
                "test_end": test_end.strftime('%Y-%m-%d'),
                "train_rows": len(train_df),
                "test_rows": len(test_df),
                "standard_acc": strat_metrics['accuracy'],
                "standard_f1": strat_metrics['f1_score'],
                "standard_prec": strat_metrics['precision'],
                "ultra_acc": ultra_metrics['accuracy'],
                "ultra_f1": ultra_metrics['f1_score'],
                "ultra_prec": ultra_metrics['precision']
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

    print(f"\n[WFO Summary] Completed {len(wfo_summary)} rolling Walk-Forward ML iterations.")
    return wfo_summary


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.abspath(os.path.join(base_dir, "data"))
    if not os.path.exists(data_dir):
        data_dir = os.path.abspath(os.path.join(base_dir, "..", "data"))
        
    print("==================================================")
    print("LOADING PROCESSED FEATURE CSVS FROM DATA DIRECTORY")
    print(f"Target Directory: {data_dir}")
    print("==================================================")
    
    target_tickers = WATCHLIST
    
    dataframes = []
    for ticker in target_tickers:
        filename = f"{ticker}_hybrid_features.csv"
        filepath = os.path.join(data_dir, filename)
        if os.path.exists(filepath):
            print(f"  [Loaded] {filename}")
            df = pd.read_csv(filepath)
            df["Ticker"] = ticker
            dataframes.append(df)
        else:
            print(f"  [Warning] {filename} not found.")

    if not dataframes:
        raise FileNotFoundError(f"No hybrid feature CSV files found in {data_dir}. Run data_scraper.py first.")

    # Concatenate individual ticker DataFrames into master DataFrame
    master_df = pd.concat(dataframes, axis=0, ignore_index=True)
    print(f"\nConcatenated {len(dataframes)} ticker feature files into Master DataFrame.")
    print(f"Master DataFrame Shape: {master_df.shape[0]} rows × {master_df.shape[1]} columns")

    # Pass master_df into walk_forward_optimization function to kick off the backtest
    wfo_results = walk_forward_optimization(master_df, train_months=24, test_months=1, tickers=target_tickers)
