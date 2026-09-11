import json
import time
import pytest
from paper_broker import (
    ExecutionAgent, 
    RiskAgent, 
    check_exits, 
    cooldown_registry, 
    record_stop_loss_cooldown
)

def test_stop_loss_records_lockout_timestamp(tmp_path):
    """Test that hitting a stop-loss exit automatically records a 4-hour lockout in cooldown_registry."""
    portfolio_file = str(tmp_path / "portfolio.json")
    ticker = "TCS.NS"
    now_ts = 1000000.0

    portfolio = {
        "cash": 50000.0,
        "positions": {
            ticker: {
                "ticker": ticker,
                "entry_price": 1000.0,
                "quantity": 10,
                "shares": 10,
                "stop_loss_pct": 0.03
            }
        },
        "closed_trades": []
    }

    # -5% loss breaches 3% stop-loss
    current_prices = {ticker: 950.0}
    check_exits(current_prices, portfolio=portfolio, portfolio_path=portfolio_file, date="2026-09-11 10:00:00")

    assert ticker in cooldown_registry
    expected_lockout = cooldown_registry[ticker]
    assert expected_lockout > 0


def test_reentry_blocked_during_lockout_without_reversal(capsys):
    """Test that approve_order blocks buy orders during active lockout when reversal setup is not confirmed."""
    risk = RiskAgent()
    ticker = "INFY.NS"
    now = time.time()
    lockout_time = now + (4 * 3600)
    cooldown_registry[ticker] = lockout_time

    # Normal RSI and dist_s2 (not oversold exhaustion)
    approved, reason = risk.approve_order(
        open_positions={},
        candidate_ticker=ticker,
        target_inr=10000.0,
        total_portfolio_value=100000.0,
        rsi_14=45.0,
        dist_s2=-0.02,
        current_timestamp=now
    )

    captured = capsys.readouterr().out
    assert approved is False
    assert f"[RE-ENTRY GUARD] Rejected {ticker}. In cooldown until {lockout_time} without confirmed reversal setup." in captured
    assert "In cooldown until" in reason


def test_reentry_allowed_during_lockout_with_confirmed_reversal(capsys):
    """Test that approve_order allows buy orders during active lockout if asset exhibits confirmed oversold exhaustion: rsi < 30 AND Dist_S2 >= -0.01."""
    risk = RiskAgent()
    ticker = "CIPLA.NS"
    now = time.time()
    lockout_time = now + (4 * 3600)
    cooldown_registry[ticker] = lockout_time

    # Confirmed oversold exhaustion reversal setup: RSI 24.5 (< 30) and Dist_S2 -0.005 (>= -0.01)
    approved, reason = risk.approve_order(
        open_positions={},
        candidate_ticker=ticker,
        target_inr=10000.0,
        total_portfolio_value=100000.0,
        rsi_14=24.5,
        dist_s2=-0.005,
        current_timestamp=now
    )

    captured = capsys.readouterr().out
    assert approved is True
    assert reason == "Approved"
    assert "[RE-ENTRY GUARD]" not in captured


def test_reentry_allowed_after_lockout_expired():
    """Test that approve_order allows buy orders after lockout has expired without needing oversold condition."""
    risk = RiskAgent()
    ticker = "WIPRO.NS"
    now = time.time()
    # Expired lockout (set in the past)
    cooldown_registry[ticker] = now - 60

    approved, reason = risk.approve_order(
        open_positions={},
        candidate_ticker=ticker,
        target_inr=10000.0,
        total_portfolio_value=100000.0,
        rsi_14=55.0,
        dist_s2=-0.05,
        current_timestamp=now
    )

    assert approved is True
    assert reason == "Approved"


def test_execution_agent_place_buy_order_gated_by_reentry_guard(capsys):
    """Test that ExecutionAgent.place_buy_order gates candidates in active lockout without reversal setup."""
    risk = RiskAgent()
    broker = ExecutionAgent(initial_capital=100000.0)
    ticker = "SBIN.NS"
    now = time.time()
    lockout_time = now + (4 * 3600)
    cooldown_registry[ticker] = lockout_time

    order_placed = broker.place_buy_order(
        ticker=ticker,
        date="2026-09-11 12:00:00",
        current_price=800.0,
        allocation=10000.0,
        current_prices={ticker: 800.0},
        risk_agent=risk,
        rsi_14=42.0,
        dist_s2=-0.03
    )

    captured = capsys.readouterr().out
    assert order_placed is False
    assert ticker not in broker.active_positions
    assert f"[RE-ENTRY GUARD] Rejected {ticker}. In cooldown until {lockout_time} without confirmed reversal setup." in captured
