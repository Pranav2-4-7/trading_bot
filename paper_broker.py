import os
import pandas as pd

class ExecutionAgent:
    """Agent responsible for order execution, account balance management, and trade logging."""
    def __init__(self, initial_capital=100000.0):
        self.initial_capital = initial_capital
        self.current_cash = initial_capital
        self.active_positions = {}  # {ticker: {entry_price: float, shares: int, entry_date: str}}
        self.cooldowns = {}         # {ticker: last_exit_date_str}
        self.trade_log = []
        self.SLIPPAGE_PCT = 0.0005          # 0.05% slippage penalty
        self.BROKERAGE_AND_TAXES_PCT = 0.0012 # ~0.12% fees

    def save_state(self, filepath="data/live_paper_portfolio.json"):
        """Saves current cash, positions, cooldowns, and trade log to a JSON file."""
        import json
        folder = os.path.dirname(filepath)
        if folder and not os.path.exists(folder):
            os.makedirs(folder)

        state = {
            "initial_capital": self.initial_capital,
            "current_cash": self.current_cash,
            "active_positions": self.active_positions,
            "cooldowns": self.cooldowns,
            "trade_log": self.trade_log
        }
        with open(filepath, "w") as f:
            json.dump(state, f, indent=4)
        print(f"Portfolio state saved to {filepath}")

    def load_state(self, filepath="data/live_paper_portfolio.json"):
        """Loads cash, positions, cooldowns, and trade log from a JSON file."""
        import json
        if not os.path.exists(filepath):
            self.save_state(filepath)
            return

        with open(filepath, "r") as f:
            state = json.load(f)
        print(f"[Broker Load] Loaded state from {filepath}: {state}")

        self.initial_capital = state.get("initial_capital", self.initial_capital)
        self.current_cash = state.get("current_cash", self.current_cash)
        self.active_positions = state.get("active_positions", {})
        self.cooldowns = state.get("cooldowns", {})
        self.trade_log = state.get("trade_log", [])
        print(f"Portfolio state loaded from {filepath}")

    def buy_asset(self, ticker, date, current_price, allocation):
        """Simulates buying an asset, deducting cash, and recording position."""
        if self.current_cash < allocation:
            return False

        # Apply buy slippage (buying slightly higher)
        execution_price = current_price * (1 + self.SLIPPAGE_PCT)
        shares_to_buy = int(allocation // execution_price)

        if shares_to_buy > 0:
            total_cost = shares_to_buy * execution_price
            transaction_fees = total_cost * self.BROKERAGE_AND_TAXES_PCT
            total_deduction = total_cost + transaction_fees

            if self.current_cash >= total_deduction:
                self.current_cash -= total_deduction
                self.active_positions[ticker] = {
                    "entry_price": execution_price,
                    "shares": shares_to_buy,
                    "entry_date": date,
                }
                print(
                    f"[{date}] BUY  | {ticker:=<11} | {shares_to_buy} Shares @ INR {execution_price:.2f} | Fees: INR {transaction_fees:.2f}"
                )
                return True
        return False

    def sell_asset(self, ticker, date, current_price, reason="Model Signal"):
        """Simulates selling an asset, adding cash, and writing to ledger."""
        if ticker not in self.active_positions:
            return False

        position = self.active_positions[ticker]
        shares_to_sell = position["shares"]

        # Apply sell slippage (selling slightly lower)
        execution_price = current_price * (1 - self.SLIPPAGE_PCT)
        gross_revenue = shares_to_sell * execution_price
        transaction_fees = gross_revenue * self.BROKERAGE_AND_TAXES_PCT
        net_revenue = gross_revenue - transaction_fees

        profit_loss = net_revenue - (shares_to_sell * position["entry_price"])
        self.current_cash += net_revenue

        print(
            f"[{date}] SELL | {ticker:=<11} | {shares_to_sell} Shares @ INR {execution_price:.2f} | PnL: INR {profit_loss:+.2f} ({reason})"
        )

        self.trade_log.append({
            "Ticker": ticker,
            "Entry_Date": position["entry_date"],
            "Exit_Date": date,
            "Entry_Price": position["entry_price"],
            "Exit_Price": execution_price,
            "Profit_Loss": profit_loss,
            "Exit_Reason": reason
        })
        
        self.cooldowns[ticker] = date
        del self.active_positions[ticker]
        return True

    def is_in_cooldown(self, ticker, current_date, cooldown_days=10):
        """Checks if a ticker was exited recently and is under re-entry block."""
        if ticker not in self.cooldowns:
            return False
        exit_date = pd.to_datetime(self.cooldowns[ticker])
        curr_date = pd.to_datetime(current_date)
        days_since = (curr_date - exit_date).days
        return days_since < cooldown_days

    def get_portfolio_value(self, current_prices_dict):
        """Calculates current total portfolio value (cash + market value of holdings)."""
        value = self.current_cash
        for ticker, position in self.active_positions.items():
            price = current_prices_dict.get(ticker, position["entry_price"])
            value += position["shares"] * price
        return value


class RiskAgent:
    """Agent responsible for risk controls: stop-loss, take-profit, and position sizing."""
    def __init__(self, stop_loss_pct=0.02, take_profit_pct=0.05, max_allocation_pct=0.20):
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_allocation_pct = max_allocation_pct

    def check_position_risk(self, ticker, current_price, entry_price):
        """Checks if a position has breached stop-loss or take-profit boundaries."""
        price_change_pct = (current_price - entry_price) / entry_price
        
        if price_change_pct <= -self.stop_loss_pct:
            return True, "Stop-Loss Breached"
        elif price_change_pct >= self.take_profit_pct:
            return True, "Take-Profit Breached"
            
        return False, None

    def calculate_buy_allocation(self, initial_capital, current_cash):
        """Allocates a portion of capital per trade if cash is available."""
        allocation = initial_capital * self.max_allocation_pct
        if current_cash >= allocation:
            return allocation
        return 0.0


def run_paper_trading_simulation(initial_capital=100000.0, signals_file="data/generated_signals.csv"):
    """Simulates a paper trading environment using historical model predictions."""
    if not os.path.exists(signals_file):
        raise FileNotFoundError(
            f"Signals file not found at {signals_file}. Please run your training script first."
        )

    signals_df = pd.read_csv(signals_file)
    signals_df = signals_df.sort_values("Date").reset_index(drop=True)

    execution_agent = ExecutionAgent(initial_capital)
    risk_agent = RiskAgent()

    print("Initializing Paper Trading Simulation...")
    print(f"Starting Capital: INR {initial_capital:,.2f}\n")

    # Group signals by date to simulate daily tick stream
    grouped_by_date = signals_df.groupby("Date")

    for date, day_data in grouped_by_date:
        # Construct a dictionary of current prices for this day to check risk
        current_prices = {}
        for _, row in day_data.iterrows():
            ticker = row["Ticker"]
            feature_file = f"data/{ticker}_hybrid_features.csv"
            if os.path.exists(feature_file):
                feat_df = pd.read_csv(feature_file)
                match = feat_df.loc[feat_df["Date"] == date, "Close"]
                if not match.empty:
                    current_prices[ticker] = match.values[0]

        # 1. RiskAgent checks active positions for Stop-Loss / Take-Profit breaches
        for ticker in list(execution_agent.active_positions.keys()):
            if ticker in current_prices:
                position = execution_agent.active_positions[ticker]
                current_price = current_prices[ticker]
                
                should_sell, reason = risk_agent.check_position_risk(
                    ticker, current_price, position["entry_price"]
                )
                if should_sell:
                    execution_agent.sell_asset(ticker, date, current_price, reason=reason)

        # 2. Process day's signals
        for _, row in day_data.iterrows():
            ticker = row["Ticker"]
            signal = row["Predicted_Signal"]
            confidence = row["Confidence_Score"]

            if ticker not in current_prices:
                continue
            current_price = current_prices[ticker]

            # CASE A: Buy signal from model & confidence >= 0.70 & not already holding position
            if signal == 1 and confidence >= 0.70 and ticker not in execution_agent.active_positions:
                if not execution_agent.is_in_cooldown(ticker, date, cooldown_days=10):
                    allocation = risk_agent.calculate_buy_allocation(
                        initial_capital, execution_agent.current_cash
                    )
                    if allocation > 0:
                        execution_agent.buy_asset(ticker, date, current_price, allocation)

            # CASE B: Hold/Sell signal from model & currently holding position
            elif signal == 0 and ticker in execution_agent.active_positions:
                execution_agent.sell_asset(ticker, date, current_price, reason="Model Signal")

    # --- SIMULATION SUMMARY ---
    # Liquidate remaining open positions at final prices
    target_tickers = list(signals_df["Ticker"].unique())
    final_prices = {}
    for ticker in target_tickers:
        feat_df = pd.read_csv(f"data/{ticker}_hybrid_features.csv")
        final_prices[ticker] = feat_df["Close"].iloc[-1]
        
    final_portfolio_value = execution_agent.get_portfolio_value(final_prices)

    print("\n================ SIMULATION RESULTS ================")
    print(f"Initial Capital:       INR {initial_capital:,.2f}")
    print(f"Final Account Value:   INR {final_portfolio_value:,.2f}")
    net_return = ((final_portfolio_value - initial_capital) / initial_capital) * 100
    print(f"Total Net Return:      {net_return:+.2f}%")

    if execution_agent.trade_log:
        trades_df = pd.DataFrame(execution_agent.trade_log)
        winning_trades = trades_df[trades_df["Profit_Loss"] > 0]
        win_rate = (len(winning_trades) / len(trades_df)) * 100
        print(f"Total Closed Trades:   {len(trades_df)}")
        print(f"Win Rate:              {win_rate:.2f}%")

        trades_df.to_csv("data/final_trade_ledger.csv", index=False)
        print("Detailed transaction ledger saved to data/final_trade_ledger.csv")


if __name__ == "__main__":
    try:
        run_paper_trading_simulation()
    except Exception as e:
        print(f"Simulation failed to complete: {e}")