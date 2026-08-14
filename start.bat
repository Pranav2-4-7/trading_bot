@echo off
title TradingBOT Startup Terminal
echo ==================================================
echo   🚀 TRADINGBOT MULTI-AGENT TERMINAL STARTUP
echo ==================================================
echo.

:: 1. Force kill any existing python server processes to prevent port conflicts
echo [1/4] Checking and clearing port locks...
taskkill /IM python3.13.exe /F 2>nul
taskkill /IM python.exe /F 2>nul
timeout /t 2 /nobreak >nul

:: 2. Detect script directory and change to it
cd /d "%~dp0"

:: 3. Determine python entrypoint path
set "RUNNER=web_server.py"
if exist "TradingBOT\web_server.py" (
    set "RUNNER=TradingBOT\web_server.py"
)

:: 4. Launch MLflow UI in a separate minimized window
echo [2/4] Launching MLflow Tracking Server (Port 5001)...
start /min cmd /c "title MLflow Server && python -m mlflow ui --port 5001"
timeout /t 3 /nobreak >nul

:: 5. Auto-open dashboard in browser
echo [3/4] Opening Web Terminal in browser...
start http://127.0.0.1:5000/

echo [4/4] Launching Flask Web Terminal Dashboard (Port 5000)...
echo.
echo Dashboard logs will stream below. Press CTRL+C to terminate all servers cleanly.
echo.

:: Start the server in the current window
python "%RUNNER%"
pause
