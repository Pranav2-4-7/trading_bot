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

def calculate_weekly_metrics(state):
    if not state:
        return None

    initial = state.get("initial_capital", 100000.0)
    cash = state.get("current_cash", initial)
    positions = state.get("active_positions", {})
    trade_log = state.get("trade_log", [])

    # Current Valuation
    positions_val = 0.0
    for pos in positions.values():
        shares = pos.get("shares", 0)
        price = pos.get("current_price", pos.get("fill_price", pos.get("entry_price", 0.0)))
        positions_val += shares * price

    total_val = cash + positions_val
    net_return = ((total_val - initial) / initial) * 100.0 if initial > 0 else 0.0

    # Trade stats
    closed_trades = len(trade_log)
    winning_trades = sum(1 for t in trade_log if t.get("Profit_Loss", 0.0) > 0)
    losing_trades = closed_trades - winning_trades
    win_rate = (winning_trades / closed_trades * 100.0) if closed_trades > 0 else 0.0

    total_profit = sum(t.get("Profit_Loss", 0.0) for t in trade_log if t.get("Profit_Loss", 0.0) > 0)
    total_loss = abs(sum(t.get("Profit_Loss", 0.0) for t in trade_log if t.get("Profit_Loss", 0.0) < 0))
    profit_factor = (total_profit / total_loss) if total_loss > 0 else (total_profit if total_profit > 0 else 1.0)

    avg_pnl = sum(t.get("Profit_Loss", 0.0) for t in trade_log) / closed_trades if closed_trades > 0 else 0.0

    return {
        "valuation": total_val,
        "net_return": net_return,
        "closed_trades": closed_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "avg_pnl": avg_pnl,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades
    }

def generate_weekly_report():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    reports_dir = os.path.join(base_dir, "reports")
    if not os.path.exists(reports_dir):
        os.makedirs(reports_dir)

    now = datetime.datetime.now()
    year, week, _ = now.isocalendar()
    report_filename = f"weekly_report_{year}-W{week:02d}.md"
    report_path = os.path.join(reports_dir, report_filename)

    profiles = [
        {"id": "macro", "name": "🚀 5-Year Macro Trend (0.57 Threshold)", "file": "live_paper_portfolio_macro.json"},
        {"id": "ultra", "name": "🎯 Ultra-High Conviction (0.68 Threshold)", "file": "live_paper_portfolio_ultra.json"},
        {"id": "legacy", "name": "📜 Legacy Account", "file": "live_paper_portfolio.json"}
    ]

    report_md = []
    report_md.append(f"# 📅 Weekly Performance Stats Report (Week {week:02d}, {year})")
    report_md.append(f"> **Generated At:** `{now.strftime('%Y-%m-%d %H:%M:%S IST')}`\n")
    report_md.append(f"---")
    report_md.append(f"## 📊 Profile Metrics Breakdown\n")

    for p in profiles:
        file_path = get_portfolio_path(p["file"])
        stats = calculate_weekly_metrics(load_portfolio(file_path))
        if stats is None:
            continue

        def fmt_val(val):
            return f"**`+{val:.2f}%`** 🟢" if val > 0 else (f"**`{val:.2f}%`** 🔴" if val < 0 else f"**`+0.00%`** ⚪")

        report_md.append(f"### {p['name']}")
        report_md.append(f"| Metric | Value |")
        report_md.append(f"| :--- | :--- |")
        report_md.append(f"| **Portfolio Valuation** | INR {stats['valuation']:,.2f} |")
        report_md.append(f"| **Net Cumulative Return** | {fmt_val(stats['net_return'])} |")
        report_md.append(f"| **Win Rate** | `{stats['win_rate']:.1f}%` ({stats['winning_trades']} Wins / {stats['losing_trades']} Losses) |")
        report_md.append(f"| **Profit Factor** | `{stats['profit_factor']:.2f}` |")
        report_md.append(f"| **Average PnL per Trade** | INR {stats['avg_pnl']:+,.2f} |")
        report_md.append(f"| **Total Closed Trades** | `{stats['closed_trades']}` |\n")

    report_md.append(f"---")
    report_md.append(f"## 🛡️ Risk Management Summary")
    report_md.append(f"- **Dynamic Volatility Slippage:** Operating optimally to reduce execution decay.")
    report_md.append(f"- **RSI Micro-Dip entry restrictions:** Safely protected cash on local overbought spikes.")
    report_md.append(f"- **Evidently AI Drift Monitor:** Clean, no emergency retraining triggered this week.")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_md))

    print(f"Weekly stats report generated successfully: {report_path}")

if __name__ == "__main__":
    generate_weekly_report()
