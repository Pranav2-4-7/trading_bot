import sys
import subprocess
import os

def print_help():
    print("🤖 TradingBOT Operations Pipeline Controller")
    print("Commands:")
    print("  python run_pipeline.py start      - Launches Web Server & MLflow tracker")
    print("  python run_pipeline.py report     - Computes & prints today's audit report")
    print("  python run_pipeline.py weekly     - Aggregates weekly metrics & logs journal")

def start_pipeline():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Starting pipeline from: {base_dir}")
    print("Run operations using python TradingBOT/web_server.py or python TradingBOT/daily_reporter.py.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)
        
    cmd = sys.argv[1].lower()
    if cmd == "start":
        start_pipeline()
    elif cmd == "report":
        subprocess.run([sys.executable, "daily_reporter.py"])
    elif cmd == "weekly":
        subprocess.run([sys.executable, "weekly_stats.py"])
    else:
        print_help()
