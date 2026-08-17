import os
import pandas as pd

# Evidently AI imports with version-agnostic fallback
try:
    from evidently import ColumnMapping
    from evidently.report import Report
    from evidently.metric_preset import DataDriftPreset
except ImportError:
    from evidently.legacy.pipeline.column_mapping import ColumnMapping
    from evidently.legacy.report import Report
    from evidently.legacy.metric_preset import DataDriftPreset

NUMERICAL_FEATURES = [
    "Close", "Volume", "MA50", "MA200", "RSI14", "Volume_Ratio",
    "MACD", "MACD_Signal", "MACD_Hist", 
    "BB_Upper_Dist", "BB_Lower_Dist", "BB_Width",
    "ATR", "ATR_Ratio", "Dist_MA50", "Dist_MA200", "ROC_10",
    "Net_Profit_Margin", "Debt_to_Equity"
]


def evaluate_market_drift(reference_data_path, current_data_path):
    """
    Evaluates market feature drift between a reference dataset (historical baseline)
    and a current dataset (recent market window) using Evidently AI.
    
    Args:
        reference_data_path (str or pd.DataFrame): Path to reference dataset CSV or DataFrame.
        current_data_path (str or pd.DataFrame): Path to current dataset CSV or DataFrame.
        
    Returns:
        bool: True if overall dataset drift is detected, False otherwise.
    """
    # 1. Load DataFrames
    if isinstance(reference_data_path, str):
        if not os.path.exists(reference_data_path):
            raise FileNotFoundError(f"Reference data file not found: {reference_data_path}")
        ref_df = pd.read_csv(reference_data_path)
    else:
        ref_df = reference_data_path.copy()

    if isinstance(current_data_path, str):
        if not os.path.exists(current_data_path):
            raise FileNotFoundError(f"Current data file not found: {current_data_path}")
        curr_df = pd.read_csv(current_data_path)
    else:
        curr_df = current_data_path.copy()

    # Filter available numerical feature columns present in both DataFrames
    available_num_features = [col for col in NUMERICAL_FEATURES if col in ref_df.columns and col in curr_df.columns]

    # 2. Define ColumnMapping object classifying technical indicators as numerical_features
    column_mapping = ColumnMapping(
        numerical_features=available_num_features
    )

    # 3. Initialize Evidently Report with DataDriftPreset
    drift_report = Report(metrics=[DataDriftPreset()])

    # 4. Run the report comparing reference to current dataset
    drift_report.run(reference_data=ref_df, current_data=curr_df, column_mapping=column_mapping)

    # 5. Extract drift results using .as_dict()
    report_dict = drift_report.as_dict()

    try:
        # Extract dataset drift boolean from Evidently report dictionary
        dataset_drift_detected = report_dict["metrics"][0]["result"]["dataset_drift"]
        drift_share = report_dict["metrics"][0]["result"].get("share_of_drifted_columns", 0.0)
        number_of_drifted = report_dict["metrics"][0]["result"].get("number_of_drifted_columns", 0)
        total_columns = report_dict["metrics"][0]["result"].get("number_of_columns", len(available_num_features))
        
        print("\n==================================================")
        print("EVIDENTLY AI MARKET DRIFT EVALUATION REPORT")
        print("==================================================")
        print(f"Overall Dataset Drift Detected: {dataset_drift_detected}")
        print(f"Drifted Feature Columns:        {number_of_drifted} / {total_columns} ({drift_share:.1%})")
        print("==================================================\n")
        
        return bool(dataset_drift_detected)
    except (KeyError, IndexError) as err:
        print(f"[Drift Monitor Warning] Error parsing Evidently dictionary output: {err}")
        return False


if __name__ == "__main__":
    # Test execution
    base_dir = os.path.dirname(os.path.abspath(__file__))
    ref_path = os.path.join(base_dir, "data", "SUNPHARMA.NS_hybrid_features.csv")
    curr_path = os.path.join(base_dir, "data", "SUNPHARMA.NS_hybrid_features.csv")
    
    if os.path.exists(ref_path):
        is_drifted = evaluate_market_drift(ref_path, curr_path)
        print(f"Test Run Completed. Dataset Drift Flag: {is_drifted}")
    else:
        print(f"Data file {ref_path} not found. Please run data_scraper.py first.")
