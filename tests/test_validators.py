import pytest
from bot.validators import InputValidator

def test_validate_symbol():
    assert InputValidator.validate_symbol("BTCUSDT") is True
    assert InputValidator.validate_symbol("ethusdt") is True
    assert InputValidator.validate_symbol("SOLUSDT") is True
    assert InputValidator.validate_symbol("BTCUSD") is False
    assert InputValidator.validate_symbol("USDT") is False
    assert InputValidator.validate_symbol("") is False

def test_validate_side():
    assert InputValidator.validate_side("BUY") is True
    assert InputValidator.validate_side("sell") is True
    assert InputValidator.validate_side("HOLD") is False
    assert InputValidator.validate_side("") is False

def test_validate_order_type():
    assert InputValidator.validate_order_type("MARKET") is True
    assert InputValidator.validate_order_type("LIMIT") is True
    assert InputValidator.validate_order_type("STOP_MARKET") is True
    assert InputValidator.validate_order_type("STOP") is False

def test_validate_quantity():
    assert InputValidator.validate_quantity("0.001") is True
    assert InputValidator.validate_quantity("10") is True
    assert InputValidator.validate_quantity("-1") is False
    assert InputValidator.validate_quantity("abc") is False
    assert InputValidator.validate_quantity("") is False

def test_validate_price():
    assert InputValidator.validate_price("95000.5") is True
    assert InputValidator.validate_price("-100") is False
    assert InputValidator.validate_price("abc") is False

def test_validate_stop_price():
    assert InputValidator.validate_stop_price("1.2") is True
    assert InputValidator.validate_stop_price("0") is False

def test_validate_stops():
    # BUY (long stop loss triggers below current price)
    assert InputValidator.validate_stops("BUY", 65000.0, 64000.0) is True
    assert InputValidator.validate_stops("BUY", 65000.0, 66000.0) is False
    
    # SELL (short stop loss triggers above current price)
    assert InputValidator.validate_stops("SELL", 65000.0, 66000.0) is True
    assert InputValidator.validate_stops("SELL", 65000.0, 64000.0) is False
