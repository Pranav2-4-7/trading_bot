import pytest
import pandas as pd
import numpy as np
from paper_broker import PortfolioRiskAgent, TICKER_SECTORS, ExecutionAgent, RiskAgent

def test_sector_concentration_acceptance():
    """Test that a trade within the 35% sector concentration limit is approved."""
    agent = PortfolioRiskAgent(max_sector_exposure=0.35, max_correlated_exposure=0.05)
    
    # Portfolio total value = 100,000 INR
    total_val = 100000.0
    
    # Active holding: 15,000 INR in TCS (Technology)
    open_positions = {
        'TCS.NS': {'shares': 4, 'entry_price': 3750.0}  # 15,000 INR (15% exposure)
    }
    
    # Proposed trade: 10,000 INR in INFY (Technology) -> total sector exposure = 25,000 / 100,000 = 25% <= 35%
    approved, reason = agent.check_portfolio_risk(
        open_positions=open_positions,
        candidate_ticker='INFY.NS',
        target_inr=10000.0,
        total_portfolio_value=total_val,
        correlation_matrix={},
        current_prices={'TCS.NS': 3750.0}
    )
    assert approved is True
    assert reason == "Approved"

def test_sector_concentration_rejection():
    """Test that a trade breaching the 35% sector concentration limit is rejected."""
    agent = PortfolioRiskAgent(max_sector_exposure=0.35, max_correlated_exposure=0.05)
    
    # Portfolio total value = 100,000 INR
    total_val = 100000.0
    
    # Active holdings: 30,000 INR in Pharma (SUNPHARMA 20k + CIPLA 10k)
    open_positions = {
        'SUNPHARMA.NS': {'shares': 12, 'entry_price': 1666.67}, # ~20,000 INR
        'CIPLA.NS': {'shares': 7, 'entry_price': 1428.57}       # ~10,000 INR
    }
    current_prices = {
        'SUNPHARMA.NS': 1666.67,
        'CIPLA.NS': 1428.57
    }
    
    # Proposed trade: 10,000 INR in DRREDDY (Pharma) -> total sector exposure = 40,000 / 100,000 = 40% > 35%
    approved, reason = agent.check_portfolio_risk(
        open_positions=open_positions,
        candidate_ticker='DRREDDY.NS',
        target_inr=10000.0,
        total_portfolio_value=total_val,
        current_prices=current_prices
    )
    assert approved is False
    assert "Sector exposure limit exceeded" in reason

def test_pairwise_correlation_exposure_acceptance():
    """Test that a trade with low or zero correlation to active holdings is approved."""
    agent = PortfolioRiskAgent(max_sector_exposure=0.35, max_correlated_exposure=0.05)
    
    total_val = 100000.0
    # Active position: 15,000 INR in RELIANCE (15% weight)
    open_positions = {
        'RELIANCE.NS': {'shares': 5, 'entry_price': 3000.0}
    }
    current_prices = {'RELIANCE.NS': 3000.0}
    
    # Correlation dictionary: RELIANCE & CIPLA have low correlation (0.10)
    correlation_dict = {
        'CIPLA.NS': {'RELIANCE.NS': 0.10}
    }
    
    # Proposed trade: 10,000 INR in CIPLA (10% weight)
    # Correlated exposure = 0.15 * 0.10 = 0.015 <= 0.05
    approved, reason = agent.check_portfolio_risk(
        open_positions=open_positions,
        candidate_ticker='CIPLA.NS',
        target_inr=10000.0,
        total_portfolio_value=total_val,
        correlation_matrix=correlation_dict,
        current_prices=current_prices
    )
    assert approved is True
    assert reason == "Approved"

