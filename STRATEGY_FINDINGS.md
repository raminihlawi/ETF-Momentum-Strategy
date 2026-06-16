# ETF Rotation Strategy — Research Findings
*Last updated: 2026-06-16*

---

## Universe & Setup

- **Universe**: UCITS ETFs listed on London Stock Exchange (LSE)
- **Data source**: yfinance via `etf_momentum_backtest.py`
- **Backtest window**: 2019-10 to 2026-06 (~6.7 years, limited by ETF listing history)
- **Transaction costs**: 0.15% per side, TER drag applied daily
- **Rebalance**: monthly (month-end signal → next open execution)
- **Config file**: `etf_universe.csv`, `marketfighter_replica.py::CONFIG`

**Sleeves:**
- Factor: IWVL.L (Value), IWQU.L (Quality), IWMO.L (Momentum), WSML.L (Small Cap)
- Sector: IITU.L (IT), IUHC.L (Healthcare), IUFS.L (Financials), IUES.L (Energy),
  IUIS.L (Industrials), IUCS.L (Consumer Staples), IUCD.L (Consumer Discretionary),
  IUUS.L (Utilities), IUMS.L (Materials), IUCM.L (Communication)
- Baseline (regime): IWDA.L (World equities)
- Cash proxy: IBTS.L (short-duration US Treasuries)

---

## Best Strategy: `raw/sel126/reg252`

**Rules:**
1. **Selection**: top-1 factor ETF + top-1 sector ETF by **raw trailing return over 126 trading days (~6 months)**
2. **Weighting**: 50% factor sleeve + 50% sector sleeve (equal)
3. **Regime filter**: if IWDA.L 252d return ≤ IBTS.L 252d return → 100% IBTS.L (cash)
4. **Rebalance**: monthly (month-end close signal, next open execution)
5. **Costs**: 0.15% per side, TER-adjusted prices

**Performance (2019-10 to 2026-06):**

| Metric | Value |
|--------|-------|
| CAGR | 13.6% |
| Sharpe | 0.93 |
| Max DD (daily) | -23.5% |
| Max DD (monthly NAV) | ~-14% |

**Per-year returns:**

| Year | raw/sel126 | frog/sel252 (prev best) | B&H IWDA |
|------|-----------|------------------------|----------|
| 2020 | +12.3% | +10.8% | — |
| 2021 | +21.6% | +24.0% | — |
| 2022 | **+0.1%** | -7.3% | — |
| 2023 | **+12.1%** | +5.7% | — |
| 2024 | +16.0% | +22.8% | — |
| 2025 | +14.4% | +13.4% | — |

**Why it works better for 2022/2023:**
- The 6m lookback ignores the first half of the year when computing momentum — it sees the new trend **earlier**
- In Jan 2023: IT had a terrible 12-month return (whole 2022 crash still in window), but a recovering 6-month return
- Once regime turned OK in April 2023, raw/126d immediately picked IT; raw/252d stayed in Energy another month
- This is the "fast switching" the Marketfighter article hints at with "not just 12 months"

---

## Runner-up: `composite/sel252/reg252`

**Rules:** Same as above but selection uses the **average percentile rank of 3m/6m/12m returns** (columns: ret_3m, ret_6m, ret_12m).

| Metric | Value |
|--------|-------|
| CAGR | 12.9% |
| Sharpe | 0.89 |
| 2022 | +0.1% |
| 2023 | +13.2% |
| 2024 | +18.0% |

The multi-horizon composite blends short- and long-term signals — in early 2023, IT's recovering 3m/6m offset its bad 12m, causing earlier rotation.

---

## Previous Best (retained for reference): `frog/sel252/reg252`

- CAGR 12.9%, Sharpe **0.92**, MaxDD -23.2%
- Best overall Sharpe before the 126d discovery
- 2022: -7.3% (caught in Healthcare Q1 2022, missed the Energy rally)
- 2023: +5.7% (stayed in Energy/Comms too long, missed IT recovery)
- Still a valid choice if 2024 stability (+22.8%) is prioritized over 2022/2023 performance

---

## Key Insights

