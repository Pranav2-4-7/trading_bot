import sys
import os
import pandas as pd

# Add current folder to path to allow importing adjacent modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_scraper import IngestionAgent
from model import StrategyAgent
from paper_broker import ExecutionAgent, RiskAgent

def run_agent_simulation():
    """Coordinates the entire multi-agent trading bot pipeline and paper trading simulation."""
    tickers = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"]
    start_date = "2021-01-01"
    end_date = "2026-06-25"
    initial_capital = 100000.0

    print("==================================================")
    print("STARTING MULTI-AGENT TRADING BOT RUN")
    print("==================================================")

    # 1. Ingestion Agent
    ingestion = IngestionAgent(output_dir="data")
    ingestion.download_historical_data(tickers, start_date, end_date)
    for ticker in tickers:
        ingestion.compute_technical_features(ticker)
        ingestion.merge_price_and_fundamental_data(ticker)

    # 2. Strategy Agent
    strategy = StrategyAgent(tickers, data_dir="data")
    test_results_df = strategy.train_model()

    # 3. Execution & Risk Agent Simulation
    test_results_df = test_results_df.sort_values("Date").reset_index(drop=True)

    execution = ExecutionAgent(initial_capital)
    risk = RiskAgent(stop_loss_pct=0.05, take_profit_pct=0.05, max_allocation_pct=0.20, trailing_stop_loss_pct=0.05)

    print("\n==================================================")
    print("STARTING PAPER TRADING SIMULATION LOOP")
    print("==================================================")

    # Group by date to process as daily ticks
    grouped_dates = test_results_df.groupby("Date")

    for date, day_data in grouped_dates:
        # Extract daily prices
        current_prices = {}
        for _, row in day_data.iterrows():
            ticker = row["Ticker"]
            feature_file = f"data/{ticker}_hybrid_features.csv"
            if os.path.exists(feature_file):
                feat_df = pd.read_csv(feature_file)
                match = feat_df.loc[feat_df["Date"] == date, "Close"]
                if not match.empty:
                    current_prices[ticker] = match.values[0]

        # A. Risk Agent Checks active positions for Stop-Loss / Take-Profit
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
                    
                should_sell, reason = risk.check_position_risk(
                    ticker, current_price, entry_price, peak_price=peak_price
                )
                if should_sell:
                    execution.sell_asset(ticker, date, current_price, reason=reason)

        # B. Decisions & Execution
        for _, row in day_data.iterrows():
            ticker = row["Ticker"]
            signal = row["Predicted_Signal"]
            confidence = row["Confidence_Score"]

            if ticker not in current_prices:
                continue
            current_price = current_prices[ticker]

            # Proposed BUY Signal Check
            if signal == 1 and confidence >= strategy.buy_threshold and ticker not in execution.active_positions:
                if not execution.is_in_cooldown(ticker, date, cooldown_days=10):
                    allocation = risk.calculate_buy_allocation(initial_capital, execution.current_cash)
                    if allocation > 0:
                        execution.buy_asset(ticker, date, current_price, allocation)

    # C. Liquidation of open positions at final prices
    final_prices = {}
    for ticker in tickers:
        feat_df = pd.read_csv(f"data/{ticker}_hybrid_features.csv")
        final_prices[ticker] = feat_df["Close"].iloc[-1]
        
    final_portfolio_value = execution.get_portfolio_value(final_prices)

    print("\n==================================================")
    print("SIMULATION COMPLETED - FINAL REPORT")
    print("==================================================")
    print(f"Initial Capital:       INR {initial_capital:,.2f}")
    print(f"Final Account Value:   INR {final_portfolio_value:,.2f}")
    net_return = ((final_portfolio_value - initial_capital) / initial_capital) * 100
    print(f"Total Net Return:      {net_return:+.2f}%")

    if execution.trade_log:
        trades_df = pd.DataFrame(execution.trade_log)
        winning_trades = trades_df[trades_df["Profit_Loss"] > 0]
        win_rate = (len(winning_trades) / len(trades_df)) * 100
        print(f"Total Closed Trades:   {len(trades_df)}")
        print(f"Win Rate:              {win_rate:.2f}%")

        output_dir = "data"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        trades_df.to_csv(os.path.join(output_dir, "final_trade_ledger.csv"), index=False)
        print("Detailed transaction ledger saved to data/final_trade_ledger.csv")


if __name__ == "__main__":
    run_agent_simulation()
