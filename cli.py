import argparse
import os
import sys
from typing import Optional, Tuple
from dotenv import load_dotenv

from bot.client import BinanceFuturesClient
from bot.validators import (
    validate_symbol,
    validate_side,
    validate_order_type,
    validate_quantity,
    validate_price,
    validate_stop_price,
    validate_all
)
from bot.orders import place_order, format_order_summary
from bot.logging_config import setup_logging, mask_api_key

# Check if questionary is available for advanced CLI UI
try:
    import questionary
    from questionary import Validator, ValidationError
    HAS_QUESTIONARY = True
except ImportError:
    HAS_QUESTIONARY = False

# Setup logger for the CLI layer
logger = setup_logging()

# ==========================================
# Questionary Validators (for Interactive Mode)
# ==========================================
if HAS_QUESTIONARY:
    class QSymbolValidator(Validator):
        def validate(self, document):
            text = document.text.strip()
            if not text:
                raise ValidationError(message="Symbol cannot be empty.")
            try:
                validate_symbol(text)
            except ValueError as e:
                raise ValidationError(message=str(e))

    class QSideValidator(Validator):
        def validate(self, document):
            text = document.text.strip()
            try:
                validate_side(text)
            except ValueError as e:
                raise ValidationError(message=str(e))

    class QQuantityValidator(Validator):
        def validate(self, document):
            text = document.text.strip()
            try:
                validate_quantity(text)
            except ValueError as e:
                raise ValidationError(message=str(e))

    class QPriceValidator(Validator):
        def __init__(self, order_type: str):
            self.order_type = order_type
        def validate(self, document):
            text = document.text.strip()
            try:
                validate_price(text, self.order_type)
            except ValueError as e:
                raise ValidationError(message=str(e))

    class QStopPriceValidator(Validator):
        def __init__(self, order_type: str):
            self.order_type = order_type
        def validate(self, document):
            text = document.text.strip()
            try:
                validate_stop_price(text, self.order_type)
            except ValueError as e:
                raise ValidationError(message=str(e))


def load_credentials(args) -> Tuple[Optional[str], Optional[str]]:
    """Loads API key and Secret key from arguments, then dotenv, then environment."""
    load_dotenv()
    
    api_key = args.api_key or os.getenv("BINANCE_API_KEY")
    secret_key = args.secret_key or os.getenv("BINANCE_SECRET_KEY")
    
    return api_key, secret_key


