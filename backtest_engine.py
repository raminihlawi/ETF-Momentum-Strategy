"""
Shared event-driven daily backtest engine, factored out of
trend_following_backtest.py so the pullback-validation harness
(validate_pullback_strategy.py) can reuse the same execution, stop and
costing logic. Strategies differ only in how `entry_signal` and `ATR`
(and optionally `momentum` for ranking) are computed per bar.

Timing convention (no look-ahead):
  * Signals are computed at the CLOSE of day d (entry_signal True means
    "conditions met as of this close").
  * Entries fill at the OPEN of day d+1.
  * A position's trailing stop is fixed at the close of day d and is the
    level checked against the LOW of day d+1.

Each `data[ticker]` DataFrame must have columns:
  Open, High, Low, Close, ATR, entry_signal (bool), momentum (for ranking
  when slots are scarce; NaN is treated as worst).
"""

import math
import numpy as np
import pandas as pd


def run_backtest(data, benchmark, cfg, regime_on=None):
    """`regime_on` may be precomputed over a longer history than `benchmark`
    (e.g. when `benchmark` is a short walk-forward slice but the 200-day
    rolling average needs lookback before the slice starts)."""
    all_dates = benchmark.index
    if regime_on is None:
        regime_on = (benchmark["Close"] >
                     benchmark["Close"].rolling(cfg["regime_sma"]).mean())

    cash = cfg["starting_capital"]
    positions = {}
    pending = []
    equity_curve = []
    trades = []

    sm = cfg["stop_atr_mult"]

    for d in all_dates:
        # ---- 1. EXITS: check stops set on the previous day ----
        for t in list(positions.keys()):
            df = data[t]
            if d not in df.index:
                continue
            row = df.loc[d]
            pos = positions[t]

            if row["Low"] <= pos["stop"]:
                fill = min(row["Open"], pos["stop"]) * (1 - cfg["slippage_pct"])
                proceeds = pos["shares"] * fill
                proceeds -= proceeds * cfg["commission_pct"]
                cash += proceeds
                pnl = (fill - pos["entry"]) * pos["shares"]
                trades.append({"ticker": t, "entry": pos["entry"],
                               "exit": fill, "shares": pos["shares"],
                               "pnl": pnl,
                               "ret": fill / pos["entry"] - 1.0,
                               "entry_date": pos["entry_date"], "exit_date": d})
                del positions[t]
                continue

            pos["hh"] = max(pos["hh"], row["Close"])
            new_stop = pos["hh"] - sm * row["ATR"]
            pos["stop"] = max(pos["stop"], new_stop)

        # ---- 2. ENTRIES: fill orders queued yesterday, at today's open ----
        def equity_now():
            held = 0.0
            for t, p in positions.items():
                df = data[t]
                if d in df.index:
                    held += p["shares"] * df.loc[d, "Open"]
                else:
                    held += p["shares"] * p["entry"]
            return cash + held

        for order in pending:
            t = order["ticker"]
            if t in positions or len(positions) >= cfg["max_positions"]:
                continue
            df = data[t]
            if d not in df.index:
                continue
            row = df.loc[d]
            entry = row["Open"] * (1 + cfg["slippage_pct"])
            init_stop = entry - sm * order["atr"]
            risk_per_share = entry - init_stop
            if risk_per_share <= 0 or math.isnan(risk_per_share):
                continue

            eq = equity_now()
            risk_dollars = eq * cfg["risk_per_trade"]
            shares = math.floor(risk_dollars / risk_per_share)
            if shares <= 0:
                continue

            cost = shares * entry
            cost_with_fee = cost * (1 + cfg["commission_pct"])
            if cost_with_fee > cash:
                shares = math.floor(cash / (entry * (1 + cfg["commission_pct"])))
                if shares <= 0:
                    continue
                cost = shares * entry
                cost_with_fee = cost * (1 + cfg["commission_pct"])

            cash -= cost_with_fee
            hh = row["Close"]
            stop = max(init_stop, hh - sm * row["ATR"])
            positions[t] = {"shares": shares, "entry": entry,
                            "stop": stop, "hh": hh, "entry_date": d}

        pending = []

        # ---- 3. SIGNALS: generate tomorrow's entry candidates ----
        if (not cfg.get("require_regime_on", True)) or bool(regime_on.get(d, False)):
            candidates = []
            slots = cfg["max_positions"] - len(positions)
            if slots > 0:
                for t, df in data.items():
                    if t in positions or d not in df.index:
                        continue
                    row = df.loc[d]
                    if (bool(row["entry_signal"]) and
                            not np.isnan(row["ATR"]) and row["ATR"] > 0):
                        mom = row.get("momentum", np.nan)
                        candidates.append((mom if not np.isnan(mom) else -9,
                                           t, row["ATR"]))
                candidates.sort(key=lambda x: x[0], reverse=True)
                for _, t, atr in candidates[:slots]:
                    pending.append({"ticker": t, "atr": atr})

        # ---- 4. mark-to-market equity ----
        held = 0.0
        for t, p in positions.items():
            df = data[t]
            if d in df.index:
                held += p["shares"] * df.loc[d, "Close"]
            else:
                held += p["shares"] * p["entry"]
        equity_curve.append((d, cash + held))

    eq = pd.Series({d: v for d, v in equity_curve}).sort_index()
    return eq, pd.DataFrame(trades)


