/* ETF Rotation Dashboard — app.js */
"use strict";

// ── Strategy specifications (shown in popup) ───────────────────────
const STRATEGY_SPECS = {
  top1_top1: {
    color: "#5b6ef5",
    tagline: "Referensstrategi — bästa momentum per sleeve, 84 dagars råavkastning",
    description: "Den enklaste formen av momentum-rotation. Väljer den ETF med högst avkastning de senaste 84 handelsdagarna (~4 månader) ur respektive sleeve, ombalanserar sista handelsdagen varje månad. Tjänar som referenspunkt för alla övriga strategier.",
    params: [
      { k: "Metric",          v: "Raw return — 84 dagars TER-justerad avkastning" },
      { k: "Urval",           v: "Top 1 faktor-ETF + Top 1 sektor-ETF (50 % / 50 %)" },
      { k: "Regimfilter",     v: "IWDA.L vs IBTS.L — 84d. Risk-off om IWDA underavkastar IBTS" },
      { k: "Rebalansering",   v: "Sista handelsdagen varje månad" },
      { k: "Handelskostnad",  v: "15 bps per sida" },
      { k: "Faktor-universum",v: "USA MOM · USA QUAL · USA VAL · USA SMALL · EUR MOM · EUR QUAL · EUR VAL · EUR SMALL" },
      { k: "Sektor-universum",v: "IT · Energy · Healthcare · Cons.Disc. · Industrials · Cons.Staples · Materials" },
    ],
    source: "Baseline — 84d lookback valdes via parametersweep (bäst Sharpe bland 21/42/63/84/126d)",
  },
  top2_top2: {
    color: "#a78bfa",
    tagline: "Bredare exponering — top 2 per sleeve för lägre koncentrationsrisk",
    description: "Identisk logik som D1-raw men väljer de 2 bästa ETF:erna ur varje sleeve. Varje sleeve viktas 50 %, delat lika mellan de 2 vinnarna (25 % var). Ger mer diversifiering men tenderar att späda ut alpha.",
    params: [
      { k: "Metric",          v: "Raw return — 84 dagars TER-justerad avkastning" },
      { k: "Urval",           v: "Top 2 faktor-ETF + Top 2 sektor-ETF (25 % / 25 % / 25 % / 25 %)" },
      { k: "Regimfilter",     v: "IWDA.L vs IBTS.L — 84d" },
      { k: "Rebalansering",   v: "Sista handelsdagen varje månad" },
      { k: "Handelskostnad",  v: "15 bps per sida" },
    ],
    source: "Variant av D1-raw för att mäta diversifieringens effekt",
  },
  d1_composite: {
    color: "#10b981",
    tagline: "Bäst i sweep — blandar kortsiktig och långsiktig momentum 50/50",
    description: "Rankar ETF:er som genomsnittet av deras 21-dagars och 84-dagars avkastning. Det korta fönstret fångar tidiga trender och leder till bättre positionering i mars–juni 2020 och november 2023 jämfört med ren 84d-momentum.",
    params: [
      { k: "Metric",          v: "Composite — 50 % × ret(21d) + 50 % × ret(84d)" },
      { k: "Urval",           v: "Top 1 + Top 1" },
      { k: "Regimfilter",     v: "IWDA.L vs IBTS.L — 84d" },
      { k: "Rebalansering",   v: "Sista handelsdagen varje månad" },
      { k: "Handelskostnad",  v: "15 bps per sida" },
    ],
    source: "Vinnare ur 40-run DEL1-3 sweep (Sharpe 1.18 vs 1.13 för raw-84d)",
  },
  d2_composite: {
    color: "#34d399",
    tagline: "Composite-signal, 2 picks per sleeve",
    description: "Samma composite-metrik som D1-composite (50 % × 21d + 50 % × 84d) men väljer top 2 ur varje sleeve. Ger liknande Sharpe som D1-composite med något lägre CAGR och mer gradvis allokationsförändring.",
    params: [
      { k: "Metric",          v: "Composite — 50 % × ret(21d) + 50 % × ret(84d)" },
      { k: "Urval",           v: "Top 2 + Top 2" },
      { k: "Regimfilter",     v: "IWDA.L vs IBTS.L — 84d" },
      { k: "Rebalansering",   v: "Sista handelsdagen varje månad" },
      { k: "Handelskostnad",  v: "15 bps per sida" },
    ],
    source: "Variant av D1-composite för att mäta diversifieringens effekt",
  },
  d1_accel: {
    color: "#f59e0b",
    tagline: "Premierar tillgångar vars momentum ökar — inte bara högt momentum",
    description: "Utgår från en mjukad prisserie (EMA-5 av mediapriset (H+L)/2) för att filtrera bort daglig brus. Beräknar sedan ROC (Rate of Change) över 84 dagar på den mjuka serien, plus en accelerationsterm: avkastningen de senaste 15 dagarna minus avkastningen de 15 dagarna dessförinnan. Tillgångar med stigande momentum rankas dubbelt belönade.",
    params: [
      { k: "Metric",          v: "Accelerated momentum: ROC(84d) + Accel(15d)" },
      { k: "Prisserie",       v: "EMA(5) av (High + Low) / 2 — filtrerar daglig brus" },
      { k: "ROC-fönster",     v: "84 handelsdagar (~4 månader)" },
      { k: "Accel-fönster",   v: "15 dagar — ROC(0→15d) minus ROC(−15→0d)" },
      { k: "Urval",           v: "Top 1 + Top 1" },
      { k: "Regimfilter",     v: "IWDA.L vs IBTS.L — 84d" },
      { k: "Handelskostnad",  v: "15 bps per sida" },
    ],
    source: "Optimerad via 160-run sweep (5 lb × 4 win × 4 ema × D1/D2) — ema=5, lb=84, win=15 gav Sharpe 1.27",
  },
  d2_accel: {
    color: "#fcd34d",
    tagline: "Accelerated momentum, 2 picks per sleeve",
    description: "Identisk accel-metrik som D1-accel (EMA-5 mediapris, ROC 84d + acceleration 15d) men väljer top 2 ur varje sleeve. Något lägre CAGR men lägre maximal nedgång.",
    params: [
      { k: "Metric",          v: "Accelerated momentum: ROC(84d) + Accel(15d)" },
      { k: "Prisserie",       v: "EMA(5) av (High + Low) / 2" },
      { k: "Urval",           v: "Top 2 + Top 2" },
      { k: "Regimfilter",     v: "IWDA.L vs IBTS.L — 84d" },
      { k: "Handelskostnad",  v: "15 bps per sida" },
    ],
    source: "D2-variant av D1-accel",
  },
  d1_lowcorr: {
    color: "#f43f5e",
    tagline: "Begränsar sektorsleeven till defensiva, lågkorrelerade sektorer",
    description: "Exkluderar sektorer som tenderar att gå ihop i marknadsnedgångar (IT, Industrials, Materials, Consumer Discretionary) och tillåter bara rotation bland de 5 minst korrelerade S&amp;P 500-sektorerna. Faktor-sleeven är oförändrad. Ger lägre beta och bättre riskjusterad avkastning i nedgångsfaser.",
    params: [
      { k: "Metric",           v: "Raw return — 84 dagars avkastning" },
      { k: "Urval",            v: "Top 1 faktor + Top 1 sektor (50 % / 50 %)" },
      { k: "Faktor-universum", v: "Oförändrat — samma 8 faktor-ETF:er" },
      { k: "Sektor-universum", v: "Energy (QDVF.DE) · Utilities (QDVH.DE) · Cons.Staples (2B7D.DE) · Communication Services (XLC) · Healthcare (QDVG.DE)" },
      { k: "Exkluderade",      v: "IT · Consumer Discretionary · Industrials · Materials" },
      { k: "Regimfilter",      v: "IWDA.L vs IBTS.L — 84d" },
      { k: "Handelskostnad",   v: "15 bps per sida" },
    ],
    source: "Optimerad via 42-run sweep B — 'no_gold + raw sel=84' gav Sharpe 1.30, CAGR 18.2 %",
  },
  d2_lowcorr: {
    color: "#fb7185",
    tagline: "Low-corr sektoruniverse, 2 picks per sleeve",
    description: "Identisk universum-begränsning som D1-low-corr men väljer top 2 ur varje sleeve. Ger bredare exponering mot de defensiva sektorerna.",
    params: [
      { k: "Metric",           v: "Raw return — 84 dagars avkastning" },
      { k: "Urval",            v: "Top 2 + Top 2" },
      { k: "Sektor-universum", v: "Energy · Utilities · Cons.Staples · Comms. · Healthcare" },
      { k: "Regimfilter",      v: "IWDA.L vs IBTS.L — 84d" },
      { k: "Handelskostnad",   v: "15 bps per sida" },
    ],
    source: "D2-variant av D1-low-corr",
  },
  ppm_top3: {
    color: "#06b6d4",
    tagline: "PPM-rotation — top-3 fonder, full historik 2001–2026",
    description: "Roterar bland 14 PPM-fonder med EMA(10)-mjukad accel-signal. Dubbelt cash-skydd: ETF-cash sync (D1-accel i cash) + PPM momentum-filter (alla top-3 scores negativa → AP7 Räntefond). Full historik inkl. dot-com & finanskrisen.",
    params: [
      { k: "Signal",        v: "EMA(10) × ROC(84d) + acceleration(30d)" },
      { k: "Urval",         v: "Top 3 fonder, likviktade" },
      { k: "Cash-skydd",    v: "ETF-cash sync + PPM momentum-filter (score < 0)" },
      { k: "Universum",     v: "14 fonder: Tech · Healthcare · Energy · Mining · Consumer Brands · US Value/Small/Quality/Growth · EUR Small/Value · Multifactor · AP7 Aktie · AP7 Räntefond" },
      { k: "Kostnad",       v: "0 kr (PPM = gratis rebalansering)" },
      { k: "Backtest",      v: "2001 → 2026  |  CAGR 9.9% · Sharpe 0.85" },
    ],
    source: "Full historik 2001–2026 inkl. dot-com-kraschen och finanskrisen 2008",
  },
  ppm_top3_recent: {
    color: "#22d3ee",
    tagline: "PPM-rotation — top-3 fonder (2020+)",
    description: "Samma strategi som PPM top-3 men backtestet startar 2020. Visar den period som ursprungligen optimerades.",
    params: [
      { k: "Signal",        v: "EMA(10) × ROC(84d) + acceleration(30d)" },
      { k: "Urval",         v: "Top 3 fonder, likviktade" },
      { k: "Cash-skydd",    v: "ETF-cash sync + PPM momentum-filter (score < 0)" },
      { k: "Backtest",      v: "2020 → 2026  |  CAGR ~19% · Sharpe ~1.5" },
    ],
    source: "Ursprunglig backtest-period (2020–2026)",
  },
  sp500_pit_top5: {
    color: "#34d399",
    tagline: "D1-ACCEL direkt på S&P 500-aktier — Top 5, point-in-time universum",
    description: "Samma accelerated-momentum-signal som ETF-kärnan men applicerat direkt på enskilda S&P 500-aktier. Universumet är point-in-time: på varje rebalansdatum tillåts bara aktier som faktiskt var med i S&P 500 vid den tidpunkten. Parametrar optimerade via grid-sweep (384 kombinationer). Pris från yfinance (nuvarande) + Tiingo justerade priser (borttagna). 842 tickers, ~490 tillgängliga per datum.",
    params: [
      { k: "Signal",        v: "ROC(84d) + Accel(20d) på EMA(3) av (H+L)/2" },
      { k: "Universum",     v: "S&P 500 — point-in-time (842 tickers, ~490/datum)" },
      { k: "Urval",         v: "Top 5 aktier, likviktade (20% var)" },
      { k: "Regimfilter",   v: "SPY 84d return ≤ 0 → 100% kontanter" },
      { k: "Rebalansering", v: "Sista handelsdagen varje månad" },
      { k: "Handelskostnad",v: "30 bps per sida" },
      { k: "Data",          v: "yfinance (aktiva) + Tiingo adj. (borttagna 1996–)" },
    ],
    source: "Optimerad sweep. Sharpe 0.97 · CAGR +29% · Max DD −28%",
  },
  sp500_pit_top7: {
    color: "#10b981",
    tagline: "D1-ACCEL S&P 500-aktier — Top 7, bäst risk-justerad avkastning",
    description: "Top-7 ger den bästa Sharpe-kvoten av alla N-varianter i parametersweepen. Balansen mellan koncentration (hög alpha) och diversifiering (lägre drawdown) är optimal vid 7 aktier med dessa parametrar.",
    params: [
      { k: "Signal",        v: "ROC(84d) + Accel(20d) på EMA(3) av (H+L)/2" },
      { k: "Universum",     v: "S&P 500 — point-in-time (~490 tickers/datum)" },
      { k: "Urval",         v: "Top 7 aktier, likviktade (~14% var)" },
      { k: "Regimfilter",   v: "SPY 84d return ≤ 0 → 100% kontanter" },
      { k: "Rebalansering", v: "Sista handelsdagen varje månad" },
      { k: "Handelskostnad",v: "30 bps per sida" },
    ],
    source: "Bäst i sweep. Sharpe 0.99 · CAGR +27% · Max DD −26%",
  },
  // ── OMXS gate-comparison variants ────────────────────────────────
  no_gate_top3: {
    color: "#8b5cf6",
    tagline: "OMXS — Top 3, ingen gate (ren rotation)",
    description: "Ren D1-ACCEL rotation på OMXS utan regime-filter. Isolerar mekanikens edge — om Sharpe är låg här är problemet mönstret självt, inte gaten. Sharpe +0.21 (vs US Top-7 ~1.08). UNVALIDATED.",
    params: [
      { k: "Signal",        v: "ROC(63d) + Accel(10d) på EMA(8) av (H+L)/2" },
      { k: "Universum",     v: "OMXS Large+Mid Cap (~75 tickers, survivorship-biased)" },
      { k: "Urval",         v: "Top 3 aktier, likviktade" },
      { k: "Regimfilter",   v: "Ingen — ren rotation" },
      { k: "Handelskostnad",v: "30 bps per sida" },
      { k: "Status",        v: "⚠ UNVALIDATED — survivorship bias" },
    ],
    source: "Gate-comparison. Sharpe +0.21 · CAGR +1.8% · MaxDD −55.5% · 2022: −38.8%",
  },
  no_gate_top5: {
    color: "#7c3aed",
    tagline: "OMXS — Top 5, ingen gate (ren rotation)",
    description: "Top-5 variant utan gate. Sharpe +0.08, CAGR −1.5%. Svag edge på OMXS även utan gate-overhead.",
    params: [
      { k: "Signal",        v: "ROC(63d) + Accel(10d) på EMA(8) av (H+L)/2" },
      { k: "Universum",     v: "OMXS Large+Mid Cap (~75 tickers, survivorship-biased)" },
      { k: "Urval",         v: "Top 5 aktier, likviktade" },
      { k: "Regimfilter",   v: "Ingen — ren rotation" },
      { k: "Handelskostnad",v: "30 bps per sida" },
      { k: "Status",        v: "⚠ UNVALIDATED — survivorship bias" },
    ],
    source: "Gate-comparison. Sharpe +0.08 · CAGR −1.5% · MaxDD −60.8% · 2022: −39.9%",
  },
  spy_gate_top3: {
    color: "#10b981",
    tagline: "OMXS — Top 3, SPY-gate (US-regime)",
    description: "SPY 84d return ≤ 0 → kontanter. Minskar MaxDD till −43.7% (från −55.5%), men lägre Sharpe (0.16) eftersom gaten missar uppgångar och skyddar mot drawdowns i fel timing.",
    params: [
      { k: "Signal",        v: "ROC(63d) + Accel(10d) på EMA(8) av (H+L)/2" },
      { k: "Universum",     v: "OMXS Large+Mid Cap (~75 tickers, survivorship-biased)" },
      { k: "Urval",         v: "Top 3 aktier, likviktade" },
      { k: "Regimfilter",   v: "SPY 84d return ≤ 0 → 100% kontanter" },
      { k: "Handelskostnad",v: "30 bps per sida" },
      { k: "Status",        v: "⚠ UNVALIDATED — survivorship bias" },
    ],
    source: "Gate-comparison. Sharpe +0.16 · CAGR +0.8% · MaxDD −43.7% · 2022: −19.9%",
  },
  spy_gate_top5: {
    color: "#059669",
    tagline: "OMXS — Top 5, SPY-gate (US-regime)",
    description: "SPY-gate på Top-5. Sharpe 0.10 — marginellt bättre än no-gate (0.08) för Top-5. Skyddade 2022 (−23.7% vs −39.9%) men försämrade 2020 och 2023.",
    params: [
      { k: "Signal",        v: "ROC(63d) + Accel(10d) på EMA(8) av (H+L)/2" },
      { k: "Universum",     v: "OMXS Large+Mid Cap (~75 tickers, survivorship-biased)" },
      { k: "Urval",         v: "Top 5 aktier, likviktade" },
      { k: "Regimfilter",   v: "SPY 84d return ≤ 0 → 100% kontanter" },
      { k: "Handelskostnad",v: "30 bps per sida" },
      { k: "Status",        v: "⚠ UNVALIDATED — survivorship bias" },
    ],
    source: "Gate-comparison. Sharpe +0.10 · CAGR −0.3% · MaxDD −51.1% · 2022: −23.7%",
  },
  omxs_gate_top3: {
    color: "#3b82f6",
    tagline: "OMXS — Top 3, lokal XACT-OMXS30 gate",
    description: "XACT-OMXS30 84d return ≤ 0 → kontanter (lokalt regimfilter). Mest aktiv gate (24 kontantmånader), men SÄMST Sharpe (0.03) — filtrar bort för mycket av den positiva avkastningen.",
    params: [
      { k: "Signal",        v: "ROC(63d) + Accel(10d) på EMA(8) av (H+L)/2" },
      { k: "Universum",     v: "OMXS Large+Mid Cap (~75 tickers, survivorship-biased)" },
      { k: "Urval",         v: "Top 3 aktier, likviktade" },
      { k: "Regimfilter",   v: "XACT-OMXS30 84d return ≤ 0 → 100% kontanter (lokalt)" },
      { k: "Handelskostnad",v: "30 bps per sida" },
      { k: "Status",        v: "⚠ UNVALIDATED — survivorship bias" },
    ],
    source: "Gate-comparison. Sharpe +0.03 · CAGR −1.8% · MaxDD −42.5% · 2022: −16.0%",
  },
  omxs_gate_top5: {
    color: "#2563eb",
    tagline: "OMXS — Top 5, lokal XACT-OMXS30 gate",
    description: "Lokal XACT-OMXS30 gate på Top-5. Sämst av alla varianter (Sharpe 0.01, CAGR −1.8%). Lokal gate är för restriktiv — filtrar bort uppgångsmånader mer än den skyddar mot nedgång.",
    params: [
      { k: "Signal",        v: "ROC(63d) + Accel(10d) på EMA(8) av (H+L)/2" },
      { k: "Universum",     v: "OMXS Large+Mid Cap (~75 tickers, survivorship-biased)" },
      { k: "Urval",         v: "Top 5 aktier, likviktade" },
      { k: "Regimfilter",   v: "XACT-OMXS30 84d return ≤ 0 → 100% kontanter (lokalt)" },
      { k: "Handelskostnad",v: "30 bps per sida" },
      { k: "Status",        v: "⚠ UNVALIDATED — survivorship bias" },
    ],
    source: "Gate-comparison. Sharpe +0.01 · CAGR −1.8% · MaxDD −45.3% · 2022: −21.7%",
  },
  // Legacy aliases (when omxs_results.json is loaded instead of gates file)
  omxs_top3: {
    color: "#818cf8",
    tagline: "D1-ACCEL OMX Stockholm — Top 3 (legacy)",
    description: "Legacy OMXS Top-3 result (broken OMXS30 gate = effectively no gate). Ersatt av gate-comparison variants.",
    params: [{ k: "Status", v: "Legacy — se gate-comparison variants" }],
    source: "Legacy result.",
  },
  omxs_top5: {
    color: "#a78bfa",
    tagline: "D1-ACCEL OMX Stockholm — Top 5 (legacy)",
    description: "Legacy OMXS Top-5 result. Ersatt av gate-comparison variants.",
    params: [{ k: "Status", v: "Legacy — se gate-comparison variants" }],
    source: "Legacy result.",
  },
  sp500_pit_top10: {
    color: "#6ee7b7",
    tagline: "D1-ACCEL S&P 500-aktier — Top 10, bredare diversifiering",
    description: "Top-10 ger lägst volatilitet och maximal Sharpe för 10-aktieportföljer. Sharpe 1.04 — högre än ETF-kärnan men med ~2× CAGR. Optimal konfiguration identifierad via grid-sweep.",
    params: [
      { k: "Signal",        v: "ROC(84d) + Accel(20d) på EMA(3) av (H+L)/2" },
      { k: "Universum",     v: "S&P 500 — point-in-time (~490 tickers/datum)" },
      { k: "Urval",         v: "Top 10 aktier, likviktade (10% var)" },
      { k: "Regimfilter",   v: "SPY 84d return ≤ 0 → 100% kontanter" },
      { k: "Rebalansering", v: "Sista handelsdagen varje månad" },
      { k: "Handelskostnad",v: "30 bps per sida" },
    ],
    source: "Optimerad sweep. Sharpe 1.04 · CAGR +26% · Max DD −21%",
  },
};

// ── Palette ────────────────────────────────────────────────────────
const SERIES_CFG = {
  top1_top1:    { label: "D1 — raw",         color: "#5b6ef5", width: 1.6 },
  top2_top2:    { label: "D2 — raw",         color: "#a78bfa", width: 1.6 },
  d1_composite: { label: "D1-composite",     color: "#10b981", width: 2.2 },
  d2_composite: { label: "D2-composite",     color: "#34d399", width: 2.2 },
  d1_accel:     { label: "D1-accel.",        color: "#f59e0b", width: 2.0 },
  d2_accel:     { label: "D2-accel.",        color: "#fcd34d", width: 2.0 },
  d1_lowcorr:   { label: "D1-low-corr.",     color: "#f43f5e", width: 2.0 },
  d2_lowcorr:   { label: "D2-low-corr.",     color: "#fb7185", width: 2.0 },
  ppm_top3:           { label: "PPM top-3 (2001+)", color: "#06b6d4", width: 2.5 },
  ppm_top3_recent:    { label: "PPM top-3 (2020+)", color: "#22d3ee", width: 2.5 },
  sp500_pit_top5:          { label: "SP500 D1-ACCEL Top-5",      color: "#34d399", width: 2.0 },
  sp500_pit_top7:          { label: "SP500 D1-ACCEL Top-7",      color: "#10b981", width: 2.0 },
  sp500_pit_top10:         { label: "SP500 D1-ACCEL Top-10",     color: "#6ee7b7", width: 1.5 },
  sp500_sammansatt_top5:   { label: "SP500 Sammansatt Top-5",    color: "#f97316", width: 2.5 },
  sp500_sammansatt_top7:   { label: "SP500 Sammansatt Top-7",    color: "#fb923c", width: 2.0 },
  sp500_sammansatt_top10:  { label: "SP500 Sammansatt Top-10",   color: "#fdba74", width: 1.5 },
  stoxx_sammansatt_top5:   { label: "STOXX Sammansatt Top-5",    color: "#c026d3", width: 2.5 },
  stoxx_sammansatt_top7:   { label: "STOXX Sammansatt Top-7",    color: "#d946ef", width: 2.0 },
  stoxx_sammansatt_top10:  { label: "STOXX Sammansatt Top-10",   color: "#e879f9", width: 1.5 },
  nasdaq_sammansatt_top5:  { label: "Nasdaq Sammansatt Top-5",    color: "#38bdf8", width: 2.5 },
  nasdaq_sammansatt_top7:  { label: "Nasdaq Sammansatt Top-7",    color: "#7dd3fc", width: 2.0 },
  nasdaq_sammansatt_top10: { label: "Nasdaq Sammansatt Top-10",   color: "#bae6fd", width: 1.5 },
  // Global — 4-universe configs (top9/12/15)
  global_top9:             { label: "Global Top-9 (4 univ)",      color: "#facc15", width: 2.5 },
  global_top12:            { label: "Global Top-12 (4 univ)",     color: "#fbbf24", width: 2.0 },
  global_top15:            { label: "Global Top-15 (4 univ)",     color: "#f59e0b", width: 1.5 },
  // Keep old keys for backwards compat (results may still use them)
  global_top7:             { label: "Global Top-7 (max 3/univ)",  color: "#facc15", width: 2.5 },
  global_top10:            { label: "Global Top-10 (max 4/univ)", color: "#fbbf24", width: 2.0 },
  no_gate_top3:       { label: "OMXS No gate — Top 3",   color: "#8b5cf6", width: 2.5 },
  no_gate_top5:       { label: "OMXS No gate — Top 5",   color: "#7c3aed", width: 2.0 },
  spy_gate_top3:      { label: "OMXS SPY gate — Top 3",  color: "#10b981", width: 2.5 },
  spy_gate_top5:      { label: "OMXS SPY gate — Top 5",  color: "#059669", width: 2.0 },
  omxs_gate_top3:     { label: "OMXS local gate — Top 3",color: "#3b82f6", width: 2.5 },
  omxs_gate_top5:     { label: "OMXS local gate — Top 5",color: "#2563eb", width: 2.0 },
  omxs_top3:                { label: "OMXS — Top 3",              color: "#818cf8", width: 2.5 },
  omxs_top5:                { label: "OMXS — Top 5",              color: "#a78bfa", width: 2.0 },
  omxs_sammansatt_top5:     { label: "Sammansatt Mom Top-5",       color: "#f97316", width: 2.5 },
  omxs_sammansatt_top7:     { label: "Sammansatt Mom Top-7",       color: "#fb923c", width: 2.0 },
  omxs_sammansatt_top10:    { label: "Sammansatt Mom Top-10",      color: "#fdba74", width: 1.5 },
  "MSCI World": { label: "MSCI World",       color: "#64748b", width: 1.4 },
  "OMXS30":     { label: "OMXS30",           color: "#38bdf8", width: 1.4 },
  "Nasdaq":     { label: "Nasdaq",            color: "#f59e0b", width: 1.4 },
  "S&P 500":    { label: "S&P 500",          color: "#f97316", width: 1.4 },
  // STOXX 600
  stoxx600_top5:  { label: "Euro STOXX Top-5",  color: "#ec4899", width: 2.5 },
  stoxx600_top10: { label: "Euro STOXX Top-10", color: "#db2777", width: 2.0 },
  stoxx600_top20: { label: "Euro STOXX Top-20", color: "#9d174d", width: 1.5 },
  "EXSA.DE":    { label: "STOXX 600 ETF",      color: "#f9a8d4", width: 1.4 },
};

const ALLOC_PALETTE = [
  "#5b6ef5","#a78bfa","#38bdf8","#10b981","#f59e0b",
  "#f43f5e","#6ee7b7","#93c5fd","#fca5a5","#c4b5fd","#64748b",
];

// ── State ──────────────────────────────────────────────────────────
let DATA = null;
let CONFIG = null;
const _ACTIVE_KEYS_DEFAULT = ["d1_composite", "d2_composite", "d1_accel", "d1_lowcorr", "ppm_top3", "ppm_top3_recent", "MSCI World"];
const _ACTIVE_KEYS_LS = "etf_active_keys";
function _loadActiveKeys() {
  try {
    const saved = localStorage.getItem(_ACTIVE_KEYS_LS);
    if (saved) return new Set(JSON.parse(saved));
  } catch (_) {}
  return new Set(_ACTIVE_KEYS_DEFAULT);
}
function _saveActiveKeys() {
  try { localStorage.setItem(_ACTIVE_KEYS_LS, JSON.stringify([...activeKeys])); } catch (_) {}
}
let activeKeys = _loadActiveKeys();
let mainChart   = null;
let stocksChart = null;
let omxsChart   = null;
let tickerColorMap = {};
let ppmColorMap    = {};
let stockColorMap  = {};
let stoxxChart     = null;
let nasdaqChart    = null;
let globalChart    = null;

// ── Init ───────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  mainChart   = echarts.init(document.getElementById("main-chart"),   null, { renderer: "canvas" });
  stocksChart = echarts.init(document.getElementById("stocks-chart"), null, { renderer: "canvas" });
  omxsChart   = echarts.init(document.getElementById("omxs-chart"),   null, { renderer: "canvas" });
  stoxxChart  = echarts.init(document.getElementById("stoxx-chart"),  null, { renderer: "canvas" });
  nasdaqChart = echarts.init(document.getElementById("nasdaq-chart"), null, { renderer: "canvas" });
  globalChart = echarts.init(document.getElementById("global-chart"), null, { renderer: "canvas" });
  window.addEventListener("resize", () => {
    mainChart?.resize(); stocksChart?.resize(); omxsChart?.resize();
    stoxxChart?.resize(); nasdaqChart?.resize(); globalChart?.resize();
  });
  document.getElementById("start-date").addEventListener("change", () => { if (DATA) renderMainChart(); });
  await loadData();
});

// ── Tab switching ──────────────────────────────────────────────────
function switchTab(tab) {
  const views = ["dashboard", "settings", "funds", "screen", "stocks", "omxs", "stoxx", "nasdaq", "global", "universe", "logs", "docs"];
  views.forEach(v => document.getElementById("view-" + v)?.classList.toggle("hidden", tab !== v));
  views.forEach(v => {
    const el = document.getElementById("tab-" + v);
    if (el) el.className = tab === v ? "tab-active pb-1 transition-colors" : "tab-inactive pb-1 transition-colors";
  });
  if (tab === "funds")     renderFundsTable();
  if (tab === "screen")    renderScreening();
  if (tab === "logs")      renderLogs();
  if (tab === "docs")      renderDocs();
  if (tab === "stocks")    renderStocksPage();
  if (tab === "omxs")      renderOMXSPage();
  if (tab === "stoxx")     renderSTOXXPage();
  if (tab === "nasdaq")    renderNasdaqPage();
  if (tab === "global")    renderGlobalPage();
  if (tab === "universe")  renderUniversePage();
  if (tab === "settings" && !CONFIG) loadConfig();
}

