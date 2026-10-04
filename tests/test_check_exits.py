import json
import os
import pytest
from paper_broker import ExecutionAgent, check_exits, calculate_dynamic_slippage

def test_stop_loss_triggered(tmp_path, capsys):
    """Test that a stop-loss breach triggers an immediate market sell exit and updates portfolio."""
    portfolio_file = str(tmp_path / "portfolio.json")
    initial_cash = 50000.0
    entry_price = 1000.0
    quantity = 10
    current_price = 960.0  # -4.0%, breaches default stop_loss_pct of 0.03 (-3%)

    portfolio = {
        "cash": initial_cash,
        "positions": {
            "TCS.NS": {
                "ticker": "TCS.NS",
                "entry_price": entry_price,
                "quantity": quantity,
                "shares": quantity,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.04
            }
        },
        "closed_trades": []
    }

    current_market_prices = {"TCS.NS": current_price}
    closed = check_exits(current_market_prices, portfolio=portfolio, portfolio_path=portfolio_file)

    captured = capsys.readouterr().out
    assert "[STOP-LOSS HIT] Closed TCS.NS at INR 960.00 (Loss: -4.00%)." in captured

    assert len(closed) == 1
    assert closed[0]["ticker"] == "TCS.NS"
    assert closed[0]["exit_reason"] == "STOP_LOSS"
    assert closed[0]["exit_price"] == current_price

    # Verify positions container no longer contains TCS.NS
    assert "TCS.NS" not in portfolio["positions"]

    # Verify closed trades list
    assert len(portfolio["closed_trades"]) == 1
    assert portfolio["closed_trades"][0]["exit_reason"] == "STOP_LOSS"

    # Verify dynamic slippage and cash update
    total_slippage = calculate_dynamic_slippage(current_price, quantity)
    exec_price = current_price - total_slippage
    expected_fees = (exec_price * quantity) * 0.0012
    slippage_and_brokerage = (total_slippage * quantity) + expected_fees
    expected_cash = initial_cash + (current_price * quantity) - slippage_and_brokerage

    assert pytest.approx(portfolio["cash"], 0.01) == expected_cash

    # Verify immediate persistence to file
    assert os.path.exists(portfolio_file)
    with open(portfolio_file, "r") as f:
        persisted = json.load(f)
    assert pytest.approx(persisted["cash"], 0.01) == expected_cash
    assert "TCS.NS" not in persisted["positions"]
    assert len(persisted["closed_trades"]) == 1


def test_take_profit_triggered(tmp_path, capsys):
    """Test that a take-profit breach triggers an immediate exit, credits cash, and logs."""
    portfolio_file = str(tmp_path / "portfolio.json")
    initial_cash = 20000.0
    entry_price = 500.0
    quantity = 20
    current_price = 525.0  # +5.0%, breaches default take_profit_pct of 0.04 (+4%)

    portfolio = {
        "cash": initial_cash,
        "positions": {
            "INFY.NS": {
                "ticker": "INFY.NS",
                "entry_price": entry_price,
                "quantity": quantity,
                "shares": quantity,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.04
            }
        },
        "closed_trades": []
    }

    current_market_prices = {"INFY.NS": current_price}
    closed = check_exits(current_market_prices, portfolio=portfolio, portfolio_path=portfolio_file)

    captured = capsys.readouterr().out
    assert "[TAKE-PROFIT HIT] Closed INFY.NS at INR 525.00 (Gain: 5.00%)." in captured

    assert len(closed) == 1
    assert closed[0]["ticker"] == "INFY.NS"
    assert closed[0]["exit_reason"] == "TAKE_PROFIT"

    assert "INFY.NS" not in portfolio["positions"]
    assert len(portfolio["closed_trades"]) == 1

    total_slippage = calculate_dynamic_slippage(current_price, quantity)
    exec_price = current_price - total_slippage
    expected_fees = (exec_price * quantity) * 0.0012
    slippage_and_brokerage = (total_slippage * quantity) + expected_fees
    expected_cash = initial_cash + (current_price * quantity) - slippage_and_brokerage

    assert pytest.approx(portfolio["cash"], 0.01) == expected_cash


def test_missing_or_zero_price_skips_and_warns(tmp_path, capsys):
    """Test that missing or zero price skips exit evaluation and logs a warning."""
    portfolio_file = str(tmp_path / "portfolio.json")
    portfolio = {
        "cash": 10000.0,
        "positions": {
            "CIPLA.NS": {
                "ticker": "CIPLA.NS",
                "entry_price": 1000.0,
                "quantity": 10
            },
            "DRREDDY.NS": {
                "ticker": "DRREDDY.NS",
                "entry_price": 5000.0,
                "quantity": 2
            }
        },
        "closed_trades": []
    }

    # CIPLA has price 0.0, DRREDDY is missing completely
    current_market_prices = {"CIPLA.NS": 0.0}
    closed = check_exits(current_market_prices, portfolio=portfolio, portfolio_path=portfolio_file)

    captured = capsys.readouterr().out
    assert "Warning: Market price for CIPLA.NS is missing or zero. Skipping exit evaluation." in captured
    assert "Warning: Market price for DRREDDY.NS is missing or zero. Skipping exit evaluation." in captured

    assert len(closed) == 0
    assert "CIPLA.NS" in portfolio["positions"]
    assert "DRREDDY.NS" in portfolio["positions"]
    assert len(portfolio["closed_trades"]) == 0


