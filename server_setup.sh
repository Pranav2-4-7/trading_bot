#!/bin/bash
set -e

echo "=================================================="
echo "  TradingBOT 24x7 Cloud Server Environment Setup   "
echo "=================================================="

# Update and install python3, venv, and build tools
if command -v apt &> /dev/null; then
    sudo apt update -y
    sudo apt install -y python3 python3-pip python3-venv tmux curl git
fi

# Setup virtual environment
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing production dependencies (PyTorch CPU & ML stack)..."
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

echo "Ensuring required directories exist..."
mkdir -p data models reports

echo "=================================================="
echo " Setup complete! Start the bot using: ./start.sh  "
echo "=================================================="
