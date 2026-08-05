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

def get_portfolio_path(filename: str) -> str:
    """Finds absolute path of portfolio file among standard data directories."""
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

def update_readme_metrics(readme_path: str = "README.md") -> None:
    """Updates README markdown metrics placeholders with latest live portfolio values."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    config_path = os.path.join(base_dir, "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as conf_f:
            config = json.load(conf_f)
            profiles = config.get("profiles", [])
    else:
        profiles = [
            {"id": "macro", "name": "🚀 5-Year Macro Trend (0.57 Threshold)", "file": "live_paper_portfolio_macro.json"},
            {"id": "ultra", "name": "🎯 Ultra-High Conviction (0.68 Threshold)", "file": "live_paper_portfolio_ultra.json"},
            {"id": "legacy", "name": "📜 Legacy Account", "file": "live_paper_portfolio.json"}
        ]

    rows = []
    for p in profiles:
        p_path = get_portfolio_path(p["file"])
        m = compute_profile_metrics(load_portfolio(p_path))
        def fmt_ret(ret):
            if ret > 0:
                return f"**`+{ret:.2f}%`** 🟢"
            elif ret < 0:
                return f"**`{ret:.2f}%`** 🔴"
            else:
                return f"**`+0.00%`** ⚪"
        rows.append(f"| **{p['name']}** | INR {m['initial_capital']:,.2f} | **INR {m['valuation']:,.2f}** | INR {m['cash']:,.2f} | {fmt_ret(m['net_return'])} | **`{m['win_rate']:.1f}%`** | {m['open_positions']} | {m['closed_trades']} |")

    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')

    table_header = f"""<!-- LIVE_METRICS_START -->
## 📈 Live Portfolio Performance Metrics

> **Last Auto-Synced:** `{now_str}`

| Strategy Profile | Initial Capital | Valuation | Cash Balance | Net Return | Win Rate | Open Positions | Closed Trades |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""
    metrics_table = table_header + "\n".join(rows) + "\n<!-- LIVE_METRICS_END -->"

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