def test_neutral_position_not_exited(tmp_path):
    """Test that positions within the profit/loss thresholds are not exited."""
    portfolio_file = str(tmp_path / "portfolio.json")
    portfolio = {
        "cash": 10000.0,
        "positions": {
            "WIPRO.NS": {
                "ticker": "WIPRO.NS",
                "entry_price": 400.0,
                "quantity": 25,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.04
            }
        },
        "closed_trades": []
    }

    # +1.25% gain (between -3% and +4%)
    current_market_prices = {"WIPRO.NS": 405.0}
    closed = check_exits(current_market_prices, portfolio=portfolio, portfolio_path=portfolio_file)

    assert len(closed) == 0
    assert "WIPRO.NS" in portfolio["positions"]
    assert len(portfolio["closed_trades"]) == 0


def test_list_based_positions_container(tmp_path, capsys):
    """Test that portfolio['positions'] structured as a list is supported properly."""
    portfolio_file = str(tmp_path / "portfolio.json")
    portfolio = {
        "cash": 15000.0,
        "positions": [
            {
                "ticker": "LT.NS",
                "entry_price": 3000.0,
                "quantity": 5,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.04
            }
        ],
        "closed_trades": []
    }

    # -5% loss -> trigger stop loss
    current_market_prices = {"LT.NS": 2850.0}
    closed = check_exits(current_market_prices, portfolio=portfolio, portfolio_path=portfolio_file)

    captured = capsys.readouterr().out
    assert "[STOP-LOSS HIT] Closed LT.NS at INR 2850.00 (Loss: -5.00%)." in captured
    assert len(closed) == 1
    assert len(portfolio["positions"]) == 0
    assert len(portfolio["closed_trades"]) == 1


def test_execution_agent_check_exits_integration(tmp_path, capsys):
    """Test ExecutionAgent.check_exits method syncs cash, positions, trade_log and cooldowns."""
    portfolio_file = str(tmp_path / "portfolio.json")
    agent = ExecutionAgent(initial_capital=100000.0, portfolio_file=portfolio_file)
    agent.active_positions["SBIN.NS"] = {
        "ticker": "SBIN.NS",
        "entry_price": 800.0,
        "quantity": 10,
        "shares": 10,
        "stop_loss_pct": 0.03,
        "take_profit_pct": 0.04
    }

    # +5% profit -> trigger take profit
    current_market_prices = {"SBIN.NS": 840.0}
    closed = agent.check_exits(current_market_prices, portfolio_path=portfolio_file)

    captured = capsys.readouterr().out
    assert "[TAKE-PROFIT HIT] Closed SBIN.NS at INR 840.00 (Gain: 5.00%)." in captured
    assert len(closed) == 1
    assert "SBIN.NS" not in agent.active_positions
    assert len(agent.trade_log) == 1
    assert agent.trade_log[0]["exit_reason"] == "TAKE_PROFIT"
    assert "SBIN.NS" in agent.cooldowns
    assert agent.current_cash > 100000.0


def test_trailing_stop_loss_ratchet_locks_in_profit(tmp_path, capsys):
    """Test that Trailing Stop-Loss Ratchet locks in profit when price pulls back 3% from a peak gain >= 3%."""
    from paper_broker import check_exits
    portfolio_file = str(tmp_path / "portfolio.json")
    initial_cash = 50000.0
    entry_price = 1000.0
    quantity = 10
    
    # Position peaked at 1050 (+5% gain), current price pulled back to 1015 (-3.33% from peak)
    portfolio = {
        "cash": initial_cash,
        "positions": {
            "RELIANCE.NS": {
                "ticker": "RELIANCE.NS",
                "entry_price": entry_price,
                "peak_price": 1050.0,
                "quantity": quantity,
                "shares": quantity,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06,
                "trailing_stop_loss_pct": 0.03
            }
        },
        "closed_trades": []
    }

    # Price at 1015.0 (down from 1050.0 peak)
    current_market_prices = {"RELIANCE.NS": 1015.0}
    closed = check_exits(current_market_prices, portfolio=portfolio, portfolio_path=portfolio_file)

    assert len(closed) == 1
    assert closed[0]["ticker"] == "RELIANCE.NS"
    assert closed[0]["exit_reason"] == "TRAILING_STOP_LOSS_RATCHET"
    assert "RELIANCE.NS" not in portfolio["positions"]
    assert len(portfolio["closed_trades"]) == 1
    assert portfolio["closed_trades"][0]["realized_pnl"] > 0.0
