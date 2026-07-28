import os
import json
import datetime

def load_portfolio(filepath):
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None

def compute_profile_metrics(state):
    if not state:
        return {
            "initial_capital": 100000.0,
            "valuation": 100000.0,
            "cash": 100000.0,
            "net_return": 0.0,
            "win_rate": 0.0,
            "open_positions": 0,
            "closed_trades": 0
        }

    initial = state.get("initial_capital", 100000.0)
    cash = state.get("current_cash", initial)
    positions = state.get("active_positions", {})
    trade_log = state.get("trade_log", [])

    # Estimate active position value based on fill_price or entry_price
    positions_val = 0.0
    for pos in positions.values():
        shares = pos.get("shares", 0)
        price = pos.get("current_price", pos.get("fill_price", pos.get("entry_price", 0.0)))
        positions_val += shares * price

    total_val = cash + positions_val
    net_return = ((total_val - initial) / initial) * 100.0 if initial > 0 else 0.0

    # Win rate calculation
    winning_trades = sum(1 for t in trade_log if t.get("Profit_Loss", 0.0) > 0)
    total_closed = len(trade_log)
    win_rate = (winning_trades / total_closed * 100.0) if total_closed > 0 else 0.0

    return {
        "initial_capital": initial,
        "valuation": total_val,
        "cash": cash,
        "net_return": net_return,
        "win_rate": win_rate,
        "open_positions": len(positions),
        "closed_trades": total_closed
    }

def get_portfolio_path(filename):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "..", "data", filename),
        os.path.join(base_dir, "data", filename),
        os.path.join(base_dir, filename)
    ]
    for path in candidates:
        full_p = os.path.abspath(path)
        if os.path.exists(full_p):
            return full_p
    return os.path.abspath(os.path.join(base_dir, "..", "data", filename))

def update_readme_metrics(readme_path="README.md"):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    macro_path = get_portfolio_path("live_paper_portfolio_macro.json")
    ultra_path = get_portfolio_path("live_paper_portfolio_ultra.json")
    legacy_path = get_portfolio_path("live_paper_portfolio.json")

    macro_m = compute_profile_metrics(load_portfolio(macro_path))
    ultra_m = compute_profile_metrics(load_portfolio(ultra_path))
    legacy_m = compute_profile_metrics(load_portfolio(legacy_path))

    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')

    def fmt_ret(ret):
        if ret > 0:
            return f"**`+{ret:.2f}%`** 🟢"
        elif ret < 0:
            return f"**`{ret:.2f}%`** 🔴"
        else:
            return f"**`+0.00%`** ⚪"

    metrics_table = f"""<!-- LIVE_METRICS_START -->
## 📈 Live Portfolio Performance Metrics

> **Last Auto-Synced:** `{now_str}`

| Strategy Profile | Initial Capital | Valuation | Cash Balance | Net Return | Win Rate | Open Positions | Closed Trades |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **🚀 5-Year Macro Trend (0.57 Threshold)** | INR {macro_m['initial_capital']:,.2f} | **INR {macro_m['valuation']:,.2f}** | INR {macro_m['cash']:,.2f} | {fmt_ret(macro_m['net_return'])} | **`{macro_m['win_rate']:.1f}%`** | {macro_m['open_positions']} | {macro_m['closed_trades']} |
| **🎯 Ultra-High Conviction (0.68 Threshold)** | INR {ultra_m['initial_capital']:,.2f} | **INR {ultra_m['valuation']:,.2f}** | INR {ultra_m['cash']:,.2f} | {fmt_ret(ultra_m['net_return'])} | **`{ultra_m['win_rate']:.1f}%`** | {ultra_m['open_positions']} | {ultra_m['closed_trades']} |
| **📜 Legacy Account** | INR {legacy_m['initial_capital']:,.2f} | **INR {legacy_m['valuation']:,.2f}** | INR {legacy_m['cash']:,.2f} | {fmt_ret(legacy_m['net_return'])} | **`{legacy_m['win_rate']:.1f}%`** | {legacy_m['open_positions']} | {legacy_m['closed_trades']} |
<!-- LIVE_METRICS_END -->"""

    full_readme_path = os.path.abspath(os.path.join(base_dir, readme_path))
    if not os.path.exists(full_readme_path):
        print(f"README not found at {full_readme_path}")
        return

    with open(full_readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    start_marker = "<!-- LIVE_METRICS_START -->"
    end_marker = "<!-- LIVE_METRICS_END -->"

    if start_marker in content and end_marker in content:
        start_idx = content.find(start_marker)
        end_idx = content.find(end_marker) + len(end_marker)
        updated_content = content[:start_idx] + metrics_table + content[end_idx:]
    else:
        # Insert after first header rule
        overview_marker = "---"
        if overview_marker in content:
            parts = content.split(overview_marker, 1)
            updated_content = parts[0] + overview_marker + "\n\n" + metrics_table + "\n\n" + overview_marker + parts[1]
        else:
            updated_content = content + "\n\n" + metrics_table

    with open(full_readme_path, "w", encoding="utf-8") as f:
        f.write(updated_content)

    print(f"Updated live performance metrics in {full_readme_path}")

if __name__ == "__main__":
    update_readme_metrics()
