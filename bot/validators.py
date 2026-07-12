import re

class InputValidator:
    """
    Input validation functions for Binance Futures Testnet Trading CLI.
    """
    
    @staticmethod
    def validate_symbol(symbol: str) -> bool:
        """
        Validates the trading symbol format (e.g. BTCUSDT, ETHUSDT).
        Must be alphanumeric and end with USDT.
        """
        if not symbol:
            return False
        pattern = r"^[A-Z0-9]{2,10}USDT$"
        return bool(re.match(pattern, symbol.upper()))

    @staticmethod
    def validate_side(side: str) -> bool:
        """Validates trading side (BUY/SELL)."""
        if not side:
            return False
        return side.upper() in ["BUY", "SELL"]

    @staticmethod
    def validate_order_type(order_type: str) -> bool:
        """Validates futures order type."""
        if not order_type:
            return False
        return order_type.upper() in ["MARKET", "LIMIT", "STOP_MARKET"]

    @staticmethod
    def validate_quantity(quantity: str) -> bool:
        """Validates order quantity is a positive float."""
        try:
            val = float(quantity)
            return val > 0
        except (ValueError, TypeError):
            return False

    @staticmethod
    def validate_price(price: str) -> bool:
        """Validates order price is a positive float."""
        try:
            val = float(price)
            return val > 0
        except (ValueError, TypeError):
            return False

    @staticmethod
    def validate_stop_price(stop_price: str) -> bool:
        """Validates stop price is a positive float."""
        try:
            val = float(stop_price)
            return val > 0
        except (ValueError, TypeError):
            return False

    @staticmethod
    def validate_stops(side: str, current_price: float, stop_price: float) -> bool:
        """
        Validates stop prices against the direction of trade.
        For BUY side (long), Stop Market triggers stop loss, so stop price must be below current price.
        For SELL side (short), Stop Market triggers stop loss, so stop price must be above current price.
        """
        if side.upper() == "BUY":
            return stop_price < current_price
        elif side.upper() == "SELL":
            return stop_price > current_price
        return False