// ── Data loading ───────────────────────────────────────────────────
async function loadData() {
  try {
    const res = await fetch("/static/data.json?t=" + Date.now());
    if (!res.ok) throw new Error(res.status);
    DATA = await res.json();
    renderAll();
  } catch (e) {
    document.getElementById("last-updated").textContent = "data.json not found — run engine.py first";
  }
}

function renderAll() {
  const ts = DATA.generated_at
    ? new Date(DATA.generated_at).toLocaleString("sv-SE", { timeZone: "Europe/Stockholm" })
    : "unknown";
  document.getElementById("last-updated").textContent = "Updated " + ts;
  buildTickerColorMap();
  buildToggles();
  renderMainChart();
  renderSignalCards();
  renderStats();
}

function buildTickerColorMap() {
  tickerColorMap = {};
  ppmColorMap    = {};
  stockColorMap  = {};
  let colorIdx = 0;
  // ETF strategies
  for (const sk of ["top1_top1","top2_top2","d1_composite","d2_composite",
                    "d1_accel","d2_accel","d1_lowcorr","d2_lowcorr"]) {
    const alloc = DATA?.strategies?.[sk]?.allocation;
    if (!alloc?.tickers) continue;
    alloc.tickers.forEach((t, i) => {
      if (!(t in tickerColorMap) && alloc.weights.some(row => row[i] > 0))
        tickerColorMap[t] = ALLOC_PALETTE[colorIdx++ % ALLOC_PALETTE.length];
    });
  }
  // PPM fund labels get their own color assignments
  const ppmAlloc = DATA?.strategies?.ppm_top3?.allocation;
  if (ppmAlloc?.tickers) {
    let ppmIdx = 0;
    ppmAlloc.tickers.forEach((t, i) => {
      if (!(t in ppmColorMap) && ppmAlloc.weights.some(row => row[i] > 0))
        ppmColorMap[t] = ALLOC_PALETTE[ppmIdx++ % ALLOC_PALETTE.length];
    });
  }
  // Stock tickers — build a single shared color map across top5/top10
  const STOCK_PALETTE = [
    "#34d399","#6ee7b7","#f59e0b","#fcd34d","#60a5fa","#93c5fd","#f43f5e","#fb7185",
    "#a78bfa","#c4b5fd","#38bdf8","#7dd3fc","#fb923c","#fdba74","#4ade80","#86efac",
    "#e879f9","#f0abfc","#2dd4bf","#5eead4","#818cf8","#a5b4fc",
  ];
  let stockIdx = 0;
  for (const sk of ["sp500_pit_top5","sp500_pit_top7","sp500_pit_top10"]) {
    const alloc = DATA?.strategies?.[sk]?.allocation;
    if (!alloc?.tickers) continue;
    alloc.tickers.forEach((t, i) => {
      if (!(t in stockColorMap) && t !== "CASH" && alloc.weights.some(row => row[i] > 0))
        stockColorMap[t] = STOCK_PALETTE[stockIdx++ % STOCK_PALETTE.length];
    });
  }
}

// ── Series toggles ─────────────────────────────────────────────────
function buildToggles() {
  const container = document.getElementById("series-toggles");
  container.innerHTML = "";
  const allKeys = [
    ...Object.keys(DATA.strategies || {}),
    ...Object.keys(DATA.benchmarks || {}),
  ];
  allKeys.forEach(key => {
    const c = SERIES_CFG[key] || {};
    const color = c.color || "#64748b";
    const on = activeKeys.has(key);
    const btn = document.createElement("button");
    btn.dataset.key = key;
    btn.className = "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-all";
    applyToggleStyle(btn, on, color);
    const dot = document.createElement("span");
    dot.className = "w-2 h-2 rounded-full flex-shrink-0";
    dot.style.background = color;
    btn.appendChild(dot);
    btn.appendChild(document.createTextNode(c.label || key));
    btn.addEventListener("click", () => {
      if (activeKeys.has(key)) activeKeys.delete(key); else activeKeys.add(key);
      _saveActiveKeys();
      applyToggleStyle(btn, activeKeys.has(key), color);
      renderMainChart();
      renderStats();
      renderSignalCards();
    });
    container.appendChild(btn);
  });
}

function applyToggleStyle(btn, on, color) {
  btn.style.background   = on ? color + "22" : "";
  btn.style.borderColor  = on ? color : "#252a3d";
  btn.style.color        = on ? color : "#8591b8";
}


// ── Allocation lookup ──────────────────────────────────────────────
function allocAtDate(stratKey, dateStr) {
  const alloc = DATA?.strategies?.[stratKey]?.allocation;
  if (!alloc?.dates?.length) return null;
  let idx = -1;
  for (let i = 0; i < alloc.dates.length; i++) {
    if (alloc.dates[i] <= dateStr) idx = i; else break;
  }
  if (idx === -1) return null;
  const row = alloc.weights[idx];
  const holdings = {};
  alloc.tickers.forEach((t, i) => { if (row[i] > 0) holdings[t] = row[i]; });
  return holdings;
}

function tickerLabel(ticker) {
  const snap = DATA?.config_snapshot || {};
  for (const [lbl, v] of Object.entries(snap.factor_sleeve || {}))
    if (v.ticker === ticker) return lbl;
  for (const [lbl, v] of Object.entries(snap.sector_sleeve || {}))
    if (v.ticker === ticker) return lbl;
  if (snap.cash_proxy?.ticker === ticker) return "CASH";
  return ticker;
}

// ── Combined chart (performance + D1 allocation + D2 allocation) ────
function renderMainChart() {
  const startDate = document.getElementById("start-date").value;

  function normalize(series) {
    if (!series?.length) return [];
    const idx = series.findIndex(p => p.date >= startDate);
    if (idx === -1) return [];
    const base = series[idx].value;
    if (!base) return [];
    return series.slice(idx).map(p => [p.date, +(p.value / base * 100).toFixed(4)]);
  }

  // ── Grid 0: performance series ────────────────────────────────────
  const perfSeries = [];
  for (const [key, strat] of Object.entries(DATA.strategies || {})) {
    if (!activeKeys.has(key)) continue;
    const c = SERIES_CFG[key] || {};
    perfSeries.push({
      name: c.label || key, type: "line",
      data: normalize(strat.nav),
      smooth: false, symbol: "none",
      lineStyle: { color: c.color, width: c.width || 2 },
      itemStyle: { color: c.color },
      xAxisIndex: 0, yAxisIndex: 0, z: 10,
    });
  }
  for (const [name, bench] of Object.entries(DATA.benchmarks || {})) {
    if (!activeKeys.has(name)) continue;
    const c = SERIES_CFG[name] || {};
    perfSeries.push({
      name: c.label || name, type: "line",
      data: normalize(bench.series),
      smooth: false, symbol: "none",
      lineStyle: { color: c.color, width: c.width || 1.5, type: "dashed" },
      itemStyle: { color: c.color },
      xAxisIndex: 0, yAxisIndex: 0, z: 5,
    });
  }

  // ── Helper: build stacked-area series for one allocation strip ────
  function buildAllocSeries(stratKey, xIdx, yIdx) {
    const alloc = DATA?.strategies?.[stratKey]?.allocation;
    if (!alloc?.tickers?.length) return [];
    const isPPM = stratKey.startsWith("ppm_top3");
    return alloc.tickers
      .map((t, i) => ({ t, i }))
      .filter(({ i }) => alloc.weights.some(row => row[i] > 0))
      .map(({ t, i }) => {
        const pts = alloc.dates
          .map((d, ri) => [d, alloc.weights[ri][i]])
          .filter(([d]) => d >= startDate);
        const color = isPPM ? (ppmColorMap[t] || "#8591b8") : (tickerColorMap[t] || "#8591b8");
        return {
          name: isPPM ? t : tickerLabel(t), type: "line",
          stack: `alloc-${stratKey}`,
          areaStyle: { color, opacity: 0.88 },
          lineStyle: { width: 0 },
          symbol: "none",
          step: "end",
          data: pts.map(([d, w]) => [d, +(w * 100).toFixed(2)]),
          xAxisIndex: xIdx, yAxisIndex: yIdx,
        };
      });
  }

  // ── Dynamic allocation strips ──────────────────────────────────────
  const STRIP_CANDIDATES = [
    "top1_top1","d1_composite","d1_accel","d1_lowcorr",
    "top2_top2","d2_composite","d2_accel","d2_lowcorr","ppm_top3","ppm_top3_recent",
  ];
  const activeStrips = STRIP_CANDIDATES.filter(
    k => activeKeys.has(k) && DATA?.strategies?.[k]?.allocation?.tickers?.length
  );
  const N = activeStrips.length;

  // Grids: perf fills top half when strips present, else full height
  const dynGrids = [];
  if (N > 0) {
    dynGrids.push({ top: 16, left: 60, right: 20, bottom: "52%" });
    const avail = 48;  // percent from 50% to 98%
    for (let i = 0; i < N; i++) {
      const top = (50 + avail * i / N).toFixed(1);
      if (i < N - 1) {
        const h = (avail / N * 0.84).toFixed(1);
        dynGrids.push({ top: `${top}%`, left: 60, right: 20, height: `${h}%` });
      } else {
        dynGrids.push({ top: `${top}%`, left: 60, right: 20, bottom: 26 });
      }
    }
  } else {
    dynGrids.push({ top: 16, left: 60, right: 20, bottom: 26 });
  }

  // xAxes: one per grid, last strip (or perf if N===0) shows date labels
  const dynXAxes = [{
    type: "time", gridIndex: 0, min: startDate,
    axisLabel: N === 0 ? { color: "#8591b8", fontSize: 10 } : { show: false },
    axisLine:  { lineStyle: { color: "#252a3d" } },
    splitLine: { show: false },
    axisTick:  N === 0 ? { lineStyle: { color: "#252a3d" } } : { show: false },
  }];
  for (let i = 0; i < N; i++) {
    const isLast = i === N - 1;
    dynXAxes.push({
      type: "time", gridIndex: i + 1, min: startDate,
      axisLabel: isLast ? { color: "#8591b8", fontSize: 10 } : { show: false },
      axisLine:  { lineStyle: { color: "#252a3d" } },
      splitLine: { show: false },
      axisTick:  isLast ? { lineStyle: { color: "#252a3d" } } : { show: false },
    });
  }

  // yAxes: one per grid
  const dynYAxes = [{
    type: "value", gridIndex: 0,
    axisLabel: { color: "#8591b8", fontSize: 10, formatter: v => v.toFixed(0) },
    axisLine:  { show: false },
    splitLine: { lineStyle: { color: "#252a3d", type: "dashed" } },
    axisTick:  { show: false },
  }];
  for (let i = 0; i < N; i++) {
    const key = activeStrips[i];
    const c = SERIES_CFG[key] || {};
    dynYAxes.push({
      type: "value", gridIndex: i + 1, max: 100, min: 0,
      name: c.label || key, nameLocation: "end",
      nameTextStyle: { color: c.color || "#8591b8", fontSize: 9, fontWeight: 600, padding: [0, 0, 4, 0] },
      axisLabel: { show: false }, axisLine: { show: false },
      splitLine: { show: false }, axisTick: { show: false },
    });
  }

  // ── Tooltip formatter ─────────────────────────────────────────────
  function tooltipFormatter(params) {
    if (!params?.length) return "";
    const dateStr = new Date(params[0].axisValue).toISOString().slice(0, 10);

    const perfParams = params.filter(p => p.axisIndex === 0);
    const perfRows = perfParams.map(p =>
      `<div style="display:flex;justify-content:space-between;gap:24px;margin-bottom:2px">
        <span style="color:${p.color}">${p.seriesName}</span>
        <span style="font-variant-numeric:tabular-nums">${(+p.value[1]).toFixed(1)}</span>
      </div>`
    ).join("");

    const ALLOC_KEYS = ["top1_top1","d1_composite","d1_accel","d1_lowcorr",
                        "top2_top2","d2_composite","d2_accel","d2_lowcorr","ppm_top3","ppm_top3_recent"];
    const allocSection = ALLOC_KEYS.filter(k => activeKeys.has(k)).map(k => {
      const holdings = allocAtDate(k, dateStr);
      if (!holdings) return "";
      const c = SERIES_CFG[k] || {};
      const isPPM = k.startsWith("ppm_top3");
      const chips = Object.entries(holdings).map(([t, w]) => {
        const color = isPPM ? (c.color || "#06b6d4") : (tickerColorMap[t] || "#8591b8");
        const label = isPPM ? t : tickerLabel(t);
        return `<span style="background:${color}22;border:1px solid ${color}55;border-radius:3px;padding:1px 5px;margin:1px 2px 1px 0;display:inline-block;color:${color}">
          ${label}<span style="opacity:.65;margin-left:3px">${Math.round(w * 100)}%</span>
        </span>`;
      }).join("");
      return `<div style="margin-top:6px;padding-top:6px;border-top:1px solid #252a3d">
        <span style="color:${c.color || "#8591b8"};font-size:10px;font-weight:600">${c.label || k}</span>
        <div style="margin-top:3px;line-height:2">${chips}</div>
      </div>`;
    }).join("");

    return `<div style="font-size:11px;max-width:320px">
      <div style="color:#8591b8;margin-bottom:6px">${dateStr}</div>
      ${perfRows}${allocSection}
    </div>`;
  }

  // ── ECharts option — dynamic grids ────────────────────────────────
  mainChart.setOption({
    backgroundColor: "transparent",
    animation: false,
    grid: dynGrids,
    xAxis: dynXAxes,
    yAxis: dynYAxes,

    tooltip: {
      trigger: "axis",
      backgroundColor: "#1a1e2e",
      borderColor:     "#252a3d",
      textStyle:       { color: "#c9d1e0", fontSize: 12 },
      axisPointer: {
        type: "cross",
        crossStyle: { color: "#8591b866" },
        link: [{ xAxisIndex: "all" }],
      },
      formatter: tooltipFormatter,
    },

    legend: { show: false },

    series: [...perfSeries, ...activeStrips.flatMap((k, i) => buildAllocSeries(k, i + 1, i + 1))],
  }, true);
}

// ── Signal cards ───────────────────────────────────────────────────
function renderSignalCards() {
  const D1_CARDS = [
    { elId: "signal-d1",   key: "top1_top1",    title: "D1 — raw"     },
    { elId: "signal-d1c",  key: "d1_composite", title: "D1-composite" },
    { elId: "signal-d1a",  key: "d1_accel",     title: "D1-accel."    },
    { elId: "signal-d1lc", key: "d1_lowcorr",   title: "D1-low-corr." },
  ];
  const D2_CARDS = [
    { elId: "signal-d2",   key: "top2_top2",    title: "D2 — raw"     },
    { elId: "signal-d2c",  key: "d2_composite", title: "D2-composite" },
    { elId: "signal-d2a",  key: "d2_accel",     title: "D2-accel."    },
    { elId: "signal-d2lc", key: "d2_lowcorr",   title: "D2-low-corr." },
  ];

  function renderRow(cards, rowId) {
    let anyActive = false;
    for (const { elId, key, title } of cards) {
      const el = document.getElementById(elId);
      if (!el) continue;
      if (!activeKeys.has(key)) {
        el.innerHTML = "";
        el.style.display = "none";
      } else {
        el.style.display = "";
        renderSignalCard(elId, DATA?.strategies?.[key], title, key);
        anyActive = true;
      }
    }
    const row = document.getElementById(rowId);
    if (row) row.style.display = anyActive ? "" : "none";
  }

  renderRow(D1_CARDS, "signal-row-d1");
  renderRow(D2_CARDS, "signal-row-d2");

  const ppmEl  = document.getElementById("signal-ppm");
  const ppmRow = document.getElementById("signal-row-ppm");
  if (ppmEl) {
    if (!activeKeys.has("ppm_top3")) {
      ppmEl.innerHTML = "";
      ppmEl.style.display = "none";
      if (ppmRow) ppmRow.style.display = "none";
    } else {
      ppmEl.style.display = "";
      if (ppmRow) ppmRow.style.display = "";
      renderPPMSignalCard("signal-ppm", DATA?.strategies?.ppm_top3);
    }
  }
}

function renderPPMSignalCard(elId, strat) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (!strat?.rebal_signal && !strat?.current_signal) { el.innerHTML = ""; return; }
  const key   = "ppm_top3";
  const spec  = STRATEGY_SPECS[key];
  const color = spec?.color || "#06b6d4";

  const rebal = strat.rebal_signal || strat.current_signal;
  const live  = strat.live_signal  || strat.current_signal;

  function ppmRows(holdings) {
    return (holdings || []).map(h => {
      const pct = Math.round(h.weight * 100);
      const ppmLink = `<a href="https://www.pensionsmyndigheten.se/service/fondtorget/fond/${h.ticker}"
          target="_blank" rel="noopener"
          class="text-xs text-accent hover:underline font-mono">${h.ticker}</a>`;
      return `
        <div class="flex items-start justify-between gap-3 py-2 border-b border-border last:border-0">
          <div class="min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="text-xs font-medium text-slate-300">${h.label}</span>
              ${ppmLink}
              <span class="text-xs px-1.5 rounded-sm bg-cyan-900/50 text-cyan-300">PPM</span>
            </div>
            ${h.nordnet_name ? `<p class="text-xs text-muted mt-0.5 truncate">${h.nordnet_name}</p>` : ""}
          </div>
          <div class="flex items-center gap-2 flex-shrink-0">
            <span class="text-xs text-muted">${pct}%</span>
          </div>
        </div>`;
    }).join("");
  }

  const rebalTickers = (rebal?.holdings || []).map(h => h.ticker).sort().join(",");
  const liveTickers  = (live?.holdings  || []).map(h => h.ticker).sort().join(",");
  const sameHoldings = rebalTickers === liveTickers;

  const rebalRows = ppmRows(rebal?.holdings) ||
    '<p class="text-xs text-muted italic">Kontanter — abs-mom filter aktivt (AP7 Räntefond)</p>';

  const liveSection = !sameHoldings ? `
    <div class="mt-3 pt-2 border-t border-border">
      <div class="flex items-center justify-between mb-1">
        <span class="text-xs text-amber-400/80 font-medium">Live idag</span>
        <span class="text-xs text-muted">${live?.date ?? ""}</span>
      </div>
      ${ppmRows(live?.holdings) || '<p class="text-xs text-muted italic">Kontanter</p>'}
    </div>` : `
    <p class="text-xs text-muted mt-2 pt-2 border-t border-border">
      Live idag: samma innehav
    </p>`;

  el.innerHTML = `
    <div class="flex items-center justify-between mb-3">
      <button onclick="openSpecModal('${key}')"
              class="flex items-center gap-2 group text-left">
        <span class="w-2 h-2 rounded-full flex-shrink-0" style="background:${color}"></span>
        <span class="text-xs font-semibold tracking-widest uppercase transition-colors"
              style="color:${color}">PPM top-3</span>
        <svg class="w-3 h-3 text-muted group-hover:text-slate-400 transition-colors flex-shrink-0"
             fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>
        </svg>
      </button>
      <span class="text-xs text-muted">Rebalansering ${rebal?.date ?? ""}</span>
    </div>
    ${rebalRows}
    ${liveSection}`;
}

function renderSignalCard(elId, strat, title, key) {
  const el = document.getElementById(elId);
  if (!strat?.rebal_signal && !strat?.current_signal) { el.innerHTML = ""; return; }
  const spec  = STRATEGY_SPECS[key];
  const color = spec?.color || SERIES_CFG[key]?.color || "#64748b";

  const rebal = strat.rebal_signal || strat.current_signal;
  const live  = strat.live_signal  || strat.current_signal;

  function holdingRows(holdings) {
    return (holdings || []).map(h => {
      const pct = Math.round(h.weight * 100);
      return `
        <div class="flex items-start justify-between gap-3 py-2 border-b border-border last:border-0">
          <div class="min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="text-xs font-medium text-slate-300">${h.label}</span>
              <span class="text-xs text-muted">${h.ticker}</span>
              <span class="text-xs px-1.5 rounded-sm ${
                h.sleeve === 'factor' ? 'bg-indigo-900/50 text-indigo-300' :
                h.sleeve === 'sector' ? 'bg-purple-900/50 text-purple-300' :
                h.sleeve === 'ppm'    ? 'bg-teal-900/50 text-teal-300' :
                'bg-slate-800 text-slate-400'}">${h.sleeve}</span>
            </div>
            ${h.nordnet_name ? `<p class="text-xs text-muted mt-0.5 truncate">${h.nordnet_name}</p>` : ""}
          </div>
          <div class="flex items-center gap-2 flex-shrink-0">
            <span class="text-xs text-muted">${pct}%</span>
            ${h.isin && h.isin !== "CASH" ? `
              <button onclick="copyISIN('${h.isin}', this)"
                      class="text-xs text-muted hover:text-accent border border-border hover:border-accent rounded px-2 py-0.5 transition-colors font-mono tracking-wide">
                ${h.isin}
              </button>` : ""}
          </div>
        </div>`;
    }).join("");
  }

  // Check if live and rebal have the same picks
  const rebalTickers = (rebal?.holdings || []).map(h => h.ticker).sort().join(",");
  const liveTickers  = (live?.holdings  || []).map(h => h.ticker).sort().join(",");
  const sameHoldings = rebalTickers === liveTickers;

  const rebalRows = holdingRows(rebal?.holdings) ||
    '<p class="text-xs text-muted italic">Kontanter — regimfilter aktivt</p>';

  const liveSection = !sameHoldings ? `
    <div class="mt-3 pt-2 border-t border-border">
      <div class="flex items-center justify-between mb-1">
        <span class="text-xs text-amber-400/80 font-medium">Live idag</span>
        <span class="text-xs text-muted">${live?.date ?? ""}</span>
      </div>
      ${holdingRows(live?.holdings) || '<p class="text-xs text-muted italic">Kontanter</p>'}
    </div>` : `
    <p class="text-xs text-muted mt-2 pt-2 border-t border-border">
      Live idag: samma innehav
    </p>`;

  el.innerHTML = `
    <div class="flex items-center justify-between mb-3">
      <button onclick="openSpecModal('${key}')"
              class="flex items-center gap-2 group text-left">
        <span class="w-2 h-2 rounded-full flex-shrink-0" style="background:${color}"></span>
        <span class="text-xs font-semibold tracking-widest uppercase transition-colors"
              style="color:${color}">${title}</span>
        <svg class="w-3 h-3 text-muted group-hover:text-slate-400 transition-colors flex-shrink-0"
             fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>
        </svg>
      </button>
      <span class="text-xs text-muted">Rebalansering ${rebal?.date ?? ""}</span>
    </div>
    ${rebalRows}
    ${liveSection}`;
}

