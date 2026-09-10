import json
import os
import pytest
from paper_broker import ExecutionAgent, RiskAgent, calculate_dynamic_slippage

def test_prune_worst_position_success(tmp_path, capsys):
    """Test that when cash is exhausted and candidate has +10% confidence premium, weakest position is pruned."""
    portfolio_file = str(tmp_path / "portfolio.json")
    risk = RiskAgent()

    initial_cash = 2000.0  # < 5000 and < 5% of 100k
    total_val = 100000.0
    incoming_conf = 0.70

    portfolio = {
        "cash": initial_cash,
        "positions": {
            "CIPLA.NS": {
                "ticker": "CIPLA.NS",
                "entry_price": 1000.0,
                "current_price": 965.0,  # PnL: -3.5%
                "quantity": 10,
                "shares": 10,
                "confidence": 0.55
            },
            "SUNPHARMA.NS": {
                "ticker": "SUNPHARMA.NS",
                "entry_price": 1500.0,
                "current_price": 1530.0,  # PnL: +2.0%
                "quantity": 10,
                "shares": 10,
                "confidence": 0.65
            }
        },
        "closed_trades": []
    }

    current_prices = {
        "CIPLA.NS": 965.0,
        "SUNPHARMA.NS": 1530.0
    }

    result = risk.prune_worst_position(
        open_positions=portfolio["positions"],
        incoming_candidate_confidence=incoming_conf,
        available_cash=portfolio["cash"],
        total_portfolio_value=total_val,
        current_prices=current_prices,
        portfolio=portfolio,
        portfolio_path=portfolio_file
    )

    captured = capsys.readouterr().out
    assert result is True
    assert "[PORTFOLIO PRUNING] Liquidated CIPLA.NS (PnL: -3.50%) to fund high-conviction candidate (Confidence: 0.70)." in captured

    # Verify CIPLA was removed from active positions and SUNPHARMA remains
    assert "CIPLA.NS" not in portfolio["positions"]
    assert "SUNPHARMA.NS" in portfolio["positions"]

    # Verify closed trades record
    assert len(portfolio["closed_trades"]) == 1
    assert portfolio["closed_trades"][0]["ticker"] == "CIPLA.NS"
    assert portfolio["closed_trades"][0]["exit_reason"] == "PORTFOLIO_PRUNING"

    # Verify cash was reclaimed
    qty = 10
    cp = 965.0
    slippage = calculate_dynamic_slippage(cp, qty)
    exec_price = cp - slippage
    fees = (exec_price * qty) * 0.0012
    net_proceeds = (cp * qty) - ((slippage * qty) + fees)
    expected_cash = initial_cash + net_proceeds

    assert pytest.approx(portfolio["cash"], 0.01) == expected_cash

    # Verify immediate persistence
    assert os.path.exists(portfolio_file)
    with open(portfolio_file, "r") as f:
        persisted = json.load(f)
    assert "CIPLA.NS" not in persisted["positions"]
    assert pytest.approx(persisted["cash"], 0.01) == expected_cash


def test_prune_worst_position_rejected_insufficient_premium(capsys):
    """Test that pruning is rejected when incoming candidate does not have +10% premium over weakest position."""
    risk = RiskAgent()
    initial_cash = 1500.0
    total_val = 100000.0

    open_positions = {
        "TCS.NS": {
            "ticker": "TCS.NS",
            "entry_price": 3000.0,
            "current_price": 3030.0,
            "quantity": 5,
            "confidence": 0.62
        }
    }

    # Incoming confidence 0.68 is < 0.62 + 0.10 (0.72)
    incoming_conf = 0.68

    result = risk.prune_worst_position(
        open_positions=open_positions,
        incoming_candidate_confidence=incoming_conf,
        available_cash=initial_cash,
        total_portfolio_value=total_val
    )

    captured = capsys.readouterr().out
    assert result is False
    assert "[PORTFOLIO PRUNING] Pruning rejected: Incoming candidate confidence (0.68) does not exceed weakest position threshold by at least +0.10. Maintaining existing holdings." in captured
    assert "TCS.NS" in open_positions


def test_prune_worst_position_sufficient_cash_no_op():
    """Test that when cash is sufficient (>= 5000 and >= 5%), no pruning is executed and True is returned."""
    risk = RiskAgent()
    cash = 25000.0
    total_val = 100000.0

    open_positions = {
        "INFY.NS": {
            "ticker": "INFY.NS",
            "entry_price": 1500.0,
            "quantity": 10,
            "confidence": 0.50
        }
    }

    result = risk.prune_worst_position(
        open_positions=open_positions,
        incoming_candidate_confidence=0.75,
        available_cash=cash,
        total_portfolio_value=total_val
    )

    assert result is True
    assert "INFY.NS" in open_positions


def test_execution_agent_pruning_integration(tmp_path, capsys):
    """Test integration of prune_worst_position with ExecutionAgent."""
    portfolio_file = str(tmp_path / "portfolio.json")
    agent = ExecutionAgent(initial_capital=100000.0, portfolio_file=portfolio_file)
    agent.current_cash = 1000.0  # Force cash-exhausted state

    agent.active_positions["WIPRO.NS"] = {
        "ticker": "WIPRO.NS",
        "entry_price": 400.0,
        "quantity": 25,
        "shares": 25,
        "confidence": 0.54
    }

    risk = RiskAgent()
    current_prices = {"WIPRO.NS": 392.0}  # PnL: -2.0%

    result = risk.prune_worst_position(
        open_positions=agent.active_positions,
        incoming_candidate_confidence=0.72,
        available_cash=agent.current_cash,
        total_portfolio_value=100000.0,
        current_prices=current_prices,
        execution_agent=agent,
        portfolio=agent.portfolio,
        portfolio_path=portfolio_file
    )

    captured = capsys.readouterr().out
    assert result is True
    assert "[PORTFOLIO PRUNING] Liquidated WIPRO.NS (PnL: -2.00%) to fund high-conviction candidate (Confidence: 0.72)." in captured

    assert "WIPRO.NS" not in agent.active_positions
    assert "WIPRO.NS" in agent.cooldowns
    assert agent.current_cash > 10000.0
    assert len(agent.trade_log) == 1
    assert agent.trade_log[0]["exit_reason"] == "PORTFOLIO_PRUNING"
