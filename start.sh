#!/bin/bash

# Activate virtualenv if present
if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "=================================================="
echo " Starting TradingBOT 24x7 Live Server & Dashboard "
echo "=================================================="

# Start in tmux session or background process
if command -v tmux &> /dev/null; then
    # Kill any existing trading_bot tmux session
    tmux kill-session -t trading_bot 2>/dev/null || true
    tmux new-session -d -s trading_bot 'python3 web_server.py'
    echo "TradingBOT is running inside tmux session 'trading_bot'!"
    echo "To view live terminal logs: tmux attach -t trading_bot"
    echo "To detach from logs:        Press Ctrl+B then D"
else
    nohup python3 web_server.py > trading_bot.log 2>&1 &
    echo "TradingBOT is running in background (PID: $!)"
    echo "To view live terminal logs: tail -f trading_bot.log"
fi

echo "Web dashboard running at http://0.0.0.0:5000"
echo "=================================================="
