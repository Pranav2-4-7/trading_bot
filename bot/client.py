import time
import hmac
import hashlib
from urllib.parse import urlencode
from curl_cffi import requests
from .logging_config import logger

class BinanceFuturesClient:
    """
    Lightweight client for Binance Futures Testnet REST API.
    Handles authentication and clock synchronization.
    """
    def __init__(self, api_key: str, secret_key: str, recv_window: int = 5000):
        self.api_key = api_key
        self.secret_key = secret_key
        self.recv_window = recv_window
        self.base_url = "https://fapi.binance.com"
        self.time_offset = 0

    def sync_clock(self):
        """Synchronizes local clock offset with Binance server time."""
        try:
            logger.info("Synchronizing system clock with Binance Futures server...")
            url = f"{self.base_url}/fapi/v1/time"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                server_time = response.json().get("serverTime")
                local_time = int(time.time() * 1000)
                self.time_offset = server_time - local_time
                logger.info(f"Clock synced successfully. Offset: {self.time_offset}ms")
            else:
                logger.warning("Failed to sync clock, status code: %s", response.status_code)
        except Exception as e:
            logger.error("Error synchronizing clock: %s", e)

    def _get_timestamp(self) -> int:
        return int(time.time() * 1000) + self.time_offset

    def _sign(self, query_string: str) -> str:
        return hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def send_signed_request(self, method: str, endpoint: str, payload: dict = None) -> dict:
        """Sends a signed HTTP request to the Binance API."""
        if not payload:
            payload = {}

        payload['timestamp'] = self._get_timestamp()
        payload['recvWindow'] = self.recv_window

        query_string = urlencode(payload)
        signature = self._sign(query_string)
        url = f"{self.base_url}{endpoint}?{query_string}&signature={signature}"

        headers = {
            "X-MBX-APIKEY": self.api_key
        }

        logger.info(f"Sending {method} request to {endpoint}")
        # Mask API Key in logs for security
        masked_headers = headers.copy()
        masked_headers['X-MBX-APIKEY'] = self.api_key[:6] + "..." if self.api_key else ""
        logger.debug(f"Request Headers: {masked_headers}")
        logger.debug(f"Request Payload (excl signature): {payload}")

        try:
            if method.upper() == 'POST':
                response = requests.post(url, headers=headers, timeout=15)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=15)
            else:
                response = requests.get(url, headers=headers, timeout=15)

            logger.info(f"Response Received: HTTP {response.status_code}")
            logger.debug(f"Response Body: {response.text}")

            return response.json()
        except Exception as e:
            logger.error(f"HTTP request error: {e}")
            raise
