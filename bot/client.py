import hmac
import hashlib
import time
import requests
from urllib.parse import urlencode
from bot.logging_config import setup_logging, mask_api_key

class BinanceFuturesClient:
    def __init__(self, api_key: str, secret_key: str, base_url: str = "https://testnet.binancefuture.com"):
        """
        Initializes the Binance Futures client.
        :param api_key: Binance Futures Testnet API Key
        :param secret_key: Binance Futures Testnet API Secret Key
        :param base_url: Testnet base URL (defaults to testnet)
        """
        if not api_key or not secret_key:
            raise ValueError("Both API Key and Secret Key must be provided.")
        
        self.api_key = api_key.strip()
        self.secret_key = secret_key.strip()
        self.base_url = base_url.rstrip('/')
        self.logger = setup_logging()
        self.time_offset = 0
        
        # Perform time synchronization immediately
        self.sync_time()

    def sync_time(self):
        """
        Synchronizes local machine time with Binance server time to avoid clock drift
        errors (e.g. timestamp outside recvWindow).
        """
        url = f"{self.base_url}/fapi/v1/time"
        self.logger.debug(f"Syncing time with Binance server at {url}...")
        try:
            start_time = int(time.time() * 1000)
            response = requests.get(url, timeout=10)
            end_time = int(time.time() * 1000)
            
            if response.status_code == 200:
                server_time = response.json().get("serverTime")
                # Calculate transit time (latency) estimation
                rtt = (end_time - start_time) // 2
                self.time_offset = server_time - (start_time + rtt)
                self.logger.debug(f"Time sync successful. Offset: {self.time_offset} ms, RTT: {rtt} ms")
            else:
                self.logger.warning(
                    f"Failed to sync time. Status code: {response.status_code}. Using local time."
                )
        except Exception as e:
            self.logger.warning(f"Failed to sync time due to exception: {e}. Using local time.")

    def _get_timestamp(self) -> int:
        """Returns the offset-adjusted timestamp in milliseconds."""
        return int(time.time() * 1000) + self.time_offset

    def _generate_signature(self, query_string: str) -> str:
        """Generates an HMAC-SHA256 signature."""
        return hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def send_signed_request(self, method: str, path: str, params: dict) -> dict:
        """
        Sends an authenticated request to the Binance Futures API.
        :param method: HTTP method (GET, POST, DELETE, etc.)
        :param path: API endpoint path (e.g. /fapi/v1/order)
        :param params: Request parameters
        """
        # Copy params to avoid mutating original dictionary
        payload = params.copy()
        payload['timestamp'] = self._get_timestamp()
        
        # Prepare query string and sign it
        query_string = urlencode(payload)
        signature = self._generate_signature(query_string)
        
        full_query = f"{query_string}&signature={signature}"
        url = f"{self.base_url}{path}"
        
        headers = {
            'X-MBX-APIKEY': self.api_key,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        # Log request safely (mask API Key)
        safe_params = payload.copy()
        # We don't want to expose secret keys or raw full strings if they leak,
        # but the secret key is never in parameters anyway.
        self.logger.info(
            f"API REQUEST | Method: {method.upper()} | Endpoint: {path} | Params: {safe_params}"
        )
        self.logger.debug(f"Raw query: {query_string}")
        
        try:
            if method.upper() == 'POST':
                response = requests.post(url, data=full_query, headers=headers, timeout=15)
            elif method.upper() == 'GET':
                response = requests.get(f"{url}?{full_query}", headers=headers, timeout=15)
            elif method.upper() == 'DELETE':
                response = requests.delete(f"{url}?{full_query}", headers=headers, timeout=15)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # Log response status
            self.logger.info(f"API RESPONSE | HTTP {response.status_code}")
            self.logger.debug(f"Response Body: {response.text}")
            
            # Handle HTTP errors
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as http_err:
            try:
                error_response = response.json()
                code = error_response.get("code", "N/A")
                msg = error_response.get("msg", "No details")
                error_msg = f"Binance API Error {code}: {msg}"
            except Exception:
                error_msg = f"HTTP Error occurred: {http_err}. Body: {response.text if 'response' in locals() else ''}"
            
            self.logger.error(error_msg)
            raise Exception(error_msg)
            
        except requests.exceptions.RequestException as req_err:
            error_msg = f"Network or Request Exception: {req_err}"
            self.logger.error(error_msg)
            raise Exception(error_msg)

    def test_connection(self) -> bool:
        """Tests connection to the API by making a simple GET /fapi/v1/ping request."""
        url = f"{self.base_url}/fapi/v1/ping"
        try:
            response = requests.get(url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False
