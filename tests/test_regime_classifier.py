import pytest
import pandas as pd
import numpy as np
from live_paper_runner import get_market_regime, calculate_dynamic_threshold

def test_market_regime_risk_on_all_true():
    """Test that market regime is classified as RISK_ON when all 3 signals are True."""
    # 1. Benchmark: Close (25000) > MA200 (24000), ATR_Ratio (0.008) < Rolling Mean (0.012)
    benchmark_df = pd.DataFrame({
        "Close": [25000.0] * 70,
        "MA200": [24000.0] * 70,
        "ATR_Ratio": [0.012] * 69 + [0.008]
    })
    
    # 2. Watchlist: 4 out of 5 stocks above 200 DMA (80% > 50%)
    watchlist_dfs = {
        "STOCK1": pd.DataFrame({"Close": [105.0], "MA200": [100.0]}),
        "STOCK2": pd.DataFrame({"Close": [110.0], "MA200": [100.0]}),
        "STOCK3": pd.DataFrame({"Close": [115.0], "MA200": [100.0]}),
        "STOCK4": pd.DataFrame({"Close": [120.0], "MA200": [100.0]}),
        "STOCK5": pd.DataFrame({"Close": [95.0], "MA200": [100.0]})
    }
    
    regime = get_market_regime(benchmark_df=benchmark_df, watchlist_dfs=watchlist_dfs)
    assert regime == "RISK_ON"

def test_market_regime_risk_on_majority_two_signals():
    """Test that market regime is classified as RISK_ON when 2 of 3 signals are True."""
    # Trend = True (25000 > 24000)
    # Volatility = False (ATR_Ratio 0.020 > Rolling Mean 0.012)
    benchmark_df = pd.DataFrame({
        "Close": [25000.0] * 70,
        "MA200": [24000.0] * 70,
        "ATR_Ratio": [0.012] * 69 + [0.020]
    })
    
    # Breadth = True (3 out of 4 stocks above 200 DMA = 75% > 50%)
    watchlist_dfs = {
        "STOCK1": pd.DataFrame({"Close": [105.0], "MA200": [100.0]}),
        "STOCK2": pd.DataFrame({"Close": [110.0], "MA200": [100.0]}),
        "STOCK3": pd.DataFrame({"Close": [115.0], "MA200": [100.0]}),
        "STOCK4": pd.DataFrame({"Close": [90.0], "MA200": [100.0]})
    }
    
    regime = get_market_regime(benchmark_df=benchmark_df, watchlist_dfs=watchlist_dfs)
    assert regime == "RISK_ON"

def test_market_regime_risk_off_minority_one_signal():
    """Test that market regime is classified as RISK_OFF when only 1 signal is True."""
    # Trend = False (23000 < 24000)
    # Volatility = False (ATR_Ratio 0.025 > Rolling Mean 0.012)
    benchmark_df = pd.DataFrame({
        "Close": [23000.0] * 70,
        "MA200": [24000.0] * 70,
        "ATR_Ratio": [0.012] * 69 + [0.025]
    })
    
    # Breadth = True (3 out of 4 stocks above 200 DMA = 75% > 50%)
    watchlist_dfs = {
        "STOCK1": pd.DataFrame({"Close": [105.0], "MA200": [100.0]}),
        "STOCK2": pd.DataFrame({"Close": [110.0], "MA200": [100.0]}),
        "STOCK3": pd.DataFrame({"Close": [115.0], "MA200": [100.0]}),
        "STOCK4": pd.DataFrame({"Close": [90.0], "MA200": [100.0]})
    }
    
    regime = get_market_regime(benchmark_df=benchmark_df, watchlist_dfs=watchlist_dfs)
    assert regime == "RISK_OFF"

def test_market_regime_risk_off_all_false():
    """Test that market regime is classified as RISK_OFF when all 3 signals are False."""
    # Trend = False (22000 < 24000)
    # Volatility = False (ATR_Ratio 0.030 > Rolling Mean 0.010)
    benchmark_df = pd.DataFrame({
        "Close": [22000.0] * 70,
        "MA200": [24000.0] * 70,
        "ATR_Ratio": [0.010] * 69 + [0.030]
    })
    
    # Breadth = False (only 1 out of 5 stocks above 200 DMA = 20% <= 50%)
    watchlist_dfs = {
        "STOCK1": pd.DataFrame({"Close": [105.0], "MA200": [100.0]}),
        "STOCK2": pd.DataFrame({"Close": [90.0], "MA200": [100.0]}),
        "STOCK3": pd.DataFrame({"Close": [85.0], "MA200": [100.0]}),
        "STOCK4": pd.DataFrame({"Close": [80.0], "MA200": [100.0]}),
        "STOCK5": pd.DataFrame({"Close": [75.0], "MA200": [100.0]})
    }
    
    regime = get_market_regime(benchmark_df=benchmark_df, watchlist_dfs=watchlist_dfs)
    assert regime == "RISK_OFF"

def test_calculate_dynamic_threshold_risk_on():
    """Test dynamic threshold in normal RISK_ON market conditions."""
    base_th = 0.57
    
    # Price above 200 DMA -> Base threshold returned
    th_above = calculate_dynamic_threshold(current_price=105.0, dma_200=100.0, base_threshold=base_th, regime="RISK_ON")
    assert th_above == 0.57
    
    # Price 10% below 200 DMA -> Base + (0.10 * 1.5) = 0.57 + 0.15 = 0.72
    th_below = calculate_dynamic_threshold(current_price=90.0, dma_200=100.0, base_threshold=base_th, regime="RISK_ON")
    assert pytest.approx(th_below, 0.001) == 0.72

def test_calculate_dynamic_threshold_risk_off_multiplier():
    """Test 1.25x scaling multiplier in RISK_OFF conditions."""
    base_th = 0.57
    
    # Price above 200 DMA in RISK_OFF -> 0.57 * 1.25 = 0.7125
    th_risk_off = calculate_dynamic_threshold(current_price=105.0, dma_200=100.0, base_threshold=base_th, regime="RISK_OFF")
    assert pytest.approx(th_risk_off, 0.001) == 0.7125
    
    # Price 10% below 200 DMA in RISK_OFF -> (0.57 + 0.15) * 1.25 = 0.72 * 1.25 = 0.90 -> capped at 0.85
    th_below_risk_off = calculate_dynamic_threshold(current_price=90.0, dma_200=100.0, base_threshold=base_th, regime="RISK_OFF")
    assert th_below_risk_off == 0.85