def run_interactive_mode(api_key: Optional[str], secret_key: Optional[str]) -> dict:
    """Runs the enhanced interactive CLI menu for user inputs."""
    print("\n=== Binance Futures Testnet Trading Bot (Interactive Mode) ===")
    
    # Prompt for credentials if missing
    if not api_key:
        if HAS_QUESTIONARY:
            api_key = questionary.text("Enter Binance Futures Testnet API Key:").ask()
        else:
            api_key = input("Enter Binance Futures Testnet API Key: ")
            
    if not secret_key:
        if HAS_QUESTIONARY:
            secret_key = questionary.password("Enter Binance Futures Testnet Secret Key:").ask()
        else:
            import getpass
            secret_key = getpass.getpass("Enter Binance Futures Testnet Secret Key: ")
            
    if not api_key or not secret_key:
        print("Error: API Key and Secret Key are required to continue.")
        sys.exit(1)
        
    if HAS_QUESTIONARY:
        # Prompt for parameters using Questionary's beautiful inputs
        symbol = questionary.text(
            "Enter Trading Symbol (e.g., BTCUSDT, ETHUSDT):",
            default="BTCUSDT",
            validate=QSymbolValidator
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
            validate=QQuantityValidator
        ).ask()
        
        price = None
        if order_type == "LIMIT":
            price = questionary.text(
                "Enter Limit Price:",
                validate=QPriceValidator(order_type)
            ).ask()
            
        stop_price = None
        if order_type == "STOP_MARKET":
            stop_price = questionary.text(
                "Enter Stop Price:",
                validate=QStopPriceValidator(order_type)
            ).ask()
            
        # Confirm placing order
        confirm = questionary.confirm(
            f"Are you sure you want to place this {order_type} {side} order for {quantity} {symbol}?",
            default=True
        ).ask()
        
        if not confirm:
            print("Order placement cancelled by user.")
            sys.exit(0)
            
    else:
        # Fallback to simple line-input with validator loops
        print("\n(Note: questionary library not found. Falling back to standard prompts.)")
        
        # Symbol
        while True:
            try:
                symbol = input("Enter Symbol (default: BTCUSDT): ").strip() or "BTCUSDT"
                validate_symbol(symbol)
                break
            except ValueError as e:
                print(f"Error: {e}")
                
        # Side
        while True:
            try:
                side = input("Enter Side (BUY/SELL): ").strip()
                validate_side(side)
                break
            except ValueError as e:
                print(f"Error: {e}")
                
        # Order Type
        while True:
            try:
                order_type = input("Enter Order Type (MARKET/LIMIT/STOP_MARKET): ").strip()
                validate_order_type(order_type)
                break
            except ValueError as e:
                print(f"Error: {e}")
                
        # Quantity
        while True:
            try:
                quantity = input("Enter Quantity: ").strip()
                validate_quantity(quantity)
                break
            except ValueError as e:
                print(f"Error: {e}")
                
        # Price
        price = None
        if order_type.upper() == "LIMIT":
            while True:
                try:
                    price = input("Enter Limit Price: ").strip()
                    validate_price(price, order_type)
                    break
                except ValueError as e:
                    print(f"Error: {e}")
                    
        # Stop Price
        stop_price = None
        if order_type.upper() == "STOP_MARKET":
            while True:
                try:
                    stop_price = input("Enter Stop Price: ").strip()
                    validate_stop_price(stop_price, order_type)
                    break
                except ValueError as e:
                    print(f"Error: {e}")
                    
        # Confirmation
        confirm = input(f"Confirm {order_type} {side} order of {quantity} {symbol}? (y/N): ").strip().lower()
        if confirm not in ['y', 'yes']:
            print("Order cancelled.")
            sys.exit(0)
            
    # Run validation check one final time to construct typed inputs
    try:
        validated_inputs = validate_all(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price
        )
        return validated_inputs, api_key, secret_key
    except ValueError as e:
        print(f"Validation failed: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Binance Futures Testnet (USDT-M) Trading Bot CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run interactively (will prompt for missing details)
  python cli.py

  # Place a MARKET BUY order
  python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001

  # Place a LIMIT SELL order
  python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.001 --price 65000

  # Place a STOP_MARKET BUY order (Stop Loss trigger)
  python cli.py --symbol BTCUSDT --side BUY --type STOP_MARKET --quantity 0.001 --stop-price 60000
"""
    )
    
    # Order Parameters
    parser.add_argument("--symbol", type=str, help="Trading Symbol (e.g. BTCUSDT)")
    parser.add_argument("--side", type=str, choices=["BUY", "SELL", "buy", "sell"], help="Order side")
    parser.add_argument("--type", type=str, choices=["MARKET", "LIMIT", "STOP_MARKET", "market", "limit", "stop_market"], help="Order type")
    parser.add_argument("--quantity", type=str, help="Quantity to trade")
    parser.add_argument("--price", type=str, help="Price (required for LIMIT orders)")
    parser.add_argument("--stop-price", type=str, help="Stop price (required for STOP_MARKET orders)")
    
    # Configuration / Credentials
    parser.add_argument("--api-key", type=str, help="Binance Futures Testnet API Key")
    parser.add_argument("--secret-key", type=str, help="Binance Futures Testnet Secret Key")
    parser.add_argument("-i", "--interactive", action="store_true", help="Force interactive mode")
    
    args = parser.parse_args()
    
    # Load API credentials
    api_key, secret_key = load_credentials(args)
    
    # Determine if we should run in interactive mode:
    # If explicitly requested, or if essential order fields are missing.
    is_interactive = args.interactive or not all([args.symbol, args.side, args.type, args.quantity])
    
    if is_interactive:
        validated_inputs, final_api_key, final_secret_key = run_interactive_mode(api_key, secret_key)
    else:
        # Enforce that credentials exist for non-interactive run
        if not api_key or not secret_key:
            print("Error: API Key and Secret Key are required. Provide them in CLI arguments or a .env file.")
            sys.exit(1)
            
        final_api_key = api_key
        final_secret_key = secret_key
        
        # Validate CLI parameters
        try:
            validated_inputs = validate_all(
                symbol=args.symbol,
                side=args.side,
                order_type=args.type,
                quantity=args.quantity,
                price=args.price,
                stop_price=args.stop_price
            )
        except ValueError as e:
            print(f"\n[ERROR] Input Validation Failed: {e}")
            logger.error(f"CLI Input Validation Failed: {e}")
            sys.exit(1)
            
    # Print Order Request Summary (evaluator requirement)
    print("\n=== Order Request Summary ===")
    print(f"Symbol:     {validated_inputs['symbol']}")
    print(f"Side:       {validated_inputs['side']}")
    print(f"Type:       {validated_inputs['type']}")
    print(f"Quantity:   {validated_inputs['quantity']}")
    if validated_inputs['price'] is not None:
        print(f"Price:      {validated_inputs['price']}")
    if validated_inputs['stopPrice'] is not None:
        print(f"Stop Price: {validated_inputs['stopPrice']}")
    print("=============================\n")
    
    logger.info(f"Initiating order request: {validated_inputs}")
    
    # Initialize Client & Place Order
    try:
        # Initialize the API client
        client = BinanceFuturesClient(api_key=final_api_key, secret_key=final_secret_key)
        
        # Test connection
        print("Checking connection to Binance Futures Testnet...")
        if not client.test_connection():
            print("[WARNING] Could not connect or ping Binance Testnet server. Attempting order placement anyway...")
        else:
            print("Connection successful.")
            
        print("Placing order...")
        response = place_order(client, validated_inputs)
        
        # Print success message and order details
        print("\n[SUCCESS] Order placed successfully!")
        summary_text = format_order_summary(response)
        print(summary_text)
        
    except Exception as e:
        print(f"\n[FAILURE] Order execution failed: {e}")
        logger.exception("Exception occurred during order execution:")
        sys.exit(1)


if __name__ == "__main__":
    main()