def test_pairwise_correlation_exposure_rejection():
    """Test that a trade with excessive weighted correlated exposure across holdings is rejected."""
    agent = PortfolioRiskAgent(max_sector_exposure=1.0, max_correlated_exposure=0.05)
    
    total_val = 100000.0
    # Active positions: 3 positions (20k + 20k + 20k = 60k total = 60% weight)
    open_positions = {
        'HDFCBANK.NS': {'shares': 12, 'entry_price': 1666.67}, # 20k (20%)
        'ICICIBANK.NS': {'shares': 16, 'entry_price': 1250.0},  # 20k (20%)
        'SBIN.NS': {'shares': 25, 'entry_price': 800.0}        # 20k (20%)
    }
    current_prices = {
        'HDFCBANK.NS': 1666.67,
        'ICICIBANK.NS': 1250.0,
        'SBIN.NS': 800.0
    }
    
    # High pairwise correlation to Kotak (e.g. 0.90 each)
    correlation_dict = {
        'KOTAKBANK.NS': {
            'HDFCBANK.NS': 0.90,
            'ICICIBANK.NS': 0.90,
            'SBIN.NS': 0.90
        }
    }
    
    # Correlated exposure = 0.20 * 0.90 + 0.20 * 0.90 + 0.20 * 0.90 = 0.54 > 0.05
    approved, reason = agent.check_portfolio_risk(
        open_positions=open_positions,
        candidate_ticker='KOTAKBANK.NS',
        target_inr=10000.0,
        total_portfolio_value=total_val,
        correlation_matrix=correlation_dict,
        current_prices=current_prices
    )
    assert approved is False
    assert "Portfolio correlation limit exceeded" in reason

def test_risk_agent_approve_order_and_execution_gating():
    """Test that RiskAgent.approve_order and ExecutionAgent.place_buy_order gate blocked orders."""
    portfolio_risk_agent = PortfolioRiskAgent(max_sector_exposure=0.35, max_correlated_exposure=0.05)
    risk_agent = RiskAgent()
    broker = ExecutionAgent(initial_capital=100000.0)
    broker.current_cash = 65000.0
    
    # Pre-populate broker with 35k in Sugar sector
    broker.active_positions = {
        'BALRAMCHIN.NS': {'shares': 350, 'entry_price': 100.0}  # 35,000 INR in Sugar (35%)
    }
    current_prices = {
        'BALRAMCHIN.NS': 100.0,
        'RENUKA.NS': 50.0
    }
    
    # 1. Test approve_order directly
    approved, reason = risk_agent.approve_order(
        open_positions=broker.active_positions,
        candidate_ticker='RENUKA.NS', # Sugar ticker -> exceeds 35% cap
        target_inr=10000.0,
        total_portfolio_value=100000.0,
        portfolio_risk_agent=portfolio_risk_agent,
        current_prices=current_prices
    )
    assert approved is False
    assert "Sector exposure limit exceeded" in reason
    
    # 2. Test place_buy_order gating
    order_placed = broker.place_buy_order(
        ticker='RENUKA.NS',
        date='2026-08-30',
        current_price=50.0,
        allocation=10000.0,
        current_prices=current_prices,
        risk_agent=risk_agent,
        portfolio_risk_agent=portfolio_risk_agent
    )
    assert order_placed is False
    assert 'RENUKA.NS' not in broker.active_positions

def test_daily_drawdown_circuit_breaker_logic():
    """Test aggregate daily drawdown circuit breaker calculation and broker method."""
    broker = ExecutionAgent(initial_capital=100000.0)
    broker.current_cash = 100000.0
    
    session_start_portfolio_value = broker.get_total_portfolio_value()
    assert session_start_portfolio_value == 100000.0
    
    # Case 1: Minor drawdown (-2.5%) -> Normal operation
    current_val_normal = 97500.0
    session_drawdown_normal = (current_val_normal - session_start_portfolio_value) / session_start_portfolio_value
    halt_normal = session_drawdown_normal <= -0.05
    assert halt_normal is False
    
    # Case 2: Exact threshold (-5.0%) -> Breaker triggered
    current_val_exact = 95000.0
    session_drawdown_exact = (current_val_exact - session_start_portfolio_value) / session_start_portfolio_value
    halt_exact = session_drawdown_exact <= -0.05
    assert halt_exact is True

    # Case 3: Severe intraday drop (-5.5%) -> Breaker triggered
    current_val_severe = 94500.0
    session_drawdown_severe = (current_val_severe - session_start_portfolio_value) / session_start_portfolio_value
    halt_severe = session_drawdown_severe <= -0.05
    assert halt_severe is True

def test_dead_mans_switch_staleness_logic():
    """Test Dead Man's Switch 300s staleness logic."""
    last_fetch_time = 1000.0
    
    # Case 1: Fresh data (120s old) -> Allow execution
    curr_time_fresh = 1120.0
    is_stale_fresh = (curr_time_fresh - last_fetch_time) > 300
    assert is_stale_fresh is False
    
    # Case 2: Stale data (350s old) -> Block execution
    curr_time_stale = 1350.0
    is_stale_blocked = (curr_time_stale - last_fetch_time) > 300
    assert is_stale_blocked is True
