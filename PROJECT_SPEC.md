# Build Spec — Hybrid Momentum Screener + Discretionary Price-Action Workflow

A daily stock workflow for the Stockholm exchange (extendable to US). The
machine does the mechanical part it's good at (momentum/trend screening); a
human does the discretionary part where skill is the edge (Al Brooks H2/H3
entries on the chart); AI assists as a research tool, never as a decision-maker.

This document is the source of truth. Build in phase order. Phase 1 is
non-negotiable and comes before any tuning or feature work.

---

## Core philosophy (read before writing code)

- **Mechanical where edge is documented, discretionary where humans add value.**
  Momentum/trend-following is one of the few robustly documented edges, and it
  suits deterministic code. Reading a pullback's bar structure for an H2/H3 entry
  is the user's skill — keep it human.
- **AI is a research assistant, not a trader.** The AI never reads a chart to
  decide a trade and never emits buy/sell calls. Its weakest use is chart/OHLC
  interpretation; the human does that.
- **Validate before trusting.** A backtest that looks good is usually overfit.
  Honest, after-cost, out-of-sample evaluation against a baseline is the only
  thing that tells us if the premise holds.
- **Simple over complex.** Prefer few parameters and few moving parts. Every
  added knob increases overfitting risk and maintenance burden.

---

## Non-goals (explicitly DO NOT build)

