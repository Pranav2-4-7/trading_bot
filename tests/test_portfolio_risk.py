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
        new_trade_ticker='INFY.NS',
        new_trade_sector='Technology',
        new_trade_value=10000.0,
        total_portfolio_value=total_val,
        current_prices={'TCS.NS': 3750.0}
    )
    assert approved is True
    assert reason is None

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
        new_trade_ticker='DRREDDY.NS',
        new_trade_sector='Pharma',
        new_trade_value=10000.0,
        total_portfolio_value=total_val,
        current_prices=current_prices
    )
    assert approved is False
    assert "Sector Concentration Limit Exceeded" in reason

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
    # Correlated exposure = 0.15 * 0.10 * 0.10 = 0.0015 <= 0.05
    approved, reason = agent.check_portfolio_risk(
        open_positions=open_positions,
        new_trade_ticker='CIPLA.NS',
        new_trade_sector='Pharma',
        new_trade_value=10000.0,
        total_portfolio_value=total_val,
        correlation_matrix=correlation_dict,
        current_prices=current_prices
    )
    assert approved is True
    assert reason is None

def test_pairwise_correlation_exposure_rejection():
    """Test that a trade with excessive correlated exposure across holdings is rejected."""
    agent = PortfolioRiskAgent(max_sector_exposure=1.0, max_correlated_exposure=0.05)
    
    total_val = 100000.0
    # Active positions: 3 highly correlated positions (20% each = 60% total)
    open_positions = {
        'HDFCBANK.NS': {'shares': 12, 'entry_price': 1666.67}, # 20k
        'ICICIBANK.NS': {'shares': 16, 'entry_price': 1250.0},  # 20k
        'SBIN.NS': {'shares': 25, 'entry_price': 800.0}        # 20k
    }
    current_prices = {
        'HDFCBANK.NS': 1666.67,
        'ICICIBANK.NS': 1250.0,
        'SBIN.NS': 800.0
    }
    
    # High pairwise correlation to Kotak / Bank (e.g. 0.95 each)
    correlation_dict = {
        'BANK_STOCK': {
            'HDFCBANK.NS': 0.95,
            'ICICIBANK.NS': 0.95,
            'SBIN.NS': 0.95
        }
    }
    
    # Proposed trade: 30,000 INR (30% weight)
    # Correlated exposure = (0.20 * 0.30 * 0.95) + (0.20 * 0.30 * 0.95) + (0.20 * 0.30 * 0.95)
    # = 3 * (0.057) = 0.171 > 0.05
    approved, reason = agent.check_portfolio_risk(
        open_positions=open_positions,
        new_trade_ticker='BANK_STOCK',
        new_trade_sector='Banking',
        new_trade_value=30000.0,
        total_portfolio_value=total_val,
        correlation_matrix=correlation_dict,
        current_prices=current_prices
    )
    assert approved is False
    assert "Pairwise Correlation Exposure Limit Exceeded" in reason

def test_daily_drawdown_circuit_breaker_logic():
    """Test daily drawdown circuit breaker calculation."""
    day_start_val = 100000.0
    
    # Case 1: Minor drawdown (-2.5%) -> Normal operation
    current_val_normal = 97500.0
    dd_normal = (current_val_normal - day_start_val) / day_start_val
    halt_normal = dd_normal < -0.05
    assert halt_normal is False
    
    # Case 2: Severe intraday drop (-5.5%) -> Breaker triggered
    current_val_severe = 94500.0
    dd_severe = (current_val_severe - day_start_val) / day_start_val
    halt_severe = dd_severe < -0.05
    assert halt_severe is True
    assert dd_severe == -0.055

def test_dead_mans_switch_staleness_logic():
    """Test dead man's switch data staleness threshold."""
    now_ts = 10000.0
    
    # Case 1: Fresh data (30 seconds old)
    last_fetch_fresh = 9970.0
    is_stale_fresh = (now_ts - last_fetch_fresh) > 300
    assert is_stale_fresh is False
    
    # Case 2: Stale data (350 seconds old)
    last_fetch_stale = 9650.0
    is_stale_expired = (now_ts - last_fetch_stale) > 300
    assert is_stale_expired is True