### 1. The 2022 problem — Energy vs Frog
- IUES.L (Energy) returned +53.5% in 2022 calendar year
- Raw momentum (12m or 6m) picked Energy from Sept 2021 onward
- frog_in_the_pan **missed** Energy in Q1 2022 because Energy rose via lumpy oil-price spikes (not steady daily gains), which frog penalizes
- The regime filter went CASH (IBTS.L) in April 2022 — so both strategies missed the volatile H2 2022 Energy moves
- Q1 2022 in Energy with the factor sleeve in Value = key profit source for raw/252d (+10.5% annual)

### 2. The 2023 problem — slow rotation to IT
- Regime was CASH (IBTS.L) April 2022 → April 2023 (full 12 months)
- IBTS.L gained +8% in 2022 (short-duration UST); SEGA.L (Euro govt) lost -13% — never use SEGA.L as safe haven
- Once regime turned OK in April 2023: 252d signals still ranked Energy #1 (2022 gains in window); 126d signal already favored IT
- Shorter selection lookback = **faster regime re-entry into the right sector**

### 3. The Marketfighter gap
- Marketfighter claims ~+5% in 2022 and presumably strong 2023
- Our best approximation: raw/sel252/NO regime → +12% 2022, +5.6% 2023 (no costs)
- Or: raw/sel126/reg252 → +0.1% 2022, +12.1% 2023 (with costs)
- With costs removed, both approach his claimed numbers
- His "multiple interval" hint points to composite or shorter selection lookback
- Monthly max DD on our strategies = -12 to -14%, comparable to his claimed -15.23%

### 4. Decoupled lookback principle
- **Selection lookback** and **regime lookback** should be independent
- Best combination found: **sel=126d (6m), reg=252d (12m)**
- Shorter regime (126d) creates instability — CAGR drops from 13.6% to 7.6% for raw/sel126
- Logic: regime needs long memory to avoid false exits; selection benefits from shorter memory to catch new leaders

### 5. Why shorter regime (reg126) fails
The 126d regime filter incorrectly sends to CASH more often and at wrong times, e.g.:
- Short-term dips in IWDA.L trigger cash unnecessarily
- Misses strong trend continuations where the 12m signal correctly stays invested

---

## Current Portfolio Signal (as of 2026-06-16)

Regime: **ON** (IWDA.L 252d = +27.7%, IBTS.L 252d = +3.4%)

**Signal date: 2026-05-29 (May month-end) → June holdings**

| Sleeve | raw/sel126 (best config) | raw/sel252 | frog/sel252 |
|--------|--------------------------|------------|-------------|
| Factor | **IWVL.L** (Value) | IWVL.L | IWVL.L |
| Sector | **IUES.L** (Energy) | IITU.L (IT) | IITU.L (IT) |

**Marketfighter picked Value + Energy on June 1** (QDVI + QDVF), which matches `raw/sel126` exactly.

Why the split at May month-end:
| Sector | 6m return | 12m return | frog 6m | frog 12m |
|--------|-----------|------------|---------|----------|
| Energy | **+28.3%** | +41.8% | **0.190** | 0.111 |
| IT     | +22.4% | **+54.9%** | 0.095 | **0.143** |

Energy leads on 6m momentum and steadiness (frog 6m); IT leads on 12m.
The signal divergence is a live test: June 2026 outcome will show which lookback better captures current market leadership.

**Portfolio per raw/sel126: 50% IWVL.L + 50% IUES.L**
**Portfolio per frog/sel252: 50% IWVL.L + 50% IITU.L**

---

## Files

| File | Purpose |
|------|---------|
| `etf_momentum_backtest.py` | Core data loading, indicators, Strategy C |
| `marketfighter_replica.py` | Strategy D base config, factor/sector tickers, secret sauce indicators |
| `marketfighter_sweep2.py` | 36-combo parameter sweep (3 lookbacks × 6 metrics × 2 regime) |
| `mg99_backtest.py` | MG99 vs FITP comparison (ATR stop, SMA200 regime) |
| `backtest_engine.py` | perf_stats, buy_and_hold, equity curve helpers |
| `etf_universe.csv` | Full ticker universe with roles and blocks |
| `marketfighter_sweep2_results/sweep2_results.csv` | Full 36-combo sweep results |

