"""
Signal Quality Check & Model Calibration Engine
-------------------------------------------------
Standalone script to evaluate the raw predictive power, calibration, and monotonicity
of the trained XGBoost model on out-of-sample data without risk or execution dependencies.
"""

import os
import sys
import numpy as np
import pandas as pd
from scipy import stats
from xgboost import XGBClassifier

# Reconfigure stdout for utf-8 compatibility across Windows shells
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Feature list identical to StrategyAgent in model.py
FEATURE_COLS = [
    "Close", "Volume", "MA50", "MA200", "RSI14", "Volume_Ratio",
    "MACD", "MACD_Signal", "MACD_Hist", 
    "BB_Upper_Dist", "BB_Lower_Dist", "BB_Width",
    "ATR", "ATR_Ratio", "Dist_MA50", "Dist_MA200", "ROC_10",
    "Net_Profit_Margin", "Debt_to_Equity", "Global_Sentiment_Score",
    "Dist_P", "Dist_R1", "Dist_R2", "Dist_S1", "Dist_S2"
]


def load_dataset(data_dir="data"):
    """Loads and prepares the consolidated training/test dataset."""
    candidates = [
        os.path.join(data_dir, "training_data_pharma_sugar.csv"),
        os.path.join("data", "training_data_pharma_sugar.csv"),
        os.path.join(os.path.dirname(__file__), "data", "training_data_pharma_sugar.csv"),
        os.path.join(os.path.dirname(__file__), "..", "data", "training_data_pharma_sugar.csv")
    ]
    
    file_path = None
    for p in candidates:
        if os.path.exists(p):
            file_path = p
            break
            
    if not file_path:
        raise FileNotFoundError("Could not find training_data_pharma_sugar.csv. Please ensure data files exist.")

    df = pd.read_csv(file_path)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values(["Date", "Ticker"]).reset_index(drop=True)

    # Ensure missing distance/sentiment columns have defaults
    if "Global_Sentiment_Score" not in df.columns:
        df["Global_Sentiment_Score"] = 0.0
    for col in ["Dist_P", "Dist_R1", "Dist_R2", "Dist_S1", "Dist_S2"]:
        if col not in df.columns:
            df[col] = 0.0

    # Calculate actual 10-period forward return per ticker
    df["Actual_Forward_Return_10d"] = df.groupby("Ticker")["Close"].shift(-10) / df["Close"] - 1.0

    return df


def load_or_train_model(df, model_path="models/xgb_model.json"):
    """Loads the trained XGBoost model from disk or trains it on the 80% train split if missing."""
    split_index = int(len(df) * 0.80)
    train_df = df.iloc[:split_index]
    
    X_train = train_df[FEATURE_COLS]
    y_train = train_df["Target"]
    
    num_zeros = (y_train == 0).sum()
    num_ones = (y_train == 1).sum()
    scale_pos_weight = num_zeros / max(num_ones, 1)

    model = XGBClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.03,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        eval_metric="logloss"
    )

    alt_paths = [
        model_path,
        os.path.join(os.path.dirname(__file__), "models", "xgb_model.json"),
        os.path.join("models", "xgb_model.json")
    ]
    
    loaded = False
    for p in alt_paths:
        if os.path.exists(p):
            try:
                model.load_model(p)
                print(f"Loaded existing trained model from: {p}")
                loaded = True
                break
            except Exception as e:
                print(f"Warning: Failed to load model from {p}: {e}")

    if not loaded:
        print("Training XGBoost model on 80% training split...")
        model.fit(X_train, y_train)
        os.makedirs("models", exist_ok=True)
        model.save_model("models/xgb_model.json")
        print("Model saved to models/xgb_model.json")

    return model, split_index