// ── Strategy spec modal ────────────────────────────────────────────
function openSpecModal(key) {
  const spec = STRATEGY_SPECS[key];
  if (!spec) return;
  const st   = DATA?.strategies?.[key]?.stats;
  const color = spec.color;

  function pct(v) { return v == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%"; }
  function colorStyle(v) { return v == null ? "color:#8591b8" : v >= 0 ? "color:#10b981" : "color:#f43f5e"; }

  const statsHtml = st ? `
    <div class="grid grid-cols-3 gap-3 mt-4">
      <div class="bg-surface rounded-lg p-3 text-center">
        <p class="text-xs text-muted mb-1">CAGR</p>
        <p class="text-base font-semibold" style="${colorStyle(st.cagr)}">${pct(st.cagr)}</p>
      </div>
      <div class="bg-surface rounded-lg p-3 text-center">
        <p class="text-xs text-muted mb-1">Sharpe</p>
        <p class="text-base font-semibold text-slate-300">${st.sharpe?.toFixed(2) ?? "—"}</p>
      </div>
      <div class="bg-surface rounded-lg p-3 text-center">
        <p class="text-xs text-muted mb-1">Max DD (mo)</p>
        <p class="text-base font-semibold" style="color:#fb923c">${pct(st.max_dd_monthly)}</p>
      </div>
    </div>` : "";

  const paramsHtml = spec.params.map(p => `
    <tr class="border-t border-border">
      <td class="py-2 pr-4 text-xs text-muted font-medium w-40 align-top">${p.k}</td>
      <td class="py-2 text-xs text-slate-300">${p.v}</td>
    </tr>`).join("");

  document.getElementById("spec-modal-content").innerHTML = `
    <div class="flex items-center gap-3 mb-4">
      <span class="w-3 h-3 rounded-full flex-shrink-0" style="background:${color}"></span>
      <h2 class="text-base font-semibold text-slate-200">${SERIES_CFG[key]?.label || key}</h2>
    </div>
    <p class="text-xs text-slate-400 italic mb-4">${spec.tagline}</p>
    <p class="text-xs text-slate-400 leading-relaxed mb-4">${spec.description}</p>
    ${statsHtml}
    <div class="mt-5">
      <p class="text-xs font-semibold text-muted uppercase tracking-widest mb-2">Parametrar</p>
      <table class="w-full border-collapse">
        <tbody>${paramsHtml}</tbody>
      </table>
    </div>
    <div class="mt-4 pt-4 border-t border-border">
      <p class="text-xs text-muted leading-relaxed">
        <span class="font-medium text-slate-500">Källa: </span>${spec.source}
      </p>
    </div>`;

  const modal = document.getElementById("spec-modal");
  modal.classList.remove("hidden");
  modal.focus();
}

function closeSpecModal() {
  document.getElementById("spec-modal").classList.add("hidden");
}

function copyISIN(isin, btn) {
  navigator.clipboard.writeText(isin).then(() => {
    const orig = btn.textContent;
    btn.textContent = "Copied";
    btn.style.color = "#10b981";
    setTimeout(() => { btn.textContent = orig; btn.style.color = ""; }, 1500);
  });
}

// ── Stats panel ────────────────────────────────────────────────────
function renderStats() {
  const el = document.getElementById("stats-panel");
  if (!el) return;
  const strategies = DATA?.strategies || {};

  const ETF_STRATS = [
    { key: "top1_top1",    label: "D1 — raw",       color: "#5b6ef5" },
    { key: "d1_composite", label: "D1-composite",    color: "#10b981" },
    { key: "d1_accel",     label: "D1-accel.",       color: "#f59e0b" },
    { key: "d1_lowcorr",   label: "D1-low-corr.",    color: "#f43f5e" },
    { key: "top2_top2",    label: "D2 — raw",        color: "#a78bfa" },
    { key: "d2_composite", label: "D2-composite",    color: "#34d399" },
    { key: "d2_accel",     label: "D2-accel.",       color: "#fcd34d" },
    { key: "d2_lowcorr",   label: "D2-low-corr.",    color: "#fb7185" },
  ];
  const PPM_STRAT  = { key: "ppm_top3", label: "PPM top-3", color: "#06b6d4" };
  const activeETF  = ETF_STRATS.filter(s => activeKeys.has(s.key));
  const ppmActive  = activeKeys.has("ppm_top3");
  const activeAll  = [...activeETF, ...(ppmActive ? [PPM_STRAT] : [])];

  if (!activeETF.length && !ppmActive) { el.innerHTML = ""; return; }

  function pct(v, decimals = 1) {
    return v == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(decimals) + "%";
  }
  function colorVal(v) {
    return v == null ? "color:#8591b8" : v >= 0 ? "color:#10b981" : "color:#f43f5e";
  }

  // ── Summary card — same 6-metric format for ETF and PPM ──────────
  function summaryCard({ key, label, color }) {
    const st  = strategies[key]?.stats;
    if (!st) return "";
    const nav = strategies[key]?.nav || [];
    const period = nav.length
      ? `<span class="text-xs text-muted ml-auto">${nav[0].date} → ${nav[nav.length-1].date}</span>`
      : "";
    const isPPM = key === "ppm_top3";
    return `
      <div class="bg-panel border border-border rounded-lg p-4"${isPPM ? ` style="border-color:${color}33"` : ""}>
        <div class="flex items-center gap-2 mb-3 flex-wrap">
          <button onclick="openSpecModal('${key}')" class="flex items-center gap-2 group text-left">
            <span class="w-2 h-2 rounded-full flex-shrink-0" style="background:${color}"></span>
            <span class="text-xs font-semibold tracking-widest uppercase group-hover:text-slate-200 transition-colors"
                  style="color:${color}">${label}</span>
            <svg class="w-3 h-3 text-muted group-hover:text-slate-400 transition-colors flex-shrink-0"
                 fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>
            </svg>
          </button>
          ${period}
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          <div><p class="text-xs text-muted mb-0.5">CAGR</p>
            <p class="text-lg font-semibold" style="${colorVal(st.cagr)}">${pct(st.cagr)}</p></div>
          <div><p class="text-xs text-muted mb-0.5">Sharpe</p>
            <p class="text-lg font-semibold text-slate-300">${st.sharpe?.toFixed(2) ?? "—"}</p></div>
          <div><p class="text-xs text-muted mb-0.5">Max DD <span class="font-normal">(dag)</span></p>
            <p class="text-lg font-semibold" style="color:#f43f5e">${pct(st.max_dd)}</p></div>
          <div><p class="text-xs text-muted mb-0.5">Max DD <span class="font-normal">(mån)</span></p>
            <p class="text-lg font-semibold" style="color:#fb923c">${pct(st.max_dd_monthly)}</p></div>
          <div><p class="text-xs text-muted mb-0.5">Volatilitet</p>
            <p class="text-lg font-semibold text-slate-300">${pct(st.ann_vol)}</p></div>
          <div><p class="text-xs text-muted mb-0.5">Total</p>
            <p class="text-lg font-semibold" style="${colorVal(st.total)}">${pct(st.total)}</p></div>
        </div>
      </div>`;
  }

  // ── Annual tables — only active strategies ────────────────────────
  const allYears = [...new Set(
    activeAll.flatMap(({ key }) => Object.keys(strategies[key]?.stats?.annual || {}))
  )].sort();

  function annualTable({ key, label, color }) {
    const annual = strategies[key]?.stats?.annual || {};
    const header = `<thead><tr>
      <th class="text-left pb-2 pr-3 text-xs font-semibold" style="color:${color}">${label}</th>
      <th class="text-right pb-2 px-2 text-xs text-muted font-normal">Avk.</th>
      <th class="text-right pb-2 px-2 text-xs text-muted font-normal">Sharpe</th>
      <th class="text-right pb-2 px-2 text-xs text-muted font-normal">Max DD</th>
      <th class="text-right pb-2 px-2 text-xs text-muted font-normal">DD mån</th>
      <th class="text-right pb-2 pl-2 text-xs text-muted font-normal">Vol</th>
    </tr></thead>`;
    const rows = allYears.map(yr => {
      const a = annual[yr];
      return `<tr class="border-t border-border">
        <td class="py-1.5 pr-3 text-xs text-slate-400">${yr}</td>
        <td class="text-right py-1.5 px-2 text-xs font-medium tabular-nums" style="${colorVal(a?.ret)}">${pct(a?.ret)}</td>
        <td class="text-right py-1.5 px-2 text-xs tabular-nums text-slate-300">${a?.sharpe != null ? a.sharpe.toFixed(2) : "—"}</td>
        <td class="text-right py-1.5 px-2 text-xs tabular-nums" style="color:#f43f5e">${pct(a?.max_dd)}</td>
        <td class="text-right py-1.5 px-2 text-xs tabular-nums" style="color:#fb923c">${pct(a?.max_dd_mo)}</td>
        <td class="text-right py-1.5 pl-2 text-xs tabular-nums text-slate-400">${pct(a?.vol)}</td>
      </tr>`;
    }).join("");
    return `<table class="w-full border-collapse">${header}<tbody>${rows}</tbody></table>`;
  }

  let annualPairs = "";
  for (let i = 0; i < activeETF.length; i += 2) {
    annualPairs += `<div class="grid grid-cols-1 xl:grid-cols-2 gap-6${i > 0 ? " mt-6" : ""}">
      ${annualTable(activeETF[i])}
      ${activeETF[i+1] ? annualTable(activeETF[i+1]) : ""}
    </div>`;
  }

  const annualSection = `
    <div class="bg-panel border border-border rounded-lg p-4">
      <p class="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">Per år</p>
      ${annualPairs}
      ${ppmActive ? `<div class="${activeETF.length ? "mt-6 pt-5 border-t border-border" : ""}">
        ${activeETF.length ? '<p class="text-xs font-semibold text-muted uppercase tracking-widest mb-3">PPM Fondtorg</p>' : ""}
        <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">${annualTable(PPM_STRAT)}</div>
      </div>` : ""}
    </div>`;

  // ── Monthly heatmaps ──────────────────────────────────────────────
  const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

  function heatCell(v) {
    if (v == null) return `<td class="text-center p-0.5"><span class="block w-full h-6 rounded text-xs leading-6 text-muted">—</span></td>`;
    const alpha = Math.min(Math.abs(v) / 0.08, 1);
    const bg  = v >= 0 ? `rgba(16,185,129,${(alpha*.7).toFixed(2)})` : `rgba(244,63,94,${(alpha*.7).toFixed(2)})`;
    const txt = v >= 0 ? "#6ee7b7" : "#fca5a5";
    return `<td class="text-center p-0.5"><span class="block w-full h-6 rounded text-xs leading-6 tabular-nums" style="background:${bg};color:${txt}">${pct(v, 0)}</span></td>`;
  }

  function buildHeatmap({ key, label, color }) {
    const monthly = strategies[key]?.stats?.monthly;
    if (!monthly) return "";
    const years = Object.keys(monthly).sort();
    const header = `<tr><th class="text-left pb-1 pr-2 text-xs text-muted font-normal w-12"></th>
      ${MONTHS.map(m => `<th class="text-center pb-1 px-0.5 text-xs text-muted font-normal">${m}</th>`).join("")}
    </tr>`;
    const rows = years.map(yr => {
      const cells = Array.from({length:12}, (_,i) => heatCell(monthly[yr]?.[String(i+1)]));
      return `<tr><td class="pr-2 text-xs text-slate-400 py-0.5">${yr}</td>${cells.join("")}</tr>`;
    }).join("");
    return `<div>
      <p class="text-xs font-semibold mb-2" style="color:${color}">${label} — monthly returns</p>
      <div class="overflow-x-auto">
        <table class="w-full min-w-max border-collapse text-xs">
          <thead>${header}</thead><tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
  }

  const etfHeatmaps = activeETF.map(buildHeatmap).filter(Boolean).join("");
  const ppmHeatmap  = ppmActive ? buildHeatmap(PPM_STRAT) : "";

  const heatmapSection = (etfHeatmaps || ppmHeatmap) ? `
    <div class="bg-panel border border-border rounded-lg p-4 space-y-8">
      ${etfHeatmaps}
      ${ppmHeatmap ? `<div class="${etfHeatmaps ? "pt-5 border-t border-border " : ""}space-y-4">
        ${etfHeatmaps ? '<p class="text-xs font-semibold text-muted uppercase tracking-widest">PPM Fondtorg</p>' : ""}
        ${ppmHeatmap}
      </div>` : ""}
    </div>` : "";

  // ── Historical holdings ───────────────────────────────────────────
  // Build full-name lookups
  const snap = DATA?.config_snapshot || {};
  const etfFullNameMap = {};
  for (const v of Object.values(snap.factor_sleeve || {}))
    etfFullNameMap[v.ticker] = v.nordnet_name || v.ticker;
  for (const v of Object.values(snap.sector_sleeve || {}))
    etfFullNameMap[v.ticker] = v.nordnet_name || v.ticker;
  if (snap.cash_proxy) etfFullNameMap[snap.cash_proxy.ticker] = "Cash";
  const ppmFundNames = DATA?.strategies?.ppm_top3?.fund_names || {};

  function buildAllocHistory({ key, label, color }) {
    const alloc = strategies[key]?.allocation;
    if (!alloc?.dates?.length) return "";
    const isPPM = key === "ppm_top3";
    const rows = [...alloc.dates].reverse().map((date, ri) => {
      const origIdx = alloc.dates.length - 1 - ri;
      const row = alloc.weights[origIdx];
      const holdings = alloc.tickers
        .map((t, i) => ({ t, w: row[i] }))
        .filter(({ w }) => w > 0)
        .sort((a, b) => b.w - a.w);
      const chips = holdings.map(({ t, w }) => {
        const c = isPPM ? (ppmColorMap[t] || color) : (tickerColorMap[t] || "#8591b8");
        const fullName = isPPM ? (ppmFundNames[t] || t) : (etfFullNameMap[t] || tickerLabel(t));
        const shortLabel = isPPM ? t : tickerLabel(t);
        return `<span style="background:${c}22;border:1px solid ${c}44;color:${c};border-radius:3px;padding:2px 7px;font-size:10px;display:inline-block;margin:1px 2px 1px 0" title="${shortLabel}">
          ${fullName} <span style="opacity:.6">${Math.round(w*100)}%</span>
        </span>`;
      }).join("");
      return `<tr class="border-b border-border/30 hover:bg-white/[0.015]">
        <td class="py-1.5 pr-4 text-xs text-slate-500 tabular-nums whitespace-nowrap">${date}</td>
        <td class="py-1.5">${chips}</td>
      </tr>`;
    }).join("");
    return `<div>
      <p class="text-xs font-semibold mb-2" style="color:${color}">${label} — ${alloc.dates.length} rebalanseringar</p>
      <div class="overflow-y-auto" style="max-height:20rem">
        <table class="w-full border-collapse"><tbody>${rows}</tbody></table>
      </div>
    </div>`;
  }

  const allocSections = activeAll.map(buildAllocHistory).filter(Boolean);
  const allocSection = allocSections.length ? `
    <div class="bg-panel border border-border rounded-lg p-4 space-y-6">
      <p class="text-xs font-semibold text-slate-400 uppercase tracking-widest">Historiska innehav</p>
      ${allocSections.join('<div class="pt-2 border-t border-border/40"></div>')}
    </div>` : "";

  // ── Assemble ──────────────────────────────────────────────────────
  const etfCards = activeETF.map(summaryCard).join("");
  const ppmCard  = ppmActive ? summaryCard(PPM_STRAT) : "";

  el.innerHTML = `
    <div class="space-y-5">
      ${etfCards ? `<div class="grid grid-cols-1 xl:grid-cols-2 gap-5">${etfCards}</div>` : ""}
      ${ppmCard ? `<div class="space-y-3">
        <p class="text-xs font-semibold text-muted uppercase tracking-widest px-1">PPM Fondtorg</p>
        ${ppmCard}
      </div>` : ""}
      ${annualSection}
      ${heatmapSection}
      ${allocSection}
    </div>`;
}

// ── Stocks (SP500) page ─────────────────────────────────────────────
const SP500_SAMMANSATT_STRATS = [
  { key: "sp500_sammansatt_top5",  label: "Sammansatt Top-5",  color: "#f97316", group: "sammansatt" },
  { key: "sp500_sammansatt_top7",  label: "Sammansatt Top-7",  color: "#fb923c", group: "sammansatt" },
  { key: "sp500_sammansatt_top10", label: "Sammansatt Top-10", color: "#fdba74", group: "sammansatt" },
];
const STOCK_STRATS = [
  { key: "sp500_pit_top5",  label: "D1-ACCEL Top-5",  color: "#34d399", group: "d1accel" },
  { key: "sp500_pit_top7",  label: "D1-ACCEL Top-7",  color: "#10b981", group: "d1accel" },
  { key: "sp500_pit_top10", label: "D1-ACCEL Top-10", color: "#6ee7b7", group: "d1accel" },
];
function _getSP500Strats(strategies) {
  if (SP500_SAMMANSATT_STRATS.some(s => strategies[s.key])) return SP500_SAMMANSATT_STRATS;
  return STOCK_STRATS;
}

function renderStocksPage() {
  if (!DATA) return;
  const strategies = DATA.strategies || {};
  const primary    = _getSP500Strats(strategies);
  const available  = primary.filter(s => strategies[s.key]);
  if (!available.length) {
    document.getElementById("stocks-stats").innerHTML =
      `<p class="text-xs text-muted italic px-1">Ingen SP500-data tillgänglig — kör engine.py för att generera.</p>`;
    return;
  }
  buildStocksToggles(available);
  renderStocksChart(available);
  renderStocksSignalCards(available);
  renderStocksStats(available);
}

let stocksActiveKeys = new Set(["sp500_sammansatt_top5","sp500_sammansatt_top7","sp500_pit_top7","d1_accel"]);

function buildStocksToggles(available) {
  const container = document.getElementById("stocks-toggles");
  if (!container) return;
  container.innerHTML = "";
  const strategies = DATA?.strategies || {};

  // All toggleable strategy keys: primary + D1-ACCEL comparison + ETF ref
  const compStrats = STOCK_STRATS.filter(s => strategies[s.key]);
  const refs = [
    ...compStrats,
    { key: "d1_accel", label: "D1-accel ETF (ref)", color: "#f59e0b" },
  ];
  const all = [...available, ...refs];

  all.forEach(({ key, label, color }) => {
    if (!strategies[key] && key !== "d1_accel") return;
    if (key !== "d1_accel" && !strategies[key]) return;
    const on  = stocksActiveKeys.has(key);
    const btn = document.createElement("button");
    btn.dataset.key = key;
    btn.className   = "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-all";
    applyToggleStyle(btn, on, color);
    const dot = document.createElement("span");
    dot.className = "w-2 h-2 rounded-full flex-shrink-0";
    dot.style.background = color;
    btn.appendChild(dot);
    btn.appendChild(document.createTextNode(label));
    btn.addEventListener("click", () => {
      if (stocksActiveKeys.has(key)) stocksActiveKeys.delete(key);
      else stocksActiveKeys.add(key);
      applyToggleStyle(btn, stocksActiveKeys.has(key), color);
      renderStocksChart(available);
      renderStocksStats(available);
    });
    container.appendChild(btn);
  });
}

function renderStocksChart(available) {
  if (!stocksChart || !DATA) return;
  stocksChart.resize();
  const strategies = DATA.strategies || {};
  const hasSammansatt = SP500_SAMMANSATT_STRATS.some(s => strategies[s.key] && stocksActiveKeys.has(s.key));
  const startDate  = hasSammansatt ? "2006-01-01" : "2019-10-01";

  function normalize(nav) {
    if (!nav?.length) return [];
    const idx = nav.findIndex(p => p.date >= startDate);
    if (idx === -1) return [];
    const base = nav[idx].value;
    if (!base) return [];
    return nav.slice(idx).map(p => [p.date, +(p.value / base * 100).toFixed(4)]);
  }

  const allKeys = [...SP500_SAMMANSATT_STRATS.map(s => s.key), ...STOCK_STRATS.map(s => s.key), "d1_accel"];
  const series  = allKeys
    .filter(k => stocksActiveKeys.has(k) && strategies[k])
    .map(k => {
      const c = SERIES_CFG[k] || {};
      return {
        name: c.label || k, type: "line",
        data: normalize(strategies[k].nav),
        smooth: false, symbol: "none",
        lineStyle: { color: c.color, width: c.width || 2 },
        itemStyle: { color: c.color },
      };
    });

  // SPY benchmark — prefer inline from sammansatt results
  const spyInline = strategies["sp500_sammansatt_top5"]?.benchmark?.series;
  const spyBench  = DATA.benchmarks?.["S&P 500"];
  const spySeries = spyInline || spyBench?.series;
  if (spySeries) {
    const c = SERIES_CFG["S&P 500"] || { color: "#f97316" };
    series.push({ name: "S&P 500 (SPY)", type: "line", data: normalize(spySeries),
                  smooth: false, symbol: "none",
                  lineStyle: { color: c.color, width: 1.5, type: "dashed" },
                  itemStyle: { color: c.color } });
  }

  stocksChart.setOption({
    backgroundColor: "transparent",
    animation: false,
    grid:  { top: 24, left: 60, right: 20, bottom: 36 },
    xAxis: { type: "time", min: startDate,
             axisLabel: { color: "#8591b8", fontSize: 10 },
             axisLine:  { lineStyle: { color: "#252a3d" } },
             splitLine: { show: false } },
    yAxis: { type: "value",
             axisLabel: { color: "#8591b8", fontSize: 10, formatter: v => v.toFixed(0) },
             axisLine:  { show: false },
             splitLine: { lineStyle: { color: "#252a3d", type: "dashed" } },
             axisTick:  { show: false } },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#1a1e2e",
      borderColor:     "#252a3d",
      textStyle:       { color: "#c9d1e0", fontSize: 11 },
      formatter(params) {
        if (!params?.length) return "";
        const d = new Date(params[0].axisValue).toISOString().slice(0, 10);
        const rows = params.map(p =>
          `<div style="display:flex;justify-content:space-between;gap:20px">
            <span style="color:${p.color}">${p.seriesName}</span>
            <span style="font-variant-numeric:tabular-nums">${(+p.value[1]).toFixed(1)}</span>
          </div>`).join("");
        return `<div style="font-size:11px"><div style="color:#8591b8;margin-bottom:4px">${d}</div>${rows}</div>`;
      },
    },
    legend: { show: false },
    series,
  }, true);
}

function renderStocksSignalCards(available) {
  const el = document.getElementById("stocks-signal-row");
  if (!el) return;
  const strategies  = DATA?.strategies || {};
  const companyInfo = DATA?.sp500_company_info || {};

  el.innerHTML = available.map(({ key, label, color }) => {
    const strat = strategies[key];
    if (!strat?.current_signal) return "";
    const { date, holdings } = strat.current_signal;

    const cashHolding = holdings?.find(h => h.ticker === "CASH" || h.ticker === "__CASH__");
    if (cashHolding) {
      return `<div class="bg-panel border border-border rounded-lg p-4">
        <div class="flex items-center justify-between mb-3">
          <button onclick="openSpecModal('${key}')" class="flex items-center gap-2 group">
            <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
            <span class="text-xs font-semibold tracking-widest uppercase" style="color:${color}">${label}</span>
            <svg class="w-3 h-3 text-muted" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>
            </svg>
          </button>
          <span class="text-xs text-muted">${date}</span>
        </div>
        <p class="text-xs text-muted italic">Kontanter — regimfilter aktivt (SPY &lt; 0)</p>
      </div>`;
    }

    const chips = (holdings || [])
      .filter(h => h.ticker !== "CASH" && h.ticker !== "__CASH__")
      .map(h => {
        const name = companyInfo[h.ticker]?.name || null;
        const pct  = Math.round(h.weight * 100);
        return `<div class="flex items-center justify-between py-1.5 border-b border-border last:border-0">
          <div class="min-w-0">
            <span class="text-xs font-mono font-medium text-slate-300">${h.ticker}</span>
            ${name ? `<span class="text-xs text-muted ml-2">${name}</span>` : ""}
          </div>
          <span class="text-xs text-muted ml-2 shrink-0">${pct}%</span>
        </div>`;
      }).join("");

    return `<div class="bg-panel border border-border rounded-lg p-4">
      <div class="flex items-center justify-between mb-3">
        <button onclick="openSpecModal('${key}')" class="flex items-center gap-2 group">
          <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
          <span class="text-xs font-semibold tracking-widest uppercase" style="color:${color}">${label}</span>
          <svg class="w-3 h-3 text-muted" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>
          </svg>
        </button>
        <span class="text-xs text-muted">${date}</span>
      </div>
      ${chips || '<p class="text-xs text-muted italic">Inga innehav</p>'}
    </div>`;
  }).join("");
}

function renderStocksStats(available) {
  const el = document.getElementById("stocks-stats");
  if (!el) return;
  const strategies = DATA?.strategies || {};

  function pct(v, d = 1) {
    return v == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(d) + "%";
  }
  function colorVal(v) {
    return v == null ? "color:#8591b8" : v >= 0 ? "color:#10b981" : "color:#f43f5e";
  }

  // Reference ETF if toggled
  const refStrats = stocksActiveKeys.has("d1_accel") && strategies["d1_accel"]
    ? [{ key: "d1_accel", label: "D1-accel ETF (ref)", color: "#f59e0b" }]
    : [];
  const activeStrats = [...available.filter(s => stocksActiveKeys.has(s.key)), ...refStrats];

  if (!activeStrats.length) { el.innerHTML = ""; return; }

  function summaryCard({ key, label, color }) {
    const st  = strategies[key]?.stats;
    if (!st) return "";
    const nav  = strategies[key]?.nav || [];
    const period = nav.length
      ? `<span class="text-xs text-muted ml-auto">${nav[0].date} → ${nav[nav.length-1].date}</span>` : "";
    return `
      <div class="bg-panel border border-border rounded-lg p-4">
        <div class="flex items-center gap-2 mb-3 flex-wrap">
          <button onclick="openSpecModal('${key}')" class="flex items-center gap-2 group text-left">
            <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
            <span class="text-xs font-semibold tracking-widest uppercase" style="color:${color}">${label}</span>
            <svg class="w-3 h-3 text-muted" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>
            </svg>
          </button>
          ${period}
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          <div><p class="text-xs text-muted mb-0.5">CAGR</p>
            <p class="text-lg font-semibold" style="${colorVal(st.cagr)}">${pct(st.cagr)}</p></div>
          <div><p class="text-xs text-muted mb-0.5">Sharpe</p>
            <p class="text-lg font-semibold text-slate-300">${st.sharpe?.toFixed(2) ?? "—"}</p></div>
          <div><p class="text-xs text-muted mb-0.5">Max DD <span class="font-normal">(dag)</span></p>
            <p class="text-lg font-semibold" style="color:#f43f5e">${pct(st.max_dd)}</p></div>
          <div><p class="text-xs text-muted mb-0.5">Max DD <span class="font-normal">(mån)</span></p>
            <p class="text-lg font-semibold" style="color:#fb923c">${pct(st.max_dd_monthly)}</p></div>
          <div><p class="text-xs text-muted mb-0.5">Volatilitet</p>
            <p class="text-lg font-semibold text-slate-300">${pct(st.ann_vol)}</p></div>
          <div><p class="text-xs text-muted mb-0.5">Total</p>
            <p class="text-lg font-semibold" style="${colorVal(st.total)}">${pct(st.total)}</p></div>
        </div>
      </div>`;
  }

  // Annual table
  const allYears = [...new Set(
    activeStrats.flatMap(s => Object.keys(strategies[s.key]?.stats?.annual || {}))
  )].sort();

  function annualTable({ key, label, color }) {
    const annual = strategies[key]?.stats?.annual || {};
    const header = `<thead><tr>
      <th class="text-left pb-2 pr-3 text-xs font-semibold" style="color:${color}">${label}</th>
      <th class="text-right pb-2 px-2 text-xs text-muted font-normal">Avk.</th>
      <th class="text-right pb-2 px-2 text-xs text-muted font-normal">Sharpe</th>
      <th class="text-right pb-2 px-2 text-xs text-muted font-normal">Max DD</th>
      <th class="text-right pb-2 px-2 text-xs text-muted font-normal">DD mån</th>
      <th class="text-right pb-2 pl-2 text-xs text-muted font-normal">Vol</th>
    </tr></thead>`;
    const rows = allYears.map(yr => {
      const a = annual[yr];
      return `<tr class="border-t border-border">
        <td class="py-1.5 pr-3 text-xs text-slate-400">${yr}</td>
        <td class="text-right py-1.5 px-2 text-xs font-medium tabular-nums" style="${colorVal(a?.ret)}">${pct(a?.ret)}</td>
        <td class="text-right py-1.5 px-2 text-xs tabular-nums text-slate-300">${a?.sharpe != null ? a.sharpe.toFixed(2) : "—"}</td>
        <td class="text-right py-1.5 px-2 text-xs tabular-nums" style="color:#f43f5e">${pct(a?.max_dd)}</td>
        <td class="text-right py-1.5 px-2 text-xs tabular-nums" style="color:#fb923c">${pct(a?.max_dd_mo)}</td>
        <td class="text-right py-1.5 pl-2 text-xs tabular-nums text-slate-400">${pct(a?.vol)}</td>
      </tr>`;
    }).join("");
    return `<table class="w-full border-collapse">${header}<tbody>${rows}</tbody></table>`;
  }

  // Monthly heatmap
  const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  function heatCell(v) {
    if (v == null) return `<td class="text-center p-0.5"><span class="block w-full h-6 rounded text-xs leading-6 text-muted">—</span></td>`;
    const alpha = Math.min(Math.abs(v) / 0.08, 1);
    const bg  = v >= 0 ? `rgba(16,185,129,${(alpha*.7).toFixed(2)})` : `rgba(244,63,94,${(alpha*.7).toFixed(2)})`;
    const txt = v >= 0 ? "#6ee7b7" : "#fca5a5";
    return `<td class="text-center p-0.5"><span class="block w-full h-6 rounded text-xs leading-6 tabular-nums" style="background:${bg};color:${txt}">${pct(v, 0)}</span></td>`;
  }
  function buildHeatmap({ key, label, color }) {
    const monthly = strategies[key]?.stats?.monthly;
    if (!monthly) return "";
    const years = Object.keys(monthly).sort();
    const header = `<tr><th class="text-left pb-1 pr-2 text-xs text-muted font-normal w-12"></th>
      ${MONTHS.map(m => `<th class="text-center pb-1 px-0.5 text-xs text-muted font-normal">${m}</th>`).join("")}</tr>`;
    const rows = years.map(yr => {
      const cells = Array.from({length:12}, (_,i) => heatCell(monthly[yr]?.[String(i+1)]));
      return `<tr><td class="pr-2 text-xs text-slate-400 py-0.5">${yr}</td>${cells.join("")}</tr>`;
    }).join("");
    return `<div>
      <p class="text-xs font-semibold mb-2" style="color:${color}">${label} — monthly returns</p>
      <div class="overflow-x-auto">
        <table class="w-full min-w-max border-collapse text-xs">
          <thead>${header}</thead><tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
  }

  // Holdings history
  function buildAllocHistory({ key, label, color }) {
    const alloc = strategies[key]?.allocation;
    if (!alloc?.dates?.length) return "";
    const rows = [...alloc.dates].reverse().map((date, ri) => {
      const origIdx  = alloc.dates.length - 1 - ri;
      const row      = alloc.weights[origIdx];
      const holdings = alloc.tickers
        .map((t, i) => ({ t, w: row[i] }))
        .filter(({ w }) => w > 0)
        .sort((a, b) => b.w - a.w);
      const chips = holdings.map(({ t, w }) => {
        const c = t === "CASH" ? "#64748b" : (stockColorMap[t] || color);
        return `<span style="background:${c}22;border:1px solid ${c}44;color:${c};border-radius:3px;padding:2px 7px;font-size:10px;display:inline-block;margin:1px 2px 1px 0;font-family:monospace">
          ${t} <span style="opacity:.6">${Math.round(w*100)}%</span>
        </span>`;
      }).join("");
      return `<tr class="border-b border-border/30 hover:bg-white/[0.015]">
        <td class="py-1.5 pr-4 text-xs text-slate-500 tabular-nums whitespace-nowrap">${date}</td>
        <td class="py-1.5">${chips}</td>
      </tr>`;
    }).join("");
    return `<div>
      <p class="text-xs font-semibold mb-2" style="color:${color}">${label} — ${alloc.dates.length} rebalanseringar</p>
      <div class="overflow-y-auto" style="max-height:20rem">
        <table class="w-full border-collapse"><tbody>${rows}</tbody></table>
      </div>
    </div>`;
  }

  const summaryCards = activeStrats.map(summaryCard).filter(Boolean);
  let annualPairs = "";
  for (let i = 0; i < activeStrats.length; i += 2) {
    annualPairs += `<div class="grid grid-cols-1 xl:grid-cols-2 gap-6${i > 0 ? " mt-6" : ""}">
      ${annualTable(activeStrats[i])}
      ${activeStrats[i+1] ? annualTable(activeStrats[i+1]) : ""}
    </div>`;
  }
  const heatmaps  = activeStrats.map(buildHeatmap).filter(Boolean);
  const histories = activeStrats.map(s => buildAllocHistory(s)).filter(Boolean);

  el.innerHTML = `<div class="space-y-5">
    ${summaryCards.length ? `<div class="grid grid-cols-1 xl:grid-cols-2 gap-5">${summaryCards.join("")}</div>` : ""}
    ${annualPairs ? `<div class="bg-panel border border-border rounded-lg p-4">
      <p class="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">Per år</p>
      ${annualPairs}
    </div>` : ""}
    ${heatmaps.length ? `<div class="bg-panel border border-border rounded-lg p-4 space-y-8">${heatmaps.join("")}</div>` : ""}
    ${histories.length ? `<div class="bg-panel border border-border rounded-lg p-4 space-y-6">
      <p class="text-xs font-semibold text-slate-400 uppercase tracking-widest">Historiska innehav</p>
      ${histories.join('<div class="pt-2 border-t border-border/40"></div>')}
    </div>` : ""}
  </div>`;
}

// ── OMXS page ──────────────────────────────────────────────────────
// Gate-comparison variants (preferred when omxs_gates_results.json is loaded)
const OMXS_SAMMANSATT_STRATS = [
  { key: "omxs_sammansatt_top5",  label: "Sammansatt Top-5",  color: "#f97316", group: "sammansatt" },
  { key: "omxs_sammansatt_top7",  label: "Sammansatt Top-7",  color: "#fb923c", group: "sammansatt" },
  { key: "omxs_sammansatt_top10", label: "Sammansatt Top-10", color: "#fdba74", group: "sammansatt" },
];
const OMXS_GATE_STRATS = [
  { key: "no_gate_top3",   label: "No gate — Top 3",         color: "#8b5cf6", group: "no_gate"   },
  { key: "no_gate_top5",   label: "No gate — Top 5",         color: "#7c3aed", group: "no_gate"   },
  { key: "spy_gate_top3",  label: "SPY gate — Top 3",        color: "#10b981", group: "spy_gate"  },
  { key: "spy_gate_top5",  label: "SPY gate — Top 5",        color: "#059669", group: "spy_gate"  },
  { key: "omxs_gate_top3", label: "OMXS-local gate — Top 3", color: "#3b82f6", group: "omxs_gate" },
  { key: "omxs_gate_top5", label: "OMXS-local gate — Top 5", color: "#2563eb", group: "omxs_gate" },
];
const OMXS_LEGACY_STRATS = [
  { key: "omxs_top3", label: "OMXS — Top 3", color: "#818cf8", group: "legacy" },
  { key: "omxs_top5", label: "OMXS — Top 5", color: "#a78bfa", group: "legacy" },
];
function _getOMXSStrats(strategies) {
  if (OMXS_SAMMANSATT_STRATS.some(s => strategies[s.key])) return OMXS_SAMMANSATT_STRATS;
  if (OMXS_GATE_STRATS.some(s => strategies[s.key])) return OMXS_GATE_STRATS;
  return OMXS_LEGACY_STRATS;
}

let omxsActiveKeys = new Set(["omxs_sammansatt_top5", "omxs_sammansatt_top7", "__omxs30__", "no_gate_top3", "spy_gate_top3", "omxs_gate_top3", "omxs_top3", "d1_accel"]);
let omxsColorMap   = {};

function renderOMXSPage() {
  if (!DATA) return;
  const strategies = DATA.strategies || {};
  const OMXS_STRATS = _getOMXSStrats(strategies);
  const available  = OMXS_STRATS.filter(s => strategies[s.key]);

  if (!available.length) {
    document.getElementById("omxs-stats").innerHTML =
      `<div class="bg-amber-900/20 border border-amber-700/40 rounded-lg p-4 text-xs text-amber-300">
        Ingen OMXS-data tillgänglig. Kör <code>python d1_accel_omxs_gates.py</code> och starta om engine.
       </div>`;
    return;
  }

  // Build omxsColorMap
  omxsColorMap = {};
  let idx = 0;
  const PALETTE = ["#818cf8","#a78bfa","#c4b5fd","#38bdf8","#7dd3fc",
                   "#34d399","#6ee7b7","#f59e0b","#fcd34d","#f43f5e","#fb7185","#64748b"];
  for (const s of available) {
    const alloc = strategies[s.key]?.allocation;
    if (!alloc?.tickers) continue;
    alloc.tickers.forEach((t, i) => {
      if (!(t in omxsColorMap) && t !== "CASH" && alloc.weights.some(row => row[i] > 0))
        omxsColorMap[t] = PALETTE[idx++ % PALETTE.length];
    });
  }

  _buildOMXSToggles(available);
  _renderOMXSChart();
  _renderOMXSHoldings(available);
  _renderOMXSStats(available);
}

function _buildOMXSToggles(available) {
  const el = document.getElementById("omxs-toggles");
  if (!el) return;
  el.innerHTML = "";
  const omxsRefStrats = [
    { key: "d1_accel",    label: "D1-accel ETF (ref)", color: "#f59e0b" },
    { key: "__omxs30__",  label: "OMXS30 index",        color: "#38bdf8" },
  ];
  [...available, ...omxsRefStrats].forEach(({ key, label, color }) => {
    const on  = omxsActiveKeys.has(key);
    const btn = document.createElement("button");
    btn.className = "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-all";
    applyToggleStyle(btn, on, color);
    const dot = document.createElement("span");
    dot.className = "w-2 h-2 rounded-full flex-shrink-0";
    dot.style.background = color;
    btn.appendChild(dot);
    btn.appendChild(document.createTextNode(label));
    btn.addEventListener("click", () => {
      if (omxsActiveKeys.has(key)) omxsActiveKeys.delete(key);
      else omxsActiveKeys.add(key);
      applyToggleStyle(btn, omxsActiveKeys.has(key), color);
      _renderOMXSChart();
      _renderOMXSStats(available);
    });
    el.appendChild(btn);
  });
}

function _renderOMXSChart() {
  if (!omxsChart || !DATA) return;
  omxsChart.resize();
  const strategies = DATA.strategies || {};
  const hasSammansatt = OMXS_SAMMANSATT_STRATS.some(s => strategies[s.key] && omxsActiveKeys.has(s.key));
  const startDate  = hasSammansatt ? "2006-01-01" : "2019-10-01";

  function normalize(nav) {
    if (!nav?.length) return [];
    const idx = nav.findIndex(p => p.date >= startDate);
    if (idx === -1) return [];
    const base = nav[idx].value;
    return base ? nav.slice(idx).map(p => [p.date, +(p.value / base * 100).toFixed(4)]) : [];
  }

  const allOMXSKeys = [...OMXS_SAMMANSATT_STRATS.map(s => s.key), ...OMXS_GATE_STRATS.map(s => s.key), ...OMXS_LEGACY_STRATS.map(s => s.key), "d1_accel"];
  const series = allOMXSKeys
    .filter(k => omxsActiveKeys.has(k) && strategies[k])
    .map(k => {
      const c = SERIES_CFG[k] || {};
      return { name: c.label || k, type: "line", data: normalize(strategies[k].nav),
               smooth: false, symbol: "none",
               lineStyle: { color: c.color, width: c.width || 2 },
               itemStyle: { color: c.color } };
    });

  // OMXS30 benchmark — always add, respect toggle
  const sammansattBench = strategies["omxs_sammansatt_top5"]?.benchmark?.series;
  const bm = DATA.benchmarks?.["OMXS30"];
  const bmSeries = sammansattBench || bm?.series;
  if (bmSeries && omxsActiveKeys.has("__omxs30__")) {
    series.push({ name: "OMXS30 index", type: "line",
                  data: normalize(bmSeries), smooth: false, symbol: "none",
                  lineStyle: { color: "#38bdf8", width: 1.5, type: "dashed" },
                  itemStyle: { color: "#38bdf8" } });
  }

  omxsChart.setOption({
    backgroundColor: "transparent", animation: false,
    grid:  { top: 24, left: 60, right: 20, bottom: 36 },
    xAxis: { type: "time", min: startDate,
             axisLabel: { color: "#8591b8", fontSize: 10 },
             axisLine:  { lineStyle: { color: "#252a3d" } },
             splitLine: { show: false } },
    yAxis: { type: "value",
             axisLabel: { color: "#8591b8", fontSize: 10, formatter: v => v.toFixed(0) },
             axisLine:  { show: false },
             splitLine: { lineStyle: { color: "#252a3d", type: "dashed" } },
             axisTick:  { show: false } },
    tooltip: {
      trigger: "axis", backgroundColor: "#1a1e2e",
      borderColor: "#252a3d", textStyle: { color: "#c9d1e0", fontSize: 11 },
      formatter(params) {
        if (!params?.length) return "";
        const d = new Date(params[0].axisValue).toISOString().slice(0, 10);
        const rows = params.map(p =>
          `<div style="display:flex;justify-content:space-between;gap:20px">
            <span style="color:${p.color}">${p.seriesName}</span>
            <span style="font-variant-numeric:tabular-nums">${(+p.value[1]).toFixed(1)}</span>
           </div>`).join("");
        return `<div style="font-size:11px"><div style="color:#8591b8;margin-bottom:4px">${d}</div>${rows}</div>`;
      },
    },
    legend: { show: false }, series,
  }, true);
}

function _renderOMXSHoldings(available) {
  const el = document.getElementById("omxs-signal-row");
  if (!el) return;
  const strategies  = DATA?.strategies || {};
  const companyInfo = DATA?.omxs_company_info || {};
  const isSammansatt = available.some(s => s.key.startsWith("omxs_sammansatt"));

  el.innerHTML = available.map(({ key, label, color }) => {
    const cs = strategies[key]?.current_signal;
    if (!cs) return "";
    const cashHolding = cs.holdings?.find(h => h.ticker === "CASH" || h.ticker === "__CASH__");
    if (cashHolding) {
      return `<div class="bg-panel border border-border rounded-lg p-4">
        <div class="flex items-center justify-between mb-3">
          <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
          <span class="text-xs font-semibold tracking-widest uppercase" style="color:${color}">${label}</span>
          <span class="text-xs text-muted">${cs.date}</span>
        </div>
        <p class="text-xs text-muted italic">Kontanter — absolut momentum negativt</p>
      </div>`;
    }
    const chips = (cs.holdings || [])
      .filter(h => h.ticker !== "CASH")
      .map(h => {
        const name = companyInfo[h.ticker]?.name || h.ticker;
        const displayName = isSammansatt ? name : h.ticker.replace(".ST","");
        const pct = Math.round(h.weight * 100);
        return `<div class="flex items-center justify-between py-1.5 border-b border-border last:border-0">
          <div class="min-w-0">
            <span class="text-xs font-mono font-medium text-slate-300">${h.ticker.replace(".ST","")}</span>
            ${isSammansatt && name !== h.ticker ? `<span class="text-xs text-muted ml-2 truncate">${name}</span>` : ""}
          </div>
          <span class="text-xs text-muted ml-2 shrink-0">${pct}%</span>
        </div>`;
      }).join("");
    return `<div class="bg-panel border border-border rounded-lg p-4">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
          <span class="text-xs font-semibold tracking-widest uppercase" style="color:${color}">${label}</span>
        </div>
        <span class="text-xs text-muted">${cs.date}</span>
      </div>
      ${!isSammansatt ? `<div class="mb-2 px-2 py-1 bg-amber-900/20 border border-amber-700/30 rounded text-xs text-amber-400">
        ⚠ UNVALIDATED — survivorship bias
      </div>` : ""}
      ${chips || '<p class="text-xs text-muted italic">Inga innehav</p>'}
    </div>`;
  }).join("");
}

function _renderOMXSStats(available) {
  const el = document.getElementById("omxs-stats");
  if (!el) return;
  const strategies = DATA?.strategies || {};

  function pct(v, d = 1) {
    return v == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(d) + "%";
  }
  function colorVal(v) {
    return v == null ? "color:#8591b8" : v >= 0 ? "color:#10b981" : "color:#f43f5e";
  }

  const refStrats = omxsActiveKeys.has("d1_accel") && strategies["d1_accel"]
    ? [{ key: "d1_accel", label: "D1-accel ETF (ref)", color: "#f59e0b" }] : [];
  const activeStrats = [...available.filter(s => omxsActiveKeys.has(s.key)), ...refStrats];
  if (!activeStrats.length) { el.innerHTML = ""; return; }

  function summaryCard({ key, label, color }) {
    const st = strategies[key]?.stats;
    if (!st) return "";
    return `<div class="bg-panel border border-border rounded-lg p-4">
      <div class="flex items-center gap-2 mb-3 flex-wrap">
        <button onclick="openSpecModal('${key}')" class="flex items-center gap-2 group text-left">
          <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
          <span class="text-xs font-semibold tracking-widest uppercase" style="color:${color}">${label}</span>
          <svg class="w-3 h-3 text-muted" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>
          </svg>
        </button>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <div><p class="text-xs text-muted mb-0.5">CAGR</p>
          <p class="text-lg font-semibold" style="${colorVal(st.cagr)}">${pct(st.cagr)}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Sharpe</p>
          <p class="text-lg font-semibold text-slate-300">${st.sharpe?.toFixed(2) ?? "—"}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Max DD</p>
          <p class="text-lg font-semibold" style="color:#f43f5e">${pct(st.max_dd)}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Volatilitet</p>
          <p class="text-lg font-semibold text-slate-300">${pct(st.ann_vol)}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Total</p>
          <p class="text-lg font-semibold" style="${colorVal(st.total)}">${pct(st.total)}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Sharpe (ref S&amp;P)</p>
          <p class="text-lg font-semibold" style="color:#f59e0b">${(strategies["sp500_pit_top7"]?.stats?.sharpe ?? 0).toFixed(2)}</p></div>
      </div>
    </div>`;
  }

  const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  function heatCell(v) {
    if (v == null) return `<td class="text-center p-0.5"><span class="block w-full h-6 rounded text-xs leading-6 text-muted">—</span></td>`;
    const alpha = Math.min(Math.abs(v)/0.08, 1);
    const bg = v>=0 ? `rgba(16,185,129,${(alpha*.7).toFixed(2)})` : `rgba(244,63,94,${(alpha*.7).toFixed(2)})`;
    const txt = v>=0 ? "#6ee7b7" : "#fca5a5";
    return `<td class="text-center p-0.5"><span class="block w-full h-6 rounded text-xs leading-6 tabular-nums" style="background:${bg};color:${txt}">${pct(v,0)}</span></td>`;
  }
  function heatmap({ key, label, color }) {
    const mo = strategies[key]?.stats?.monthly;
    if (!mo) return "";
    const years = Object.keys(mo).sort();
    const header = `<tr><th class="text-left pb-1 pr-2 text-xs text-muted font-normal w-12"></th>
      ${MONTHS.map(m=>`<th class="text-center pb-1 px-0.5 text-xs text-muted font-normal">${m}</th>`).join("")}</tr>`;
    const rows = years.map(yr => {
      const cells = Array.from({length:12},(_,i)=>heatCell(mo[yr]?.[String(i+1)]));
      return `<tr><td class="pr-2 text-xs text-slate-400 py-0.5">${yr}</td>${cells.join("")}</tr>`;
    }).join("");
    return `<div><p class="text-xs font-semibold mb-2" style="color:${color}">${label}</p>
      <div class="overflow-x-auto"><table class="w-full min-w-max border-collapse text-xs">
        <thead>${header}</thead><tbody>${rows}</tbody></table></div></div>`;
  }

  function annualTable({ key, label, color }) {
    const annual = strategies[key]?.stats?.annual || {};
    const years  = Object.keys(annual).sort();
    const header = `<thead><tr>
      <th class="text-left pb-2 pr-3 text-xs font-semibold" style="color:${color}">${label}</th>
      <th class="text-right pb-2 px-2 text-xs text-muted font-normal">Avk.</th>
      <th class="text-right pb-2 px-2 text-xs text-muted font-normal">Sharpe</th>
      <th class="text-right pb-2 pl-2 text-xs text-muted font-normal">Max DD</th>
    </tr></thead>`;
    const rows = years.map(yr => {
      const a = annual[yr];
      return `<tr class="border-t border-border">
        <td class="py-1.5 pr-3 text-xs text-slate-400">${yr}</td>
        <td class="text-right py-1.5 px-2 text-xs font-medium tabular-nums" style="${colorVal(a?.ret)}">${pct(a?.ret)}</td>
        <td class="text-right py-1.5 px-2 text-xs tabular-nums text-slate-300">${a?.sharpe != null ? a.sharpe.toFixed(2) : "—"}</td>
        <td class="text-right py-1.5 pl-2 text-xs tabular-nums" style="color:#f43f5e">${pct(a?.max_dd)}</td>
      </tr>`;
    }).join("");
    return `<table class="w-full border-collapse">${header}<tbody>${rows}</tbody></table>`;
  }

  const isSammansatt = available.some(s => s.key.startsWith("omxs_sammansatt"));
  const companyInfo  = DATA?.omxs_company_info || {};

  const summaries = activeStrats.map(summaryCard).filter(Boolean);
  const heatmaps  = available.filter(s => omxsActiveKeys.has(s.key)).map(heatmap).filter(Boolean);
  let annualPairs = "";
  for (let i = 0; i < activeStrats.length; i += 2) {
    annualPairs += `<div class="grid grid-cols-1 xl:grid-cols-2 gap-6${i>0?" mt-6":""}">
      ${annualTable(activeStrats[i])}${activeStrats[i+1] ? annualTable(activeStrats[i+1]) : ""}
    </div>`;
  }

  // ── Sammansatt holdings history ─────────────────────────────────────
  function _sammansattHistory() {
    const top5key = "omxs_sammansatt_top5";
    const log = strategies[top5key]?.alloc_log;
    if (!log?.length) return "";

    // Build sorted list of all tickers that appear (not CASH)
    const tickerSet = new Set();
    log.forEach(e => Object.keys(e.holdings).forEach(t => { if (t !== "CASH") tickerSet.add(t); }));
    const allTickers = [...tickerSet].sort();

    // Unique colors per ticker
    const PALETTE = ["#f97316","#fb923c","#fdba74","#a78bfa","#818cf8","#38bdf8",
                     "#34d399","#6ee7b7","#f59e0b","#fcd34d","#f43f5e","#fb7185",
                     "#c4b5fd","#7dd3fc","#86efac","#fde68a","#fda4af","#cbd5e1"];
    const tColor = {};
    allTickers.forEach((t, i) => { tColor[t] = PALETTE[i % PALETTE.length]; });

    const rows = [...log].reverse().map(e => {
      const held = Object.entries(e.holdings).filter(([t]) => t !== "CASH");
      const isCash = held.length === 0;
      const dateStr = e.date.slice(0,7);
      if (isCash) {
        return `<tr class="border-t border-border/40 hover:bg-white/[0.02]">
          <td class="py-1.5 pr-3 text-xs text-slate-500 font-mono whitespace-nowrap">${dateStr}</td>
          <td colspan="2" class="text-xs text-slate-600 italic py-1.5">kontanter</td>
        </tr>`;
      }
      const chips = held.map(([t, w]) => {
        const name = companyInfo[t]?.name || t;
        const tk   = t.replace(".ST","");
        const col  = tColor[t] || "#8591b8";
        return `<span class="inline-flex items-center gap-1 mr-1.5 mb-0.5">
          <span class="w-1.5 h-1.5 rounded-full shrink-0" style="background:${col}"></span>
          <span class="text-xs font-mono font-medium" style="color:${col}">${tk}</span>
          <span class="text-xs text-slate-500">${(w*100).toFixed(0)}%</span>
        </span>`;
      }).join("");
      const names = held.map(([t]) => (companyInfo[t]?.name || t).split(" ").slice(0,2).join(" ")).join(", ");
      return `<tr class="border-t border-border/40 hover:bg-white/[0.02]">
        <td class="py-1.5 pr-3 text-xs text-slate-500 font-mono whitespace-nowrap align-top pt-2">${dateStr}</td>
        <td class="py-1 pr-2 align-top">${chips}</td>
        <td class="py-1.5 text-xs text-slate-600 align-top hidden xl:table-cell whitespace-nowrap">${names}</td>
      </tr>`;
    }).join("");

    return `<div class="bg-panel border border-border rounded-lg p-4">
      <div class="flex items-center justify-between mb-3">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-widest">
          Innehavshistorik — Sammansatt Top-5 (2006–idag)
        </p>
        <span class="text-xs text-slate-600">${log.length} månader</span>
      </div>
      <div class="overflow-y-auto max-h-[520px] pr-1">
        <table class="w-full border-collapse">
          <thead class="sticky top-0 bg-panel z-10">
            <tr>
              <th class="text-left pb-2 pr-3 text-xs text-muted font-normal w-16">Datum</th>
              <th class="text-left pb-2 pr-2 text-xs text-muted font-normal">Innehav</th>
              <th class="text-left pb-2 text-xs text-muted font-normal hidden xl:table-cell">Bolag</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
  }

  // ── Gate-comparison note (legacy) ──────────────────────────────────
  const hasGateData = !isSammansatt && (strategies["no_gate_top3"] || strategies["spy_gate_top3"] || strategies["omxs_gate_top3"]);
  const corrNote = hasGateData ? (() => {
    const ng = strategies["no_gate_top5"]?.stats  || {};
    const sp = strategies["spy_gate_top5"]?.stats  || {};
    const om = strategies["omxs_gate_top5"]?.stats || {};
    const p  = v => v != null ? `${v >= 0 ? "+" : ""}${(v*100).toFixed(1)}%` : "—";
    return `<div class="bg-panel border border-amber-700/30 rounded-lg p-4">
      <p class="text-xs font-semibold text-amber-400 mb-2">Gate-isoleringsanalys (UNVALIDATED — survivorship bias)</p>
      <div class="grid grid-cols-3 gap-3 text-xs">
        <div class="bg-surface/60 rounded p-2">
          <p class="text-muted mb-1 font-medium">Ingen gate</p>
          <p>Sharpe: <span class="text-slate-300">${ng.sharpe?.toFixed(2) || "—"}</span></p>
          <p>CAGR: <span class="text-slate-300">${p(ng.cagr)}</span></p>
        </div>
        <div class="bg-surface/60 rounded p-2">
          <p class="text-muted mb-1 font-medium">SPY-gate</p>
          <p>Sharpe: <span class="text-slate-300">${sp.sharpe?.toFixed(2) || "—"}</span></p>
          <p>CAGR: <span class="text-slate-300">${p(sp.cagr)}</span></p>
        </div>
        <div class="bg-surface/60 rounded p-2">
          <p class="text-muted mb-1 font-medium">XACT-OMXS30 gate</p>
          <p>Sharpe: <span class="text-slate-300">${om.sharpe?.toFixed(2) || "—"}</span></p>
          <p>CAGR: <span class="text-slate-300">${p(om.cagr)}</span></p>
        </div>
      </div>
    </div>`;
  })() : "";

  el.innerHTML = `<div class="space-y-5">
    ${summaries.length ? `<div class="grid grid-cols-1 xl:grid-cols-2 gap-5">${summaries.join("")}</div>` : ""}
    ${isSammansatt ? _sammansattHistory() : corrNote}
    ${annualPairs ? `<div class="bg-panel border border-border rounded-lg p-4">
      <p class="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">Per år</p>
      ${annualPairs}
    </div>` : ""}
    ${heatmaps.length ? `<div class="bg-panel border border-border rounded-lg p-4 space-y-8">${heatmaps.join("")}</div>` : ""}
  </div>`;
}

// ── Settings ───────────────────────────────────────────────────────
async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    CONFIG = await res.json();
    renderSettingsForm();
  } catch (e) {
    document.getElementById("settings-form").innerHTML =
      `<p class="text-xs text-red-400">Failed to load config: ${e.message}</p>`;
  }
}

function renderSettingsForm() {
  const form = document.getElementById("settings-form");
  if (!CONFIG) return;

  function sleeveTable(sleeveKey, title) {
    const sleeve = CONFIG[sleeveKey] || {};
    const rows = Object.entries(sleeve).map(([label, info]) => `
      <tr class="border-b border-border">
        <td class="py-2 pr-4 text-xs font-medium text-slate-400 w-28 pl-4">${label}</td>
        <td class="py-2 pr-3">
          <input class="w-full bg-surface border border-border rounded px-2 py-1 text-xs text-slate-300 focus:outline-none focus:border-accent"
                 data-sleeve="${sleeveKey}" data-label="${label}" data-field="ticker"
                 value="${info.ticker || ""}" placeholder="IITU.L"/>
        </td>
        <td class="py-2 pr-3">
          <input class="w-full bg-surface border border-border rounded px-2 py-1 text-xs text-slate-300 focus:outline-none focus:border-accent"
                 data-sleeve="${sleeveKey}" data-label="${label}" data-field="nordnet_name"
                 value="${info.nordnet_name || ""}" placeholder="Fund name"/>
        </td>
        <td class="py-2 pr-4">
          <input class="w-40 bg-surface border border-border rounded px-2 py-1 text-xs font-mono text-slate-300 focus:outline-none focus:border-accent"
                 data-sleeve="${sleeveKey}" data-label="${label}" data-field="isin"
                 value="${info.isin || ""}" placeholder="SE0012345678"/>
        </td>
      </tr>`).join("");
    return `
      <div>
        <p class="text-xs font-semibold text-muted uppercase tracking-widest mb-2">${title}</p>
        <div class="bg-panel border border-border rounded-lg overflow-hidden">
          <table class="w-full">
            <thead>
              <tr class="border-b border-border">
                <th class="text-left text-xs text-muted py-2 pl-4 w-28">Slot</th>
                <th class="text-left text-xs text-muted py-2 pr-3">Ticker</th>
                <th class="text-left text-xs text-muted py-2 pr-3">Nordnet Proxy Name</th>
                <th class="text-left text-xs text-muted py-2 pr-4">ISIN</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`;
  }

  form.innerHTML = sleeveTable("factor_sleeve", "Factor Sleeve") + sleeveTable("sector_sleeve", "Sector Sleeve");

  form.querySelectorAll("input[data-sleeve]").forEach(inp => {
    inp.addEventListener("input", () => {
      const { sleeve, label, field } = inp.dataset;
      if (CONFIG[sleeve]?.[label]) CONFIG[sleeve][label][field] = inp.value;
    });
  });
}

async function saveConfig() {
  if (!CONFIG) return;
  const btn     = document.getElementById("save-btn");
  const label   = document.getElementById("save-label");
  const spinner = document.getElementById("save-spinner");
  const status  = document.getElementById("save-status");

  btn.disabled = true;
  label.textContent = "Saving…";
  spinner.classList.remove("hidden");
  status.textContent = "";

  try {
    const prevTs = DATA?.generated_at || "";
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(CONFIG),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || res.status);
    }
    status.textContent = "Saved. Waiting for engine…";
    label.textContent  = "Recalculating…";
    await pollForNewData(prevTs, 120_000);
    status.textContent = "Done — reloading…";
    setTimeout(() => location.reload(), 800);
  } catch (e) {
    status.textContent = "Error: " + e.message;
    status.style.color = "#f43f5e";
  } finally {
    btn.disabled = false;
    label.textContent = "Save & Recalculate";
    spinner.classList.add("hidden");
  }
}

// ── Fund mapping data ──────────────────────────────────────────────
const FUND_MAPPINGS = [
  // ── FACTOR SLEEVE ────────────────────────────────────────────────
  {
    sleeve: "Faktor", label: "USA MOM", ticker: "QDVA.DE", isin: "IE00BD1F4N50",
    name: "iShares Edge MSCI USA Momentum Factor UCITS ETF",
    nordnet_etf: { note: "Exakt match (Xetra)", quality: "exact" },
    nordnet_fund: { name: "Handelsbanken Amerika Tema A1 SEK", note: "~97% USA, tillväxt/momentum-profil", fee: "1.60%", quality: "partial" },
    ppm: { name: "Öhman Global Growth A", sub: "~65% USA, fokus tillväxt/innovation — implicit momentum", nr: "163923", quality: "partial",
           alt: "Storebrand Global Multifactor A (162099) — enda multifaktorfonden i PPM" },
  },
  {
    sleeve: "Faktor", label: "USA QUAL", ticker: "QDVB.DE", isin: "IE00BD1F4L38",
    name: "iShares Edge MSCI USA Quality Factor UCITS ETF",
    nordnet_etf: { note: "Exakt match (Xetra)", quality: "exact" },
    nordnet_fund: { name: "Länsförsäkringar USA Aktiv A", isin: "SE0005191982", note: "Explicit kvalitetsmandat: hög ROE, låg skuldsättning", fee: "1.60%", quality: "partial" },
    ppm: { name: "Länsförsäkringar USA Aktiv A", sub: "Målbolag med 'hög kvalitet till attraktiv värdering'", nr: "456475", quality: "partial",
           alt: "Fidelity America Fund A (850776) — kvalitet/värde-blend" },
  },
  {
    sleeve: "Faktor", label: "USA VAL", ticker: "QDVI.DE", isin: "IE00BD1F4M44",
    name: "iShares Edge MSCI USA Value Factor UCITS ETF",
    nordnet_etf: { note: "Exakt match (Xetra)", quality: "exact" },
    nordnet_fund: { name: "BGF US Basic Value A2", note: "Explicita värdeaktier USA large-cap", fee: "~1.50%", quality: "good" },
    ppm: { name: "BlackRock – US Basic Value A2", sub: "Explicit värdemandat, USA large-cap", nr: "768556", quality: "good",
           alt: "Fidelity America Fund A (850776)" },
  },
  {
    sleeve: "Faktor", label: "USA SMALL", ticker: "SXRG.DE", isin: "IE00B3VWM098",
    name: "iShares MSCI USA Small Cap ESG Enhanced CTB UCITS ETF",
    nordnet_etf: { note: "Exakt match, ESG-variant (Xetra)", quality: "exact" },
    nordnet_fund: { name: "Carnegie US Small & Micro Cap", note: "Aktiv, US small/micro-cap, koncentrerad portfölj", fee: "1.60%", quality: "good" },
    ppm: { name: "SEB Nordamerikafond Små och Medelstora Bolag A", sub: "Aktiv förvaltning, US small/mid-cap", nr: "916354", quality: "good",
           alt: "BL – American Small & Mid Caps B (285990)" },
  },
  {
    sleeve: "Faktor", label: "EUR MOM", ticker: "CEMR.DE", isin: "IE00BQN1K786",
    name: "iShares Edge MSCI Europe Momentum Factor UCITS ETF",
    nordnet_etf: { note: "Exakt match (Xetra)", quality: "exact" },
    nordnet_fund: { name: "MS INVF Europe Opportunity A", isin: "LU1387591305", note: "Europa tillväxt/momentum — ASML, Moncler, Spotify", fee: "1.74%", quality: "partial" },
    ppm: { name: "Swedbank Robur Europafond A", sub: "Europa tillväxtbolag, implicit momentumtilt", nr: "160267", quality: "partial",
           alt: "Storebrand Global Multifactor A (162099) — inkl. Europa momentum" },
  },
  {
    sleeve: "Faktor", label: "EUR QUAL", ticker: "CEMQ.DE", isin: "IE00BQN1K562",
    name: "iShares Edge MSCI Europe Quality Factor UCITS ETF",
    nordnet_etf: { note: "Exakt match (Xetra)", quality: "exact" },
    nordnet_fund: { name: "Comgest Growth Europe", isin: "IE00B0XJXQ01", note: "Renodlad kvalitet/tillväxt Europa — Comgest är kvalitetsfokuserade förvaltare", fee: "~1.60%", quality: "good" },
    ppm: { name: "JPMorgan Europe Sustainable Equity Fund", sub: "FTN-godkänd, kvalitet/tillväxt-mandat Europa", nr: "124438", quality: "partial",
           alt: "SEB Europe Equity Fund (988600) — FTN-godkänd" },
  },
  {
    sleeve: "Faktor", label: "EUR VAL", ticker: "CEMS.DE", isin: "IE00BQN1K901",
    name: "iShares Edge MSCI Europe Value Factor UCITS ETF",
    nordnet_etf: { note: "Exakt match (Xetra)", quality: "exact" },
    nordnet_fund: { name: "Fidelity European Growth A-Dis-EUR", note: "Europa värdebolag/blend, bred exponering", fee: "~1.90%", quality: "partial" },
    ppm: { name: "AMF Aktiefond Europa", sub: "Bred Europa, låg avgift, värdeinriktad förvaltning", nr: "538462", quality: "partial",
           alt: "abrdn European Sustainable Equity I Acc EUR (952770)" },
  },
  {
    sleeve: "Faktor", label: "EUR SMALL", ticker: "XXSC.DE", isin: "LU0322253906",
    name: "Xtrackers MSCI Europe Small Cap UCITS ETF 1C",
    nordnet_etf: { note: "Exakt match (Xetra)", quality: "exact" },
    nordnet_fund: { name: "SEB Europafond Småbolag", isin: "SE0000433252", note: "Aktiv, europeisk small-cap med kvalitetstilt", fee: "1.51%", quality: "good" },
    ppm: { name: "Lannebo Europa Småbolag A", sub: "Aktiv, europeisk small-cap", nr: "182759", quality: "good",
           alt: "SEB Europafond Småbolag (556589)" },
  },
  // ── SECTOR SLEEVE ────────────────────────────────────────────────
  {
    sleeve: "Sektor", label: "IT", ticker: "QDVE.DE", isin: "IE00B3WJKG14",
    name: "iShares S&P 500 Information Technology Sector UCITS ETF",
    nordnet_etf: { note: "Exakt match (Xetra)", quality: "exact" },
    nordnet_fund: { name: "Nordnet Teknologi Index", note: "Dedikerad teknikindexfond, Technology Sector Equity, 5★ Morningstar — 4× billigare än aktiva alternativ", fee: "0.40%", quality: "good",
                   alt: "DNB Teknologi S (1.20%) — aktiv förvaltning, mer global diversifiering" },
    ppm: { name: "Swedbank Robur Technology A", sub: "US-tung tech, nära S&P 500 IT-profil", nr: "283408", quality: "good",
           alt: "BlackRock World Technology A2 (446088)" },
  },
  {
    sleeve: "Sektor", label: "ENERGY", ticker: "QDVF.DE", isin: "IE00B42NKQ00",
    name: "iShares S&P 500 Energy Sector UCITS ETF",
    nordnet_etf: { note: "Exakt match (Xetra)", quality: "exact" },
    nordnet_fund: { name: "BGF World Energy A2", isin: "LU0122376428", note: "Global energi, ~57% USA — bästa tillgängliga konventionella fond", fee: "2.06%", quality: "partial" },
    ppm: { name: "BlackRock – World Energy A2", sub: "Global energi, ~57% USA — bäst tillgängligt i PPM", nr: "517748", quality: "partial",
           alt: "BGF Natural Resources Growth & Income A2 (536806) — bredare" },
  },
  {
    sleeve: "Sektor", label: "HEALTHCARE", ticker: "QDVG.DE", isin: "IE00B43HR379",
    name: "iShares S&P 500 Health Care Sector UCITS ETF",
    nordnet_etf: { note: "Exakt match (Xetra)", quality: "exact" },
    nordnet_fund: { name: "DNB Health Care S", note: "Global hälsovård, bred sektorexponering", fee: "~1.20%", quality: "good",
                   alt: "C WorldWide Healthcare Select 1A (PPM 443895)" },
    ppm: { name: "Handelsbanken Hälsovård Tema A1", sub: "Global hälsovård, prisvinnande, bred matchning", nr: "644005", quality: "good",
           alt: "DNB Health Care S (255001)" },
  },
  {
    sleeve: "Sektor", label: "CONS DISC", ticker: "QDVK.DE", isin: "IE00B4MCHD36",
    name: "iShares S&P 500 Consumer Discretionary Sector UCITS ETF",
    nordnet_etf: { note: "Exakt match (Xetra)", quality: "exact" },
    nordnet_fund: { name: "FF – Global Consumer Brands A-Dis-EUR", isin: "LU0114721508", note: "Blandar Cons.Disc + Cons.Stap (Amazon, Netflix, L'Oréal, Nestlé)", fee: "1.90%", quality: "partial" },
    ppm: { name: "Ingen nära matchning i PPM", sub: "PPM saknar dedikerad Consumer Discretionary-fond", nr: null, quality: "none",
           alt: "Seligson Global Top 25 Brands A (479550) — 41% consumer discretionary (Amazon, LVMH, Adidas)" },
  },
  {
    sleeve: "Sektor", label: "INDUSTRIALS", ticker: "2B7C.DE", isin: "IE00B4LN9N13",
    name: "iShares S&P 500 Industrials Sector UCITS ETF",
    nordnet_etf: { note: "Exakt match (Xetra)", quality: "exact" },
    nordnet_fund: { name: "Fidelity Global Industrials A-Dis-EUR", isin: "LU0114722902", note: "Dedikerad global industrifond — flygplan, försvar, maskiner, konstruktion (4 ★ Morningstar)", fee: "1.90%", quality: "good" },
    ppm: { name: "Ingen nära matchning i PPM", sub: "PPM saknar dedikerad Industrials-fond (ej upphandlad av FTN)", nr: null, quality: "none",
           alt: "Storebrand Global Multifactor A (162099) — enda multifaktorfonden i PPM, ~10% industrials" },
  },
  {
    sleeve: "Sektor", label: "CONS STAP", ticker: "2B7D.DE", isin: "IE00B40B8R38",
    name: "iShares S&P 500 Consumer Staples Sector UCITS ETF",
    nordnet_etf: { note: "Exakt match (Xetra)", quality: "exact" },
    nordnet_fund: { name: "FF – Global Consumer Brands A-Dis-EUR", isin: "LU0114721508", note: "Blandar Cons.Disc + Cons.Stap — Nestlé, P&G, Unilever, Walmart", fee: "1.90%", quality: "partial" },
    ppm: { name: "Seligson Global Top 25 Brands A", sub: "38% consumer staples (Coca-Cola, PepsiCo, Nestlé) + 41% discretionary — närmaste i PPM", nr: "479550", quality: "partial",
           alt: "Ingen renodlad consumer staples-fond i PPM" },
  },
  {
    sleeve: "Sektor", label: "MATERIALS", ticker: "2B7B.DE", isin: "IE00B4MKCJ84",
    name: "iShares S&P 500 Materials Sector UCITS ETF",
    nordnet_etf: { note: "Exakt match (Xetra)", quality: "exact" },
    nordnet_fund: { name: "BGF Natural Resources A2", note: "Bredare än ren gruvfond — energi+metaller+jordbruk, ~70% materialsrelaterat", fee: "1.82%", quality: "partial",
                   alt: "BGF World Mining A2 — smalare, ren gruvfokus" },
    ppm: { name: "BlackRock – World Mining A2", sub: "Metaller/gruvor, saknar kemikalier", nr: "481911", quality: "partial",
           alt: "BGF Natural Resources Growth & Income A2 (536806) — bredare" },
  },
];

function renderFundsTable() {
  const el = document.getElementById("funds-table");
  if (!el || el.dataset.rendered) return;
  el.dataset.rendered = "1";

  const qualityBadge = (q) => {
    if (q === "exact")   return `<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-emerald-900/40 text-emerald-400">Direkt</span>`;
    if (q === "good")    return `<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-blue-900/40 text-blue-400">Bra matchning</span>`;
    if (q === "partial") return `<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-amber-900/40 text-amber-400">Partiell</span>`;
    return `<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-slate-800 text-muted">Ingen matchning</span>`;
  };

  const sleeveColor = { "Faktor": "#5b6ef5", "Sektor": "#10b981" };

  let html = `
    <div class="text-xs text-muted mb-3 flex flex-wrap gap-x-6 gap-y-1">
      <span class="flex items-center gap-1.5"><span class="inline-block w-2 h-2 rounded-full bg-emerald-400"></span>Direkt — exakt ETF tillgänglig</span>
      <span class="flex items-center gap-1.5"><span class="inline-block w-2 h-2 rounded-full bg-blue-400"></span>Bra matchning — nära index/tema</span>
      <span class="flex items-center gap-1.5"><span class="inline-block w-2 h-2 rounded-full bg-amber-400"></span>Partiell — delvis överlapp</span>
      <span class="flex items-center gap-1.5"><span class="inline-block w-2 h-2 rounded-full bg-slate-600"></span>Ingen matchning</span>
    </div>`;

  let currentSleeve = null;
  for (const f of FUND_MAPPINGS) {
    if (f.sleeve !== currentSleeve) {
      if (currentSleeve !== null) html += `</tbody></table></div></div>`;
      currentSleeve = f.sleeve;
      const c = sleeveColor[f.sleeve] || "#64748b";
      html += `
        <div class="mb-4">
          <h3 class="text-xs font-semibold tracking-widest uppercase mb-2" style="color:${c}">${f.sleeve}sleeve — Top-1 väljs månadsvis via accelerated momentum</h3>
          <div class="bg-panel border border-border rounded-lg overflow-x-auto">
            <table class="w-full text-xs">
              <thead>
                <tr class="border-b border-border text-muted">
                  <th class="px-3 py-2 text-left w-20">Exponering</th>
                  <th class="px-3 py-2 text-left w-24">ETF (Xetra)</th>
                  <th class="px-3 py-2 text-left">Fondnamn</th>
                  <th class="px-3 py-2 text-left w-48">Nordnet ETF (direkt)</th>
                  <th class="px-3 py-2 text-left w-64">Nordnet Fond (konventionell)</th>
                  <th class="px-3 py-2 text-left w-72">PPM-fond</th>
                  <th class="px-3 py-2 text-left w-20">PPM-nr</th>
                </tr>
              </thead>
              <tbody>`;
    }

    const ppmNr = f.ppm.nr
      ? `<a href="https://www.pensionsmyndigheten.se/service/fondtorg/fond/${f.ppm.nr}"
             target="_blank" rel="noopener"
             class="text-accent hover:underline">${f.ppm.nr}</a>`
      : `<span class="text-muted">—</span>`;

    const ppmAlt = f.ppm.alt
      ? `<div class="text-muted mt-0.5">Alt: ${f.ppm.alt}</div>`
      : "";

    const fundAlt = f.nordnet_fund.alt
      ? `<div class="text-muted mt-0.5">Alt: ${f.nordnet_fund.alt}</div>`
      : "";

    html += `
      <tr class="border-b border-border/50 hover:bg-white/[0.02] transition-colors">
        <td class="px-3 py-2.5 font-medium" style="color:${sleeveColor[f.sleeve]}">${f.label}</td>
        <td class="px-3 py-2.5 font-mono text-slate-400">${f.ticker}</td>
        <td class="px-3 py-2.5 text-slate-400">${f.name}</td>
        <td class="px-3 py-2.5">
          <div class="flex items-start gap-1.5">
            ${qualityBadge(f.nordnet_etf.quality)}
            <div class="text-slate-300">${f.nordnet_etf.note}</div>
          </div>
          <div class="text-muted mt-0.5">${f.ticker} · ${f.isin}</div>
        </td>
        <td class="px-3 py-2.5">
          <div class="flex items-start gap-1.5">
            ${qualityBadge(f.nordnet_fund.quality)}
            <div>
              <div class="text-slate-300">${f.nordnet_fund.name}</div>
              <div class="text-muted mt-0.5">${f.nordnet_fund.note}${f.nordnet_fund.fee ? ` · ${f.nordnet_fund.fee}` : ""}</div>
              ${fundAlt}
            </div>
          </div>
        </td>
        <td class="px-3 py-2.5">
          <div class="flex items-start gap-1.5">
            ${qualityBadge(f.ppm.quality)}
            <div>
              <div class="text-slate-300">${f.ppm.name}</div>
              <div class="text-muted mt-0.5">${f.ppm.sub}</div>
              ${ppmAlt}
            </div>
          </div>
        </td>
        <td class="px-3 py-2.5">${ppmNr}</td>
      </tr>`;
  }
  html += `</tbody></table></div></div>`;

  html += `
    <div class="bg-panel border border-border rounded-lg p-4 text-xs text-muted space-y-1">
      <p class="text-slate-400 font-medium mb-2">Sammanfattning</p>
      <p>• <span class="text-slate-300">Nordnet:</span> Alla 15 ETF:er är direkthandelbara på Nordnet.se (Xetra, EUR-denominerade). Ingen proxy behövs.</p>
      <p>• <span class="text-slate-300">PPM — faktorsleeve:</span> Faktorfonder (momentum, quality, value) saknas helt i PPM-universumet. Strategin är ej replikerbar i PPM för faktordelen.</p>
      <p>• <span class="text-slate-300">PPM — small cap:</span> Rimliga aktiva alternativ finns för USA small cap (916354) och Europa small cap (182759).</p>
      <p>• <span class="text-slate-300">PPM — sektorsleeve:</span> Tech (283408) och Healthcare (644005) har starka PPM-alternativ. Energy partiellt (517748). Industrials, Consumer Disc. och Consumer Staples saknar PPM-ekvivalent.</p>
      <p class="pt-1">PPM-nr länkar till Pensionsmyndighetens fondtorg. Kontrollera alltid att fonden är öppen för nyteckning.</p>
    </div>`;

  el.innerHTML = html;
}

async function pollForNewData(prevTs, maxWait) {
  const deadline = Date.now() + maxWait;
  while (Date.now() < deadline) {
    await sleep(3000);
    try {
      const res  = await fetch("/static/data.json?t=" + Date.now());
      const json = await res.json();
      if (json.generated_at && json.generated_at !== prevTs) return json;
    } catch (_) {}
  }
  throw new Error("Timed out waiting for recalculation");
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── Screening ──────────────────────────────────────────────────────
async function renderScreening() {
  const scr = DATA?.screening;
  if (!scr) {
    document.getElementById("screen-table").innerHTML =
      '<p class="text-xs text-muted">Ingen screening-data. Kör engine.py.</p>';
    return;
  }

  // Fetch streak history (non-blocking — degrade gracefully if API unavailable)
  let streaks = {};
  try {
    const hr = await fetch("/api/screening/history");
    if (hr.ok) streaks = await hr.json();
  } catch (_) {}

  const sorted    = [...scr.candidates].sort((a, b) => (b.score ?? -99) - (a.score ?? -99));
  const threshold = scr.portfolio_threshold ?? 0;

  let html = `
    <div class="text-xs text-muted mb-3">
      Portfölj-tröskel (D1-ACCEL min score): <span class="text-slate-300 font-medium">${threshold.toFixed(3)}</span>
      &nbsp;·&nbsp; Beräknad: ${new Date(scr.computed_at).toLocaleString("sv-SE")}
    </div>
    <div class="overflow-x-auto">
    <table class="w-full text-xs border-collapse">
      <thead>
        <tr class="text-muted border-b border-border">
          <th class="text-left py-2 pr-4">Label</th>
          <th class="text-left py-2 pr-4">Ticker</th>
          <th class="text-right py-2 pr-4">Score</th>
          <th class="text-right py-2 pr-4">ROC 63d</th>
          <th class="text-center py-2 pr-4">Status</th>
          <th class="text-center py-2 pr-4" title="Antal månader i rad med Välj nu-signal">Streak</th>
          <th class="text-left py-2 pr-4">Not</th>
          <th class="text-center py-2">Ta bort</th>
        </tr>
      </thead>
      <tbody>`;

  for (const c of sorted) {
    const hasScore    = c.score != null;
    const wouldSelect = c.would_select === true;
    const streak      = streaks[c.ticker]?.streak ?? 0;

    const statusBadge = c.error
      ? `<span class="text-red-400">Fel</span>`
      : wouldSelect
        ? `<span class="text-emerald-400 font-medium">● Välj nu</span>`
        : hasScore && c.roc_63d > 0
          ? `<span class="text-yellow-400">○ Bevakning</span>`
          : `<span class="text-muted">– Neutral</span>`;

    // Streak badge: dots for each month, coloured by strength
    let streakBadge = '<span class="text-muted">—</span>';
    if (streak >= 1) {
      const dots  = "●".repeat(Math.min(streak, 6)) + (streak > 6 ? "+" : "");
      const color = streak >= 3 ? "text-emerald-400" :
                    streak === 2 ? "text-yellow-400" : "text-slate-400";
      const tip   = `${streak} månad${streak > 1 ? "er" : ""} i rad`;
      streakBadge = `<span class="${color} font-mono" title="${tip}">${dots}</span>`;
    }

    const rowColor = wouldSelect ? "text-emerald-300" : "text-slate-300";
    html += `
      <tr class="border-b border-border/40 hover:bg-panel/50 ${rowColor}">
        <td class="py-2 pr-4 font-medium">${c.label}</td>
        <td class="py-2 pr-4 font-mono text-muted">${c.ticker}</td>
        <td class="py-2 pr-4 text-right font-mono">${hasScore ? c.score.toFixed(3) : "—"}</td>
        <td class="py-2 pr-4 text-right font-mono">${c.roc_63d != null ? (c.roc_63d * 100).toFixed(1) + "%" : "—"}</td>
        <td class="py-2 pr-4 text-center">${statusBadge}</td>
        <td class="py-2 pr-4 text-center">${streakBadge}</td>
        <td class="py-2 pr-4 text-muted">${c.note ?? ""}</td>
        <td class="py-2 text-center">
          <button onclick="removeScreenCandidate('${c.ticker}')" class="text-muted hover:text-red-400 transition-colors">✕</button>
        </td>
      </tr>`;
  }
  html += "</tbody></table></div>";

  // ── Portfolio universe comparison ─────────────────────────────────
  const universe = scr.portfolio_universe;
  if (universe?.length) {
    const sortedU = [...universe].sort((a, b) => (b.score ?? -99) - (a.score ?? -99));
    html += `
      <div class="mt-6 mb-2 text-xs font-semibold text-muted uppercase tracking-widest">
        Nuvarande ETF-universum (factor + sector sleeve)
      </div>
      <div class="overflow-x-auto">
      <table class="w-full text-xs border-collapse">
        <thead>
          <tr class="text-muted border-b border-border">
            <th class="text-left py-2 pr-4">Slot</th>
            <th class="text-left py-2 pr-4">Ticker</th>
            <th class="text-left py-2 pr-4">Ärm</th>
            <th class="text-right py-2 pr-4">Score</th>
            <th class="text-right py-2 pr-4">ROC 63d</th>
            <th class="text-center py-2">Hålls nu</th>
          </tr>
        </thead>
        <tbody>`;

    for (const u of sortedU) {
      const hasScore = u.score != null;
      const heldBadge = u.is_held
        ? `<span class="text-emerald-400 font-medium">● Aktiv</span>`
        : `<span class="text-muted">—</span>`;
      const rowColor = u.is_held ? "text-emerald-300" : "text-slate-400";
      const sleeveLabel = u.sleeve === "factor" ? "Faktor" : "Sektor";
      html += `
        <tr class="border-b border-border/30 hover:bg-panel/50 ${rowColor}">
          <td class="py-2 pr-4 font-medium">${u.label}</td>
          <td class="py-2 pr-4 font-mono text-muted">${u.ticker}</td>
          <td class="py-2 pr-4 text-muted">${sleeveLabel}</td>
          <td class="py-2 pr-4 text-right font-mono">${hasScore ? u.score.toFixed(3) : "—"}</td>
          <td class="py-2 pr-4 text-right font-mono">${u.roc_63d != null ? (u.roc_63d * 100).toFixed(1) + "%" : "—"}</td>
          <td class="py-2 text-center">${heldBadge}</td>
        </tr>`;
    }
    html += "</tbody></table></div>";
  }

  document.getElementById("screen-table").innerHTML = html;
}

async function addScreenCandidate() {
  const ticker = document.getElementById("screen-ticker").value.trim().toUpperCase();
  const label  = document.getElementById("screen-label").value.trim();
  const note   = document.getElementById("screen-note").value.trim();
  if (!ticker || !label) { alert("Ticker och label krävs"); return; }

  const res = await fetch("/api/screening/add", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ ticker, label, note }),
  });
  if (res.ok) {
    document.getElementById("screen-ticker").value = "";
    document.getElementById("screen-label").value  = "";
    document.getElementById("screen-note").value   = "";
    await loadData();
  } else {
    alert("Fel: " + await res.text());
  }
}