# ============================ METRICS ============================
def perf_stats(equity, label=None, print_report=True):
    rets = equity.pct_change().dropna()
    n = len(equity)
    years = n / 252.0
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1 if years > 0 else 0
    ann_vol = rets.std() * math.sqrt(252)
    sharpe = (rets.mean() / rets.std() * math.sqrt(252)
              if rets.std() > 0 else float("nan"))
    dd = equity / equity.cummax() - 1.0
    max_dd = dd.min()
    if print_report and label:
        print(f"\n=== {label} ===")
        print(f"  Period            : {equity.index[0].date()} -> {equity.index[-1].date()}")
        print(f"  Final equity      : {equity.iloc[-1]:,.0f}")
        print(f"  CAGR              : {cagr*100:6.2f}%")
        print(f"  Annualized vol    : {ann_vol*100:6.2f}%")
        print(f"  Sharpe (rf=0)     : {sharpe:6.2f}")
        print(f"  Max drawdown      : {max_dd*100:6.2f}%")
    return {"cagr": cagr, "sharpe": sharpe, "max_dd": max_dd, "ann_vol": ann_vol}


def trade_stats(trades, print_report=True):
    if trades.empty:
        if print_report:
            print("\n  No trades generated.")
        return {"n_trades": 0, "win_rate": float("nan"), "payoff": float("nan"),
                "profit_factor": float("nan")}
    wins = trades[trades["pnl"] > 0]
    losses = trades[trades["pnl"] <= 0]
    win_rate = len(wins) / len(trades)
    avg_win = wins["ret"].mean() if not wins.empty else 0
    avg_loss = losses["ret"].mean() if not losses.empty else 0
    payoff = (avg_win / abs(avg_loss)) if avg_loss != 0 else float("nan")
    gross_win = wins["pnl"].sum()
    gross_loss = abs(losses["pnl"].sum())
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("nan")
    if print_report:
        print(f"\n  --- Trade stats ---")
        print(f"  Total trades      : {len(trades)}")
        print(f"  Win rate          : {win_rate*100:6.2f}%")
        print(f"  Avg win  / Avg loss: {avg_win*100:5.2f}% / {avg_loss*100:5.2f}%")
        print(f"  Payoff ratio      : {payoff:6.2f}")
        print(f"  Profit factor     : {profit_factor:6.2f}")
    return {"n_trades": len(trades), "win_rate": win_rate, "payoff": payoff,
            "profit_factor": profit_factor}


def buy_and_hold(benchmark, starting_capital):
    px = benchmark["Close"].dropna()
    shares = starting_capital / px.iloc[0]
    return px * shares
