# Binance Futures Testnet Trading Bot

A structured, lightweight, and robust Python command-line application built to place and manage orders on the Binance Futures Testnet (USDT-M). This project uses raw HTTP requests to ensure high reliability, zero package deprecation issues, and complete control over the network layer.

## Features

- **Core Orders**: Supports `MARKET` and `LIMIT` orders for both `BUY` and `SELL` sides.
- **Bonus Order Type**: Supports `STOP_MARKET` orders (Stop Loss triggers).
- **Time Synchronization**: Automatically synchronizes system clock with Binance server time to prevent clock drift issues (`-1021: timestamp outside recvWindow` error).
- **Dual CLI Interface**:
  - **Direct CLI Mode**: Fully automated headless script execution using command-line arguments.
  - **Enhanced Interactive Mode (Bonus)**: Beautiful interactive prompt workflow using `questionary` with dropdown selection lists, autocomplete, password hiding for secret keys, and pre-execution confirmations.
- **Robust Validation**: Real-time validation of symbol formatting, sides, order types, quantities, limit prices, and stop prices before sending requests.
- **Structured Logging**: Comprehensive but clean log outputs to both the console and a persistent `trading_bot.log` file with masked API credentials for security.
- **Unit Tests**: Full unit test coverage for inputs validation.

---

## Project Structure

```
trading_bot/
  bot/
    __init__.py
    client.py           # Authenticated REST API Client wrapper with clock sync
    orders.py           # Order parameters preparation and execution logic
    validators.py       # User input sanitization and verification logic
    logging_config.py   # Console and file logging configuration
  tests/
    test_validators.py  # Unit tests for the validation logic
  cli.py                # Main CLI entry point (Direct & Interactive)
  .env.example          # Template for API credentials
  requirements.txt      # External dependencies
  README.md             # This documentation
```

---

## Setup & Installation

### 1. Prerequisites
- Python 3.8 or higher.
- A Binance Futures Testnet account. You can register/login at [Binance Futures Testnet](https://testnet.binancefuture.com) and generate an **API Key** and **Secret Key**.

### 2. Install Dependencies
Initialize a virtual environment and install the required libraries:

```bash
# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Credentials
Duplicate the `.env.example` file to create a `.env` file in the project root:

```bash
cp .env.example .env
```

Open `.env` and fill in your Binance Futures Testnet credentials:
```env
BINANCE_API_KEY=your_actual_testnet_api_key_here
BINANCE_SECRET_KEY=your_actual_testnet_secret_key_here
```

---

## How to Run Examples

### 1. Interactive Mode (Enhanced UX)
If you run the CLI without any arguments, it will launch the interactive menus. If credentials are not set in the `.env` file, it will prompt you to type them securely.

```bash
python cli.py
```

### 2. Direct CLI Mode (Headless Automation)
You can place orders instantly by supplying the parameters directly in your shell:

#### Placement Examples:

- **Place a MARKET BUY Order**:
  ```bash
  python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001
  ```

- **Place a LIMIT SELL Order**:
  ```bash
  python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.001 --price 95000.0
  ```

- **Place a STOP_MARKET BUY Order (Stop Loss)**:
  ```bash
  python cli.py --symbol BTCUSDT --side BUY --type STOP_MARKET --quantity 0.001 --stop-price 90000.0
  ```

---

## Running Unit Tests

We use `pytest` for unit testing the input validator. To run the test suite:

```bash
python -m pytest tests/
```

---

## Log Files

All logs (containing outgoing request URLs, timestamp offsets, request params, response codes, and JSON bodies) are saved to `trading_bot.log` in the root folder. Sensitive keys are obfuscated automatically.