async function removeScreenCandidate(ticker) {
  const res = await fetch(`/api/screening/${encodeURIComponent(ticker)}`, { method: "DELETE" });
  if (res.ok) {
    if (DATA?.screening?.candidates) {
      DATA.screening.candidates = DATA.screening.candidates.filter(c => c.ticker !== ticker);
    }
    renderScreening();
  } else {
    alert("Kunde inte ta bort " + ticker + ": " + res.status);
  }
}

// ── Logs page ──────────────────────────────────────────────────────
let _logsAutoRefresh = null;

async function renderLogs() {
  const el = document.getElementById("view-logs");
  if (!el) return;

  function colorLine(line) {
    if (/ERROR|CRITICAL/i.test(line))   return `<span class="text-red-400">${escHtml(line)}</span>`;
    if (/WARNING/i.test(line))          return `<span class="text-yellow-400">${escHtml(line)}</span>`;
    if (/Wrote|upserted|Done|started|ready|complete/i.test(line))
                                         return `<span class="text-emerald-400">${escHtml(line)}</span>`;
    return `<span class="text-slate-400">${escHtml(line)}</span>`;
  }

  function escHtml(s) {
    return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  }

  async function fetchAndRender() {
    const box = document.getElementById("log-lines");
    if (!box) return;
    try {
      const res = await fetch("/api/logs?n=300");
      if (!res.ok) throw new Error(res.status);
      const { lines } = await res.json();
      box.innerHTML = lines.map(colorLine).join("\n");
      box.scrollTop = box.scrollHeight;
    } catch (e) {
      if (box) box.innerHTML = `<span class="text-red-400">Kunde inte hämta loggar: ${e.message}</span>`;
    }
  }

  el.innerHTML = `
    <div class="flex items-center gap-3 mb-3">
      <span class="text-xs font-semibold text-muted uppercase tracking-widest">Systemloggar</span>
      <button onclick="renderLogs()"
        class="text-xs px-3 py-1 rounded border border-border text-muted hover:text-slate-300 hover:border-slate-500 transition-colors">
        ↻ Uppdatera
      </button>
      <span class="text-xs text-muted">Senaste 300 rader · journalctl -u etf-dashboard</span>
    </div>
    <pre id="log-lines"
      class="bg-panel border border-border rounded-lg p-4 text-xs font-mono leading-5
             overflow-auto h-[70vh] whitespace-pre-wrap break-all text-slate-400">
Laddar…</pre>`;

  await fetchAndRender();
}

