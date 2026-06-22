# Strategy C — Multi-Asset ETF Dual-Momentum Rotation (Swedish ISK / IBKR)

A precise, backtestable spec for a cross-asset momentum strategy on broad ETFs /
ETPs, sized for a Swedish ISK at Interactive Brokers. Complements
`PROJECT_SPEC.md` and `STRATEGY_SPEC.md`.

This is the **broad mechanical base for most of the capital**. The single-stock
screeners and discretionary Brooks trading are a separate, smaller sleeve.

"Best" here means the most robust, evidence-grounded, simplest viable design —
cross-asset trend-following is the variant the academic literature actually
supports (Antonacci dual momentum / GEM; Moskowitz-Ooi-Pedersen time-series
momentum; Faber GTAA). It is still a backtest until validated out-of-sample after
real costs. Honest target: equity-like returns with shallower drawdowns — risk
reduction, not alpha.

---

## 0. CRITICAL PREREQUISITES — verify the investable universe FIRST

Account-specific; nothing below matters until this is settled:

- **PRIIPs/KID:** most US-domiciled ETFs (SPY/EFA/AGG — the tickers GEM backtests
  use) are **not available to EU retail**. Use **UCITS** ETFs.
- **Gold and silver are NOT UCITS ETFs** — they are **ETCs** (exchange-traded
  commodities), a different legal structure with its own tax treatment and
  ISK-eligibility. **Verify each is tradable on a Swedish ISK at IBKR.**
- **Verify with IBKR** which specific products you can trade and that monthly
  rotation is permitted. Do not assume — confirm.
- **FX:** many products trade in EUR/USD. Prefer **SEK-denominated** (e.g. Xact)
  where available; otherwise account for IBKR's FX conversion fee.
- Every ticker below is a **placeholder to verify and replace**.

---

## 1. Asset universe (Classes + Expanded Factor/Sector Menu)

A broader, principled menu: all major equity regions + Marketfighter's factor and sector suite + key alternatives. The menu is chosen on **a-priori principle**, decided in advance to prevent cherry-picking to fit the backtest. **Freeze the list; do NOT add/remove assets based on backtest results.**

| Block | Assets | Example products / Index (VERIFY UCITS ON IBKR) |
|---|---|---|
| **1. Developed equity — regional** | Nordic (SEK), Europe, North America / US, Developed Asia-Pacific | `XACT Norden`/`XACT OMXS30`; iShares Core MSCI Europe (`IMEU`); iShares Core S&P 500 (`CSPX`); iShares Core MSCI Pacific |
| **2. Equity — 10 GICS Sectors** | Technology, Health Care, Financials, Energy, Industrials, Consumer Staples, Consumer Discretionary, Utilities, Materials, Communication + *Defense (Tactical)* | iShares MSCI World [Sektor] UCITS ETF series / SPDR S&P 500 Sector UCITS series / VanEck Defense UCITS (`DFNS`) |
| **3. Equity — 5 Factors** | Value, Quality, Momentum, Growth, Minimum Volatility | iShares Edge MSCI World [Factor] UCITS ETF series (e.g., `IWVL`, `IWQU`, `IWMO`) |
| **4. Emerging equity** | EM Asia, Latin America | iShares MSCI EM Asia; iShares MSCI EM Latin America |
| **5. Precious metals (ETC)** | Gold, Silver | iShares Physical Gold ETC; iShares Physical Silver ETC |
| **6. Defensive (where it hides)** | Government bonds | SEK/EUR govt-bond UCITS (`XACT Obligationer` / iShares) |
| **7. Cash proxy (the hurdle)** | Short govt bonds / money market | 0–1yr govt bond UCITS |

### 1.1 Special handling — high-volatility assets (Silver, Tech, Energy)
- **Silver** (ETC) runs ~1.5–2× gold's volatility; tech, energy, and momentum factors are also high-beta.
- Because of these, **inverse-volatility weighting is the default** (§4), not an option — otherwise the hottest, most volatile asset dominates the book and its crash sinks the portfolio. The **absolute-momentum gate (§3) matters more, not less**, with a volatile menu.

### 1.2 Special handling — sector and factor tilts (The Marketfighter Integration)
Sectors and smart-beta factors add genuine dispersion, allowing the relative-momentum engine to express tactical shifts. However, heed three strict cautions:
- **Overlap & Concentration.** You already own these sectors and factors *inside* your broad regional ETFs. Stacking specific sector and factor ETFs on top makes the portfolio's true exposure muddy and heavily concentrated. This requires strict correlation limits during allocation (§4 `MAX_PER_BLOCK`).
- **Sectors/Factors chase and whipsaw harder** than broad indices. The absolute-momentum gate (§3) and inverse-vol weighting (§4) are non-negotiable backstops here.

---

## 2. Momentum Score / Ranking

- For each **risk asset**, compute trailing **total return** (dividends/where applicable reinvested) over `LOOKBACK` (default 252 trading days ≈ 12 months). For ETPs/ETCs without distributions this is just price return.
- `COMPOSITE` (default off): average the cross-sectional ranks of 3/6/12-month returns instead of a single 12m. Include in the sweep; default single 12m (canonical, simplest, least over-fit).
- Rank the risk assets by this return.

---

## 3. Absolute momentum filter (the regime gate — the heart of dual momentum)

