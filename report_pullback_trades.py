"""
Per-trade breakdown of the pullback-strategy held-out backtest, rendered as
a single self-contained HTML page with a price chart per trade (entry/exit
marked, EMA20/EMA50 and the recent swing high shown) so the entries can be
eyeballed for sanity.

Run:  python report_pullback_trades.py
Output: pullback_holdout_trades.html
"""

import base64
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import price_db
import backtest_engine as engine
import validate_pullback_strategy as val

CONFIG = dict(val.CONFIG)
OUTPUT_HTML = "pullback_holdout_trades.html"
CONTEXT_DAYS_BEFORE = 60
CONTEXT_DAYS_AFTER = 10


def fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=90)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def plot_trade(df, trade):
    entry_date, exit_date = trade["entry_date"], trade["exit_date"]
    start = entry_date - pd.Timedelta(days=CONTEXT_DAYS_BEFORE)
    end = exit_date + pd.Timedelta(days=CONTEXT_DAYS_AFTER)
    window = df[(df.index >= start) & (df.index <= end)]

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(window.index, window["Close"], label="Close", color="black", linewidth=1)
    ax.plot(window.index, window["EMA20"], label="EMA20", color="tab:blue", linewidth=1)
    ax.plot(window.index, window["EMA50"], label="EMA50", color="tab:orange", linewidth=1)
    ax.plot(window.index, window["recent_high"], label="Recent high (40d)",
            color="grey", linestyle="--", linewidth=0.8)

    ax.scatter([entry_date], [trade["entry"]], color="green", marker="^", s=80,
               zorder=5, label="Entry")
    ax.scatter([exit_date], [trade["exit"]], color="red", marker="v", s=80,
               zorder=5, label="Exit")

    ax.set_title(f"{trade['ticker']}  entry {entry_date.date()} -> exit {exit_date.date()}  "
                  f"ret {trade['ret']*100:+.1f}%")
    ax.legend(fontsize=7, loc="best")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    return fig_to_base64(fig)


def main():
    cfg = CONFIG
    print("Loading data...")
    data, bench = val.load_all(cfg)
    regime_on = (bench["Close"] > bench["Close"].rolling(cfg["regime_sma"]).mean())

    print("Running held-out backtest...")
    eq, trades = val.run_window(data, bench, cfg, regime_on,
                                  start=cfg["held_out_start"], end=cfg["full_end"])
    if trades is None or trades.empty:
        raise SystemExit("No trades in held-out window.")

    trades = trades.sort_values("entry_date").reset_index(drop=True)
    strat = engine.perf_stats(eq, print_report=False)
    tstats = engine.trade_stats(trades, print_report=False)

    print(f"Rendering {len(trades)} trade charts...")
    rows_html = []
    for _, tr in trades.iterrows():
        df = data[tr["ticker"]]
        img = plot_trade(df, tr)
        outcome = "win" if tr["pnl"] > 0 else "loss"
        rows_html.append(f"""
        <div class="trade {outcome}">
          <h3>{tr['ticker']} &mdash; {tr['entry_date'].date()} &rarr; {tr['exit_date'].date()}
              &nbsp; <span class="{outcome}">{tr['ret']*100:+.2f}%</span>
              (pnl {tr['pnl']:+.0f})</h3>
          <table class="meta">
            <tr><td>Entry price</td><td>{tr['entry']:.2f}</td>
                <td>Exit price</td><td>{tr['exit']:.2f}</td>
                <td>Shares</td><td>{tr['shares']}</td></tr>
          </table>
          <img src="data:image/png;base64,{img}" />
        </div>
        """)

    summary = f"""
    <h2>Held-out period summary ({cfg['held_out_start']} &rarr; latest)</h2>
    <table class="meta">
      <tr><td>Total trades</td><td>{tstats['n_trades']}</td></tr>
      <tr><td>Win rate</td><td>{tstats['win_rate']*100:.1f}%</td></tr>
      <tr><td>Payoff ratio</td><td>{tstats['payoff']:.2f}</td></tr>
      <tr><td>Profit factor</td><td>{tstats['profit_factor']:.2f}</td></tr>
      <tr><td>CAGR</td><td>{strat['cagr']*100:.2f}%</td></tr>
      <tr><td>Sharpe</td><td>{strat['sharpe']:.2f}</td></tr>
      <tr><td>Max drawdown</td><td>{strat['max_dd']*100:.2f}%</td></tr>
    </table>
    <p>Green markers = entry (open of fill day), red markers = exit (stop hit).
       Dashed grey = 40-day recent high used for the room-to-resistance check.</p>
    """

    html = f"""<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="utf-8">
<title>Pullback strategy &mdash; held-out trade breakdown</title>
<style>
  body {{ font-family: sans-serif; max-width: 1000px; margin: 20px auto; }}
  h1, h2 {{ }}
  table.meta {{ border-collapse: collapse; margin: 8px 0; }}
  table.meta td {{ padding: 2px 10px; font-size: 0.9em; }}
  .trade {{ border: 1px solid #ddd; border-radius: 6px; padding: 10px; margin: 16px 0; }}
  .trade.win {{ border-left: 6px solid #2a9d2a; }}
  .trade.loss {{ border-left: 6px solid #c0392b; }}
  .win {{ color: #2a9d2a; font-weight: bold; }}
  .loss {{ color: #c0392b; font-weight: bold; }}
  img {{ max-width: 100%; }}
</style>
</head>
<body>
<h1>Pullback strategy &mdash; held-out trade breakdown</h1>
{summary}
{''.join(rows_html)}
</body>
</html>
"""
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