// ── STOXX 600 page ─────────────────────────────────────────────────
const STOXX_SAMMANSATT_STRATS = [
  { key: "stoxx_sammansatt_top5",  label: "Sammansatt Top-5",  color: "#c026d3", group: "sammansatt" },
  { key: "stoxx_sammansatt_top7",  label: "Sammansatt Top-7",  color: "#d946ef", group: "sammansatt" },
  { key: "stoxx_sammansatt_top10", label: "Sammansatt Top-10", color: "#e879f9", group: "sammansatt" },
];
const STOXX_D1ACCEL_STRATS = [
  { key: "stoxx600_top5",  label: "D1-ACCEL Top-5",  color: "#ec4899", group: "d1accel" },
  { key: "stoxx600_top10", label: "D1-ACCEL Top-10", color: "#db2777", group: "d1accel" },
  { key: "stoxx600_top20", label: "D1-ACCEL Top-20", color: "#9d174d", group: "d1accel" },
];
const STOXX_STRATS = STOXX_D1ACCEL_STRATS;
function _getSTOXXStrats(strategies) {
  if (STOXX_SAMMANSATT_STRATS.some(s => strategies[s.key])) return STOXX_SAMMANSATT_STRATS;
  return STOXX_D1ACCEL_STRATS;
}
let stoxxActiveKeys = new Set(["stoxx_sammansatt_top5","stoxx_sammansatt_top7","stoxx600_top5","stoxx600_top10"]);

function renderSTOXXPage() {
  if (!DATA) return;
  const strategies = DATA.strategies || {};
  const primary    = _getSTOXXStrats(strategies);
  const available  = primary.filter(s => strategies[s.key]);

  if (!available.length) {
    document.getElementById("stoxx-stats").innerHTML =
      `<div class="bg-amber-900/20 border border-amber-700/40 rounded-lg p-4 text-xs text-amber-300">
        Ingen STOXX-data. Kör <code>python d1_accel_stoxx600.py</code> och starta om engine.
       </div>`;
    return;
  }

  _buildSTOXXToggles(available);
  _renderSTOXXChart(available);
  _renderSTOXXHoldings(available);
  _renderSTOXXStats(available);
}

function _buildSTOXXToggles(available) {
  const el = document.getElementById("stoxx-toggles");
  if (!el) return;
  el.innerHTML = "";
  const strategies = DATA?.strategies || {};
  const compStrats = STOXX_D1ACCEL_STRATS.filter(s => strategies[s.key]);
  const all = [...available, ...compStrats.filter(s => !available.find(a=>a.key===s.key))];
  all.forEach(({ key, label, color }) => {
    const on  = stoxxActiveKeys.has(key);
    const btn = document.createElement("button");
    btn.className = "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-all";
    applyToggleStyle(btn, on, color);
    const dot = document.createElement("span");
    dot.className = "w-2 h-2 rounded-full flex-shrink-0";
    dot.style.background = color;
    btn.appendChild(dot);
    btn.appendChild(document.createTextNode(label));
    btn.addEventListener("click", () => {
      if (stoxxActiveKeys.has(key)) stoxxActiveKeys.delete(key);
      else stoxxActiveKeys.add(key);
      applyToggleStyle(btn, stoxxActiveKeys.has(key), color);
      _renderSTOXXChart(available);
      _renderSTOXXStats(available);
    });
    el.appendChild(btn);
  });
}

function _renderSTOXXHoldings(available) {
  const el = document.getElementById("stoxx-signal-row");
  if (!el) return;
  const strategies  = DATA?.strategies || {};
  const companyInfo = DATA?.stoxx_company_info || {};

  el.innerHTML = available.map(({ key, label, color }) => {
    const cs = strategies[key]?.current_signal;
    if (!cs) return "";
    const cashHolding = cs.holdings?.find(h => h.ticker === "CASH");
    if (cashHolding) {
      return `<div class="bg-panel border border-border rounded-lg p-4">
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
            <span class="text-xs font-semibold tracking-widest uppercase" style="color:${color}">${label}</span>
          </div>
          <span class="text-xs text-muted">${cs.date}</span>
        </div>
        <p class="text-xs text-muted italic">Kontanter — absolut momentum negativt</p>
      </div>`;
    }
    const chips = (cs.holdings || []).filter(h => h.ticker !== "CASH").map(h => {
      const ticker  = h.ticker.replace(/\.[A-Z]+$/, "");
      const name    = companyInfo[h.ticker]?.name || null;
      const pct     = Math.round(h.weight * 100);
      return `<div class="flex items-center justify-between py-1.5 border-b border-border last:border-0">
        <div class="min-w-0">
          <span class="text-xs font-mono font-medium text-slate-300">${ticker}</span>
          ${name ? `<span class="text-xs text-muted ml-2">${name}</span>` : ""}
        </div>
        <span class="text-xs text-muted ml-2 shrink-0">${pct}%</span>
      </div>`;
    }).join("");
    return `<div class="bg-panel border border-border rounded-lg p-4">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
          <span class="text-xs font-semibold tracking-widest uppercase" style="color:${color}">${label}</span>
        </div>
        <span class="text-xs text-muted">${cs.date}</span>
      </div>
      ${chips || '<p class="text-xs text-muted italic">Inga innehav</p>'}
    </div>`;
  }).join("");
}

function _renderSTOXXChart(available) {
  if (!stoxxChart || !DATA) return;
  stoxxChart.resize();
  const strategies = DATA.strategies || {};
  const hasSammansatt = STOXX_SAMMANSATT_STRATS.some(s => strategies[s.key] && stoxxActiveKeys.has(s.key));
  const startDate  = hasSammansatt ? "2006-01-01" : "2010-01-01";

  function normalize(nav) {
    if (!nav?.length) return [];
    const idx = nav.findIndex(p => p.date >= startDate);
    if (idx === -1) return [];
    const base = nav[idx].value;
    return base ? nav.slice(idx).map(p => [p.date, +(p.value / base * 100).toFixed(4)]) : [];
  }

  const allKeys = [...STOXX_SAMMANSATT_STRATS.map(s => s.key), ...STOXX_D1ACCEL_STRATS.map(s => s.key)];
  const series = allKeys
    .filter(k => stoxxActiveKeys.has(k) && strategies[k])
    .map(k => {
      const c = SERIES_CFG[k] || {}; const { key, label, color } = { key: k, label: c.label||k, color: c.color||"#fff" };
      return { name: label, type: "line", data: normalize(strategies[k].nav),
               smooth: false, symbol: "none",
               lineStyle: { color, width: c.width || 2 }, itemStyle: { color } };
    });

  // Benchmark from sammansatt or D1-ACCEL first strategy
  const benchKey = [...STOXX_SAMMANSATT_STRATS, ...STOXX_D1ACCEL_STRATS].find(s => strategies[s.key])?.key;
  const bench = strategies[benchKey]?.benchmark?.series;
  if (bench) {
    const c = "#f9a8d4";
    series.push({ name: "STOXX 600 ETF (EXSA.DE)", type: "line",
                  data: normalize(bench), smooth: false, symbol: "none",
                  lineStyle: { color: c, width: 1.4, type: "dashed" }, itemStyle: { color: c } });
  }

  stoxxChart.setOption({
    backgroundColor: "transparent", animation: false,
    grid:  { top: 24, left: 60, right: 20, bottom: 36 },
    xAxis: { type: "time", min: startDate,
             axisLabel: { color: "#8591b8", fontSize: 10 },
             axisLine:  { lineStyle: { color: "#252a3d" } },
             splitLine: { show: false } },
    yAxis: { type: "value",
             axisLabel: { color: "#8591b8", fontSize: 10, formatter: v => v.toFixed(0) },
             axisLine:  { show: false },
             splitLine: { lineStyle: { color: "#252a3d", type: "dashed" } },
             axisTick:  { show: false } },
    tooltip: {
      trigger: "axis", backgroundColor: "#1a1e2e",
      borderColor: "#252a3d", textStyle: { color: "#c9d1e0", fontSize: 11 },
      formatter(params) {
        if (!params?.length) return "";
        const d = new Date(params[0].axisValue).toISOString().slice(0, 10);
        const rows = params.map(p =>
          `<div style="display:flex;justify-content:space-between;gap:20px">
            <span style="color:${p.color}">${p.seriesName}</span>
            <span style="font-variant-numeric:tabular-nums">${(+p.value[1]).toFixed(1)}</span>
           </div>`).join("");
        return `<div style="font-size:11px"><div style="color:#8591b8;margin-bottom:4px">${d}</div>${rows}</div>`;
      },
    },
    legend: { show: false }, series,
  }, true);
}

// Sector color palette
const SECTOR_COLORS = {
  "Technology":           "#6366f1",
  "Financial Services":   "#0ea5e9",
  "Industrials":          "#f59e0b",
  "Consumer Cyclical":    "#f97316",
  "Consumer Defensive":   "#10b981",
  "Healthcare":           "#ec4899",
  "Energy":               "#eab308",
  "Basic Materials":      "#84cc16",
  "Communication Services":"#8b5cf6",
  "Utilities":            "#38bdf8",
  "Real Estate":          "#a78bfa",
};
function sectorColor(s) { return SECTOR_COLORS[s] || "#64748b"; }

