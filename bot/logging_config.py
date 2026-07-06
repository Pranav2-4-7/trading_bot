import logging
import os
import re

def mask_api_key(api_key: str) -> str:
    """Masks the API key for safe logging, exposing only the first 4 and last 4 characters."""
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "****"
    return f"{api_key[:4]}...{api_key[-4:]}"

def setup_logging(log_file='trading_bot.log'):
    """
    Sets up logging for the trading bot.
    Logs DEBUG and above to the specified log file.
    Logs INFO and above to the console.
    """
    logger = logging.getLogger('trading_bot')
    logger.setLevel(logging.DEBUG)
    
    # Prevent duplicate handlers
    if logger.handlers:
        return logger
        
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    
    # File Handler: Detailed logging for troubleshooting/records
    try:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not create log file '{log_file}': {e}. Logging only to console.")
        
    # Console Handler: Cleaner logging for the user during execution
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger
