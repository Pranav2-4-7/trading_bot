from .client import BinanceFuturesClient
from .logging_config import logger

class OrderManager:
    """
    Prepares and executes trading orders on the Binance Futures Testnet.
    """
    def __init__(self, client: BinanceFuturesClient):
        self.client = client

    def place_order(self, symbol: str, side: str, order_type: str, quantity: float, price: float = None, stop_price: float = None) -> dict:
        """
        Executes a futures order on Binance Testnet.
        """
        endpoint = "/fapi/v1/order"
        payload = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": quantity
        }

        # Handle specific order type requirements
        if order_type.upper() == "LIMIT":
            if price is None:
                raise ValueError("Limit price must be specified for LIMIT orders.")
            payload["price"] = price
            payload["timeInForce"] = "GTC"
        
        elif order_type.upper() == "STOP_MARKET":
            if stop_price is None:
                raise ValueError("Stop price must be specified for STOP_MARKET orders.")
            payload["stopPrice"] = stop_price

        logger.info(f"Configured Payload: {payload}")
        
        try:
            result = self.client.send_signed_request("POST", endpoint, payload)
            if "orderId" in result:
                logger.info(f"Order placed successfully! ID: {result.get('orderId')}")
            else:
                logger.error(f"Order failed. Response: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to place order due to: {e}")
            raise