function _renderSTOXXStats(available) {
  const el = document.getElementById("stoxx-stats");
  if (!el) return;
  const strategies   = DATA?.strategies || {};
  const companyInfo  = DATA?.stoxx_company_info || {};

  function pct(v, d = 1) {
    return v == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(d) + "%";
  }
  function colorVal(v) {
    return v == null ? "color:#8591b8" : v >= 0 ? "color:#10b981" : "color:#f43f5e";
  }
  function tickerLabel(t) {
    const info = companyInfo[t];
    return info ? `${info.name} <span class="text-muted font-normal">(${t})</span>` : t;
  }
  function sectorBadge(t) {
    const sec = companyInfo[t]?.sector;
    if (!sec) return "";
    const c = sectorColor(sec);
    return `<span class="text-xs px-1.5 py-0.5 rounded-full" style="background:${c}22;color:${c};border:1px solid ${c}44">${sec}</span>`;
  }

  const activeStrats = available.filter(s => stoxxActiveKeys.has(s.key));
  if (!activeStrats.length) { el.innerHTML = ""; return; }

  const cards = activeStrats.map(({ key, label, color }) => {
    const strat  = strategies[key];
    const st     = strat?.stats;
    if (!st) return "";
    const params    = strat.params || {};
    const cs        = strat.current_signal || {};
    const allocLog  = strat.alloc_log || [];

    // ── Stats summary (handle both D1-ACCEL and sammansatt field names) ──
    const mdd  = st.max_dd  ?? st.mdd;
    const vol  = st.ann_vol ?? st.vol;
    const isSammansattKey = key.startsWith("stoxx_sammansatt");
    const summaryHtml = `
      <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 gap-4 mt-3">
        <div><p class="text-xs text-muted mb-0.5">CAGR</p>
          <p class="text-lg font-semibold" style="${colorVal(st.cagr)}">${pct(st.cagr)}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Sharpe</p>
          <p class="text-lg font-semibold text-slate-300">${st.sharpe?.toFixed(2) ?? "—"}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Max DD</p>
          <p class="text-lg font-semibold" style="color:#f43f5e">${pct(mdd)}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Volatilitet</p>
          <p class="text-lg font-semibold text-slate-300">${pct(vol)}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Total</p>
          <p class="text-lg font-semibold" style="${colorVal(st.total)}">${pct(st.total)}</p></div>
      </div>
      ${!isSammansattKey ? `<div class="mt-2 text-xs text-muted">
        lb=${params.lb ?? 63} win=${params.win ?? 10} ema=${params.ema ?? 8}
        · top_n=${params.top_n ?? "?"} · cost=${((params.cost ?? 0.003)*100).toFixed(1)}bp
        · gate=EXSA.DE 84d</div>` : ""}
      ${isSammansantKey ? `<div class="mt-2 text-xs text-muted">
        score=mean(ret3m,ret6m,ret12m) med 1M skip · absolut momentum · ~295 EUR-aktier</div>` : ""}`;

    // ── Current holdings ───────────────────────────────────────────
    const currentRows = (cs.holdings || [])
      .filter(h => h.ticker !== "CASH")
      .map(h => {
        const w = Math.round((h.weight || 0) * 100);
        return `<div class="flex items-center justify-between py-2 border-b border-border last:border-0 gap-3">
          <div class="min-w-0">
            <span class="text-xs font-mono font-medium text-slate-300">${tickerLabel(h.ticker)}</span>
            <div class="mt-0.5">${sectorBadge(h.ticker)}</div>
          </div>
          <span class="text-xs text-muted flex-shrink-0">${w}%</span>
        </div>`;
      }).join("") || '<p class="text-xs text-muted italic py-2">Inga innehav (kontanter)</p>';

    const currentHtml = `
      <div>
        <p class="text-xs font-semibold text-slate-400 mb-2">Aktuell portfölj · ${cs.date || "—"}</p>
        ${currentRows}
      </div>`;

    // ── Allocation history (last 24 months, most recent first) ─────
    const histRows = [...allocLog].reverse().slice(0, 36).map(e => {
      if (e.holdings["CASH"]) {
        return `<tr class="border-b border-border">
          <td class="py-1.5 pr-3 text-xs text-slate-400 whitespace-nowrap">${e.date}</td>
          <td colspan="${params.top_n || 5}" class="py-1.5 text-xs text-muted italic">Kontanter (gate aktiv)</td>
        </tr>`;
      }
      const cells = Object.keys(e.holdings).map(t => {
        const info = companyInfo[t];
        const sec  = info?.sector || "";
        const c    = sectorColor(sec);
        const shortName = info?.name
          ? info.name.replace(/ (SE|SA|NV|AG|SpA|S\.p\.A\.|N\.V\.|plc|PLC|AB|AS|ASA|OYJ|Oyj|GmbH|KGaA|Holding|Group|Corp\.|Inc\.|Ltd\.?)/g, "").trim().slice(0, 22)
          : t.replace(/\.[A-Z]+$/, "");
        return `<td class="py-1.5 px-1">
          <div class="text-xs text-slate-300 font-mono leading-tight">${t.replace(/\.[A-Z]+$/, "")}</div>
          <div class="text-xs leading-tight" style="color:${c}">${shortName}</div>
        </td>`;
      });
      return `<tr class="border-b border-border hover:bg-white/[0.02]">
        <td class="py-1.5 pr-3 text-xs text-slate-400 whitespace-nowrap">${e.date}</td>
        ${cells.join("")}
      </tr>`;
    }).join("");

    const topN   = params.top_n || 5;
    const colHdr = Array.from({length: topN}, (_, i) => `<th class="text-xs text-muted font-normal px-1 pb-2">#${i+1}</th>`).join("");
    const histHtml = allocLog.length ? `
      <div>
        <p class="text-xs font-semibold text-slate-400 mb-2">Historik — månadsinnehav (senaste 36)</p>
        <div class="overflow-auto max-h-[480px] rounded border border-border">
          <table class="w-full min-w-max border-collapse">
            <thead class="sticky top-0 bg-[#0f1117]">
              <tr><th class="text-xs text-muted font-normal pr-3 pb-2 text-left">Datum</th>${colHdr}</tr>
            </thead>
            <tbody>${histRows}</tbody>
          </table>
        </div>
      </div>` : "";

    return `<div class="bg-panel border border-border rounded-lg p-4 space-y-5">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
        <span class="text-xs font-semibold tracking-widest uppercase" style="color:${color}">${label}</span>
      </div>
      <div class="px-2 py-1.5 bg-amber-900/20 border border-amber-700/30 rounded text-xs text-amber-400">
        ⚠ UNVALIDATED — survivorship bias
      </div>
      ${summaryHtml}
      ${histHtml ? `<div class="pt-2">${histHtml}</div>` : ""}
    </div>`;
  }).join("");

  el.innerHTML = `<div class="space-y-6">${cards}</div>`;
}

// ── Nasdaq page ────────────────────────────────────────────────────
const NASDAQ_SAMMANSATT_STRATS = [
  { key: "nasdaq_sammansatt_top5",  label: "Nasdaq Top-5",  color: "#38bdf8", group: "sammansatt" },
  { key: "nasdaq_sammansatt_top7",  label: "Nasdaq Top-7",  color: "#7dd3fc", group: "sammansatt" },
  { key: "nasdaq_sammansatt_top10", label: "Nasdaq Top-10", color: "#bae6fd", group: "sammansatt" },
];
let nasdaqActiveKeys = new Set(["nasdaq_sammansatt_top5", "nasdaq_sammansatt_top7"]);

function renderNasdaqPage() {
  if (!DATA) return;
  const strategies = DATA.strategies || {};
  const available  = NASDAQ_SAMMANSATT_STRATS.filter(s => strategies[s.key]);

  if (!available.length) {
    document.getElementById("nasdaq-stats").innerHTML =
      `<p class="text-xs text-muted italic px-1">Ingen Nasdaq-data tillgänglig. Kör run_all() för att generera resultat.</p>`;
    return;
  }
  _buildNasdaqToggles(available);
  _renderNasdaqChart(available);
  _renderNasdaqHoldings(available);
  _renderNasdaqStats(available);
}

function _buildNasdaqToggles(available) {
  const el = document.getElementById("nasdaq-toggles");
  if (!el) return;
  el.innerHTML = "";
  available.forEach(({ key, label, color }) => {
    const on  = nasdaqActiveKeys.has(key);
    const btn = document.createElement("button");
    btn.className = "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-all";
    applyToggleStyle(btn, on, color);
    const dot = document.createElement("span");
    dot.className = "w-2 h-2 rounded-full flex-shrink-0";
    dot.style.background = color;
    btn.appendChild(dot);
    btn.appendChild(document.createTextNode(label));
    btn.addEventListener("click", () => {
      if (nasdaqActiveKeys.has(key)) nasdaqActiveKeys.delete(key);
      else nasdaqActiveKeys.add(key);
      applyToggleStyle(btn, nasdaqActiveKeys.has(key), color);
      _renderNasdaqChart(available);
      _renderNasdaqStats(available);
    });
    el.appendChild(btn);
  });
}

function _renderNasdaqChart(available) {
  if (!nasdaqChart || !DATA) return;
  nasdaqChart.resize();
  const strategies = DATA.strategies || {};
  const startDate  = "2006-01-01";

  function normalize(nav) {
    if (!nav?.length) return [];
    const idx = nav.findIndex(p => p.date >= startDate);
    if (idx === -1) return [];
    const base = nav[idx].value;
    return base ? nav.slice(idx).map(p => [p.date, +(p.value / base * 100).toFixed(4)]) : [];
  }

  const series = NASDAQ_SAMMANSATT_STRATS
    .filter(s => nasdaqActiveKeys.has(s.key) && strategies[s.key])
    .map(({ key, label, color }) => ({
      name: label, type: "line", data: normalize(strategies[key].nav),
      smooth: false, symbol: "none",
      lineStyle: { color, width: SERIES_CFG[key]?.width || 2 }, itemStyle: { color },
    }));

  // Benchmark: QQQ
  const benchSeries = available[0] ? strategies[available[0].key]?.benchmark?.series : null;
  if (benchSeries) {
    const c = "#94a3b8";
    series.push({ name: "QQQ", type: "line",
                  data: normalize(benchSeries), smooth: false, symbol: "none",
                  lineStyle: { color: c, width: 1.4, type: "dashed" }, itemStyle: { color: c } });
  }

  nasdaqChart.setOption({
    backgroundColor: "transparent", animation: false,
    grid:  { top: 24, left: 60, right: 20, bottom: 36 },
    xAxis: { type: "time", min: startDate,
             axisLabel: { color: "#8591b8", fontSize: 10 },
             axisLine:  { lineStyle: { color: "#252a3d" } }, splitLine: { show: false } },
    yAxis: { type: "value",
             axisLabel: { color: "#8591b8", fontSize: 10, formatter: v => v.toFixed(0) },
             axisLine: { show: false },
             splitLine: { lineStyle: { color: "#252a3d", type: "dashed" } }, axisTick: { show: false } },
    tooltip: {
      trigger: "axis", backgroundColor: "#1a1e2e", borderColor: "#252a3d",
      textStyle: { color: "#c9d1e0", fontSize: 11 },
      formatter(params) {
        if (!params?.length) return "";
        const d = new Date(params[0].axisValue).toISOString().slice(0, 10);
        const rows = params.map(p =>
          `<div style="display:flex;justify-content:space-between;gap:20px">
            <span style="color:${p.color}">${p.seriesName}</span>
            <span style="font-variant-numeric:tabular-nums">${(+p.value[1]).toFixed(1)}</span>
           </div>`).join("");
        return `<div style="font-size:11px"><div style="color:#8591b8;margin-bottom:4px">${d}</div>${rows}</div>`;
      },
    },
    legend: { show: false }, series,
  }, true);
}

function _renderNasdaqHoldings(available) {
  const el = document.getElementById("nasdaq-signal-row");
  if (!el) return;
  const strategies  = DATA?.strategies || {};
  const companyInfo = DATA?.nasdaq_company_info || {};

  el.innerHTML = available.map(({ key, label, color }) => {
    const cs = strategies[key]?.current_signal;
    if (!cs) return "";
    const cashHolding = cs.holdings?.find(h => h.ticker === "CASH");
    if (cashHolding) {
      return `<div class="bg-panel border border-border rounded-lg p-4">
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
            <span class="text-xs font-semibold tracking-widest uppercase" style="color:${color}">${label}</span>
          </div>
          <span class="text-xs text-muted">${cs.date}</span>
        </div>
        <p class="text-xs text-muted italic">Kontanter — absolut momentum negativt</p>
      </div>`;
    }
    const chips = (cs.holdings || []).filter(h => h.ticker !== "CASH").map(h => {
      const ticker = h.ticker.replace(/\.[A-Z]+$/, "");
      const name   = companyInfo[h.ticker]?.name || null;
      const pct    = Math.round(h.weight * 100);
      return `<div class="flex items-center justify-between py-1.5 border-b border-border last:border-0">
        <div class="min-w-0">
          <span class="text-xs font-mono font-medium text-slate-300">${ticker}</span>
          ${name ? `<span class="text-xs text-muted ml-2">${name}</span>` : ""}
        </div>
        <span class="text-xs text-muted ml-2 shrink-0">${pct}%</span>
      </div>`;
    }).join("");
    return `<div class="bg-panel border border-border rounded-lg p-4">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
          <span class="text-xs font-semibold tracking-widest uppercase" style="color:${color}">${label}</span>
        </div>
        <span class="text-xs text-muted">${cs.date}</span>
      </div>
      ${chips || '<p class="text-xs text-muted italic">Inga innehav</p>'}
    </div>`;
  }).join("");
}

function _renderNasdaqStats(available) {
  const el = document.getElementById("nasdaq-stats");
  if (!el) return;
  const strategies  = DATA?.strategies || {};
  const companyInfo = DATA?.nasdaq_company_info || {};

  function pct(v, d = 1) {
    return v == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(d) + "%";
  }
  function colorVal(v) {
    return v == null ? "color:#8591b8" : v >= 0 ? "color:#10b981" : "color:#f43f5e";
  }

  const activeStrats = available.filter(s => nasdaqActiveKeys.has(s.key));
  if (!activeStrats.length) { el.innerHTML = ""; return; }

  const cards = activeStrats.map(({ key, label, color }) => {
    const strat = strategies[key];
    const st    = strat?.stats;
    if (!st) return "";
    const params   = strat.params || {};
    const cs       = strat.current_signal || {};
    const allocLog = strat.alloc_log || [];

    const summaryHtml = `
      <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 gap-4 mt-3">
        <div><p class="text-xs text-muted mb-0.5">CAGR</p>
          <p class="text-lg font-semibold" style="${colorVal(st.cagr)}">${pct(st.cagr)}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Sharpe</p>
          <p class="text-lg font-semibold text-slate-300">${st.sharpe?.toFixed(2) ?? "—"}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Max DD</p>
          <p class="text-lg font-semibold" style="color:#f43f5e">${pct(st.max_dd)}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Volatilitet</p>
          <p class="text-lg font-semibold text-slate-300">${pct(st.ann_vol)}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Total</p>
          <p class="text-lg font-semibold" style="${colorVal(st.total)}">${pct(st.total)}</p></div>
      </div>`;

    const currentRows = (cs.holdings || [])
      .filter(h => h.ticker !== "CASH")
      .map(h => {
        const info = companyInfo[h.ticker];
        const name = info?.name ? `<span class="text-xs text-muted ml-2">${info.name}</span>` : "";
        const w    = Math.round((h.weight || 0) * 100);
        return `<div class="flex items-center justify-between py-2 border-b border-border last:border-0 gap-3">
          <div class="min-w-0">
            <span class="text-xs font-mono font-medium text-slate-300">${h.ticker}</span>
            ${name}
          </div>
          <span class="text-xs text-muted flex-shrink-0">${w}%</span>
        </div>`;
      }).join("") || '<p class="text-xs text-muted italic py-2">Inga innehav (kontanter)</p>';

    const histRows = [...allocLog].reverse().slice(0, 36).map(e => {
      if (e.holdings["CASH"]) {
        return `<tr class="border-b border-border">
          <td class="py-1.5 pr-3 text-xs text-slate-400 whitespace-nowrap">${e.date}</td>
          <td colspan="${params.top_n || 5}" class="py-1.5 text-xs text-muted italic">Kontanter</td>
        </tr>`;
      }
      const cells = Object.keys(e.holdings).map(t => {
        const info = companyInfo[t];
        const shortName = info?.name ? info.name.replace(/ (Inc\.|Corp\.|Ltd\.?|Group|Holdings?)/g, "").trim().slice(0, 20) : t;
        return `<td class="py-1.5 px-1">
          <div class="text-xs text-slate-300 font-mono leading-tight">${t}</div>
          <div class="text-xs text-muted leading-tight">${shortName !== t ? shortName : ""}</div>
        </td>`;
      });
      return `<tr class="border-b border-border hover:bg-white/[0.02]">
        <td class="py-1.5 pr-3 text-xs text-slate-400 whitespace-nowrap">${e.date}</td>
        ${cells.join("")}
      </tr>`;
    }).join("");

    const topN   = params.top_n || 5;
    const colHdr = Array.from({ length: topN }, (_, i) =>
      `<th class="text-xs text-muted font-normal px-1 pb-2">#${i + 1}</th>`).join("");
    const histHtml = allocLog.length ? `
      <div>
        <p class="text-xs font-semibold text-slate-400 mb-2">Historik — månadsinnehav (senaste 36)</p>
        <div class="overflow-auto max-h-[480px] rounded border border-border">
          <table class="w-full min-w-max border-collapse">
            <thead class="sticky top-0 bg-[#0f1117]">
              <tr><th class="text-xs text-muted font-normal pr-3 pb-2 text-left">Datum</th>${colHdr}</tr>
            </thead>
            <tbody>${histRows}</tbody>
          </table>
        </div>
      </div>` : "";

    return `<div class="bg-panel border border-border rounded-lg p-4 space-y-5">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
        <span class="text-xs font-semibold tracking-widest uppercase" style="color:${color}">${label}</span>
      </div>
      ${summaryHtml}
      <div>
        <p class="text-xs font-semibold text-slate-400 mb-2">Aktuell portfölj · ${cs.date || "—"}</p>
        ${currentRows}
      </div>
      ${histHtml ? `<div class="pt-2">${histHtml}</div>` : ""}
    </div>`;
  }).join("");

  el.innerHTML = `<div class="space-y-6">${cards}</div>`;
}

// ── Universe (all-instrument screener) page ────────────────────────
// Kept as var so inline onclick can access them from global scope
var _universeSort = { col: "score", dir: -1 };
var _universeFilters = new Set(["OMXS", "STOXX", "SP500", "Nasdaq"]);

function renderUniversePage() {
  if (!DATA) return;

  // Collect all_scores from all universes
  const universeData = [];
  const universes = [
    { key: "omxs",   label: "OMXS",   scores: DATA.omxs_all_scores,   info: DATA.omxs_company_info   || {} },
    { key: "stoxx",  label: "STOXX",  scores: DATA.stoxx_all_scores,  info: DATA.stoxx_company_info  || {} },
    { key: "sp500",  label: "SP500",  scores: DATA.sp500_all_scores,  info: DATA.sp500_company_info  || {} },
    { key: "nasdaq", label: "Nasdaq", scores: DATA.nasdaq_all_scores, info: DATA.nasdaq_company_info || {} },
  ];

  for (const { label, scores, info } of universes) {
    if (!scores || !Object.keys(scores).length) continue;
    for (const [ticker, score] of Object.entries(scores)) {
      universeData.push({
        ticker,
        name:     info[ticker]?.name || "",
        universe: label,
        score:    typeof score === "number" ? score : null,
      });
    }
  }

  if (!universeData.length) {
    document.getElementById("universe-table-wrap").innerHTML =
      `<p class="text-xs text-muted italic">Ingen universe-data tillgänglig. Kör run_all() för att generera resultat.</p>`;
    _buildUniverseFilters(universes.map(u => u.label), universeData);
    return;
  }

  _buildUniverseFilters(universes.map(u => u.label), universeData);
  _renderUniverseTable(universeData);

  // Wire up search
  const searchEl = document.getElementById("universe-search");
  if (searchEl) {
    searchEl.oninput = () => _renderUniverseTable(universeData);
  }
}

function _buildUniverseFilters(labels, universeData) {
  const el = document.getElementById("universe-filters");
  if (!el) return;
  el.innerHTML = "";
  const uColors = { OMXS: "#f97316", STOXX: "#c026d3", SP500: "#34d399", Nasdaq: "#38bdf8" };
  labels.forEach(label => {
    const on  = _universeFilters.has(label);
    const col = uColors[label] || "#8591b8";
    const btn = document.createElement("button");
    btn.className = "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-all";
    _applyUniFilterStyle(btn, on, col);
    const dot = document.createElement("span");
    dot.className = "w-2 h-2 rounded-full flex-shrink-0";
    dot.style.background = col;
    btn.appendChild(dot);
    btn.appendChild(document.createTextNode(label));
    btn.addEventListener("click", () => {
      if (_universeFilters.has(label)) _universeFilters.delete(label);
      else _universeFilters.add(label);
      _applyUniFilterStyle(btn, _universeFilters.has(label), col);
      _renderUniverseTable(universeData);
    });
    el.appendChild(btn);
  });
}

function _applyUniFilterStyle(btn, on, color) {
  if (on) {
    btn.style.borderColor = color;
    btn.style.background  = color + "22";
    btn.style.color       = color;
  } else {
    btn.style.borderColor = "#252a3d";
    btn.style.background  = "transparent";
    btn.style.color       = "#8591b8";
  }
}

function _renderUniverseTable(universeData) {
  const el = document.getElementById("universe-table-wrap");
  if (!el) return;

  const search = (document.getElementById("universe-search")?.value || "").toLowerCase().trim();
  const { col, dir } = _universeSort;
  const uColors = { OMXS: "#f97316", STOXX: "#c026d3", SP500: "#34d399", Nasdaq: "#38bdf8" };

  let rows = universeData
    .filter(r => _universeFilters.has(r.universe))
    .filter(r => !search ||
      r.ticker.toLowerCase().includes(search) ||
      r.name.toLowerCase().includes(search))
    .sort((a, b) => {
      let va = a[col], vb = b[col];
      if (col === "score") {
        va = va ?? -Infinity;
        vb = vb ?? -Infinity;
      } else {
        va = (va || "").toLowerCase();
        vb = (vb || "").toLowerCase();
      }
      if (va < vb) return -dir;
      if (va > vb) return  dir;
      return 0;
    });

  function sortBtn(c, label) {
    const active = _universeSort.col === c;
    const arrow  = active ? (_universeSort.dir === 1 ? " ▲" : " ▼") : "";
    return `<th class="text-left text-xs text-muted font-normal px-3 py-2 cursor-pointer hover:text-slate-300 select-none whitespace-nowrap"
                onclick="_universeSort={col:'${c}',dir:${active ? -_universeSort.dir : (c === 'score' ? -1 : 1)}};_renderUniverseTable(window._universeDataRef)"
            >${label}${arrow}</th>`;
  }

  // Store ref for sort callbacks
  window._universeDataRef = universeData;

  const tbody = rows.map(r => {
    const uCol    = uColors[r.universe] || "#8591b8";
    const sc      = r.score;
    const scStr   = sc == null ? "—" : (sc >= 0 ? "+" : "") + (sc * 100).toFixed(1) + "%";
    const scColor = sc == null ? "#8591b8" : sc > 0 ? "#10b981" : "#f43f5e";
    const name    = r.name ? `<span class="text-muted">${r.name}</span>` : "";
    return `<tr class="border-b border-border hover:bg-white/[0.02]">
      <td class="px-3 py-2">
        <span class="text-xs px-1.5 py-0.5 rounded font-medium" style="background:${uCol}22;color:${uCol}">${r.universe}</span>
      </td>
      <td class="px-3 py-2 text-xs font-mono font-medium text-slate-300 whitespace-nowrap">${r.ticker}</td>
      <td class="px-3 py-2 text-xs">${name}</td>
      <td class="px-3 py-2 text-xs font-semibold text-right whitespace-nowrap" style="color:${scColor}">${scStr}</td>
    </tr>`;
  }).join("");

  el.innerHTML = `
    <p class="text-xs text-muted mb-2">${rows.length} instrument visas</p>
    <table class="w-full border-collapse min-w-[500px]">
      <thead class="bg-[#0f1117] sticky top-0">
        <tr>
          ${sortBtn("universe", "Universum")}
          ${sortBtn("ticker",   "Ticker")}
          ${sortBtn("name",     "Namn")}
          ${sortBtn("score",    "Score")}
        </tr>
      </thead>
      <tbody>${tbody}</tbody>
    </table>`;
}