What moves the portfolio defensive when everything is trending down — and the single most important safeguard given the volatile menu.

- A risk asset is **ELIGIBLE** only if its `LOOKBACK` return **exceeds the cash proxy's** `LOOKBACK` return (it is beating cash).
- `ABS_BENCHMARK`: `cash_proxy` (default) or `zero` (asset's 12m return > 0).

---

## 4. Selection & allocation

- Hold the top `HOLD_N` **eligible** risk assets. Default `HOLD_N = 4` or `5` (The expanded menu of ~25 assets warrants a slightly higher N to avoid single-asset concentration, especially with niche sectors/factors in play). Sweep 3/4/5.
- **`WEIGHTING = inv_vol` (DEFAULT — MANDATORY FOR THIS MENU)** — weight ∝ 1 / (126-day stdev). Optional `vol_target`: cap any single asset's risk contribution (useful when high-vol assets like silver or a hot sector top the ranking). `equal` is available for testing but **not** recommended.
- For any of the `HOLD_N` slots whose ranked asset is **not eligible**, allocate that slot to the **defensive** (government bonds). If bonds also fail absolute momentum, that slot goes to the **cash proxy**.
- Consequence: in a full risk-off regime the book rotates entirely into bonds/cash — crash protection built into the selection.
- **`MAX_PER_BLOCK` (CRITICAL FOR EXPANDED MENU):** Cap how many of the `HOLD_N` slots may come from the same structural block to prevent hidden clustering (e.g., holding Tech + Growth + Momentum + US Region simultaneously).
  - Max 2 from **Block 2 (Sectors)**
  - Max 2 from **Block 3 (Factors)**
  - Max 2 from **Block 1 & 4 combined (Regions)**
  - If a block is full, skip to the next highest-ranked asset in a non-full block. Sweep on/off to isolate the structural impact.

---

## 5. Rebalancing

- **Monthly**, last trading day. `REBAL` = `monthly` (default) | `quarterly`.
- `BAND` (default off): hysteresis (a held asset stays until it drops out of the top `HOLD_N + 1`) to cut turnover. Test it; default off.
- **No look-ahead:** signal on the month-end close, executed next session.

---

## 6. Costs & frictions (all must be modeled)

- `COST_PER_SIDE`: commission + spread + slippage. ETFs are tight; **silver ETCs have wider spreads** — use a higher per-side cost for those.
- **FX conversion fee** for non-SEK products (critical at IBKR when rotating across multiple non-SEK denominated sector/factor funds).
- **TER / ETC fee:** subtract the annualized fee from each holding's return.
- **ISK:** rotation incurs **no capital-gains tax** (a genuine ISK advantage for a strategy that trades often). The yearly ISK standard tax (schablonskatt) is separate and applies regardless — note it; it does not affect the relative comparisons.

---

## 7. Backtest plan

**Baselines** (the strategy must justify itself against these):
- (a) Buy & hold a single global-equity ETF (e.g. `IWDA`) — the "just index it" benchmark, the one that matters most.
- (b) Static 60/40 equity/bond.
- (c) **Naive** relative momentum (top-`HOLD_N`, **no** absolute-momentum filter) — to isolate the filter's value.
- (d) **The full strategy WITHOUT the sector/factor tilts** (regions + alternatives only) — to see whether the Marketfighter universe adds true alpha or just extra turnover and whipsaw (mandatory).

**Robustness sweep** (report the plateau, not the peak): `LOOKBACK` (6/9/12m), `HOLD_N` (3/4/5), `COMPOSITE` on/off, `ABS_BENCHMARK`, `REBAL`, `WEIGHTING` (inv_vol / vol_target), `MAX_PER_BLOCK` on/off, **sectors/factors in/out**.

**Metrics after costs/FX/fees:** CAGR, Sharpe, Sortino, max drawdown, turnover, % time in the defensive asset, and the **longest stretch of underperformance vs buy-&-hold equity** (破坏性 dry spells).

---

## 8. Honest expectations (read before trusting any result)

- This has the **strongest evidence base** of anything in the project (cross-asset trend-following). But the edge is **modest**, with documented **dry spells** (lagging equities for years in the 2010s) and **whipsaw risk** in sharp recoveries.
- Integrating factors and sectors can boost the CAGR during strong, trend-heavy regimes, but it materially increases the risk of false break-outs.
- **Count is not diversification.** The ~25 assets map to a few core underlying risk drivers. The broader menu mainly helps the rotation always have *something* trending to hold — it does not multiply the edge.
- The benchmark to beat is (a): a cheap global index fund held passively. If, after costs and out-of-sample, this can't clearly improve on that risk-adjusted, the honest answer is to just hold the index fund — a valid result.

---

## 9. How it fits the whole plan

- **Core (most of the capital):** this multi-asset ETF dual-momentum rotation, run mechanically on the ISK at IBKR.
- **Satellite (smaller, separate):** the single-stock screeners (`pullback_screener.py`, `reversal_pattern_screener.py`, `range_low_screener.py`) feeding discretionary Brooks price-action trades, every trade logged so its edge can be measured over time.

**Build order for Code:** implement Strategy C as above, then run the Section 7 backtest (including the comparison against the Marketfighter-only equity universe) and held-out validation **before** any live capital.