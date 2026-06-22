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

## 1. Asset universe (classes + EXAMPLE products — VERIFY & REPLACE)

A broader, principled menu: all major equity regions + key alternatives. The menu
is chosen on **a-priori principle ("all major regions + alternatives"), decided in
advance** — this is what keeps it from being cherry-picked to fit the backtest.
**Freeze the list; do NOT add/remove assets based on backtest results.**

**Important — count is not diversification.** These ~13 assets are really ~5
independent blocks. Adding an 8th equity region gives little new diversification;
in a risk-off shock the equity regions all fall together. The blocks:

| Block | Assets | Example products (VERIFY) |
|---|---|---|
| Developed equity — regional | Nordic (SEK), Europe, North America / US, Developed Asia-Pacific | `XACT Norden`/`XACT OMXS30`; iShares Core MSCI Europe (`IMEU`); iShares Core S&P 500 (`CSPX`); iShares Core MSCI Pacific |
| Equity — sector tilts | Tech, Energy, Health Care, Industrials (heavy industry), Defense | Nasdaq 100 (`CNDX`); iShares S&P 500 Energy (`IUES`)/MSCI World Energy; iShares MSCI World Health Care; iShares MSCI World Industrials; VanEck Defense UCITS (`DFNS`) — **see §1.2** |
| Emerging equity | EM Asia, Latin America | iShares MSCI EM Asia; iShares MSCI EM Latin America |
| Precious metals (ETC) | Gold, Silver | iShares Physical Gold ETC; iShares Physical Silver ETC |
| Defensive (where it hides) | Government bonds | SEK/EUR govt-bond UCITS (`XACT Obligationer` / iShares) |
| Cash proxy (the hurdle) | Short govt bonds / money market | 0–1yr govt bond UCITS |

Keep it to roughly this set. More equity regions ≈ more correlated copies, not more
edge.

### 1.1 Special handling — high-volatility assets (Silver, Tech)
- **Silver** (ETC) runs ~1.5–2× gold's volatility; tech and energy are also
  high-beta.
- Because of these, **inverse-volatility weighting is the default** (§4), not an
  option — otherwise the hottest, most volatile asset dominates the book and its
  crash sinks the portfolio. The **absolute-momentum gate (§3) matters more, not
  less**, with a volatile menu.

### 1.2 Special handling — sector ETFs (Tech, Energy, Health Care, Industrials, Defense)
Sectors add genuine dispersion (energy vs tech diverge hard), so a relative-momentum
rotation can use them. But three real cautions:
- **Overlap with regional holdings.** You already own these sectors *inside* your
  broad regional ETFs (the S&P 500 holds energy, health care, industrials, tech).
  Stacking sector ETFs on top makes the portfolio's true exposure muddy and
  concentrated. The cleanest design is region-based **OR** sector-based for the
  equity sleeve, not both — if you mix, watch the effective concentration (§4
  `MAX_PER_BLOCK`).
- **Hand-picked vs principled.** Including the full standard GICS sector set is
  principled; hand-picking four is closer to cherry-picking. **Defense especially**
  is a narrow, recently-hot theme (post-2022 rearmament) with very short fund
  history — including it because it has run is exactly the trap to avoid. Keep it if
  you want, but flag it to yourself as a theme bet, and judge it on the
  with/without-sectors test (§7e), not on its recent run.
- **Sectors chase and whipsaw harder** than broad indices. The absolute-momentum
  gate (§3) and inverse-vol weighting (§4) matter even more here.



- For each **risk asset**, compute trailing **total return** (dividends/where
  applicable reinvested) over `LOOKBACK` (default 252 trading days ≈ 12 months).
  For ETPs/ETCs without distributions this is just price return.
- `COMPOSITE` (default off): average the cross-sectional ranks of 3/6/12-month
  returns instead of a single 12m. Include in the sweep; default single 12m
  (canonical, simplest, least over-fit).
- Rank the risk assets by this return.

---

## 3. Absolute momentum filter (the regime gate — the heart of dual momentum)

What moves the portfolio defensive when everything is trending down — and the
single most important safeguard given the volatile menu.

- A risk asset is **ELIGIBLE** only if its `LOOKBACK` return **exceeds the cash
  proxy's** `LOOKBACK` return (it is beating cash).
- `ABS_BENCHMARK`: `cash_proxy` (default) or `zero` (asset's 12m return > 0).

---

## 4. Selection & allocation

- Hold the top `HOLD_N` **eligible** risk assets. Default `HOLD_N = 4` (a larger
  menu warrants holding a few more to avoid violent single-asset concentration,
  especially with metals and high-beta sectors in the mix). Sweep 3/4/5.
- **`WEIGHTING = inv_vol` (DEFAULT)** — weight ∝ 1 / (126-day stdev). Optional
  `vol_target`: cap any single asset's risk contribution (useful when high-vol
  assets like silver or a hot sector top the ranking). `equal` is available but
  **not** recommended for this menu.
- For any of the `HOLD_N` slots whose ranked asset is **not eligible**, allocate
  that slot to the **defensive** (government bonds). If bonds also fail absolute
  momentum, that slot goes to the **cash proxy**.
- Consequence: in a full risk-off regime the book rotates entirely into bonds/cash
  — crash protection built into the selection.