// ── Documentation page ─────────────────────────────────────────────
function renderDocs() {
  const el = document.getElementById("view-docs");
  if (!el) return;
  if (el.dataset.rendered) return;
  el.dataset.rendered = "1";

  el.innerHTML = `
<style>
  .doc-h1  { font-size:1.35rem; font-weight:600; color:#e2e8f0; margin-bottom:.5rem; }
  .doc-h2  { font-size:1.05rem; font-weight:600; color:#c7d2fe; margin-bottom:.35rem; padding-top:.1rem; border-top:1px solid #252a3d; }
  .doc-h3  { font-size:.875rem; font-weight:600; color:#a5b4fc; margin-bottom:.25rem; margin-top:.75rem; }
  .doc-p   { font-size:.8rem; color:#94a3b8; line-height:1.65; }
  .doc-ul  { font-size:.8rem; color:#94a3b8; line-height:1.7; padding-left:1.25rem; list-style:disc; }
  .doc-tbl { width:100%; border-collapse:collapse; font-size:.78rem; }
  .doc-tbl th { background:#1a1e2e; color:#8591b8; text-align:left; padding:.45rem .7rem; font-weight:500; border-bottom:1px solid #252a3d; }
  .doc-tbl td { padding:.4rem .7rem; border-bottom:1px solid #1a1e2e; color:#94a3b8; vertical-align:top; }
  .doc-tbl tr:hover td { background:#1a1e2e44; }
  .doc-badge { display:inline-block; padding:.15rem .5rem; border-radius:.25rem; font-size:.7rem; font-weight:600; }
  .badge-etf { background:#1e3a5f; color:#60a5fa; }
  .badge-ppm { background:#134e4a; color:#34d399; }
  .badge-mc  { background:#3b1f5e; color:#c084fc; }
  .formula   { font-family:monospace; background:#13161f; border:1px solid #252a3d; border-radius:.35rem; padding:.6rem 1rem; font-size:.78rem; color:#a5b4fc; line-height:1.8; }
  .kv-row    { display:flex; gap:.5rem; font-size:.78rem; margin:.2rem 0; }
  .kv-key    { color:#5b6ef5; min-width:9rem; font-weight:500; }
  .kv-val    { color:#94a3b8; }
  .doc-card  { background:#1a1e2e; border:1px solid #252a3d; border-radius:.6rem; padding:1rem 1.25rem; }
  .callout   { background:#1e2233; border-left:3px solid #5b6ef5; border-radius:0 .4rem .4rem 0; padding:.6rem 1rem; font-size:.78rem; color:#94a3b8; line-height:1.65; }
  .callout-green { border-left-color:#10b981; }
  .callout-amber { border-left-color:#f59e0b; }
  .callout-cyan  { border-left-color:#06b6d4; }
</style>

<!-- ─ TOC ─────────────────────────────────────────────────────── -->
<div class="doc-card space-y-1">
  <p class="doc-h1">Strategidokumentation</p>
  <p class="doc-p">Komplett teknisk beskrivning av samtliga backtestade strategier, beräkningsmetodik och resultat. Senast uppdaterad juni 2026.</p>
  <div class="flex flex-wrap gap-3 mt-3 text-xs text-muted">
    <a href="#sec-overview"    class="hover:text-slate-300 transition-colors">1. Översikt</a>
    <span>·</span>
    <a href="#sec-data"        class="hover:text-slate-300 transition-colors">2. Data &amp; priser</a>
    <span>·</span>
    <a href="#sec-etf"         class="hover:text-slate-300 transition-colors">3. ETF-strategier</a>
    <span>·</span>
    <a href="#sec-ppm"         class="hover:text-slate-300 transition-colors">4. PPM-strategi</a>
    <span>·</span>
    <a href="#sec-backtest"    class="hover:text-slate-300 transition-colors">5. Backtest-metodologi</a>
    <span>·</span>
    <a href="#sec-montecarlo"  class="hover:text-slate-300 transition-colors">6. Monte Carlo</a>
    <span>·</span>
    <a href="#sec-screening"   class="hover:text-slate-300 transition-colors">7. Screening</a>
    <span>·</span>
    <a href="#sec-findings"    class="hover:text-slate-300 transition-colors">8. Nyckelresultat</a>
    <span>·</span>
    <a href="#sec-sammansatt"  class="hover:text-slate-300 transition-colors">9. Sammansatt Momentum — Aktier</a>
    <span>·</span>
    <a href="#sec-autoupdate"  class="hover:text-slate-300 transition-colors">10. Automatisk datauppdatering</a>
  </div>
</div>

<!-- ─ 1. OVERVIEW ─────────────────────────────────────────────── -->
<div class="doc-card space-y-3" id="sec-overview">
  <p class="doc-h2">1 · Översikt</p>
  <p class="doc-p">Systemet backtestaro två parallella momentum-rotationsstrategier: en ETF-portfölj handlad på Xetra (via Nordnet) och en PPM-portfölj på Pensionsmyndighetens fondtorg. Båda bygger på samma grundprincip — <em>trend-following momentum</em> — men är anpassade till respektive marknads karakteristika.</p>
  <div class="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-2">
    <div class="space-y-2">
      <p class="doc-h3">ETF-portfölj</p>
      <ul class="doc-ul">
        <li>8 faktor-ETF:er (Xetra-listade, EUR) + 7 sektor-ETF:er</li>
        <li>2 sleeves: faktor och sektor, vardera 50 %</li>
        <li>Regimfilter: IWDA.L vs IBTS.L avgör risk-on/off</li>
        <li>Handelskostnad: 15 bps per transaktion per sida</li>
        <li>Rebalansering: sista handelsdagen varje månad</li>
      </ul>
    </div>
    <div class="space-y-2">
      <p class="doc-h3">PPM-portfölj</p>
      <ul class="doc-ul">
        <li>14 fondtorg-fonder (sektorer, regioner, räntefond)</li>
        <li>Ingen sleeves — rankingbaserad rotation</li>
        <li>Absolut momentum-filter: om momentum &lt; 0 → räntefond</li>
        <li>Handelskostnad: 0 kr (PPM är gratis)</li>
        <li>Rebalansering: sista handelsdagen varje månad</li>
      </ul>
    </div>
  </div>
  <div class="callout mt-2">
    <strong class="text-slate-300">Varför två system?</strong> ETF-portföljen ger bredare exponering mot internationella faktor- och sektorpremiumer. PPM-portföljen är ett separat konto (ingen skatteeffekt vid byten) och drar nytta av AP7 Räntefonds faktiska avkastning som defensivt alternativ, till skillnad från ETF-systemets kontanta 0 % cash.
  </div>
</div>

<!-- ─ 2. DATA ──────────────────────────────────────────────────── -->
<div class="doc-card space-y-3" id="sec-data">
  <p class="doc-h2">2 · Data &amp; priser</p>

  <p class="doc-h3">ETF-priser</p>
  <p class="doc-p">Hämtas dagligen från Yahoo Finance via <code>yfinance</code>-biblioteket. Prisserie = justerat stängningspris (adj. close) — justerat för split och utdelning automatiskt av yfinance. Varje ETF TER-justeras genom att multiplicera daglig avkastning med <code>(1 − TER/252)</code> per handelsdag, vilket ger en rättvisande kostnadsavdragen NAV-kurva.</p>

  <div class="formula">
NAV_justerad(t) = NAV(t-1) × (1 + r_rå(t)) × (1 − TER / 252)
  </div>

  <p class="doc-h3 mt-3">PPM-priser</p>
  <p class="doc-p">Hämtas från Supabase (tabell <code>ppm_all_nav</code>). CSV-filen <code>ppm_all_nav.csv</code> innehåller ~676 000 rader med daglig NAV-data för alla PPM-fonder fr.o.m. år 2000. Eftersom fondtorget inte handlas varje dag forward-fylls NAV till full affärsdagskalender med pandas <code>ffill()</code> — senast kända kurs gäller till nästa handel.</p>

  <p class="doc-h3 mt-3">Benchmark</p>
  <ul class="doc-ul">
    <li><strong class="text-slate-400">ETF:</strong> MSCI World (IWDA.L) med TER-justering</li>
    <li><strong class="text-slate-400">PPM:</strong> AP7 Aktiefond (PPM-nr 581371) — globalt aktieindex med upp till 1,5× hävstång</li>
  </ul>
</div>

<!-- ─ 3. ETF-STRATEGIER ────────────────────────────────────────── -->
<div class="doc-card space-y-4" id="sec-etf">
  <p class="doc-h2">3 · ETF-strategier</p>

  <p class="doc-p">Alla ETF-strategier delar samma sleeve-struktur och regimfilter. Det som skiljer dem är <em>rankingmetrik</em> och hur många ETF:er som väljs per sleeve.</p>

  <p class="doc-h3">3.1 Sleeve-struktur</p>
  <p class="doc-p">Portföljen delas i två lika delar (50 % var):</p>
  <ul class="doc-ul">
    <li><strong class="text-slate-400">Faktor-sleeve:</strong> USA MOM · USA QUAL · USA VAL · USA SMALL · EUR MOM · EUR QUAL · EUR VAL · EUR SMALL</li>
    <li><strong class="text-slate-400">Sektor-sleeve:</strong> IT (IITU.L) · Energy (QDVF.DE) · Healthcare (QDVG.DE) · Consumer Discretionary · Industrials · Consumer Staples · Materials</li>
  </ul>
  <p class="doc-p mt-1">Low-corr-varianten begränsar sektorsleeven till: Energy · Utilities · Consumer Staples · Communication Services · Healthcare — de historiskt minst korrelerade med den breda marknaden i nedgångsfaser.</p>

  <p class="doc-h3">3.2 Regimfilter</p>
  <p class="doc-p">Varje månad jämförs IWDA.L (MSCI World) med IBTS.L (kortränta) på 84 dagars horisont:</p>
  <div class="formula">
risk_on  = return(IWDA.L, 84d) &gt; return(IBTS.L, 84d)
risk_off = annars → sleeve viktas 100 % till IBTS.L (kortränta)
  </div>
  <p class="doc-p mt-1">Filtret stänger ned aktieexponeringen automatiskt när den globala aktiemarknaden underpresterar kortränta de senaste 4 månaderna — ett enkelt men effektivt marknadsregimfilter.</p>

  <p class="doc-h3">3.3 Rankingmetriker</p>
  <table class="doc-tbl mt-1">
    <thead>
      <tr><th>Metrik</th><th>Formel</th><th>Strategier</th></tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>Raw return</strong></td>
        <td><code>ret(t, t-84d) = P(t)/P(t-84) - 1</code></td>
        <td>D1-raw, D2-raw, D1-low-corr, D2-low-corr</td>
      </tr>
      <tr>
        <td><strong>Composite</strong></td>
        <td><code>0.5 × ret(21d) + 0.5 × ret(84d)</code></td>
        <td>D1-composite, D2-composite</td>
      </tr>
      <tr>
        <td><strong>Accel momentum</strong></td>
        <td><code>EMA(5, HL/2) → ROC(84d) + [ROC(0→15d) − ROC(−15→0d)]</code></td>
        <td>D1-accel, D2-accel</td>
      </tr>
    </tbody>
  </table>

  <p class="doc-h3">3.4 Accel-signal i detalj</p>
  <p class="doc-p">Accel-signalen är den mest sofistikerade och bäst presterande metriken. Steg-för-steg:</p>
  <div class="formula">
1. Mjukningsprisserie:  smooth(t) = EMA₅( (High(t) + Low(t)) / 2 )
   (EMA med span=5 — halverar daglig brus utan stor eftersläpning)

2. Råa ROC (Rate of Change):
   roc(t) = smooth(t) / smooth(t − 84) − 1

3. Accelerationssterm (momentum-förändring):
   accel(t) = roc(t) − roc(t − 15)
   Positiv accel → momentumet ökar (trend accelererar)
   Negativ accel → momentumet försvagas (trend avtar)

4. Sammansatt score:
   score(t) = roc(t) + accel(t)
   = roc(t) + roc(t) − roc(t−15)
   = 2×roc(t) − roc(t−15)
  </div>
  <div class="callout callout-amber mt-2">
    <strong class="text-slate-300">Intuition:</strong> En tillgång vars momentum <em>ökar</em> rankas dubbelt belönad. En tillgång med högt absolut momentum men avtagande trend straffas. Det gör att portföljen tenderar att rotera ur tillgångar som "toppar ut" och in i tillgångar som just börjar accelerera.
  </div>

  <p class="doc-h3">3.5 Parametersweep — ETF</p>
  <p class="doc-p">Accel-parametrarna optimerades via 160-run sweep: 5 lookback-fönster (21/42/63/84/126d) × 4 accel-fönster (10/15/21/30d) × 4 EMA-span (3/5/8/10) × D1/D2. Vinnare: <code>ema=5, lb=84, win=15</code> med Sharpe 1.27. Composite-metriken är vinnare i ett separat 40-run DEL1-3 sweep.</p>

  <p class="doc-h3">3.6 Sammanfattning ETF-strategier</p>
  <table class="doc-tbl mt-1">
    <thead>
      <tr><th>Strategi</th><th>Metrik</th><th>Urval</th><th>Sektorer</th><th>CAGR*</th><th>Sharpe*</th><th>MaxDD*</th></tr>
    </thead>
    <tbody>
      <tr><td>D1-raw</td><td>Raw 84d</td><td>Top1+Top1</td><td>Full</td><td>~14%</td><td>~1.13</td><td>~-20%</td></tr>
      <tr><td>D2-raw</td><td>Raw 84d</td><td>Top2+Top2</td><td>Full</td><td>~13%</td><td>~1.10</td><td>~-18%</td></tr>
      <tr><td>D1-composite</td><td>50%×21d + 50%×84d</td><td>Top1+Top1</td><td>Full</td><td>~15%</td><td>~1.18</td><td>~-19%</td></tr>
      <tr><td>D2-composite</td><td>Composite</td><td>Top2+Top2</td><td>Full</td><td>~14%</td><td>~1.17</td><td>~-17%</td></tr>
      <tr><td>D1-accel</td><td>ROC+Accel</td><td>Top1+Top1</td><td>Full</td><td>~16%</td><td>~1.27</td><td>~-19%</td></tr>
      <tr><td>D2-accel</td><td>ROC+Accel</td><td>Top2+Top2</td><td>Full</td><td>~15%</td><td>~1.24</td><td>~-17%</td></tr>
      <tr><td>D1-low-corr</td><td>Raw 84d</td><td>Top1+Top1</td><td>Defensiv</td><td>~18%</td><td>~1.30</td><td>~-14%</td></tr>
      <tr><td>D2-low-corr</td><td>Raw 84d</td><td>Top2+Top2</td><td>Defensiv</td><td>~16%</td><td>~1.26</td><td>~-13%</td></tr>
    </tbody>
  </table>
  <p class="text-xs text-muted mt-1">* Approximativa värden — exakta siffror beror på vald tidsperiod. Se Dashboard för aktuella tal.</p>
</div>

<!-- ─ 4. PPM-STRATEGI ──────────────────────────────────────────── -->
<div class="doc-card space-y-4" id="sec-ppm">
  <p class="doc-h2">4 · PPM-strategi — top-3 + absolut momentum</p>
  <span class="doc-badge badge-ppm">CAGR 23.7% · Sharpe 1.92 · MaxDD −7.8%</span>

  <p class="doc-h3">4.1 Universum</p>
  <table class="doc-tbl mt-1">
    <thead><tr><th>PPM-nr</th><th>Fondnamn</th><th>Roll</th></tr></thead>
    <tbody>
      <tr><td>581371</td><td>AP7 Aktiefond</td><td>Passiv global med hävstång — möjligt rotationsval OCH benchmark</td></tr>
      <tr><td>283408</td><td>Swedbank Robur Technology A</td><td>Sektorfond — IT</td></tr>
      <tr><td>644005</td><td>Handelsbanken Hälsovård Tema A1</td><td>Sektorfond — Healthcare</td></tr>
      <tr><td>517748</td><td>BlackRock World Energy A2</td><td>Sektorfond — Energy</td></tr>
      <tr><td>481911</td><td>BlackRock World Mining A2</td><td>Sektorfond — Mining &amp; Materials</td></tr>
      <tr><td>479550</td><td>Seligson Global Top 25 Brands A</td><td>Sektorfond — Consumer Staples/Brands</td></tr>
      <tr><td>768556</td><td>BlackRock US Basic Value A2</td><td>Faktor — USA Värde</td></tr>
      <tr><td>916354</td><td>SEB Nordamerikafond Små och Medelstora A</td><td>Faktor — USA Småbolag</td></tr>
      <tr><td>456475</td><td>Länsförsäkringar USA Aktiv A</td><td>Faktor — USA Kvalitet</td></tr>
      <tr><td>163923</td><td>Öhman Global Growth A</td><td>Faktor — USA Tillväxt</td></tr>
      <tr><td>182759</td><td>Lannebo Europa Småbolag A</td><td>Faktor — Europa Småbolag</td></tr>
      <tr><td>538462</td><td>AMF Aktiefond Europa</td><td>Faktor — Europa Värde</td></tr>
      <tr><td>162099</td><td>Storebrand Global Multifactor A</td><td>Faktor — Global multifaktor</td></tr>
      <tr><td>545541</td><td>AP7 Räntefond</td><td>Defensivt alternativ — väljs av abs-mom-filter</td></tr>
    </tbody>
  </table>

  <p class="doc-h3">4.2 Accel-signal (PPM)</p>
  <p class="doc-p">Identisk logik som ETF-systemets accel-signal med parametrar optimerade via sweep på rättad data (jun 2026):</p>
  <div class="formula">
1. Mjukningsserie:  smooth(t) = EMA₁₀( NAV(t) )
   (EMA med span=10 på PPM:s dagliga NAV-kurs)

2. ROC (4-månaders momentum):
   roc(t) = smooth(t) / smooth(t − 84) − 1
   (84 handelsdagar ≈ 4 månader — synkar med D1-accel)

3. Acceleration (30-dagars momentum-förändring):
   accel(t) = roc(t) − roc(t − 30)

4. Accel-score:
   score(t) = roc(t) + accel(t)
  </div>

  <p class="doc-h3">4.3 ETF-cash-synk</p>
  <p class="doc-p">Varje månad kontrolleras om D1-accel (ETF-portföljens primärstrategi) är 100 % i cash via sitt regimfilter (IWDA.L vs IBTS.L). Om ja → PPM håller 100 % AP7 Räntefond den månaden, oavsett momentum-signal:</p>
  <div class="formula">
om D1-accel är i cash (månad m):
    portfölj = 100 % AP7 Räntefond
annars:
    portfölj = top-3 fonder per accel-score, likviktade (33.3 % var)
  </div>
  <div class="callout callout-cyan mt-2">
    <strong class="text-slate-300">Varför ETF-cash sync istället för absolut momentum?</strong> Sweepen visade att ETF-regimfiltret (IWDA vs IBTS, 84d) är ett starkare defensivt signal än PPM:s absoluta momentum-filter (raw ROC &lt; 0). ETF-cash sync gav Sharpe 1.92 vs 1.54 för standalone abs-mom — och synkar de två systemen så att de inte slår varandra i onödan.
  </div>

  <p class="doc-h3">4.4 Parametersweep — PPM</p>
  <p class="doc-p">1 440 konfigurationer testades i <code>sweep_ppm_curated.py</code>, omkörd med rättad data juni 2026:</p>
  <ul class="doc-ul">
    <li>EMA-span: 3, 5, 10</li>
    <li>ROC-fönster: 42d, 63d, 84d, 126d (2m, 3m, 4m, 6m)</li>
    <li>Accel-fönster: 10d, 15d, 30d</li>
    <li>Top-N: 1, 2, 3</li>
    <li>DD-stop: inget, −15 %, −20 %</li>
    <li>Absolut momentum: av/på</li>
    <li>ETF-cash-synk: av/på</li>
  </ul>
  <p class="doc-p mt-1">Vinnarkonfiguration på Sharpe: <strong class="text-slate-400">EMA10 · ROC84d · accel30d · top3 · ETF-cash sync</strong>. CAGR 23.7 %, Sharpe 1.92, MaxDD −7.8 %. ETF-cash sync dominerar hela topp-20 — alla vinnarkonfigurationer har ETF-cash aktiverat.</p>

  <p class="doc-h3">4.6 Varför PPM slår ETF-portföljen</p>
  <ul class="doc-ul">
    <li><strong class="text-slate-400">Sektorreinhet:</strong> PPM:s Mining-fond är 100 % mining. ETF-universumet har Materials-sektor som spädas ut av cement, glas m.m.</li>
    <li><strong class="text-slate-400">Räntefond vs cash:</strong> AP7 Räntefond ger faktisk avkastning under defensiva perioder (obligationsränta), ETF-systemet är 100 % kontant (0 %).</li>
    <li><strong class="text-slate-400">Periodseffekt:</strong> 2020–2026 är ett utmärkt momentum-klimat för sektorer (tech-boom, energichock, mining-supercykel).</li>
    <li><strong class="text-slate-400">0 % handelskostnad:</strong> PPM har inga transaktionstillägg — ETF-systemet betalar 15 bps per sida per byte.</li>
  </ul>
</div>

<!-- ─ 5. BACKTEST-METODOLOGI ──────────────────────────────────── -->
<div class="doc-card space-y-3" id="sec-backtest">
  <p class="doc-h2">5 · Backtest-metodologi</p>

  <p class="doc-h3">5.1 NAV-beräkning</p>
  <p class="doc-p">Backtestet simulerar en portfölj som startar med 100 000 kr. Varje månad:</p>
  <div class="formula">
1. Bestäm innehav (picks) per sista affärsdag i månaden
2. Beräkna månadsavkastning baserat på <em>föregående månads</em> innehav:
   ret = Σ ( P(dt) / P(dt_prev) − 1 )  ×  (1 / |holdings|)
   (likviktad, ingen hävstång)
3. Uppdatera NAV: NAV = NAV × (1 + ret)
4. Uppdatera innehav till årets nya picks (byten sker i månadsslut)
  </div>
  <div class="callout mt-2">
    <strong class="text-slate-300">Look-ahead bias:</strong> Signalen beräknas på stängningspris för sista handelsdagen i månaden. Samma pris används som "ingångspris" för nästa månad. Det finns ingen look-ahead bias — vi handlar alltid i nästa periods öppning i verkligheten, men skillnaden mot stängning är försumbar vid månadsrebalansering.
  </div>

  <p class="doc-h3">5.2 Nyckeltal</p>
  <div class="formula">
CAGR  = (NAV_slut / NAV_start) ^ (1 / n_år) − 1

Sharpe = (mean(r_mån) × 12) / (std(r_mån) × √12)
  (riskfri ränta = 0, annualisering via månadsdata)

MaxDD = min( (NAV(t) − max(NAV[0:t])) / max(NAV[0:t]) )
  (lägsta dradown från löpande toppkurs)
  </div>

  <p class="doc-h3">5.3 Rebalansering</p>
  <p class="doc-p">Rebalansering sker alltid månadsvis om innehaven förändras. Om exakt samma fonder väljs nästa månad hålls positionerna och vikterna förblir oförändrade (eventuell drift korrigeras ej intra-månad). Empiriskt bekräftat: det finns noll skillnad i metrics om man alltid eller aldrig rebalanserar när innehav är identiska.</p>

  <p class="doc-h3">5.4 Transaktionskostnader (ETF)</p>
  <p class="doc-p">Varje köp/sälj belastas med 15 bps (0.15 %) per sida. Beräknas på den andel av portföljvärdet som omsätts månadsvis. PPM har inga transaktionskostnader.</p>

  <p class="doc-h3">5.5 Warumup-period</p>
  <p class="doc-p">Ingen signal kan beräknas förrän det finns tillräckligt med historik. PPM kräver minst <code>ROC_DAYS + 2 × ACCEL_WIN + 10 = 63 + 20 + 10 = 93 handelsdagar</code> per fond. ETF kräver ~134 handelsdagar. Backtestet börjar med det datum då tillräckliga data finns för alla ingående positioner.</p>
</div>

<!-- ─ 6. MONTE CARLO ───────────────────────────────────────────── -->
<div class="doc-card space-y-3" id="sec-montecarlo">
  <p class="doc-h2">6 · Monte Carlo-analys</p>
  <span class="doc-badge badge-mc">10 000 bootstrap-simuleringar</span>

  <p class="doc-h3">6.1 Metodik</p>
  <p class="doc-p">Monte Carlo-analysen testar strategins robusthet mot urvalsbias ("har vi råkat backtesta på ett ovanligt bra marknadsklimat?"). Metodiken är bootstrap-resampling med återläggning:</p>
  <div class="formula">
För i = 1 … 10 000:
  s = slumpmässigt urval (med återläggning) av N månadsavkastningar
      (N = faktisk antal månader i backtestet)

  CAGR_i  = prod(1 + s)^(12/N) − 1
  Sharpe_i = mean(s) × 12 / (std(s) × √12)
  MaxDD_i  = min drawdown för kumulativ prod(1 + s)

Rapportera percentilfördelning: P5, P25, P50, P75, P95
  </div>
  <div class="callout callout-green mt-2">
    <strong class="text-slate-300">Vad bootstrap-MC mäter:</strong> Variansen i utfall om vi dragit ett <em>annat</em> urval av månader ur samma fördelning. Det testar inte om marknadsregimerna är representativa — det är ett komplement till out-of-sample-test, inte en ersättning.
  </div>

  <p class="doc-h3">6.2 PPM-resultat (top-3 + abs-mom)</p>
  <table class="doc-tbl mt-1">
    <thead><tr><th>Metrik</th><th>P5</th><th>P25</th><th>P50</th><th>P75</th><th>P95</th></tr></thead>
    <tbody>
      <tr><td>CAGR</td><td>+11.5%</td><td>+20.2%</td><td>+26.5%</td><td>+33.1%</td><td>+42.8%</td></tr>
      <tr><td>Sharpe</td><td>+0.71</td><td>+1.08</td><td>+1.35</td><td>+1.63</td><td>+2.05</td></tr>
      <tr><td>MaxDD</td><td>−21.4%</td><td>−14.2%</td><td>−10.1%</td><td>−7.2%</td><td>−4.5%</td></tr>
    </tbody>
  </table>
  <ul class="doc-ul mt-2">
    <li><strong class="text-slate-400">P(slår AP7):</strong> 88.2 % av simuleringar</li>
    <li><strong class="text-slate-400">P(CAGR &gt; 0):</strong> 99.4 %</li>
    <li><strong class="text-slate-400">P(CAGR &gt; 15%):</strong> 83.7 %</li>
    <li><strong class="text-slate-400">P(DD &lt; −15%):</strong> 13.1 % vs AP7:s 48 %</li>
  </ul>
</div>

<!-- ─ 7. SCREENING ─────────────────────────────────────────────── -->
<div class="doc-card space-y-3" id="sec-screening">
  <p class="doc-h2">7 · Screening — kandidatövervakning</p>

  <p class="doc-p">Screening-systemet tillåter löpande bevakning av ETF-kandidater som ännu inte ingår i portföljen. Syftet är att tidigt identifiera nya sektor- eller faktortrender som borde inkluderas i framtida portföljversioner.</p>

  <p class="doc-h3">7.1 Beräkning</p>
  <p class="doc-p">Kandidaterna utvärderas med exakt samma accel-signal som D1-accel (EMA5, ROC84d, accel15d). Signalen beräknas på senaste tillgängliga data och jämförs med portföljens nuvarande innehav:</p>
  <div class="formula">
portfolio_threshold = min(score(t) för ETF:er i nuvarande D1-accel-allokering)

would_select = score(kandidat, t) &gt; portfolio_threshold
  </div>

  <p class="doc-h3">7.2 Tolkning</p>
  <ul class="doc-ul">
    <li><strong class="text-slate-400">Grön (Would Select):</strong> Kandidatens accel-score överstiger den svagaste nuvarande portföljmedlemmen — den skulle väljas om den vore i universumet.</li>
    <li><strong class="text-slate-400">Grå (Watching):</strong> Kandidaten har positiv momentum men inte tillräcklig styrka att tränga ut nuvarande innehav.</li>
    <li><strong class="text-slate-400">Rött:</strong> Negativ eller svag momentum — ej intressant just nu.</li>
  </ul>

  <p class="doc-h3">7.3 Nuvarande kandidater</p>
  <p class="doc-p">Kandidatlistan lagras i <code>dashboard/backend/screening_config.json</code> och kan utökas via Screening-fliken. Initiala kandidater inkluderar: SEMI.DE (halvledare), AIAI.DE (AI), IQQH.DE (clean energy), DFND.SW (defense), NDIA.DE (Indien), XDJP.DE (Japan), BNKS.DE (europeiska banker), ISPY.DE (S&P 500 med collar), 2B7A.DE (aggregated bonds), QDVH.DE (utilities).</p>
</div>

<!-- ─ 8. NYCKELRESULTAT ────────────────────────────────────────── -->
<div class="doc-card space-y-4" id="sec-findings">
  <p class="doc-h2">8 · Nyckelresultat &amp; insikter</p>

  <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
    <div class="space-y-3">
      <p class="doc-h3">Full PPM-sweep (566 fonder) — förkastades</p>
      <p class="doc-p">Initial approach med alla ~566 PPM-fonder och kategori-constraints producerade negativa CAGR trots korrekt implementering. Orsak: 2022 björnmarknad straffar momentumstrategier hårt på nisch- och exotiska fonder (guld, Latinamerika, Östeuropa). Lösning: kuraterat 14-fonds universum med sektor- och faktorfonder av hög kvalitet.</p>

      <p class="doc-h3">Diversifiering hjälper inte alltid</p>
      <p class="doc-p">Top-3 ger <em>sämre</em> MaxDD än top-1 utan absolut momentum-filter (korrelerade sektorer faller tillsammans). Det är abs-mom-filtret — inte diversifiering — som ger DD-skyddet. Top-3 ger bättre Sharpe via mer stabil avkastning, inte lägre risk.</p>
    </div>
    <div class="space-y-3">
      <p class="doc-h3">EMA-smoothing vs råa priser</p>
      <p class="doc-p">EMA(5) på PPM-fondernas NAV-kurs reducerar "brus" i signalen. Sweep bekräftade att EMA5 konsekvent ger bättre Sharpe än EMA3 (för reaktiv) eller EMA10 (för trög) för 63-dagars ROC. Accel-fönstret 10d är optimalt — snabbare än 15d men inte så snabbt att det skapar onödig handel.</p>

      <p class="doc-h3">ETF-cash-synk: lägre DD, lägre CAGR</p>
      <p class="doc-p">Att synka PPM med D1-acelels cash-signal ger MaxDD −9.4 % (bättre) men CAGR 23.9 % (lägre). Abs-mom-filtret allena ger MaxDD −12.0 % men CAGR 26.6 %. Val beror på individuell riskaptit. Kombination av båda (abs-mom + ETF-cash) ger ingen ytterligare förbättring utöver enbart ETF-cash.</p>
    </div>
  </div>

  <div class="callout callout-green mt-3">
    <strong class="text-slate-300">Sammanfattning:</strong> Den optimala PPM-konfigurationen (EMA10/ROC84/accel30/top3/ETF-cash sync) levererar Sharpe 1.92 och CAGR 23.7 % med MaxDD −7.8 % — väsentligt bättre än AP7 Aktiefond (Sharpe 1.23, CAGR 15.8 %, MaxDD −16.7 %) på alla tre nyckeltal. ETF-cash sync är den viktigaste enskilda innovationen: genom att dela regimfilter med D1-accel synkas de defensiva perioderna och risken minskar utan att avkastningen offras.
  </div>
</div>

<!-- ─ 9. SAMMANSATT MOMENTUM — AKTIER ────────────────────────────── -->
<div class="doc-card space-y-4" id="sec-sammansatt">
  <p class="doc-h2">9 · Sammansatt Momentum — Aktiestrategier</p>

  <p class="doc-p">BörsLabbet Sammansatt Momentum är en svensk aktiestrategimodell baserad på kombinerad rankingpoäng av tre momentum-horisonter. Strategin implementeras här på fyra universum: OMXS, STOXX 600, S&P 500 och ett globalt kombinerat universum.</p>

  <p class="doc-h3">9.1 Scoreformel</p>
  <div class="formula">
score(t) = mean( ret_3m, ret_6m, ret_12m )

där:
  ret_Xm = P(t − 21) / P(t − 21 − LB) − 1
  LB = 63d (3m), 126d (6m), 252d (12m)
  21 handelsdagars "skip" (1 månads eftersläpning)
  → undviker mean-reversion på kort sikt (Jegadeesh 1990)

Absolut momentumfilter: om score(t) ≤ 0 → CASH den månaden
  </div>

  <p class="doc-p">Skip-perioden (21 dagar) är avgörande: utan den fångar strategin kortsiktig mean-reversion — aktier som rasat häftigt nyligen rankas falskt högt. Skipet börjar mäta 1 månad tillbaka och undviker denna effekt.</p>

  <p class="doc-h3">9.2 Backtest-parametrar (gemensamma)</p>
  <div class="kv-row"><span class="kv-key">Skip (1M lag)</span><span class="kv-val">21 handelsdagar</span></div>
  <div class="kv-row"><span class="kv-key">Lookback 3M</span><span class="kv-val">63 handelsdagar</span></div>
  <div class="kv-row"><span class="kv-key">Lookback 6M</span><span class="kv-val">126 handelsdagar</span></div>
  <div class="kv-row"><span class="kv-key">Lookback 12M</span><span class="kv-val">252 handelsdagar</span></div>
  <div class="kv-row"><span class="kv-key">Min-data per aktie</span><span class="kv-val">294 handelsdagar (21+252+21 warm-up)</span></div>
  <div class="kv-row"><span class="kv-key">Rebalansering</span><span class="kv-val">Sista handelsdagen varje månad</span></div>
  <div class="kv-row"><span class="kv-key">Handelskostnad</span><span class="kv-val">30 bps (0.30 %) per transaktion (köp+sälj)</span></div>
  <div class="kv-row"><span class="kv-key">Viktning</span><span class="kv-val">Likviktat bland valda aktier</span></div>
  <div class="kv-row"><span class="kv-key">Startkapital</span><span class="kv-val">100 000 kr</span></div>
  <div class="kv-row"><span class="kv-key">Backtest-period</span><span class="kv-val">2006–2026 (beroende på datatillgång)</span></div>

  <p class="doc-h3">9.3 OMXS — Svenska large-cap-aktier</p>
  <div class="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-1">
    <div>
      <p class="doc-h3" style="color:#f97316">Universum &amp; filter</p>
      <ul class="doc-ul">
        <li>141 svenska aktier med marknadsvärde &gt; 2 miljarder SEK</li>
        <li>Priser i SEK, konverterade till USD via SEKUSD=X för jämförelse</li>
        <li>Inkluderar Stockholmsbörsen och Helsingforsbörsen (HEX)</li>
        <li><strong class="text-orange-400">Survivorship bias:</strong> universumet är statiskt (nuvarande large-caps) — bolag som gick i konkurs eller avnoterades finns ej</li>
      </ul>
    </div>
    <div>
      <p class="doc-h3" style="color:#f97316">Resultat</p>
      <table class="doc-tbl mt-1">
        <thead><tr><th>Top-N</th><th>CAGR</th><th>Sharpe</th><th>MaxDD</th></tr></thead>
        <tbody>
          <tr><td>Top-5</td><td>+33.7%</td><td>1.26</td><td>-40%</td></tr>
          <tr><td>Top-7</td><td>+30.2%</td><td>1.19</td><td>-38%</td></tr>
          <tr><td>Top-10</td><td>+26.8%</td><td>1.14</td><td>-37%</td></tr>
        </tbody>
      </table>
      <p class="text-xs text-muted mt-1">Benchmark: OMXS30 (^OMX)</p>
    </div>
  </div>

  <p class="doc-h3">9.4 Euro STOXX 600 — Europeiska aktier</p>
  <div class="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-1">
    <div>
      <p class="doc-h3" style="color:#c026d3">Universum &amp; filter</p>
      <ul class="doc-ul">
        <li>296 europeiska aktier ur STOXX 600-indexet</li>
        <li>Priser i EUR (lokal notering), konverterade till USD via EURUSD=X</li>
        <li>Inkluderar Xetra (DE), Euronext (FR/NL/BE), Milano (IT), Madrid (ES), m.fl.</li>
        <li><strong class="text-purple-400">Survivorship bias:</strong> statiskt universum — exkluderar avnoterade och sämre bolag</li>
      </ul>
    </div>
    <div>
      <p class="doc-h3" style="color:#c026d3">Resultat</p>
      <table class="doc-tbl mt-1">
        <thead><tr><th>Top-N</th><th>CAGR</th><th>Sharpe</th><th>MaxDD</th></tr></thead>
        <tbody>
          <tr><td>Top-5</td><td>+28.2%</td><td>1.09</td><td>-41%</td></tr>
          <tr><td>Top-7</td><td>+25.1%</td><td>1.06</td><td>-40%</td></tr>
          <tr><td>Top-10</td><td>+21.4%</td><td>1.01</td><td>-39%</td></tr>
        </tbody>
      </table>
      <p class="text-xs text-muted mt-1">Benchmark: EXSA.DE (STOXX 600 ETF, USD)</p>
    </div>
  </div>

  <p class="doc-h3">9.5 S&amp;P 500 — Amerikanska aktier (PIT)</p>
  <div class="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-1">
    <div>
      <p class="doc-h3" style="color:#34d399">Universum &amp; filter</p>
      <ul class="doc-ul">
        <li>500 aktier med <strong class="text-emerald-400">point-in-time (PIT) membership</strong></li>
        <li>Priser i USD (ingen FX-konvertering)</li>
        <li>PIT-listan innehåller start- och slutdatum för varje akties S&P 500-medlemsskap — vid varje rebalansering används bara aktier som faktiskt var i index den månaden</li>
        <li><strong class="text-emerald-400">Ingen survivorship bias</strong> — den korrektaste av de tre universen</li>
        <li>Datat sträcker sig bakåt till ~2015 för flertalet aktier (begränsad historik)</li>
      </ul>
    </div>
    <div>
      <p class="doc-h3" style="color:#34d399">Resultat</p>
      <table class="doc-tbl mt-1">
        <thead><tr><th>Top-N</th><th>CAGR</th><th>Sharpe</th><th>MaxDD</th></tr></thead>
        <tbody>
          <tr><td>Top-5</td><td>+24.7%</td><td>0.82</td><td>-43%</td></tr>
          <tr><td>Top-7</td><td>+22.3%</td><td>0.79</td><td>-42%</td></tr>
          <tr><td>Top-10</td><td>+19.8%</td><td>0.77</td><td>-41%</td></tr>
        </tbody>
      </table>
      <p class="text-xs text-muted mt-1">Benchmark: SPY. Lägre Sharpe förklaras delvis av kortare historik och avsaknad av survivorship bias.</p>
    </div>
  </div>

  <p class="doc-h3">9.6 Global — SP500 + STOXX + OMXS kombinerat</p>
  <p class="doc-p">Det globala universumet kombinerar alla tre regioner i en gemensam rangordning. Valutaomräkning sker till USD för rättvis jämförelse. För att undvika dominans av ett enskilt land eller sektor gäller ett tak på max 3 aktier per universum i Top-7 (anpassas med N).</p>

  <div class="formula">
Globalt pool: OMXS (141) + STOXX (296) + SP500 (500) = 937 aktier

FX-konvertering:
  OMXS-aktier × SEKUSD(t)  → USD-pris
  STOXX-aktier × EURUSD(t) → USD-pris
  SP500-aktier              → redan i USD

Urval Top-7 med cap: max 3 per universum
  → minst 1 aktie från varje region om de har positivt momentum
  → undviker 100% koncentration i ett enskilt momentum-klimat
  </div>

  <div class="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-2">
    <div>
      <p class="doc-h3">Resultat — Global</p>
      <table class="doc-tbl mt-1">
        <thead><tr><th>Strategi</th><th>CAGR</th><th>Sharpe</th><th>MaxDD</th></tr></thead>
        <tbody>
          <tr><td>Top-7 (max 3/univ)</td><td>+39.7%</td><td>1.33</td><td>-35%</td></tr>
          <tr><td>Top-10 (max 4/univ)</td><td>+37.0%</td><td>1.35</td><td>-36%</td></tr>
          <tr><td>Top-15 (max 5/univ)</td><td>+29.7%</td><td>1.21</td><td>-39%</td></tr>
          <tr><td><em>Ingen cap (original)</em></td><td><em>+38.6%</em></td><td><em>1.26</em></td><td><em>-39%</em></td></tr>
        </tbody>
      </table>
    </div>
    <div>
      <p class="doc-h3">Varför cap förbättrar Sharpe</p>
      <ul class="doc-ul">
        <li>Utan cap dominerar en enda region/sektor när den toppar — ex. sju halvledar-aktier (2025)</li>
        <li>Cap 3/univ tvingar regional diversifiering → jämnare avkastning → högre Sharpe trots liknande CAGR</li>
        <li>MDD förbättras från -39% till -35% — cap är ett implicit diversifieringsskydd</li>
      </ul>
    </div>
  </div>

  <div class="callout callout-amber mt-3">
    <strong class="text-slate-300">Viktigt om bias:</strong> OMXS och STOXX har survivorship bias (statiska universum utan avnoterade bolag). SP500 är PIT-korrekt. De höga globala CAGR-talen är troligen 5–8 procentenheter överdrivna jämfört med verkliga utfall. Trots detta är Sharpe 1.33 och regional spridning genuint värdefullt — strategin identifierar korrekt vilken region/sektor som har starkast momentum och roterar dit.
  </div>

  <p class="doc-h3">9.7 Jämförelse av universum</p>
  <table class="doc-tbl mt-1">
    <thead><tr><th>Universum</th><th>Antal aktier</th><th>Valuta</th><th>Bias</th><th>Historik</th><th>Top-5/7 CAGR</th><th>Top-5/7 Sharpe</th></tr></thead>
    <tbody>
      <tr><td>OMXS (Top-5)</td><td>141</td><td>SEK→USD</td><td>Survivorship</td><td>2006–2026</td><td>+33.7%</td><td>1.26</td></tr>
      <tr><td>STOXX (Top-5)</td><td>296</td><td>EUR→USD</td><td>Survivorship</td><td>2006–2026</td><td>+28.2%</td><td>1.09</td></tr>
      <tr><td>SP500 (Top-5)</td><td>500 (PIT)</td><td>USD</td><td>Ingen</td><td>~2015–2026</td><td>+24.7%</td><td>0.82</td></tr>
      <tr><td>Global (Top-7)</td><td>937</td><td>USD</td><td>Delvis</td><td>2006–2026</td><td>+39.7%</td><td>1.33</td></tr>
    </tbody>
  </table>

  <div class="callout callout-cyan mt-3">
    <strong class="text-slate-300">Slutsats om aktiestrategier vs ETF-strategier:</strong> Sammansatt Momentum på enskilda aktier ger väsentligt högre CAGR (24–40%) jämfört med ETF-rotationsstrategierna (13–18%). Priset är högre volatilitet, djupare drawdowns och mer koncentrerade portföljer (5–10 aktier). ETF-strategierna är bättre lämpade för stabila kassaflöden och lägre psykologisk belastning — aktiestrategierna för den som accepterar 30–40% volatilitet i utbyte mot höga genomsnittliga avkastningar.
  </div>
</div>

<!-- ─ 10. AUTOMATISK DATAUPPDATERING ─────────────────────────────── -->
<div class="doc-card space-y-4" id="sec-autoupdate">
  <p class="doc-h2">10 · Automatisk datauppdatering</p>

  <p class="doc-p">Dashboarden hämtar och beräknar all data autonomt på servern (VPS). Ingen manuell åtgärd krävs för löpande drift — systemet håller sig uppdaterat med marknadsdata och omberäknar strategisignalerna enligt schema nedan.</p>

  <p class="doc-h3">10.1 Uppdateringsschema</p>
  <table class="doc-tbl mt-1">
    <thead>
      <tr>
        <th>Tid (CET)</th><th>Frekvens</th><th>Vad händer</th><th>Data som uppdateras</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td class="font-mono">09:30</td><td>Vardagar</td>
        <td>Hämtar PPM NAV (föregående dag)</td>
        <td>PPM-kurser → PPM-signal → <code>data.json</code></td>
      </tr>
      <tr>
        <td class="font-mono">18:00</td><td>Vardagar</td>
        <td>Hämtar PPM NAV (dagens stängning, tillgänglig efter ~17:30)</td>
        <td>PPM-kurser → PPM-signal → <code>data.json</code></td>
      </tr>
      <tr>
        <td class="font-mono">22:30</td><td>Vardagar</td>
        <td>Hämtar ETF-priser från Yahoo Finance</td>
        <td>ETF-priser → D1/D2/PPM-strategier → screening → <code>data.json</code></td>
      </tr>
      <tr>
        <td class="font-mono">22:45</td><td>Vardagar</td>
        <td>Hämtar aktiekurser (inkrementellt) → om ny månad: kör inkrementell rebalansering (~1 min) → annars: förlänger NAV-kurvan för nuvarande innehav</td>
        <td>Aktiepriser + ny allokering (om månadsskifte) eller daglig NAV-uppdatering</td>
      </tr>
      <tr>
        <td class="font-mono">01:00</td><td>1:a varje månad</td>
        <td>Säkerhetsnät: kör inkrementell rebalansering om inte redan gjord (täcker fall där sista handelsdagen är fredag/helg)</td>
        <td>Ny allokering klar senast 01:30 — 7.5h innan europeiska marknader öppnar</td>
      </tr>
    </tbody>
  </table>
  <div class="callout callout-cyan mt-2">
    <strong class="text-slate-300">Timing:</strong> Priser hämtas dagligen (22:45) för alla ~1 200 instrument. När en ny månad detekteras kör 22:45-jobbet en inkrementell rebalansering direkt — tar ~1 minut istället för 30 minuter eftersom bara de senaste 320 dagarna per aktie behöver laddas. Om sista handelsdagen råkar vara helg körs säkerhetsnätet kl 01:00 natten mot den 1:a. Allokeringen är alltid klar långt innan europeiska marknader öppnar 09:00.
  </div>

  <p class="doc-h3">10.2 Vad som uppdateras per datakälla</p>
  <div class="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-1">
    <div>
      <p class="doc-h3">ETF-priser (daglig)</p>
      <ul class="doc-ul">
        <li>Alla ETF:er i faktor- och sektor-sleeve</li>
        <li>Benchmark: IWDA.L, IBTS.L, ^OMX, ^GSPC, ^IXIC</li>
        <li>Screening-kandidater (konfigurerbar lista)</li>
        <li>Inkrementell: hämtar bara bars sedan senast</li>
        <li>Sparas i SQLite-databasen (<code>dashboard.db</code>)</li>
      </ul>
    </div>
    <div>
      <p class="doc-h3">PPM-kurser (daglig)</p>
      <ul class="doc-ul">
        <li>Hämtas från Pensionsmyndighetens öppna API</li>
        <li>14 fonder i PPM-universumet</li>
        <li>Inkrementell: bara nya datum sedan senaste hämtning</li>
        <li>Vid månadsslut: PPM-strategisignalen beräknas om med ny data</li>
        <li>Manuell import via Loggar-fliken (CSV/Excel)</li>
      </ul>
    </div>
    <div>
      <p class="doc-h3">Aktiekurser (månadsvis)</p>
      <ul class="doc-ul">
        <li>141 OMXS large-cap-aktier (SEK)</li>
        <li>296 STOXX 600-aktier (EUR, lokal valuta)</li>
        <li>~1 200 SP500-aktier, alla historiska medlemmar</li>
        <li>Valutakurser: SEKUSD=X, EURUSD=X</li>
        <li>Gate-ETF:er: SPY, EXSA.DE, ^OMX</li>
        <li>Inkrementell: laddar hem bara perioden sedan senaste fil</li>
        <li>Sparas som komprimerade CSV-filer (<code>.csv.gz</code>)</li>
      </ul>
    </div>
    <div>
      <p class="doc-h3">Backtest-beräkning (månadsvis)</p>
      <ul class="doc-ul">
        <li>Kör om hela Sammansatt Momentum-backtesten för alla fyra universum</li>
        <li>Beräkningstid: ~15–30 min (937 aktier × 20 år × daglig data)</li>
        <li>Uppdaterar innehåll och grafer på OMXS/STOXX/SP500/Global-sidorna</li>
        <li>Startar automatiskt vid deploy om resultaten är äldre än 35 dagar</li>
      </ul>
    </div>
  </div>

  <p class="doc-h3">10.3 Manuell uppdatering</p>
  <table class="doc-tbl mt-1">
    <thead><tr><th>Åtgärd</th><th>API-anrop</th><th>Effekt</th></tr></thead>
    <tbody>
      <tr>
        <td>Hämta ETF+PPM och räkna om</td>
        <td><code>POST /api/refresh-data</code></td>
        <td>Full ETF+PPM fetch + engine-kör (~2 min)</td>
      </tr>
      <tr>
        <td>Räkna om utan ny data</td>
        <td><code>POST /api/recalculate</code></td>
        <td>Kör engine på befintlig data (~30 sek)</td>
      </tr>
      <tr>
        <td>Hämta aktiedata + backtest</td>
        <td><code>POST /api/recalculate-stocks</code></td>
        <td>Full aktie-fetch + alla 4 backtests (~30–60 min)</td>
      </tr>
      <tr>
        <td>Importera PPM-data manuellt</td>
        <td><code>POST /api/import-ppm</code></td>
        <td>Ladda upp CSV/Excel från Pensionsmyndigheten</td>
      </tr>
    </tbody>
  </table>

  <div class="callout callout-green mt-3">
    <strong class="text-slate-300">Praktisk implikation för månadsallokeringar:</strong> Aktiestrategiernas signal (OMXS/STOXX/SP500/Global) uppdateras den 2:a i varje månad med föregående månads stängningspriser. Månadsallokeringen för ETF/PPM uppdateras kl 22:30 sista handelsdagen i månaden. Man kan alltså se den aktuella signalen för alla strategier redan på morgonen den 2:a.
  </div>

  <p class="doc-h3">10.4 Datastatus &amp; loggning</p>
  <p class="doc-p">Alla automatiska jobb loggar till <code>dashboard.log</code> på servern. Loggar är tillgängliga i realtid via Loggar-fliken i navigeringen. Systemstatus (engine körandes, senaste beräkning, nästa schemalagda jobb) visas via <code>GET /api/status</code>.</p>
</div>
`;
}

