import os
import argparse
import sys
from dotenv import load_dotenv
import questionary
from curl_cffi import requests

# Add root folder to sys.path to allow module imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.logging_config import logger
from bot.client import BinanceFuturesClient
from bot.orders import OrderManager
from bot.validators import InputValidator

# Load environment variables
load_dotenv()

def get_current_mark_price(symbol: str) -> float:
    """Fetches the current mark price of the futures contract."""
    try:
        url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol.upper()}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return float(response.json().get("markPrice", 0.0))
    except Exception as e:
        logger.error(f"Error fetching current price: {e}")
    return 0.0

def run_interactive_menu():
    """Runs the CLI in interactive mode with questionary."""
    print("=" * 60)
    print("Welcome to the Binance Futures Testnet Trading Bot Interactive Terminal")
    print("=" * 60)

    # Secure credentials check/input
    api_key = os.getenv("BINANCE_API_KEY")
    secret_key = os.getenv("BINANCE_SECRET_KEY")

    if not api_key:
        api_key = questionary.text("Enter your Binance Futures Testnet API Key:").ask()
    if not secret_key:
        secret_key = questionary.password("Enter your Binance Futures Testnet Secret Key:").ask()

    if not api_key or not secret_key:
        print("Error: API Key and Secret Key are required to run the bot.")
        sys.exit(1)

    # Setup client
    client = BinanceFuturesClient(api_key, secret_key)
    client.sync_clock()
    order_manager = OrderManager(client)

    # Questionary Inputs
    symbol = questionary.text(
        "Enter trading symbol (e.g. BTCUSDT, ETHUSDT):",
        validate=lambda text: InputValidator.validate_symbol(text) or "Invalid symbol format. Symbol must end with USDT."
    ).ask()

    side = questionary.select(
        "Select Side:",
        choices=["BUY", "SELL"]
    ).ask()

    order_type = questionary.select(
        "Select Order Type:",
        choices=["MARKET", "LIMIT", "STOP_MARKET"]
    ).ask()

    quantity = questionary.text(
        "Enter Quantity:",
        validate=lambda text: InputValidator.validate_quantity(text) or "Quantity must be a positive number."
    ).ask()

    price = None
    if order_type == "LIMIT":
        price = questionary.text(
            "Enter Limit Price:",
            validate=lambda text: InputValidator.validate_price(text) or "Price must be a positive number."
        ).ask()
        price = float(price)

    stop_price = None
    if order_type == "STOP_MARKET":
        current_price = get_current_mark_price(symbol)
        if current_price > 0:
            print(f"Current mark price for {symbol}: {current_price}")
        
        while True:
            stop_price_str = questionary.text(
                "Enter Stop Price:",
                validate=lambda text: InputValidator.validate_stop_price(text) or "Stop price must be a positive number."
            ).ask()
            stop_price = float(stop_price_str)
            
            if current_price > 0:
                if InputValidator.validate_stops(side, current_price, stop_price):
                    break
                else:
                    print(f"Validation failed: For {side} orders, Stop Price must be "
                          f"{'below' if side == 'BUY' else 'above'} the current price ({current_price}).")
            else:
                break

    # Confirmation
    confirm_text = f"Confirm Order: {side} {quantity} {symbol} ({order_type}"
    if price:
        confirm_text += f" @ {price}"
    if stop_price:
        confirm_text += f" trigger @ {stop_price}"
    confirm_text += ")?"

    confirm = questionary.confirm(confirm_text).ask()

    if confirm:
        print("Sending order to testnet...")
        try:
            order_manager.place_order(symbol, side, order_type, float(quantity), price, stop_price)
        except Exception as e:
            print(f"An error occurred: {e}")
    else:
        print("Order cancelled.")

def run_direct_cli():
    """Runs the CLI in direct headless mode with argparse."""
    parser = argparse.ArgumentParser(description="Binance Futures Testnet Trading Bot CLI")
    parser.add_argument("--symbol", type=str, required=True, help="Trading Symbol (e.g. BTCUSDT)")
    parser.add_argument("--side", type=str, required=True, choices=["BUY", "SELL"], help="Trade Side")
    parser.add_argument("--type", type=str, required=True, choices=["MARKET", "LIMIT", "STOP_MARKET"], help="Order Type")
    parser.add_argument("--quantity", type=str, required=True, help="Order Quantity")
    parser.add_argument("--price", type=str, help="Limit Price (Required for LIMIT orders)")
    parser.add_argument("--stop-price", type=str, help="Stop Price (Required for STOP_MARKET orders)")

    args = parser.parse_args()

    # Validations
    if not InputValidator.validate_symbol(args.symbol):
        print(f"Error: Invalid Symbol: {args.symbol}")
        sys.exit(1)
    if not InputValidator.validate_quantity(args.quantity):
        print(f"Error: Invalid Quantity: {args.quantity}")
        sys.exit(1)

    price_val = None
    if args.type == "LIMIT":
        if not args.price or not InputValidator.validate_price(args.price):
            print("Error: Invalid or missing price parameter for LIMIT order.")
            sys.exit(1)
        price_val = float(args.price)

    stop_price_val = None
    if args.type == "STOP_MARKET":
        if not args.stop_price or not InputValidator.validate_stop_price(args.stop_price):
            print("Error: Invalid or missing stop price parameter for STOP_MARKET order.")
            sys.exit(1)
        stop_price_val = float(args.stop_price)

        current_price = get_current_mark_price(args.symbol)
        if current_price > 0 and not InputValidator.validate_stops(args.side, current_price, stop_price_val):
            print(f"Error: Invalid stop price configuration. For {args.side} order, Stop Price must be "
                  f"{'below' if args.side == 'BUY' else 'above'} current market price ({current_price}).")
            sys.exit(1)

    api_key = os.getenv("BINANCE_API_KEY")
    secret_key = os.getenv("BINANCE_SECRET_KEY")

    if not api_key or not secret_key:
        print("Error: Environment variables BINANCE_API_KEY and BINANCE_SECRET_KEY must be set in direct CLI mode.")
        sys.exit(1)

    client = BinanceFuturesClient(api_key, secret_key)
    client.sync_clock()
    order_manager = OrderManager(client)

    try:
        order_manager.place_order(args.symbol, args.side, args.type, float(args.quantity), price_val, stop_price_val)
    except Exception as e:
        print(f"Execution Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_direct_cli()
    else:
        run_interactive_menu()