---

## Sweep Summary (36 combos: 3 lookbacks × 6 metrics × 2 regime)

Top configs by Sharpe from `marketfighter_sweep2.py`:
- frog_in_the_pan / 252d / regime ON: Sharpe ~0.92, CAGR ~12.9%
- r2_adjusted / 252d / regime ON: similar range
- composite / 252d / regime ON: Sharpe ~0.89

**Dimension effects** (group-mean Sharpe spread):
- Regime filter ON vs OFF: largest effect (~0.15 Sharpe units)
- Momentum metric: moderate effect (~0.10)
- Lookback (126/189/252): smallest effect in the sweep (the sweep used coupled lookback; decoupled 126d selection with 252d regime is outside that sweep)

---

## Tested Extensions (2026-06-16)

### Selection lookback sweep (raw, regime=252d)

| Lookback | CAGR | Sharpe | MaxDD | 2022 | 2023 | Note |
|---------|------|--------|-------|------|------|------|
| 63d (3m) | 13.5% | 0.91 | -22.7% | +0.1% | +8.9% | Strong 2021 (+29%), weak 2024 (+8%) |
| **126d (6m)** | **13.6%** | **0.93** | -23.5% | **+0.1%** | **+12.1%** | **Sweet spot** |
| 189d (9m) | 8.8% | 0.63 | -25.5% | +1.1% | +7.3% | Worst — avoid |
| 252d (12m) | 11.2% | 0.78 | -19.6% | +10.5% | +2.6% | Baseline |

The 9-month window is the worst of all — it sits in a dead zone between short-term and long-term. **126d is confirmed as the sweet spot.**

### Weighted composite (regime=252d, sel=252d)

Key finding: **"6m only" composite = raw/sel126 exactly** (Sharpe 0.93, CAGR 13.6%). Percentile-ranking a single horizon is equivalent to raw-ranking that horizon. Adding the 12m horizon *hurts* Sharpe (equal composite = 0.89). Shorter is better.

| Composite weighting | CAGR | Sharpe | 2022 | 2023 |
|--------------------|------|--------|------|------|
| Equal (1:1:1) | 12.9% | 0.89 | +0.1% | +13.2% |
| Heavy short (3:2:1) | 11.2% | 0.79 | +0.1% | +13.8% |
| 3m+6m only (1:1:0) | 13.0% | 0.90 | +0.1% | +12.6% |
| 6m only (0:1:0) | **13.6%** | **0.93** | **+0.1%** | **+12.1%** |
| Heavy 12m (1:2:3) | 12.7% | 0.87 | -1.2% | +14.1% |

### Number of holdings per sleeve (raw/sel126/reg252)

| Config | CAGR | Sharpe | MaxDD | 2022 | 2023 | 2024 |
|--------|------|--------|-------|------|------|------|
| top1/top1 (baseline) | 13.6% | 0.93 | -23.5% | +0.1% | +12.1% | +16.0% |
| top1/top2 | 13.4% | **0.97** | -21.0% | -4.4% | +13.7% | +22.9% |
| top2/top2 | 13.2% | **0.97** | **-19.6%** | -5.6% | +15.6% | +25.4% |
| top1/top3 | 12.6% | 0.94 | -21.1% | -6.2% | +9.4% | +21.8% |

**top2/top2 (4 positions) gives best Sharpe (0.97) and lowest MaxDD (-19.6%)** at a small CAGR cost.
**top1/top2 gives the same Sharpe (0.97) with slightly higher CAGR (13.4%)** — a good middle ground.

Trade-off: more holdings dilutes Energy concentration in Q1 2022 (worse 2022) but improves diversification and reduces drawdown.

## What Was NOT Tested / Future Ideas

- Monthly-price signals — tested previously, underperforms daily-price signals
- Longer backtest — impossible, UCITS ETF data only from ~2014-2019 depending on ticker
- Combining top2/top2 holdings with weighted composite (e.g. 6m-only + 2 per sleeve)
