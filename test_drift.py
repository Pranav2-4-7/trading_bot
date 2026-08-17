import os
import pandas as pd
from drift_monitor import evaluate_market_drift

def run_drift_test():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_csv = os.path.join(base_dir, "data", "SUNPHARMA.NS_hybrid_features.csv")
    
    if not os.path.exists(input_csv):
        input_csv = os.path.abspath(os.path.join(base_dir, "..", "data", "SUNPHARMA.NS_hybrid_features.csv"))

    if not os.path.exists(input_csv):
        print(f"Error: Input file {input_csv} not found.")
        return

    print(f"Loading dataset: {input_csv}")
    df = pd.read_csv(input_csv)
    
    # Split DataFrame: first 80% of rows as reference_df, last 20% of rows as current_df
    split_idx = int(len(df) * 0.80)
    reference_df = df.iloc[:split_idx].copy()
    current_df = df.iloc[split_idx:].copy()

    ref_file = os.path.join(base_dir, "test_ref.csv")
    curr_file = os.path.join(base_dir, "test_curr.csv")

    reference_df.to_csv(ref_file, index=False)
    current_df.to_csv(curr_file, index=False)
    print(f"Saved temporary test files:\n - {ref_file} ({len(reference_df)} rows)\n - {curr_file} ({len(current_df)} rows)")

    print("\nTriggering evaluate_market_drift() from drift_monitor.py...")
    drift_result = evaluate_market_drift(ref_file, curr_file)

    print("==================================================")
    print(f"DRIFT TEST FINAL BOOLEAN RESULT: {drift_result}")
    print("==================================================")

    # Cleanup temporary test files
    for temp_f in [ref_file, curr_file]:
        if os.path.exists(temp_f):
            os.remove(temp_f)
    print("Temporary test files cleaned up successfully.")

if __name__ == "__main__":
    run_drift_test()
