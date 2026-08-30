import math
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
        self.BROKERAGE_AND_TAXES_PCT = 0.0012 # ~0.12% fees

    def calculate_dynamic_slippage(self, price, order_quantity, atr_14, avg_volume_20, bid_ask_spread=None):
        """
        Calculates dynamic liquidity- and volatility-based slippage.
        
        Args:
            price (float): Asset current market price.
            order_quantity (int or float): Number of shares in order.
            atr_14 (float): 14-period Average True Range.
            avg_volume_20 (float): 20-period Average Volume.
            bid_ask_spread (float, optional): Bid-ask spread. If None, estimated as 2 bps (0.0002 * price).
            
        Returns:
            float: Total price slippage penalty per share in currency units.
        """
        if bid_ask_spread is None or bid_ask_spread <= 0:
            half_spread = 0.0002 * price
        else:
            half_spread = bid_ask_spread / 2.0

        atr_val = atr_14 if (atr_14 is not None and atr_14 > 0) else (0.015 * price)
        vol_val = avg_volume_20 if (avg_volume_20 is not None and avg_volume_20 > 0) else 1000000.0
        qty_val = max(float(order_quantity), 1.0)

        impact = 0.1 * atr_val * math.sqrt(qty_val / max(vol_val, 1.0))
        total_slippage = half_spread + impact
        return total_slippage

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

    def buy_asset(self, ticker, date, current_price, allocation, atr_14=None, avg_volume_20=None, bid_ask_spread=None, kelly_fraction=None, confidence_score=None):
        """Simulates buying an asset using dynamic slippage, deducting cash, and recording position metadata."""
        if self.current_cash < allocation:
            return False

        # Estimate order quantity for dynamic slippage calculation
        approx_shares = max(int(allocation // current_price), 1)
        total_slippage = self.calculate_dynamic_slippage(current_price, approx_shares, atr_14, avg_volume_20, bid_ask_spread)
        slippage_pct = (total_slippage / current_price) if current_price > 0 else 0.0

        # Buy Price = Current Price + Total Slippage
        execution_price = current_price + total_slippage
        shares_to_buy = int(allocation // execution_price)

        if shares_to_buy > 0:
            total_cost = shares_to_buy * execution_price
            total_slippage_cost = total_slippage * shares_to_buy
            transaction_fees = total_cost * self.BROKERAGE_AND_TAXES_PCT
            total_deduction = total_cost + transaction_fees

            if self.current_cash >= total_deduction:
                self.current_cash -= total_deduction
                
                if ticker in self.active_positions:
                    pos = self.active_positions[ticker]
                    old_shares = pos["shares"]
                    old_price = pos["entry_price"]
                    total_shares = old_shares + shares_to_buy
                    average_price = ((old_shares * old_price) + (shares_to_buy * execution_price)) / total_shares
                    
                    self.active_positions[ticker] = {
                        "entry_price": average_price,
                        "fill_price": execution_price,
                        "slippage_inr": total_slippage,
                        "slippage_pct": slippage_pct,
                        "total_slippage_cost": total_slippage_cost,
                        "shares": total_shares,
                        "entry_date": pos.get("entry_date", date),
                        "last_buy_date": date,
                        "buy_count": pos.get("buy_count", 1) + 1,
                        "peak_price": average_price,
                        "kelly_fraction": kelly_fraction if kelly_fraction is not None else pos.get("kelly_fraction"),
                        "confidence_score": confidence_score if confidence_score is not None else pos.get("confidence_score")
                    }
                    print(
                        f"[{date}] AVG-DOWN | {ticker:=<11} | Added {shares_to_buy} Shares @ Fill: INR {execution_price:.2f} | Slippage: INR {total_slippage:.2f} ({slippage_pct:.4%}) | Total Slippage Cost: INR {total_slippage_cost:.2f} | New Avg Price: INR {average_price:.2f}"
                    )
                else:
                    self.active_positions[ticker] = {
                        "entry_price": execution_price,
                        "fill_price": execution_price,
                        "slippage_inr": total_slippage,
                        "slippage_pct": slippage_pct,
                        "total_slippage_cost": total_slippage_cost,
                        "shares": shares_to_buy,
                        "entry_date": date,
                        "buy_count": 1,
                        "peak_price": execution_price,
                        "kelly_fraction": kelly_fraction,
                        "confidence_score": confidence_score
                    }
                    print(
                        f"[{date}] BUY      | {ticker:=<11} | {shares_to_buy} Shares @ Fill: INR {execution_price:.2f} | Slippage: INR {total_slippage:.2f} ({slippage_pct:.4%}) | Total Slippage Cost: INR {total_slippage_cost:.2f} | Fees: INR {transaction_fees:.2f}"
                    )
                return True
        return False

    def place_buy_order(self, ticker, date, current_price, allocation, current_prices, risk_agent, portfolio_risk_agent=None, atr_14=None, avg_volume_20=None, bid_ask_spread=None, kelly_fraction=None, confidence_score=None):
        """Attempts to execute a buy order after validating portfolio risk gating and capital recycling."""
        total_port_val = self.get_portfolio_value(current_prices)
        
        # Validate portfolio risk boundaries prior to computing share sizes
        if risk_agent is not None and hasattr(risk_agent, "approve_order"):
            approved, reason = risk_agent.approve_order(
                open_positions=self.active_positions,
                candidate_ticker=ticker,
                target_inr=allocation,
                total_portfolio_value=total_port_val,
                portfolio_risk_agent=portfolio_risk_agent,
                current_prices=current_prices
            )
            if not approved:
                return False
        elif portfolio_risk_agent is not None:
            approved, reason = portfolio_risk_agent.check_portfolio_risk(
                open_positions=self.active_positions,
                candidate_ticker=ticker,
                target_inr=allocation,
                total_portfolio_value=total_port_val,
                current_prices=current_prices
            )
            if not approved:
                print(f"[PortfolioRiskAgent Rejection] Order for {ticker} blocked: {reason}")
                return False

        if self.current_cash < allocation and confidence_score is not None:
            risk_agent.rebalance_for_high_conviction(self, allocation, confidence_score, current_prices, date)
            
        return self.buy_asset(ticker, date, current_price, allocation, atr_14, avg_volume_20, bid_ask_spread, kelly_fraction, confidence_score)

    def sell_asset(self, ticker, date, current_price, reason="Model Signal", atr_14=None, avg_volume_20=None, bid_ask_spread=None):
        """Simulates selling an asset using dynamic slippage, adding cash, and writing to ledger."""
        if ticker not in self.active_positions:
            return False

        position = self.active_positions[ticker]
        shares_to_sell = position["shares"]

        total_slippage = self.calculate_dynamic_slippage(current_price, shares_to_sell, atr_14, avg_volume_20, bid_ask_spread)
        slippage_pct = (total_slippage / current_price) if current_price > 0 else 0.0
        total_slippage_cost = total_slippage * shares_to_sell

        # Sell Price = Current Price - Total Slippage
        execution_price = current_price - total_slippage
        gross_revenue = shares_to_sell * execution_price
        transaction_fees = gross_revenue * self.BROKERAGE_AND_TAXES_PCT
        net_revenue = gross_revenue - transaction_fees

        profit_loss = net_revenue - (shares_to_sell * position["entry_price"])
        self.current_cash += net_revenue

        print(
            f"[{date}] SELL | {ticker:=<11} | {shares_to_sell} Shares @ Fill: INR {execution_price:.2f} | Slippage: INR {total_slippage:.2f} ({slippage_pct:.4%}) | Total Slippage Cost: INR {total_slippage_cost:.2f} | PnL: INR {profit_loss:+.2f} ({reason})"
        )

        self.trade_log.append({
            "Ticker": ticker,
            "Entry_Date": position["entry_date"],
            "Exit_Date": date,
            "Entry_Price": position["entry_price"],
            "Exit_Price": execution_price,
            "Fill_Price": execution_price,
            "Slippage_INR": total_slippage,
            "Slippage_Pct": slippage_pct,
            "Total_Slippage_Cost": total_slippage_cost,
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
# Sector mapping across all 20 watchlist tickers
TICKER_SECTORS = {
    # Core Leaders
    'RELIANCE.NS': 'Energy',
    'TCS.NS': 'Technology',
    'INFY.NS': 'Technology',
    'WIPRO.NS': 'Technology',
    'HDFCBANK.NS': 'Banking',
    'ICICIBANK.NS': 'Banking',
    'SBIN.NS': 'Banking',
    'BHARTIARTL.NS': 'Telecom',
    'ITC.NS': 'FMCG',
    'LT.NS': 'Industrials',
    # Pharma Leaders
    'SUNPHARMA.NS': 'Pharma',
    'CIPLA.NS': 'Pharma',
    'DRREDDY.NS': 'Pharma',
    'DIVISLAB.NS': 'Pharma',
    'LUPIN.NS': 'Pharma',
    # Sugar Leaders
    'BALRAMCHIN.NS': 'Sugar',
    'EIDPARRY.NS': 'Sugar',
    'RENUKA.NS': 'Sugar',
    'TRIVENI.NS': 'Sugar',
    'DALMIASUG.NS': 'Sugar'
}


# Sector mapping across all 20 watchlist tickers
TICKER_SECTORS = {
    # Core Leaders
    'RELIANCE.NS': 'Energy',
    'TCS.NS': 'Technology',
    'INFY.NS': 'Technology',
    'WIPRO.NS': 'Technology',
    'HDFCBANK.NS': 'Banking',
    'ICICIBANK.NS': 'Banking',
    'SBIN.NS': 'Banking',
    'BHARTIARTL.NS': 'Telecom',
    'ITC.NS': 'FMCG',
    'LT.NS': 'Industrials',
    # Pharma Leaders
    'SUNPHARMA.NS': 'Pharma',
    'CIPLA.NS': 'Pharma',
    'DRREDDY.NS': 'Pharma',
    'DIVISLAB.NS': 'Pharma',
    'LUPIN.NS': 'Pharma',
    # Sugar Leaders
    'BALRAMCHIN.NS': 'Sugar',
    'EIDPARRY.NS': 'Sugar',
    'RENUKA.NS': 'Sugar',
    'TRIVENI.NS': 'Sugar',
    'DALMIASUG.NS': 'Sugar'
}


class PortfolioRiskAgent:
    """Agent responsible for gating trade allocations based on aggregate portfolio risk and cross-asset correlation."""
    def __init__(self, correlation_file="data/correlation_matrix.json", max_sector_exposure=0.35, max_correlated_exposure=0.05):
        self.MAX_SECTOR_EXPOSURE = max_sector_exposure
        self.MAX_CORRELATED_EXPOSURE = max_correlated_exposure
        self.max_sector_exposure = max_sector_exposure
        self.max_correlated_exposure = max_correlated_exposure
        
        # Sector mapping for active watchlist
        self.SECTOR_MAP = {
            'Pharma': ['SUNPHARMA.NS', 'CIPLA.NS', 'DRREDDY.NS', 'DIVISLAB.NS', 'LUPIN.NS'],
            'Sugar': ['BALRAMCHIN.NS', 'EIDPARRY.NS', 'RENUKA.NS', 'TRIVENI.NS', 'DALMIASUG.NS'],
            'Technology': ['TCS.NS', 'INFY.NS', 'WIPRO.NS'],
            'Banking': ['HDFCBANK.NS', 'ICICIBANK.NS', 'SBIN.NS'],
            'Energy': ['RELIANCE.NS'],
            'Telecom': ['BHARTIARTL.NS'],
            'FMCG': ['ITC.NS'],
            'Industrials': ['LT.NS']
        }
        
        # Load correlation_matrix.json if it exists, defaulting to empty dict if absent
        self.correlation_matrix = {}
        candidate_paths = [
            correlation_file,
            os.path.join("data", "correlation_matrix.json"),
            os.path.join(os.path.dirname(__file__), "data", "correlation_matrix.json"),
            os.path.join(os.path.dirname(__file__), "..", "data", "correlation_matrix.json")
        ]
        for p in candidate_paths:
            if os.path.exists(p):
                try:
                    import json
                    with open(p, "r") as f:
                        self.correlation_matrix = json.load(f)
                    break
                except Exception as e:
                    print(f"[PortfolioRiskAgent] Warning: Could not load correlation file {p}: {e}")

    def get_ticker_sector(self, ticker):
        """Returns the sector name for a given ticker."""
        if ticker in TICKER_SECTORS:
            return TICKER_SECTORS[ticker]
        for sector, tickers in self.SECTOR_MAP.items():
            if ticker in tickers:
                return sector
        return "Other"

    def check_portfolio_risk(self, open_positions, candidate_ticker=None, target_inr=None, total_portfolio_value=None, 
                             new_trade_ticker=None, new_trade_sector=None, new_trade_value=None, 
                             correlation_matrix=None, current_prices=None):
        """
        Evaluates aggregate portfolio risk and cross-asset correlation before allocating capital.
        
        Args:
            open_positions (dict): Active positions dictionary.
            candidate_ticker (str): Ticker for the proposed new trade.
            target_inr (float): Proposed INR allocation value for the trade.
            total_portfolio_value (float): Current net liquidation value of the portfolio.
            current_prices (dict, optional): Current live prices for positions.
            correlation_matrix (dict or pd.DataFrame, optional): Preloaded 60-day correlation dictionary/matrix.
            
        Returns:
            tuple: (is_approved: bool, rejection_reason: str)
        """
        ticker = candidate_ticker or new_trade_ticker
        value = target_inr if target_inr is not None else (new_trade_value if new_trade_value is not None else 0.0)
        tot_val = total_portfolio_value if total_portfolio_value is not None else 0.0

        if tot_val <= 0:
            return True, "Approved"

        current_prices = current_prices or {}
        corr_data = correlation_matrix if correlation_matrix is not None else self.correlation_matrix
        target_sector = new_trade_sector or self.get_ticker_sector(ticker)

        # 1. Sector Concentration Check: (current_sector_value + target_inr) / total_portfolio_value > MAX_SECTOR_EXPOSURE
        current_sector_value = 0.0
        for pos_ticker, pos in open_positions.items():
            if pos_ticker == ticker:
                continue
            pos_sec = self.get_ticker_sector(pos_ticker)
            if pos_sec == target_sector:
                price = current_prices.get(pos_ticker, pos.get("entry_price", 0.0))
                current_sector_value += pos.get("shares", 0) * price

        proposed_sector_value = current_sector_value + value
        proposed_sector_ratio = proposed_sector_value / tot_val

        if proposed_sector_ratio > self.MAX_SECTOR_EXPOSURE:
            reason = f"Sector exposure limit exceeded: {target_sector} exposure would reach {proposed_sector_ratio:.1%} (Max: {self.MAX_SECTOR_EXPOSURE:.1%})"
            return False, reason

        # 2. Pairwise Correlation Check:
        # Correlated Exposure = sum_i ( (Position Value_i / Total Portfolio Value) * max(0, rho_i,candidate) )
        if corr_data and len(open_positions) > 0:
            correlated_exposure = 0.0

            for pos_ticker, pos in open_positions.items():
                if pos_ticker == ticker:
                    continue
                price = current_prices.get(pos_ticker, pos.get("entry_price", 0.0))
                pos_val = pos.get("shares", 0) * price
                weight_i = pos_val / tot_val

                # Look up Pearson correlation coefficient rho between pos_ticker and candidate_ticker
                rho = 0.0
                if isinstance(corr_data, pd.DataFrame):
                    if ticker in corr_data.index and pos_ticker in corr_data.columns:
                        rho = float(corr_data.loc[ticker, pos_ticker])
                    elif pos_ticker in corr_data.index and ticker in corr_data.columns:
                        rho = float(corr_data.loc[pos_ticker, ticker])
                elif isinstance(corr_data, dict):
                    if ticker in corr_data and isinstance(corr_data[ticker], dict):
                        rho = float(corr_data[ticker].get(pos_ticker, 0.0))
                    elif pos_ticker in corr_data and isinstance(corr_data[pos_ticker], dict):
                        rho = float(corr_data[pos_ticker].get(ticker, 0.0))
                    elif (ticker, pos_ticker) in corr_data:
                        rho = float(corr_data[(ticker, pos_ticker)])
                    elif (pos_ticker, ticker) in corr_data:
                        rho = float(corr_data[(pos_ticker, ticker)])

                # Accumulate positive correlation exposure
                correlated_exposure += weight_i * max(0.0, rho)

            if correlated_exposure > self.MAX_CORRELATED_EXPOSURE:
                reason = f"Portfolio correlation limit exceeded: Weighted correlated exposure {correlated_exposure:.4f} > Max {self.MAX_CORRELATED_EXPOSURE:.4f}"
                return False, reason

        return True, "Approved"


def compute_60d_correlation_matrix(tickers=None, data_dir="data", save_json=True):
    """Computes or loads the 60-day price return correlation matrix across active tickers."""
    tickers = tickers or list(TICKER_SECTORS.keys())
    close_series = {}

    candidates = [
        data_dir,
        os.path.join(os.path.dirname(__file__), "data"),
        os.path.join(os.path.dirname(__file__), "..", "data"),
        "data"
    ]

    for ticker in tickers:
        for c in candidates:
            feat_file = os.path.join(c, f"{ticker}_features.csv")
            raw_file = os.path.join(c, f"{ticker}_raw.csv")
            target_f = feat_file if os.path.exists(feat_file) else (raw_file if os.path.exists(raw_file) else None)
            if target_f:
                try:
                    df = pd.read_csv(target_f)
                    if "Close" in df.columns:
                        close_series[ticker] = df["Close"].tail(60).reset_index(drop=True)
                        break
                except Exception:
                    pass

    if len(close_series) >= 2:
        price_df = pd.DataFrame(close_series)
        corr_df = price_df.pct_change().dropna().corr()
        if save_json:
            try:
                import json
                json_path = os.path.join(data_dir, "correlation_matrix.json")
                os.makedirs(os.path.dirname(json_path) or ".", exist_ok=True)
                with open(json_path, "w") as f:
                    json.dump(corr_df.to_dict(), f, indent=4)
            except Exception:
                pass
        return corr_df
    return pd.DataFrame()


class RiskAgent:
    """Agent responsible for risk controls: stop-loss, take-profit, and position sizing."""
    def __init__(self, stop_loss_pct=0.02, take_profit_pct=0.05, max_allocation_pct=0.20, trailing_stop_loss_pct=0.02):
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_allocation_pct = max_allocation_pct
        self.trailing_stop_loss_pct = trailing_stop_loss_pct

    def approve_order(self, open_positions, candidate_ticker, target_inr, total_portfolio_value, portfolio_risk_agent=None, current_prices=None):
        """Runs PortfolioRiskAgent.check_portfolio_risk() prior to computing share sizes, logging the exact rejection reason if blocked."""
        if portfolio_risk_agent is not None:
            approved, reason = portfolio_risk_agent.check_portfolio_risk(
                open_positions=open_positions,
                candidate_ticker=candidate_ticker,
                target_inr=target_inr,
                total_portfolio_value=total_portfolio_value,
                current_prices=current_prices
            )
            if not approved:
                print(f"[PortfolioRiskAgent Rejection] Order for {candidate_ticker} blocked: {reason}")
                return False, reason
        return True, "Approved"

    def check_position_risk(self, ticker, current_price, entry_price, peak_price):
        """Checks if a position has breached trailing stop-loss, fixed stop-loss, or take-profit boundaries."""
        # 1. Check Take-Profit from initial entry price
        price_change_pct = (current_price - entry_price) / entry_price
        if price_change_pct >= self.take_profit_pct:
            return True, "Take-Profit Breached"
            
        # 2. Check Fixed Stop-Loss from initial entry price
        if price_change_pct <= -self.stop_loss_pct:
            return True, "Stop-Loss Breached"
            
        # 3. Check Trailing Stop-Loss from highest recorded peak price
        if peak_price and peak_price > entry_price:
            trailing_drawdown_pct = (peak_price - current_price) / peak_price
            if trailing_drawdown_pct >= self.trailing_stop_loss_pct:
                return True, "Trailing Stop-Loss Breached"
                
        return False, None

    def calculate_buy_allocation(self, initial_capital, current_cash):
        """Allocates a portion of capital per trade if cash is available."""
        allocation = initial_capital * self.max_allocation_pct
        if current_cash >= allocation:
            return allocation
        return 0.0

    def calculate_kelly_allocation(self, confidence, tp_pct, sl_pct, total_portfolio_value, available_cash):
        """Calculates dynamic capital allocation using the Half-Kelly Criterion.
        
        Args:
            confidence (float): Probability prediction score from model [0.0, 1.0].
            tp_pct (float): Take-profit threshold percent (e.g. 0.05 for 5%).
            sl_pct (float): Stop-loss threshold percent (e.g. 0.02 for 2%).
            total_portfolio_value (float): Current net asset value of the portfolio.
            available_cash (float): Liquid cash balance in the account.
            
        Returns:
            float: Sized allocation amount in INR.
        """
        b = tp_pct / max(sl_pct, 0.001)
        f = confidence - (1.0 - confidence) / b
        f_kelly = 0.5 * f
        f_kelly = max(0.02, min(f_kelly, 0.20))
        target_inr = total_portfolio_value * f_kelly
        return min(target_inr, available_cash)

    def rebalance_for_high_conviction(self, execution_agent, required_inr, incoming_confidence, current_prices, date):
        """Forcefully sells lowest confidence/return positions to free up cash for high-conviction signals."""
        if incoming_confidence < 0.68:
            return execution_agent.current_cash
            
        if execution_agent.current_cash >= required_inr:
            return execution_agent.current_cash

        active_positions = execution_agent.active_positions
        if not active_positions:
            return execution_agent.current_cash

        weakest_ticker = None
        weakest_confidence = 1.0
        weakest_return_pct = float('inf')

        for ticker, pos in active_positions.items():
            conf = pos.get("confidence_score")
            if conf is None:
                conf = 0.57
                
            entry_price = pos["entry_price"]
            curr_price = current_prices.get(ticker, entry_price)
            return_pct = (curr_price - entry_price) / entry_price
            
            if conf < weakest_confidence:
                weakest_confidence = conf
                weakest_return_pct = return_pct
                weakest_ticker = ticker
            elif abs(conf - weakest_confidence) < 1e-5:
                if return_pct < weakest_return_pct:
                    weakest_confidence = conf
                    weakest_return_pct = return_pct
                    weakest_ticker = ticker

        if weakest_ticker is not None:
            if incoming_confidence >= weakest_confidence + 0.10:
                print(f"[{date}] [REBALANCING] Incoming signal confidence ({incoming_confidence:.1%}) is at least 10% higher than weakest position {weakest_ticker} confidence ({weakest_confidence:.1%}). Force closing {weakest_ticker} to recycle capital.")
                current_price = current_prices.get(weakest_ticker)
                if current_price is not None:
                    execution_agent.sell_asset(
                        weakest_ticker, 
                        date, 
                        current_price, 
                        reason="Capital Recycling (Recycled for High Conviction)"
                    )
                else:
                    print(f"Warning: Cannot sell {weakest_ticker} because current price is missing.")
                    
        return execution_agent.current_cash


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
                # Initialize or update peak price
                entry_price = position["entry_price"]
                peak_price = position.get("peak_price", entry_price)
                if current_price > peak_price:
                    position["peak_price"] = current_price
                    peak_price = current_price
                    
                should_sell, reason = risk_agent.check_position_risk(
                    ticker, current_price, entry_price, peak_price=peak_price
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
                    total_port_val = execution_agent.get_portfolio_value(current_prices)
                    allocation = risk_agent.calculate_kelly_allocation(
                        confidence,
                        tp_pct=risk_agent.take_profit_pct,
                        sl_pct=risk_agent.trailing_stop_loss_pct,
                        total_portfolio_value=total_port_val,
                        available_cash=execution_agent.current_cash
                    )
                    if allocation > 0:
                        execution_agent.place_buy_order(
                            ticker, 
                            date, 
                            current_price, 
                            allocation,
                            current_prices=current_prices,
                            risk_agent=risk_agent,
                            kelly_fraction=None,
                            confidence_score=confidence
                        )

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