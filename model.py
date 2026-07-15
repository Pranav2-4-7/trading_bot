import os
import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, classification_report, f1_score, precision_score

class StrategyAgent:
    """Agent responsible for training the machine learning brain and generating trading signals."""
    def __init__(self, tickers, data_dir="data"):
        self.tickers = tickers
        self.data_dir = data_dir
        self.model = None
        self.feature_cols = ["Close", "Volume", "MA50", "MA200", "RSI14", "Volume_Ratio", "Net_Profit_Margin", "Debt_to_Equity"]
        # Set default threshold, will be optimized during training
        self.buy_threshold = 0.65

    def load_and_combine_data(self):
        """Loads hybrid feature files for all tickers and combines them into one dataset."""
        combined_df = pd.DataFrame()
        for ticker in self.tickers:
            file_path = os.path.join(self.data_dir, f"{ticker}_hybrid_features.csv")
            if os.path.exists(file_path):
                df = pd.read_csv(file_path)
                df["Ticker"] = ticker
                combined_df = pd.concat([combined_df, df], axis=0)
            else:
                print(f"Warning: Feature file for {ticker} not found.")
                
        if combined_df.empty:
            raise ValueError("No feature data found. Please run the data scraper script first.")
            
        combined_df["Date"] = pd.to_datetime(combined_df["Date"])
        combined_df = combined_df.sort_values("Date").reset_index(drop=True)
        combined_df["Date"] = combined_df["Date"].dt.strftime("%Y-%m-%d %H:%M:%S")
        return combined_df

    def train_model(self):
        """Trains the XGBoost brain using scale_pos_weight to offset imbalance."""
        df = self.load_and_combine_data()
        X = df[self.feature_cols]
        y = df["Target"]
        
        # 80/20 Time-Series Split
        split_index = int(len(df) * 0.80)
        
        X_train, X_test = X.iloc[:split_index], X.iloc[split_index:]
        y_train, y_test = y.iloc[:split_index], y.iloc[split_index:]
        test_dates = df["Date"].iloc[split_index:]
        test_tickers = df["Ticker"].iloc[split_index:]
        
        print(f"Training samples: {len(X_train)} | Testing samples: {len(X_test)}")
        
        # Balance class ratio using training targets
        num_zeros = (y_train == 0).sum()
        num_ones = (y_train == 1).sum()
        scale_pos_weight = num_zeros / max(num_ones, 1)
        print(f"Calculated scale_pos_weight: {scale_pos_weight:.2f}")
        
        # Inner train-validation split for threshold optimization (chronological 80/20 of train)
        inner_split = int(len(X_train) * 0.80)
        X_train_inner, X_val_inner = X_train.iloc[:inner_split], X_train.iloc[inner_split:]
        y_train_inner, y_val_inner = y_train.iloc[:inner_split], y_train.iloc[inner_split:]
        
        # Fit model on inner train for threshold search
        temp_model = XGBClassifier(
            n_estimators=50,
            max_depth=5,
            learning_rate=0.03,
            scale_pos_weight=1.0,
            random_state=42,
            eval_metric="logloss"
        )
        temp_model.fit(X_train_inner, y_train_inner)
        
        # Predict on inner validation to optimize threshold
        y_val_proba = temp_model.predict_proba(X_val_inner)[:, 1]
        
        best_threshold = 0.50
        best_f1 = 0.0
        
        for th in np.arange(0.35, 0.75, 0.01):
            preds = (y_val_proba >= th).astype(int)
            prec = precision_score(y_val_inner, preds, zero_division=0)
            f1 = f1_score(y_val_inner, preds, zero_division=0)
            # Optimize F1 score but ensure precision is at least 45% to minimize false buys
            if prec >= 0.45 and f1 > best_f1:
                best_f1 = f1
                best_threshold = th
                
        print(f"Optimized Decision Threshold (based on validation set): {best_threshold:.4f} (Validation F1: {best_f1:.2%})")
        self.buy_threshold = float(best_threshold)

        # Train final model on full training set using optimized parameters
        self.model = XGBClassifier(
            n_estimators=50,
            max_depth=5,
            learning_rate=0.03,
            scale_pos_weight=1.0,
            random_state=42,
            eval_metric="logloss"
        )
        
        print("Training the final XGBoost 'Brain'...")
        self.model.fit(X_train, y_train)
        
        # Evaluate Predictions on unseen test set
        y_pred_proba = self.model.predict_proba(X_test)[:, 1]
        y_pred = (y_pred_proba >= self.buy_threshold).astype(int)
        
        accuracy = accuracy_score(y_test, y_pred)
        print("\n================ MODEL PERFORMANCE ================")
        print(f"Accuracy Score: {accuracy:.2%}")
        print("\nClassification Report:")
        print(classification_report(y_test, y_pred, zero_division=0))
        
        results_df = pd.DataFrame({
            "Date": test_dates,
            "Ticker": test_tickers,
            "Actual_Target": y_test,
            "Predicted_Signal": y_pred,
            "Confidence_Score": y_pred_proba
        })
        
        buy_signals = results_df[results_df["Predicted_Signal"] == 1]
        print(f"Total Buy Signals Generated in Test Set: {len(buy_signals)}")
        
        return results_df

    def predict_signal(self, current_features_df):
        """Real-time signal generator for streaming data."""
        if self.model is None:
            raise ValueError("Brain model is not trained yet.")
        
        X = current_features_df[self.feature_cols]
        proba = self.model.predict_proba(X)[:, 1]
        signal = (proba >= self.buy_threshold).astype(int)
        return signal, proba


if __name__ == "__main__":
    target_tickers = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"]
    
    try:
        agent = StrategyAgent(target_tickers)
        signals_log = agent.train_model()
        
        output_path = os.path.join("data", "generated_signals.csv")
        signals_log.to_csv(output_path, index=False)
        print(f"Signals log saved to {output_path}")
        
    except Exception as e:
        print(f"Error during training: {e}")