- ❌ An LLM that reads charts or OHLC and decides/scores trades.
- ❌ Automated order execution.
- ❌ Price-prediction ML (LSTM/ARIMA/etc.). The "predict the price" genre is a
  known illusion (low RMSE on price levels ≈ lagging yesterday's price).
- ❌ A heavy self-improving journal/memory system at the start. (A lightweight
  deterministic stats loop is fine later — see Phase 4.)
- ❌ Sentiment-driven decisioning. Swedish small/mid caps have thin English
  news; sentiment edge is weak. Use news only for event-risk flagging.

---

## What already exists (build ON these — do not rewrite from scratch)

- **`pullback_screener.py`** — the screener. Surfaces momentum names in an
  established uptrend that are currently pulling back toward the EMA20 zone and
  have room to run, ranked by Clenow R²-composite momentum. Outputs a watchlist
  with context (pullback depth in ATR, distance to EMA20, pullback age, room in
  R). Emits NO signals — the human confirms the H2/H3.
- **`trend_following_backtest.py`** — a mechanical long-only trend-following
  backtest (Donchian breakout + ATR chandelier + volatility sizing + regime
  filter). Serves as a BASELINE the discretionary approach must beat. Already
  prints CAGR, Sharpe, max DD, win rate, payoff, profit factor vs buy & hold.

---

## Cross-cutting discipline (applies to every phase)

- **No look-ahead.** Signals computed only on closed bars; indicators shifted so
  no future data leaks. Entries execute at next bar's open, not the signal bar.
- **Survivorship bias.** Any real backtest needs a point-in-time (delisting-aware)
  constituent list. A hand-picked list of today's names is optimistic by an
  unknown, possibly large margin — document this wherever results are reported.
- **Multiple testing.** Decide parameter ranges in advance from theory/convention,
  not by iterating until the curve looks good. Seek a *plateau* of good results
  across neighboring parameters, not the single best point. Discount the best
  result for the number of trials.
- **Realistic frictions.** Model commission + slippage. For Stockholm small caps,
  spreads are wider and gaps are real — be conservative.
- **Log everything** (foundation for Phase 4): each screener run, each trade the
  user takes or skips and why, and the outcome.

---

## Phase 1 — Validation harness (DO THIS FIRST)

Goal: answer one question — *does the screen surface tradeable setups that beat
the baseline on a purged out-of-sample window, after costs?* Until this is
answered, do not build features or tune.

Build a backtest that:
- Uses a **mechanical proxy** for the discretionary entry (e.g., "enter on a
  close above the prior bar's high while the stock is in the screen's pullback
  zone"). This underestimates the user's skilled entry but tests the premise.
- Exits via stop / ATR chandelier (reuse logic from `trend_following_backtest.py`).
- Splits data into **train / test with a held-out final period used exactly once.**
- Runs **walk-forward** (rolling train→test windows through time).
- Runs a **parameter robustness sweep** over the screen's key thresholds
  (pullback depth, EMA20 band, momentum window, room-in-R) and reports the
  **distribution / plateau**, not just the best configuration.
- Compares against TWO baselines: (a) index buy & hold, (b) the existing
  trend-following backtest.
- Reports, after costs: CAGR, Sharpe, max drawdown, win rate, payoff ratio,
  profit factor, trade count, exposure.

**Acceptance:** prints a clear verdict on whether the proxy strategy beats both
baselines on the held-out window after costs, plus the robustness plateau plot/
table. If it can't beat buy & hold risk-adjusted, that's a real and useful result.

---

## Phase 2 — Screener improvements (priority order)

Add to `pullback_screener.py`. Stop here unless validation justifies more.

1. **Liquidity filter (real gap — do first).** Median daily turnover in SEK over
   a configurable threshold. Without it, illiquid pump-and-dump small caps
   (e.g. Sivers-type names) slip through and gap through stops.
2. **Pullback quality (highest value for the user).** Score the *character* of the
   pullback bars, not just location: small, overlapping bars with small bodies (a
   calm bull flag) rank above deep large bear bars or gaps (a trend-killing
   pullback). This is the triage signal a Brooks trader's eye looks for, encoded.
3. **Relative strength.** Strength of the stock vs the index and vs its sector. A
   pullback in a name strong relative to a weak index is higher quality.
4. **True swing structure.** Require actual higher highs / higher lows rather than
   relying on moving averages; define "trend intact" as "has not broken the prior
   higher low" instead of `close > EMA50`.

---

## Phase 3 — AI context & event-risk digest (first AI layer — highest value, lowest risk)

A separate module that consumes the screener's watchlist and annotates each name.

- **Input:** the ranked watchlist from `pullback_screener.py`.
- **Per name, produce:** any earnings/report within ~5 trading days; news that
  explains the pullback (rights issue? guidance cut? sector rotation?); obvious
  red flags. This captures exactly what the chart does NOT show.
- **Hard constraints (enforce in the prompt):**
  - NEVER a buy/sell/hold recommendation. Context only.
  - Cite sources for every factual claim.
  - Structured output (JSON) so it's parseable and loggable.
  - temperature 0.
- **Data:** web search / a news API for headlines + an LLM (Claude) to summarize
  and flag. Respect copyright (paraphrase, short quotes only).

**Acceptance:** given a watchlist, outputs a per-name JSON digest of event risk and
pullback-explaining news with citations, and zero trade recommendations.

---

## Phase 4 — Optional AI advisory + lightweight feedback (only after the above earns its place)

- **Pre-mortem prompt.** On a name the user is considering: given the user's own
  read, return the 3 strongest reasons the pullback becomes a real reversal
  instead of the trend resuming — overhead resistance, macro risk, "this is the
  third push of a wedge," etc. Advisory, never a decision.
- **Post-trade reflector + per-setup stats** (inspired by prism-insight, kept
  simple):
  - Deterministic part: log every trade with its entry context (the screen's
    metrics + which conditions were met) and outcome (hit 1R / stopped, holding
    days, return). Compute **per-setup-type win rate × payoff with a minimum-n
    guard.** This is backtestable and answers "which setups actually have edge."
  - Optional LLM part: a structured post-mortem (situation analysis, judgment
    evaluation, lessons as condition→action→reason→priority, pattern tags,
    one-line summary, confidence) per closed trade.
  - Bias guards (borrow from prism): require minimum n before trusting a stat;
    require ≥2 supporting trades before promoting a "rule"; do NOT feed the system
    "what it missed" (induces FOMO). Keep any feedback into the screen a
    **deterministic gate**, not an LLM suggestion, so it stays testable.

---

## Tech stack & conventions

- Python; `pandas`, `numpy`, `yfinance` for data.
- Stockholm: `.ST` tickers, benchmark `^OMX`. (US: plain tickers, `SPY`.)
- LLM layers via the Anthropic API (Claude), temperature 0, structured/JSON output.
- Keep each module independently runnable with a `CONFIG` block at the top.
- All tunable thresholds live in `CONFIG`, never hard-coded inline.

---

## Daily workflow this enables (the end state)

1. After close, `pullback_screener.py` runs → ranked watchlist.
2. The context digest (Phase 3) annotates each name with event risk / news.
3. The user opens each chart, decides if an H2/H3 trigger prints, and takes the
   position discretionarily.
4. The user logs the decision (taken/skipped + reason) and the outcome.
5. Periodically, the reflector + per-setup stats (Phase 4) show what actually has
   edge — feeding back into thresholds deterministically.

The machine narrows the field and flags hazards. The human reads the bar and
pulls the trigger. The discipline (validation + logging) is what tells you,
over time, whether any of it is real.
