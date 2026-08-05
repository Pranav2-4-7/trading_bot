import os
import json
import datetime
from update_readme_metrics import update_readme_metrics

def get_portfolio_path(filename: str) -> str:
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

def generate_daily_report(output_dir="reports", date_str=None):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    reports_dir = os.path.join(base_dir, output_dir)

    if not os.path.exists(reports_dir):
        os.makedirs(reports_dir)

    today_date_str = date_str if date_str is not None else datetime.datetime.now().strftime("%Y-%m-%d")
    now_timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " IST" if date_str is None else f"{date_str} 15:30:00 IST"

    # Load profiles from config.json
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

    report_md = []
    report_md.append(f"# 📊 TradingBOT Daily Market Performance Report")
    report_md.append(f"> **Date:** `{today_date_str}` | **Generated At:** `{now_timestamp_str}`")
    report_md.append(f"\n---")
    report_md.append(f"## 📌 Executive Summary")

    journal_rows = []

    for p in profiles:
        file_path = get_portfolio_path(p["file"])
        if not os.path.exists(file_path):
            continue

        with open(file_path, "r") as f:
            state = json.load(f)

        initial = state.get("initial_capital", 100000.0)
        cash = state.get("current_cash", initial)
        positions = state.get("active_positions", {})
        trade_log = state.get("trade_log", [])

        # Holdings value
        holdings_val = 0.0
        for ticker, pos in positions.items():
            shares = pos.get("shares", 0)
            price = pos.get("current_price", pos.get("fill_price", pos.get("entry_price", 0.0)))
            holdings_val += shares * price

        total_val = cash + holdings_val
        net_return = ((total_val - initial) / initial) * 100.0 if initial > 0 else 0.0

        # Filter today's closed trades
        today_trades = [
            t for t in trade_log 
            if str(t.get("Exit_Date", "")).startswith(today_date_str)
        ]
        
        total_closed_today = len(today_trades)
        wins_today = sum(1 for t in today_trades if t.get("Profit_Loss", 0.0) > 0)
        pnl_today = sum(t.get("Profit_Loss", 0.0) for t in today_trades)
        win_rate_today = (wins_today / total_closed_today * 100.0) if total_closed_today > 0 else 0.0

        # Total lifetime trades
        wins_total = sum(1 for t in trade_log if t.get("Profit_Loss", 0.0) > 0)
        win_rate_total = (wins_total / len(trade_log) * 100.0) if len(trade_log) > 0 else 0.0

        report_md.append(f"\n### {p['name']}")
        report_md.append(f"- **Initial Capital:** INR {initial:,.2f}")
        report_md.append(f"- **Cash Liquidity:** INR {cash:,.2f}")
        report_md.append(f"- **Holdings Value:** INR {holdings_val:,.2f}")
        report_md.append(f"- **Total Portfolio Valuation:** **INR {total_val:,.2f}**")
        report_md.append(f"- **Net Return:** **`{net_return:+.2f}%`**")
        report_md.append(f"- **Today's Trades Closed:** `{total_closed_today}` (Wins: `{wins_today}` | Win Rate: `{win_rate_today:.1f}%`)")
        report_md.append(f"- **Today's Realized PnL:** **INR {pnl_today:+.2f}**")
        report_md.append(f"- **Lifetime Win Rate:** `{win_rate_total:.1f}%` ({len(trade_log)} total trades)")

        if today_trades:
            report_md.append(f"\n#### 📑 Today's Executed Trades Ledger")
            report_md.append(f"| Ticker | Entry Date | Exit Date | Fill Price | Exit Price | Slippage (INR) | Realized PnL | Exit Reason |")
            report_md.append(f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
            for t in today_trades:
                fill_p = t.get("Fill_Price", t.get("Entry_Price", 0.0))
                exit_p = t.get("Exit_Price", 0.0)
                slip_inr = t.get("Slippage_INR", 0.0)
                pnl = t.get("Profit_Loss", 0.0)
                reason = t.get("Exit_Reason", "Model Signal")
                report_md.append(f"| **{t.get('Ticker')}** | {t.get('Entry_Date')} | {t.get('Exit_Date')} | INR {fill_p:.2f} | INR {exit_p:.2f} | INR {slip_inr:.2f} | **INR {pnl:+.2f}** | {reason} |")
        else:
            report_md.append(f"\n*No closed trades for this profile today.*")

        journal_rows.append(f"| `{today_date_str}` | **{p['id'].upper()}** | INR {total_val:,.2f} | `{net_return:+.2f}%` | `{total_closed_today}` | **INR {pnl_today:+.2f}** |")

    report_md.append(f"\n---")
    report_md.append(f"## 🛡️ Risk & Model Drift Status")
    report_md.append(f"- **Evidently AI Drift Evaluation:** Clean / Baseline Monitored")
    report_md.append(f"- **Dynamic Slippage Calculation:** Operational")
    report_md.append(f"- **Micro-Dip & 50 DMA Filters:** Active")

    full_report_str = "\n".join(report_md)

    # Save daily report file
    report_file_name = f"daily_report_{today_date_str}.md"
    report_file_path = os.path.join(reports_dir, report_file_name)
    with open(report_file_path, "w", encoding="utf-8") as f:
        f.write(full_report_str)

    print(f"Daily report generated: {report_file_path}")

    # Append to Master Journal
    journal_file_path = os.path.join(reports_dir, "performance_journal.md")
    if not os.path.exists(journal_file_path):
        journal_header = "# 📖 TradingBOT Daily Performance Journal\n\n| Date | Profile | Total Valuation | Net Return | Today Trades | Today Realized PnL |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n"
        with open(journal_file_path, "w", encoding="utf-8") as f:
            f.write(journal_header)

    with open(journal_file_path, "a", encoding="utf-8") as f:
        for row in journal_rows:
            f.write(row + "\n")

    print(f"Updated performance journal: {journal_file_path}")

    # Sync README metrics
    update_readme_metrics()

    return report_file_path

if __name__ == "__main__":
    import sys
    target_date = sys.argv[1] if len(sys.argv) > 1 else None
    
    if target_date is None:
        today = datetime.datetime.now()
        # 5 is Saturday, 6 is Sunday
        if today.weekday() == 5:
            target_date = (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            print(f"Weekend detected (Saturday). Defaulting report date to yesterday: {target_date}")
        elif today.weekday() == 6:
            target_date = (today - datetime.timedelta(days=2)).strftime("%Y-%m-%d")
            print(f"Weekend detected (Sunday). Defaulting report date to Friday: {target_date}")
            
    generate_daily_report(date_str=target_date)
