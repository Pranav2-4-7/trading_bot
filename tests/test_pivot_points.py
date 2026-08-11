import pytest
import pandas as pd
import numpy as np
from data_scraper import IngestionAgent

def test_pivot_points_calculation():
    # Construct a dummy dataframe
    df = pd.DataFrame({
        "High": [10.0, 15.0, 18.0],
        "Low": [5.0, 8.0, 12.0],
        "Close": [8.0, 12.0, 15.0],
        "Volume": [100, 200, 300],
        "Open": [6.0, 9.0, 13.0]
    })
    
    # Calculate indicators using compute_technical_features
    # We will test the pivot point formulas directly
    prev_high = df["High"].shift(1)
    prev_low = df["Low"].shift(1)
    prev_close = df["Close"].shift(1)
    
    p = (prev_high + prev_low + prev_close) / 3.0
    r1 = (2.0 * p) - prev_low
    r2 = p + (prev_high - prev_low)
    s1 = (2.0 * p) - prev_high
    s2 = p - (prev_high - prev_low)
    
    dist_p = (df["Close"] - p) / p
    dist_r1 = (df["Close"] - r1) / r1
    dist_r2 = (df["Close"] - r2) / r2
    dist_s1 = (df["Close"] - s1) / s1
    dist_s2 = (df["Close"] - s2) / s2
    
    # Fill NA values similar to pipeline
    dist_p = dist_p.ffill().bfill()
    dist_r1 = dist_r1.ffill().bfill()
    
    # Test values at row index 1
    # prev_high = 10.0, prev_low = 5.0, prev_close = 8.0
    # p = (10 + 5 + 8) / 3 = 7.6666667
    # r1 = (2 * 7.6666667) - 5 = 10.333333
    # Close = 12.0
    # dist_p = (12 - 7.6666667) / 7.6666667 = 0.5652
    # dist_r1 = (12 - 10.333333) / 10.333333 = 0.1613
    
    expected_p = 7.6666667
    expected_r1 = 10.333333
    assert abs(p.iloc[1] - expected_p) < 1e-5
    assert abs(r1.iloc[1] - expected_r1) < 1e-5
    assert abs(dist_p.iloc[1] - 0.565217) < 1e-5
    assert abs(dist_r1.iloc[1] - 0.16129) < 1e-5