// ── Global page ────────────────────────────────────────────────────
// New 4-universe configs (top9/12/15). Old keys (top7/10) kept for backwards compat.
const GLOBAL_STRATS = [
  { key: "global_top9",  label: "Global Top-9 (4 univ)",  color: "#facc15" },
  { key: "global_top12", label: "Global Top-12 (4 univ)", color: "#fbbf24" },
  { key: "global_top15", label: "Global Top-15 (4 univ)", color: "#f59e0b" },
  // Old 3-universe keys still shown if new ones absent
  { key: "global_top7",  label: "Global Top-7 (3 univ)",  color: "#facc15" },
  { key: "global_top10", label: "Global Top-10 (3 univ)", color: "#fbbf24" },
];
let globalActiveKeys = new Set(["global_top9", "global_top12", "global_top7", "global_top10"]);

function renderGlobalPage() {
  if (!DATA) return;
  const strategies = DATA.strategies || {};
  const available  = GLOBAL_STRATS.filter(s => strategies[s.key]);
  if (!available.length) {
    document.getElementById("global-stats").innerHTML =
      `<p class="text-xs text-muted italic px-1">Ingen global data tillgänglig.</p>`;
    return;
  }
  _buildGlobalToggles(available);
  _renderGlobalChart(available);
  _renderGlobalSignal(available);
  _renderGlobalStats(available);
}

function _buildGlobalToggles(available) {
  const el = document.getElementById("global-toggles");
  if (!el) return;
  el.innerHTML = "";
  available.forEach(({ key, label, color }) => {
    const on  = globalActiveKeys.has(key);
    const btn = document.createElement("button");
    btn.className = "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-all";
    applyToggleStyle(btn, on, color);
    const dot = document.createElement("span"); dot.className = "w-2 h-2 rounded-full flex-shrink-0";
    dot.style.background = color;
    btn.appendChild(dot); btn.appendChild(document.createTextNode(label));
    btn.addEventListener("click", () => {
      if (globalActiveKeys.has(key)) globalActiveKeys.delete(key); else globalActiveKeys.add(key);
      applyToggleStyle(btn, globalActiveKeys.has(key), color);
      _renderGlobalChart(available); _renderGlobalStats(available);
    });
    el.appendChild(btn);
  });
}

function _renderGlobalChart(available) {
  if (!globalChart || !DATA) return;
  globalChart.resize();
  const strategies = DATA.strategies || {};
  const startDate  = "2006-01-01";

  function normalize(nav) {
    if (!nav?.length) return [];
    const idx = nav.findIndex(p => p.date >= startDate);
    if (idx === -1) return [];
    const base = nav[idx].value;
    return base ? nav.slice(idx).map(p => [p.date, +(p.value / base * 100).toFixed(4)]) : [];
  }

  const series = GLOBAL_STRATS
    .filter(s => globalActiveKeys.has(s.key) && strategies[s.key])
    .map(({ key, label, color }) => ({
      name: label, type: "line", data: normalize(strategies[key].nav),
      smooth: false, symbol: "none",
      lineStyle: { color, width: SERIES_CFG[key]?.width || 2 }, itemStyle: { color },
    }));

  // Benchmark — prefer new key, fall back to old
  const benchKey0 = ["global_top9", "global_top12", "global_top7", "global_top10"].find(k => strategies[k]);
  const benchSeries = benchKey0 ? strategies[benchKey0]?.benchmark?.series : null;
  if (benchSeries) {
    series.push({ name: "Equal-weight SPY+EXSA+OMX", type: "line",
                  data: normalize(benchSeries), smooth: false, symbol: "none",
                  lineStyle: { color: "#64748b", width: 1.4, type: "dashed" },
                  itemStyle: { color: "#64748b" } });
  }

  globalChart.setOption({
    backgroundColor: "transparent", animation: false,
    grid:  { top: 24, left: 60, right: 20, bottom: 36 },
    xAxis: { type: "time", min: startDate,
             axisLabel: { color: "#8591b8", fontSize: 10 },
             axisLine:  { lineStyle: { color: "#252a3d" } }, splitLine: { show: false } },
    yAxis: { type: "value",
             axisLabel: { color: "#8591b8", fontSize: 10, formatter: v => v.toFixed(0) },
             axisLine: { show: false },
             splitLine: { lineStyle: { color: "#252a3d", type: "dashed" } }, axisTick: { show: false } },
    tooltip: {
      trigger: "axis", backgroundColor: "#1a1e2e", borderColor: "#252a3d",
      textStyle: { color: "#c9d1e0", fontSize: 11 },
      formatter(params) {
        if (!params?.length) return "";
        const d = new Date(params[0].axisValue).toISOString().slice(0,10);
        const rows = params.map(p => `<div style="display:flex;justify-content:space-between;gap:20px">
          <span style="color:${p.color}">${p.seriesName}</span>
          <span style="font-variant-numeric:tabular-nums">${(+p.value[1]).toFixed(1)}</span></div>`).join("");
        return `<div style="font-size:11px"><div style="color:#8591b8;margin-bottom:4px">${d}</div>${rows}</div>`;
      },
    },
    legend: { show: false }, series,
  }, true);
}

// Universe label colors
const UNIVERSE_COLORS = { OMXS: "#f97316", STOXX: "#c026d3", SP500: "#34d399", NASDAQ: "#38bdf8" };

function _renderGlobalSignal(available) {
  const el = document.getElementById("global-signal-row");
  if (!el) return;
  const strategies = DATA?.strategies || {};

  el.innerHTML = available.map(({ key, label, color }) => {
    const cs = strategies[key]?.current_signal;
    if (!cs) return "";
    const cashHolding = cs.holdings?.find(h => h.ticker === "CASH");
    if (cashHolding) return `<div class="bg-panel border border-border rounded-lg p-4">
      <div class="flex items-center gap-2 mb-3">
        <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
        <span class="text-xs font-semibold uppercase" style="color:${color}">${label}</span>
        <span class="text-xs text-muted ml-auto">${cs.date}</span>
      </div>
      <p class="text-xs text-muted italic">Kontanter — absolut momentum negativt</p>
    </div>`;

    const globalInfo = DATA?.global_company_info  || {};
    const omxsInfo   = DATA?.omxs_company_info   || {};
    const stoxxInfo  = DATA?.stoxx_company_info  || {};
    const sp500Info  = DATA?.sp500_company_info  || {};
    const nasdaqInfo = DATA?.nasdaq_company_info || {};
    const chips = (cs.holdings || []).filter(h => h.ticker !== "CASH").map(h => {
      const parts    = h.ticker.split(":");
      const universe = parts.length > 1 ? parts[0] : h.universe || "";
      const rawTicker = parts.length > 1 ? parts.slice(1).join(":") : h.ticker;
      const uCol      = UNIVERSE_COLORS[universe] || "#8591b8";
      const pct       = Math.round(h.weight * 100);
      const infoMap = globalInfo[rawTicker] ? globalInfo
                     : universe === "OMXS"   ? omxsInfo
                     : universe === "STOXX"  ? stoxxInfo
                     : universe === "NASDAQ" ? nasdaqInfo : sp500Info;
      const name    = infoMap[rawTicker]?.name || null;
      const shortTicker = rawTicker.replace(/\.[A-Z]+$/, "");
      return `<div class="flex items-center justify-between py-1.5 border-b border-border last:border-0">
        <div class="min-w-0 flex items-center gap-2 flex-wrap">
          <span class="text-xs font-mono font-medium text-slate-300">${shortTicker}</span>
          <span class="text-xs px-1.5 py-0.5 rounded font-medium" style="background:${uCol}22;color:${uCol}">${universe}</span>
          ${name ? `<span class="text-xs text-muted">${name}</span>` : ""}
        </div>
        <span class="text-xs text-muted ml-2 shrink-0">${pct}%</span>
      </div>`;
    }).join("");

    return `<div class="bg-panel border border-border rounded-lg p-4">
      <div class="flex items-center gap-2 mb-3">
        <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
        <span class="text-xs font-semibold uppercase" style="color:${color}">${label}</span>
        <span class="text-xs text-muted ml-auto">${cs.date}</span>
      </div>
      ${chips || '<p class="text-xs text-muted italic">Inga innehav</p>'}
    </div>`;
  }).join("");
}

function _renderGlobalStats(available) {
  const el = document.getElementById("global-stats");
  if (!el) return;
  const strategies = DATA?.strategies || {};

  function pct(v, d=1) { return v==null ? "—" : (v>=0?"+":"")+(v*100).toFixed(d)+"%"; }
  function colorVal(v) { return v==null?"color:#8591b8":v>=0?"color:#10b981":"color:#f43f5e"; }

  const activeStrats = available.filter(s => globalActiveKeys.has(s.key));

  const summaries = activeStrats.map(({ key, label, color }) => {
    const st = strategies[key]?.stats;
    if (!st) return "";
    return `<div class="bg-panel border border-border rounded-lg p-4">
      <div class="flex items-center gap-2 mb-3">
        <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
        <span class="text-xs font-semibold uppercase" style="color:${color}">${label}</span>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <div><p class="text-xs text-muted mb-0.5">CAGR</p>
          <p class="text-lg font-semibold" style="${colorVal(st.cagr)}">${pct(st.cagr)}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Sharpe</p>
          <p class="text-lg font-semibold text-slate-300">${st.sharpe?.toFixed(2)??"—"}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Max DD</p>
          <p class="text-lg font-semibold" style="color:#f43f5e">${pct(st.max_dd)}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Volatilitet</p>
          <p class="text-lg font-semibold text-slate-300">${pct(st.ann_vol)}</p></div>
        <div><p class="text-xs text-muted mb-0.5">Total</p>
          <p class="text-lg font-semibold" style="${colorVal(st.total)}">${pct(st.total)}</p></div>
      </div>
    </div>`;
  }).filter(Boolean);

  const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  function heatCell(v) {
    if (v==null) return `<td class="text-center p-0.5"><span class="block w-full h-6 rounded text-xs leading-6 text-muted">—</span></td>`;
    const alpha=Math.min(Math.abs(v)/0.08,1);
    const bg=v>=0?`rgba(16,185,129,${(alpha*.7).toFixed(2)})`:`rgba(244,63,94,${(alpha*.7).toFixed(2)})`;
    const txt=v>=0?"#6ee7b7":"#fca5a5";
    return `<td class="text-center p-0.5"><span class="block w-full h-6 rounded text-xs leading-6 tabular-nums" style="background:${bg};color:${txt}">${pct(v,0)}</span></td>`;
  }

  const heatmaps = activeStrats.map(({ key, label, color }) => {
    const mo = strategies[key]?.stats?.monthly;
    if (!mo) return "";
    const years = Object.keys(mo).sort();
    const header = `<tr><th class="text-left pb-1 pr-2 text-xs text-muted font-normal w-12"></th>
      ${MONTHS.map(m=>`<th class="text-center pb-1 px-0.5 text-xs text-muted font-normal">${m}</th>`).join("")}</tr>`;
    const rows = years.map(yr => {
      const cells = Array.from({length:12},(_,i)=>heatCell(mo[yr]?.[String(i+1)]));
      return `<tr><td class="pr-2 text-xs text-slate-400 py-0.5">${yr}</td>${cells.join("")}</tr>`;
    }).join("");
    return `<div><p class="text-xs font-semibold mb-2" style="color:${color}">${label}</p>
      <div class="overflow-x-auto"><table class="w-full min-w-max border-collapse text-xs">
        <thead>${header}</thead><tbody>${rows}</tbody></table></div></div>`;
  }).filter(Boolean);

  // Holdings history for global_top7
  function _globalHistory() {
    const log = strategies["global_top7"]?.alloc_log;
    if (!log?.length) return "";
    const PALETTE = ["#facc15","#fb923c","#34d399","#38bdf8","#a78bfa","#f43f5e","#818cf8","#6ee7b7","#c026d3","#10b981"];
    const tColor = {};
    let ci = 0;
    log.forEach(e => Object.keys(e.holdings).forEach(t => { if (!tColor[t] && t!=="CASH") tColor[t]=PALETTE[ci++%PALETTE.length]; }));

    const rows = [...log].reverse().map(e => {
      const held = Object.entries(e.holdings).filter(([t])=>t!=="CASH");
      const dateStr = e.date.slice(0,7);
      if (!held.length) return `<tr class="border-t border-border/40">
        <td class="py-1.5 pr-3 text-xs text-slate-500 font-mono">${dateStr}</td>
        <td colspan="2" class="text-xs text-slate-600 italic py-1.5">kontanter</td></tr>`;

      const chips = held.map(([t,w]) => {
        const parts = t.split(":");
        const universe = parts.length>1?parts[0]:"";
        const ticker   = parts.length>1?parts.slice(1).join(":")  :t;
        const uCol = UNIVERSE_COLORS[universe]||"#8591b8";
        const col  = tColor[t]||"#8591b8";
        return `<span class="inline-flex items-center gap-1 mr-1.5 mb-0.5">
          <span class="w-1.5 h-1.5 rounded-full shrink-0" style="background:${uCol}"></span>
          <span class="text-xs font-mono font-medium" style="color:${col}">${ticker}</span>
          <span class="text-xs text-slate-500">${(w*100).toFixed(0)}%</span>
          <span class="text-xs text-slate-600">[${universe}]</span>
        </span>`;
      }).join("");

      return `<tr class="border-t border-border/40 hover:bg-white/[0.02]">
        <td class="py-1.5 pr-3 text-xs text-slate-500 font-mono whitespace-nowrap align-top pt-2">${dateStr}</td>
        <td class="py-1 align-top">${chips}</td>
      </tr>`;
    }).join("");

    return `<div class="bg-panel border border-border rounded-lg p-4">
      <div class="flex items-center justify-between mb-3">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-widest">Innehavshistorik — Global Top-7</p>
        <span class="text-xs text-slate-600">${log.length} månader</span>
      </div>
      <div class="text-xs text-slate-500 mb-2">
        <span class="inline-flex items-center gap-1 mr-3"><span class="w-2 h-2 rounded-full inline-block" style="background:#f97316"></span>OMXS</span>
        <span class="inline-flex items-center gap-1 mr-3"><span class="w-2 h-2 rounded-full inline-block" style="background:#c026d3"></span>STOXX</span>
        <span class="inline-flex items-center gap-1"><span class="w-2 h-2 rounded-full inline-block" style="background:#34d399"></span>SP500</span>
      </div>
      <div class="overflow-y-auto max-h-[520px] pr-1">
        <table class="w-full border-collapse">
          <thead class="sticky top-0 bg-panel z-10">
            <tr><th class="text-left pb-2 pr-3 text-xs text-muted font-normal w-16">Datum</th>
            <th class="text-left pb-2 text-xs text-muted font-normal">Innehav</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
  }

  el.innerHTML = `<div class="space-y-5">
    ${summaries.length ? `<div class="grid grid-cols-1 xl:grid-cols-2 gap-5">${summaries.join("")}</div>` : ""}
    ${_globalHistory()}
    ${heatmaps.length ? `<div class="bg-panel border border-border rounded-lg p-4 space-y-8">${heatmaps.join("")}</div>` : ""}
  </div>`;
}