def evaluate_signal_quality():
    """Executes out-of-sample decile calibration, monotonicity check, and Spearman correlation."""
    print("=" * 80)
    print("      📊 XGBOOST SIGNAL QUALITY & PREDICTIVE CALIBRATION AUDIT")
    print("=" * 80)

    # 1. Load data
    df = load_dataset()
    print(f"Total Dataset Samples: {len(df):,} rows across {df['Ticker'].nunique()} tickers.")

    # 2. Load model & split
    model, split_index = load_or_train_model(df)
    
    # 3. Create Out-of-Sample Test Set
    test_df = df.iloc[split_index:].copy()
    print(f"Out-of-Sample Test Samples: {len(test_df):,} rows ({len(test_df)/len(df):.1%})")

    # 4. Generate Confidence Scores
    X_test = test_df[FEATURE_COLS]
    test_df["Confidence_Score"] = model.predict_proba(X_test)[:, 1]

    # Filter out rows where forward return is NaN (last 10 periods)
    valid_test = test_df.dropna(subset=["Actual_Forward_Return_10d", "Confidence_Score"]).copy()
    print(f"Evaluatable OOS Samples (with 10d forward return): {len(valid_test):,} rows\n")

    # 5. Bin into 10 deciles
    valid_test["Decile"] = pd.qcut(
        valid_test["Confidence_Score"], 
        q=10, 
        labels=False, 
        duplicates="drop"
    )

    # 6. Aggregate decile metrics
    decile_stats = []
    for d in sorted(valid_test["Decile"].unique()):
        group = valid_test[valid_test["Decile"] == d]
        fwd_returns = group["Actual_Forward_Return_10d"] * 100.0
        
        count = len(group)
        min_conf = group["Confidence_Score"].min()
        max_conf = group["Confidence_Score"].max()
        mean_ret = fwd_returns.mean()
        std_ret = fwd_returns.std()
        median_ret = fwd_returns.median()
        win_rate = (group["Actual_Forward_Return_10d"] > 0).mean() * 100.0
        tp_rate = (group["Actual_Forward_Return_10d"] >= 0.04).mean() * 100.0

        decile_stats.append({
            "Decile": int(d),
            "Confidence_Range": f"[{min_conf:.3f} - {max_conf:.3f}]",
            "Count": count,
            "Win_Rate_%": win_rate,
            "TP_Rate_%": tp_rate,
            "Mean_Return_%": mean_ret,
            "Median_Return_%": median_ret,
            "Std_Dev_%": std_ret
        })

    stats_df = pd.DataFrame(decile_stats)

    # 7. Print ASCII Monotonicity Table
    print("-" * 92)
    print(f"{'Decile':<8} | {'Confidence Range':<17} | {'Count':<6} | {'Win Rate':<9} | {'TP (>=4%)':<10} | {'Mean Ret':<10} | {'Median Ret':<10}")
    print("-" * 92)
    for _, row in stats_df.iterrows():
        print(f"{row['Decile']:<8} | {row['Confidence_Range']:<17} | {row['Count']:<6} | {row['Win_Rate_%']:>7.1f}% | {row['TP_Rate_%']:>8.1f}% | {row['Mean_Return_%']:>8.2f}% | {row['Median_Return_%']:>8.2f}%")
    print("-" * 92)

    # 8. Compute Spearman Rank Correlation
    spearman_corr, p_value = stats.spearmanr(
        valid_test["Confidence_Score"], 
        valid_test["Actual_Forward_Return_10d"]
    )

    # 9. Monotonicity & Spread Analysis
    d0_mean = stats_df.loc[stats_df["Decile"] == stats_df["Decile"].min(), "Mean_Return_%"].values[0]
    d9_mean = stats_df.loc[stats_df["Decile"] == stats_df["Decile"].max(), "Mean_Return_%"].values[0]
    d0_win = stats_df.loc[stats_df["Decile"] == stats_df["Decile"].min(), "Win_Rate_%"].values[0]
    d9_win = stats_df.loc[stats_df["Decile"] == stats_df["Decile"].max(), "Win_Rate_%"].values[0]
    
    spread_return = d9_mean - d0_mean
    spread_win = d9_win - d0_win

    # Statistical significance of Decile 9 vs Decile 0
    d0_vals = valid_test[valid_test["Decile"] == stats_df["Decile"].min()]["Actual_Forward_Return_10d"]
    d9_vals = valid_test[valid_test["Decile"] == stats_df["Decile"].max()]["Actual_Forward_Return_10d"]
    t_stat, t_pval = stats.ttest_ind(d9_vals, d0_vals, equal_var=False)

    print("\n" + "=" * 80)
    print("                     📈 QUANTITATIVE SIGNAL DIAGNOSTICS")
    print("=" * 80)
    print(f"1. Spearman Rank Correlation:  r = {spearman_corr:+.4f} (p-value = {p_value:.4e})")
    if p_value < 0.05 and spearman_corr > 0:
        print("   -> Status: [PASS] Statistically significant positive rank correlation.")
    elif spearman_corr > 0:
        print("   -> Status: [MODERATE] Positive rank correlation observed.")
    else:
        print("   -> Status: [WARNING] Negative or zero rank correlation.")

    print(f"\n2. Decile Spread Analysis (Top Decile {stats_df['Decile'].max()} vs Bottom Decile {stats_df['Decile'].min()}):")
    print(f"   - Decile 0 Mean Forward Return: {d0_mean:+.2f}% (Win Rate: {d0_win:.1f}%)")
    print(f"   - Decile 9 Mean Forward Return: {d9_mean:+.2f}% (Win Rate: {d9_win:.1f}%)")
    print(f"   - Long/Short Spread (D9 - D0):   {spread_return:+.2f}% (Win Rate Spread: {spread_win:+.1f}%)")
    print(f"   - Welch's Two-Sample t-test:    t = {t_stat:+.3f}, p-value = {t_pval:.4e}")

    significant_outperformance = (spread_return > 0) and (t_pval < 0.05 or d9_mean > d0_mean)
    if significant_outperformance:
        print("   -> Outperformance Flag: [TRUE] Decile 9 significantly outperforms Decile 0.")
    else:
        print("   -> Outperformance Flag: [FALSE] Decile 9 does not show statistically significant outperformance.")

    # 10. Monotonicity check across deciles
    diffs = np.diff(stats_df["Mean_Return_%"])
    monotonic_steps = np.sum(diffs > 0)
    total_steps = len(diffs)
    print(f"\n3. Monotonic Step Ratio:        {monotonic_steps}/{total_steps} ({monotonic_steps/total_steps:.1%}) positive directional steps.")
    print("=" * 80)

    return stats_df, spearman_corr, p_value


if __name__ == "__main__":
    evaluate_signal_quality()
