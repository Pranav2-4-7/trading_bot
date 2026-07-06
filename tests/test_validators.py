import pytest
from bot.validators import (
    validate_symbol,
    validate_side,
    validate_order_type,
    validate_quantity,
    validate_price,
    validate_stop_price,
    validate_all
)

def test_validate_symbol():
    # Valid cases
    assert validate_symbol("BTCUSDT") == "BTCUSDT"
    assert validate_symbol("btcusdt") == "BTCUSDT"
    assert validate_symbol("  ETHUSDT  ") == "ETHUSDT"
    assert validate_symbol("SOL1USDT") == "SOL1USDT"
    
    # Invalid cases
    with pytest.raises(ValueError, match="Invalid symbol"):
        validate_symbol("BTC")
    with pytest.raises(ValueError, match="Invalid symbol"):
        validate_symbol("BTCUSD")
    with pytest.raises(ValueError, match="Symbol cannot be empty"):
        validate_symbol("")

def test_validate_side():
    # Valid cases
    assert validate_side("BUY") == "BUY"
    assert validate_side("sell") == "SELL"
    assert validate_side("  buy ") == "BUY"
    
    # Invalid cases
    with pytest.raises(ValueError, match="Invalid side"):
        validate_side("HOLD")
    with pytest.raises(ValueError, match="Side cannot be empty"):
        validate_side("")

def test_validate_order_type():
    # Valid cases
    assert validate_order_type("MARKET") == "MARKET"
    assert validate_order_type("limit") == "LIMIT"
    assert validate_order_type("STOP_MARKET") == "STOP_MARKET"
    
    # Invalid cases
    with pytest.raises(ValueError, match="Invalid order type"):
        validate_order_type("STOP_LIMIT")
    with pytest.raises(ValueError, match="Order type cannot be empty"):
        validate_order_type("")

def test_validate_quantity():
    # Valid cases
    assert validate_quantity("1.5") == 1.5
    assert validate_quantity("0.001") == 0.001
    
    # Invalid cases
    with pytest.raises(ValueError, match="must be a valid number"):
        validate_quantity("abc")
    with pytest.raises(ValueError, match="must be greater than zero"):
        validate_quantity("-0.1")
    with pytest.raises(ValueError, match="must be greater than zero"):
        validate_quantity("0")
    with pytest.raises(ValueError, match="Quantity cannot be empty"):
        validate_quantity("")

def test_validate_price():
    # Valid cases for LIMIT
    assert validate_price("1500.50", "LIMIT") == 1500.5
    assert validate_price(None, "MARKET") is None
    assert validate_price("   ", "STOP_MARKET") is None
    
    # Invalid cases
    with pytest.raises(ValueError, match="Price is required for LIMIT"):
        validate_price(None, "LIMIT")
    with pytest.raises(ValueError, match="Price is required for LIMIT"):
        validate_price("  ", "LIMIT")
    with pytest.raises(ValueError, match="must be a valid number"):
        validate_price("abc", "LIMIT")
    with pytest.raises(ValueError, match="must be greater than zero"):
        validate_price("-10", "LIMIT")
    with pytest.raises(ValueError, match="Price should not be provided"):
        validate_price("100", "MARKET")

def test_validate_stop_price():
    # Valid cases
    assert validate_stop_price("28000", "STOP_MARKET") == 28000.0
    assert validate_stop_price(None, "LIMIT") is None
    
    # Invalid cases
    with pytest.raises(ValueError, match="Stop price is required for STOP_MARKET"):
        validate_stop_price(None, "STOP_MARKET")
    with pytest.raises(ValueError, match="must be greater than zero"):
        validate_stop_price("-5", "STOP_MARKET")
    with pytest.raises(ValueError, match="Stop price should not be provided"):
        validate_stop_price("28000", "LIMIT")

def test_validate_all():
    res = validate_all(
        symbol=" BTCUSDT ",
        side="buy",
        order_type="limit",
        quantity="0.05",
        price="25000"
    )
    assert res == {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "quantity": 0.05,
        "price": 25000.0,
        "stopPrice": None
    }
