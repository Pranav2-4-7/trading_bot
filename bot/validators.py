import re
from typing import Optional, Tuple

ALLOWED_SIDES = {"BUY", "SELL"}
ALLOWED_ORDER_TYPES = {"MARKET", "LIMIT", "STOP_MARKET"}

def validate_symbol(symbol: str) -> str:
    """
    Validates a trading symbol.
    Must be alphanumeric, uppercase, and end with USDT (for USDT-M futures).
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty.")
    
    clean_symbol = symbol.strip().upper()
    
    # Binance symbols are alphanumeric. Let's make sure it has a valid pattern.
    if not re.match(r"^[A-Z0-9]{3,12}USDT$", clean_symbol):
        raise ValueError(
            f"Invalid symbol '{symbol}'. Must be an uppercase alphanumeric string ending with 'USDT' (e.g. BTCUSDT)."
        )
    return clean_symbol

def validate_side(side: str) -> str:
    """
    Validates the order side.
    Must be BUY or SELL.
    """
    if not side:
        raise ValueError("Side cannot be empty.")
    
    clean_side = side.strip().upper()
    if clean_side not in ALLOWED_SIDES:
        raise ValueError(f"Invalid side '{side}'. Must be one of {ALLOWED_SIDES}.")
    return clean_side

def validate_order_type(order_type: str) -> str:
    """
    Validates the order type.
    Must be MARKET, LIMIT, or STOP_MARKET.
    """
    if not order_type:
        raise ValueError("Order type cannot be empty.")
    
    clean_type = order_type.strip().upper()
    if clean_type not in ALLOWED_ORDER_TYPES:
        raise ValueError(f"Invalid order type '{order_type}'. Must be one of {ALLOWED_ORDER_TYPES}.")
    return clean_type

def validate_quantity(quantity: str) -> float:
    """
    Validates that the quantity is a positive float.
    """
    if not quantity:
        raise ValueError("Quantity cannot be empty.")
    try:
        qty_val = float(quantity)
    except ValueError:
        raise ValueError(f"Quantity '{quantity}' must be a valid number.")
    
    if qty_val <= 0:
        raise ValueError("Quantity must be greater than zero.")
    return qty_val

def validate_price(price: Optional[str], order_type: str) -> Optional[float]:
    """
    Validates the price parameter.
    Required for LIMIT orders; must be a positive float.
    Ignored/Not allowed for MARKET orders.
    """
    if order_type.upper() == "LIMIT":
        if not price or not price.strip():
            raise ValueError("Price is required for LIMIT orders.")
        try:
            price_val = float(price)
        except ValueError:
            raise ValueError(f"Price '{price}' must be a valid number.")
        if price_val <= 0:
            raise ValueError("Price must be greater than zero.")
        return price_val
    else:
        if price and price.strip():
            # If price is provided for a MARKET/STOP_MARKET order, warn or ignore.
            # We choose to raise an error to ensure user intent is clear.
            raise ValueError(f"Price should not be provided for {order_type} orders.")
        return None

def validate_stop_price(stop_price: Optional[str], order_type: str) -> Optional[float]:
    """
    Validates the stop_price parameter.
    Required for STOP_MARKET orders; must be a positive float.
    """
    if order_type.upper() == "STOP_MARKET":
        if not stop_price or not stop_price.strip():
            raise ValueError("Stop price is required for STOP_MARKET orders.")
        try:
            stop_val = float(stop_price)
        except ValueError:
            raise ValueError(f"Stop price '{stop_price}' must be a valid number.")
        if stop_val <= 0:
            raise ValueError("Stop price must be greater than zero.")
        return stop_val
    else:
        if stop_price and stop_price.strip():
            raise ValueError(f"Stop price should not be provided for {order_type} orders.")
        return None

def validate_all(
    symbol: str,
    side: str,
    order_type: str,
    quantity: str,
    price: Optional[str] = None,
    stop_price: Optional[str] = None
) -> dict:
    """
    Validates all inputs and returns a structured dictionary of typed inputs.
    """
    v_symbol = validate_symbol(symbol)
    v_side = validate_side(side)
    v_type = validate_order_type(order_type)
    v_qty = validate_quantity(quantity)
    v_price = validate_price(price, v_type)
    v_stop_price = validate_stop_price(stop_price, v_type)
    
    return {
        "symbol": v_symbol,
        "side": v_side,
        "type": v_type,
        "quantity": v_qty,
        "price": v_price,
        "stopPrice": v_stop_price
    }