- **`MAX_PER_BLOCK` (optional, recommended with the sector menu):** cap how many of
  the `HOLD_N` slots may come from the same correlation block (default 2). Prevents
  the book from becoming all-energy or all-defense when one theme dominates the
  ranking — a real risk now that the equity menu is large and correlated. Sweep
  on/off to see its effect.

---

## 5. Rebalancing

- **Monthly**, last trading day. `REBAL` = `monthly` (default) | `quarterly`.
- `BAND` (default off): hysteresis (a held asset stays until it drops out of the
  top `HOLD_N + 1`) to cut turnover. Test it; default off.
- **No look-ahead:** signal on the month-end close, executed next session.

---

## 6. Costs & frictions (all must be modeled)

- `COST_PER_SIDE`: commission + spread + slippage. ETFs are tight; **silver ETCs
  have wider spreads** — use a higher per-side cost for those.
- **FX conversion fee** for non-SEK products.
- **TER / ETC fee:** subtract the annualized fee from each holding's return.
- **ISK:** rotation incurs **no capital-gains tax** (a genuine ISK advantage for a
  strategy that trades often). The yearly ISK standard tax (schablonskatt) is
  separate and applies regardless — note it; it does not affect the relative
  comparisons.

---

## 7. Backtest plan

**Baselines** (the strategy must justify itself against these):
- (a) Buy & hold a single global-equity ETF (e.g. `IWDA`) — the "just index it"
  benchmark, the one that matters most.
- (b) Static 60/40 equity/bond.
- (c) **Naive** relative momentum (top-`HOLD_N`, **no** absolute-momentum filter) —
  to isolate the filter's value.
- (d) **The full strategy WITHOUT the sector tilts** (regions + alternatives only) —
  to see whether sectors add anything beyond chasing, or just add overlap and
  whipsaw (per §1.2, mandatory).

**Robustness sweep** (report the plateau, not the peak): `LOOKBACK` (6/9/12m),
`HOLD_N` (3/4/5), `COMPOSITE` on/off, `ABS_BENCHMARK`, `REBAL`, `WEIGHTING`
(inv_vol / vol_target), `MAX_PER_BLOCK` on/off, **sectors in/out**.

**Metrics after costs/FX/fees:** CAGR, Sharpe, Sortino, max drawdown, turnover,
% time in the defensive asset, and the **longest stretch of underperformance vs
buy-&-hold equity** (dual momentum's known weakness).

**Key diagnostics:**
1. Does the absolute-momentum filter measurably cut drawdown in bear markets
   (2020, 2022, 2008 if data allows)?
2. How long/deep are the dry spells where it lags buy-&-hold equity (the 2010s)?
3. **Whipsaw count** — round-trips into/out of defensive within a few months
   (V-shaped recoveries punish trend-following).
4. **Sector sensitivity** — the gap between the with-sectors and regions-only runs.
   If sectors don't measurably improve risk-adjusted results, drop them: they add
   overlap, turnover, and whipsaw for nothing. Also watch how often the book
   clusters in one sector block (the `MAX_PER_BLOCK` rationale).

**Validation discipline (unchanged):** train/test with a held-out final period
used **exactly once**; walk-forward across regimes; parameters and the asset menu
decided in advance. Survivorship of broad equity/bond ETFs is a non-issue; the main data constraint is
ETF/ETC inception dates (backfill with index data where defensible and document it).

---

## 8. Honest expectations (read before trusting any result)

- This has the **strongest evidence base** of anything in the project (cross-asset
  trend-following). But the edge is **modest**, with documented **dry spells**
  (lagging equities for years in the 2010s) and **whipsaw risk** in sharp recoveries.
- The realistic outcome is **equity-like returns with shallower drawdowns** — risk
  reduction and fewer brutal declines, not alpha. A perfectly good goal; just hold
  that expectation, not a hope of beating the market.
- **Count is not diversification.** The ~13 assets are ~5 correlated blocks; the
  effective number of independent bets is small, so single regime turns matter a
  lot. The broader menu mainly helps the rotation always have *something* trending
  to hold — it does not multiply the edge.
- **Sectors may be overlap and chasing, not edge.** Because you already hold these
  sectors inside the regional ETFs, the sector tilts must *earn* their place on the
  with/without-sectors test (§7e). If they don't clearly help risk-adjusted, drop
  them — and treat "defense" with particular suspicion given its short, hot history.
- The benchmark to beat is (a): a cheap global index fund held passively. If, after
  costs and out-of-sample, this can't clearly improve on that risk-adjusted, the
  honest answer is to just hold the index fund — a valid result.

---

## 9. How it fits the whole plan

- **Core (most of the capital):** this multi-asset ETF dual-momentum rotation, run
  mechanically on the ISK at IBKR.
- **Satellite (smaller, separate):** the single-stock screeners
  (`pullback_screener.py`, `reversal_pattern_screener.py`, `range_low_screener.py`)
  feeding discretionary Brooks price-action trades, every trade logged so its edge
  can be measured over time.
- Two sleeves, two philosophies: passive cross-asset momentum for the core; active
  discretionary price action for the satellite. The core is where the documented
  edge lives; the satellite is where your skill is tested honestly.

**Build order for Code:** implement Strategy C as above, then run the Section 7
backtest (including the regions-only baseline) and held-out validation **before**
any live capital. A modest or disappointing result is information, not failure.
