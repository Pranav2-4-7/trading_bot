import pytest
import numpy as np
import pandas as pd
from live_paper_runner import calculate_dynamic_threshold

def test_calculate_dynamic_threshold_above_dma():
    # If current_price >= dma_200, return base_threshold
    threshold = calculate_dynamic_threshold(current_price=105.0, dma_200=100.0, base_threshold=0.57)
    assert threshold == 0.57

def test_calculate_dynamic_threshold_below_dma_scales_up():
    # dma_200 = 100, current_price = 90 (10% drop)
    # drop_pct = 0.10
    # dynamic_threshold = 0.57 + (0.10 * 1.5) = 0.57 + 0.15 = 0.72
    threshold = calculate_dynamic_threshold(current_price=90.0, dma_200=100.0, base_threshold=0.57)
    assert abs(threshold - 0.72) < 1e-5

def test_calculate_dynamic_threshold_caps_at_85():
    # dma_200 = 100, current_price = 50 (50% drop)
    # drop_pct = 0.50
    # dynamic_threshold = 0.57 + (0.50 * 1.5) = 0.57 + 0.75 = 1.32
    # capped at 0.85
    threshold = calculate_dynamic_threshold(current_price=50.0, dma_200=100.0, base_threshold=0.57)
    assert threshold == 0.85

def test_calculate_dynamic_threshold_invalid_dma():
    # Missing or zero dma_200 should fall back to base_threshold
    assert calculate_dynamic_threshold(100.0, None, 0.57) == 0.57
    assert calculate_dynamic_threshold(100.0, np.nan, 0.57) == 0.57
    assert calculate_dynamic_threshold(100.0, 0, 0.57) == 0.57
    assert calculate_dynamic_threshold(100.0, -10.0, 0.57) == 0.57
