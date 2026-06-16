/* ETF Rotation Dashboard — app.js */
"use strict";

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
  "MSCI World": { label: "MSCI World",       color: "#64748b", width: 1.4 },
  "OMXS30":     { label: "OMXS30",           color: "#38bdf8", width: 1.4 },
  "Nasdaq":     { label: "Nasdaq",            color: "#f59e0b", width: 1.4 },
  "S&P 500":    { label: "S&P 500",          color: "#f97316", width: 1.4 },
};

const ALLOC_PALETTE = [
  "#5b6ef5","#a78bfa","#38bdf8","#10b981","#f59e0b",
  "#f43f5e","#6ee7b7","#93c5fd","#fca5a5","#c4b5fd","#64748b",
];

// ── State ──────────────────────────────────────────────────────────
let DATA = null;
let CONFIG = null;
let activeKeys = new Set(["d1_composite", "d2_composite", "d1_accel", "d1_lowcorr", "MSCI World"]);
let mainChart = null;

// ── Init ───────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  mainChart = echarts.init(document.getElementById("main-chart"), null, { renderer: "canvas" });
  window.addEventListener("resize", () => mainChart?.resize());
  document.getElementById("start-date").addEventListener("change", () => { if (DATA) renderMainChart(); });
  await loadData();
});

// ── Tab switching ──────────────────────────────────────────────────
function switchTab(tab) {
  document.getElementById("view-dashboard").classList.toggle("hidden", tab !== "dashboard");
  document.getElementById("view-settings").classList.toggle("hidden",  tab !== "settings");
  document.getElementById("tab-dashboard").className = tab === "dashboard" ? "tab-active pb-1 transition-colors" : "tab-inactive pb-1 transition-colors";
  document.getElementById("tab-settings").className  = tab === "settings"  ? "tab-active pb-1 transition-colors" : "tab-inactive pb-1 transition-colors";
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
  buildToggles();
  renderMainChart();
  renderSignalCards();
  renderStats();
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
      applyToggleStyle(btn, activeKeys.has(key), color);
      renderMainChart();
    });
    container.appendChild(btn);
  });
}

function applyToggleStyle(btn, on, color) {
  btn.style.background   = on ? color + "22" : "";
  btn.style.borderColor  = on ? color : "#252a3d";
  btn.style.color        = on ? color : "#4a5170";
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

  // ── Build a consistent ticker→color map across all strategies ─────
  // Same ETF always gets the same color regardless of which strip it's in.
  const tickerColorMap = {};
  let colorIdx = 0;
  for (const sk of ["top1_top1", "top2_top2", "d1_composite", "d2_composite",
                    "d1_accel", "d2_accel", "d1_lowcorr", "d2_lowcorr"]) {
    const alloc = DATA?.strategies?.[sk]?.allocation;
    if (!alloc?.tickers) continue;
    alloc.tickers.forEach((t, i) => {
      if (!(t in tickerColorMap) && alloc.weights.some(row => row[i] > 0))
        tickerColorMap[t] = ALLOC_PALETTE[colorIdx++ % ALLOC_PALETTE.length];
    });
  }

  // ── Helper: build stacked-area series for one allocation strip ────
  function buildAllocSeries(stratKey, xIdx, yIdx) {
    const alloc = DATA?.strategies?.[stratKey]?.allocation;
    if (!alloc?.tickers?.length) return [];
    return alloc.tickers
      .map((t, i) => ({ t, i }))
      .filter(({ i }) => alloc.weights.some(row => row[i] > 0))
      .map(({ t, i }) => {
        const pts = alloc.dates
          .map((d, ri) => [d, alloc.weights[ri][i]])
          .filter(([d]) => d >= startDate);
        return {
          name: tickerLabel(t), type: "line",
          stack: `alloc-${stratKey}`,
          areaStyle: { color: tickerColorMap[t] || "#4a5170", opacity: 0.88 },
          lineStyle: { width: 0 },
          symbol: "none",
          step: "end",
          data: pts.map(([d, w]) => [d, +(w * 100).toFixed(2)]),
          xAxisIndex: xIdx, yAxisIndex: yIdx,
        };
      });
  }

  const allocD1raw  = buildAllocSeries("top1_top1",    1, 1);
  const allocD1comp = buildAllocSeries("d1_composite",  2, 2);
  const allocD2raw  = buildAllocSeries("top2_top2",     3, 3);
  const allocD2comp = buildAllocSeries("d2_composite",  4, 4);

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

    const allocSection = ["top1_top1", "d1_composite", "d1_accel", "d1_lowcorr",
                          "top2_top2", "d2_composite", "d2_accel", "d2_lowcorr"].map(k => {
      const holdings = allocAtDate(k, dateStr);
      if (!holdings) return "";
      const c = SERIES_CFG[k] || {};
      const chips = Object.entries(holdings).map(([t, w]) => {
        const color = tickerColorMap[t] || "#4a5170";
        return `<span style="background:${color}22;border:1px solid ${color}55;border-radius:3px;padding:1px 5px;margin:1px 2px 1px 0;display:inline-block;color:${color}">
          ${tickerLabel(t)}<span style="opacity:.65;margin-left:3px">${Math.round(w * 100)}%</span>
        </span>`;
      }).join("");
      return `<div style="margin-top:6px;padding-top:6px;border-top:1px solid #252a3d">
        <span style="color:${c.color || "#4a5170"};font-size:10px;font-weight:600">${c.label || k}</span>
        <div style="margin-top:3px;line-height:2">${chips}</div>
      </div>`;
    }).join("");

    return `<div style="font-size:11px;max-width:320px">
      <div style="color:#4a5170;margin-bottom:6px">${dateStr}</div>
      ${perfRows}${allocSection}
    </div>`;
  }

  // ── ECharts option — 5 grids, all x-axes share startDate min ─────
  mainChart.setOption({
    backgroundColor: "transparent",
    animation: false,

    grid: [
      { top: 16,    left: 60, right: 20, bottom: "52%" },   // perf
      { top: "50%", left: 60, right: 20, height: "10%" },   // D1-raw strip
      { top: "62%", left: 60, right: 20, height: "10%" },   // D1-composite strip
      { top: "74%", left: 60, right: 20, height: "10%" },   // D2-raw strip
      { top: "86%", left: 60, right: 20, bottom: 26 },      // D2-composite strip
    ],

    xAxis: [
      { type: "time", gridIndex: 0, min: startDate,
        axisLabel: { show: false },
        axisLine:  { lineStyle: { color: "#252a3d" } },
        splitLine: { show: false }, axisTick: { show: false } },
      { type: "time", gridIndex: 1, min: startDate,
        axisLabel: { show: false },
        axisLine:  { lineStyle: { color: "#252a3d" } },
        splitLine: { show: false }, axisTick: { show: false } },
      { type: "time", gridIndex: 2, min: startDate,
        axisLabel: { show: false },
        axisLine:  { lineStyle: { color: "#252a3d" } },
        splitLine: { show: false }, axisTick: { show: false } },
      { type: "time", gridIndex: 3, min: startDate,
        axisLabel: { show: false },
        axisLine:  { lineStyle: { color: "#252a3d" } },
        splitLine: { show: false }, axisTick: { show: false } },
      { type: "time", gridIndex: 4, min: startDate,
        axisLabel: { color: "#4a5170", fontSize: 10 },
        axisLine:  { lineStyle: { color: "#252a3d" } },
        splitLine: { show: false },
        axisTick:  { lineStyle: { color: "#252a3d" } } },
    ],

    yAxis: [
      { type: "value", gridIndex: 0,
        axisLabel: { color: "#4a5170", fontSize: 10, formatter: v => v.toFixed(0) },
        axisLine:  { show: false },
        splitLine: { lineStyle: { color: "#252a3d", type: "dashed" } },
        axisTick:  { show: false } },
      { type: "value", gridIndex: 1, max: 100, min: 0,
        name: "D1-raw", nameLocation: "end",
        nameTextStyle: { color: "#5b6ef5", fontSize: 9, fontWeight: 600, padding: [0, 0, 4, 0] },
        axisLabel: { show: false }, axisLine: { show: false },
        splitLine: { show: false }, axisTick: { show: false } },
      { type: "value", gridIndex: 2, max: 100, min: 0,
        name: "D1-comp", nameLocation: "end",
        nameTextStyle: { color: "#10b981", fontSize: 9, fontWeight: 600, padding: [0, 0, 4, 0] },
        axisLabel: { show: false }, axisLine: { show: false },
        splitLine: { show: false }, axisTick: { show: false } },
      { type: "value", gridIndex: 3, max: 100, min: 0,
        name: "D2-raw", nameLocation: "end",
        nameTextStyle: { color: "#a78bfa", fontSize: 9, fontWeight: 600, padding: [0, 0, 4, 0] },
        axisLabel: { show: false }, axisLine: { show: false },
        splitLine: { show: false }, axisTick: { show: false } },
      { type: "value", gridIndex: 4, max: 100, min: 0,
        name: "D2-comp", nameLocation: "end",
        nameTextStyle: { color: "#34d399", fontSize: 9, fontWeight: 600, padding: [0, 0, 4, 0] },
        axisLabel: { show: false }, axisLine: { show: false },
        splitLine: { show: false }, axisTick: { show: false } },
    ],

    tooltip: {
      trigger: "axis",
      backgroundColor: "#1a1e2e",
      borderColor:     "#252a3d",
      textStyle:       { color: "#c9d1e0", fontSize: 12 },
      axisPointer: {
        type: "cross",
        crossStyle: { color: "#4a517066" },
        link: [{ xAxisIndex: "all" }],
      },
      formatter: tooltipFormatter,
    },

    legend: { show: false },

    series: [...perfSeries, ...allocD1raw, ...allocD1comp, ...allocD2raw, ...allocD2comp],
  }, true);
}

// ── Signal cards ───────────────────────────────────────────────────
function renderSignalCards() {
  renderSignalCard("signal-d1",    DATA?.strategies?.top1_top1,    "D1 — raw");
  renderSignalCard("signal-d1c",   DATA?.strategies?.d1_composite, "D1-composite");
  renderSignalCard("signal-d1a",   DATA?.strategies?.d1_accel,     "D1-accel.");
  renderSignalCard("signal-d1lc",  DATA?.strategies?.d1_lowcorr,   "D1-low-corr.");
  renderSignalCard("signal-d2",    DATA?.strategies?.top2_top2,    "D2 — raw");
  renderSignalCard("signal-d2c",   DATA?.strategies?.d2_composite, "D2-composite");
  renderSignalCard("signal-d2a",   DATA?.strategies?.d2_accel,     "D2-accel.");
  renderSignalCard("signal-d2lc",  DATA?.strategies?.d2_lowcorr,   "D2-low-corr.");
}

function renderSignalCard(elId, strat, title) {
  const el = document.getElementById(elId);
  if (!strat?.current_signal) { el.innerHTML = ""; return; }
  const { date, holdings } = strat.current_signal;
  const rows = (holdings || []).map(h => {
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
  el.innerHTML = `
    <div class="flex items-center justify-between mb-3">
      <p class="text-xs font-medium text-muted uppercase tracking-widest">${title}</p>
      <span class="text-xs text-muted">${date}</span>
    </div>
    ${rows || '<p class="text-xs text-muted italic">Cash — regime filter off</p>'}`;
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

  // ── Summary metrics ──────────────────────────────────────────────
  const STRATS = [
    { key: "top1_top1",    label: "D1 — raw",       color: "#5b6ef5" },
    { key: "d1_composite", label: "D1-composite",    color: "#10b981" },
    { key: "d1_accel",     label: "D1-accel.",       color: "#f59e0b" },
    { key: "d1_lowcorr",   label: "D1-low-corr.",    color: "#f43f5e" },
    { key: "top2_top2",    label: "D2 — raw",       color: "#a78bfa" },
    { key: "d2_composite", label: "D2-composite",    color: "#34d399" },
    { key: "d2_accel",     label: "D2-accel.",       color: "#fcd34d" },
    { key: "d2_lowcorr",   label: "D2-low-corr.",    color: "#fb7185" },
  ];

  function pct(v, decimals = 1) {
    return v == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(decimals) + "%";
  }
  function colorClass(v) {
    if (v == null) return "color:#4a5170";
    return v >= 0 ? "color:#10b981" : "color:#f43f5e";
  }

  const summaryCards = STRATS.map(({ key, label, color }) => {
    const st = strategies[key]?.stats;
    if (!st) return "";
    return `
      <div class="bg-panel border border-border rounded-lg p-4">
        <div class="flex items-center gap-2 mb-3">
          <span class="w-2 h-2 rounded-full flex-shrink-0" style="background:${color}"></span>
          <span class="text-xs font-semibold tracking-widest text-slate-400 uppercase">${label}</span>
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          <div>
            <p class="text-xs text-muted mb-0.5">CAGR</p>
            <p class="text-lg font-semibold" style="${colorClass(st.cagr)}">${pct(st.cagr)}</p>
          </div>
          <div>
            <p class="text-xs text-muted mb-0.5">Sharpe</p>
            <p class="text-lg font-semibold text-slate-300">${st.sharpe?.toFixed(2) ?? "—"}</p>
          </div>
          <div>
            <p class="text-xs text-muted mb-0.5">Max DD <span class="text-muted font-normal">(daglig)</span></p>
            <p class="text-lg font-semibold" style="color:#f43f5e">${pct(st.max_dd)}</p>
          </div>
          <div>
            <p class="text-xs text-muted mb-0.5">Max DD <span class="text-muted font-normal">(månadsslut)</span></p>
            <p class="text-lg font-semibold" style="color:#fb923c">${pct(st.max_dd_monthly)}</p>
          </div>
          <div>
            <p class="text-xs text-muted mb-0.5">Volatilitet</p>
            <p class="text-lg font-semibold text-slate-300">${pct(st.ann_vol)}</p>
          </div>
          <div>
            <p class="text-xs text-muted mb-0.5">Total</p>
            <p class="text-lg font-semibold" style="${colorClass(st.total)}">${pct(st.total)}</p>
          </div>
        </div>
      </div>`;
  }).join("");

  // ── Annual table (two side-by-side tables, one per strategy) ─────
  const allYears = [...new Set(
    STRATS.flatMap(({ key }) => Object.keys(strategies[key]?.stats?.annual || {}))
  )].sort();

  function annualTable({ key, label, color }) {
    const annual = strategies[key]?.stats?.annual || {};
    const header = `<thead><tr>
      <th class="text-left pb-2 pr-3 text-xs font-semibold" style="color:${color}">${label}</th>
      <th class="text-right pb-2 px-2 text-xs text-muted font-normal">Avkastning</th>
      <th class="text-right pb-2 px-2 text-xs text-muted font-normal">Sharpe</th>
      <th class="text-right pb-2 px-2 text-xs text-muted font-normal">Max DD</th>
      <th class="text-right pb-2 px-2 text-xs text-muted font-normal">DD månadsslut</th>
      <th class="text-right pb-2 pl-2 text-xs text-muted font-normal">Vol</th>
    </tr></thead>`;
    const rows = allYears.map(yr => {
      const a = annual[yr];
      const ret   = a?.ret;
      const sh    = a?.sharpe;
      const dd    = a?.max_dd;
      const ddmo  = a?.max_dd_mo;
      const vol   = a?.vol;
      return `<tr class="border-t border-border">
        <td class="py-1.5 pr-3 text-xs text-slate-400">${yr}</td>
        <td class="text-right py-1.5 px-2 text-xs font-medium tabular-nums" style="${colorClass(ret)}">${pct(ret)}</td>
        <td class="text-right py-1.5 px-2 text-xs tabular-nums text-slate-300">${sh != null ? sh.toFixed(2) : "—"}</td>
        <td class="text-right py-1.5 px-2 text-xs tabular-nums" style="color:#f43f5e">${pct(dd)}</td>
        <td class="text-right py-1.5 px-2 text-xs tabular-nums" style="color:#fb923c">${pct(ddmo)}</td>
        <td class="text-right py-1.5 pl-2 text-xs tabular-nums text-slate-400">${pct(vol)}</td>
      </tr>`;
    }).join("");
    return `<table class="w-full border-collapse">${header}<tbody>${rows}</tbody></table>`;
  }

  const annualSection = `
    <div class="bg-panel border border-border rounded-lg p-4">
      <p class="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">Per Year — full-period summary in the cards above</p>
      ${[0,2,4,6].map(i => `
        <div class="grid grid-cols-1 xl:grid-cols-2 gap-6 ${i > 0 ? 'mt-6' : ''}">
          ${STRATS[i] ? annualTable(STRATS[i]) : ""}
          ${STRATS[i+1] ? annualTable(STRATS[i+1]) : ""}
        </div>`).join("")}
    </div>`;

  // ── Monthly heatmap ──────────────────────────────────────────────
  const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

  function heatCell(v) {
    if (v == null) return `<td class="text-center p-0.5"><span class="block w-full h-6 rounded text-xs leading-6 text-muted">—</span></td>`;
    const abs = Math.abs(v);
    const alpha = Math.min(abs / 0.08, 1);  // saturates at 8%
    const bg = v >= 0
      ? `rgba(16,185,129,${(alpha * 0.7).toFixed(2)})`
      : `rgba(244,63,94,${(alpha * 0.7).toFixed(2)})`;
    const txt = v >= 0 ? "#6ee7b7" : "#fca5a5";
    return `<td class="text-center p-0.5"><span class="block w-full h-6 rounded text-xs leading-6 tabular-nums" style="background:${bg};color:${txt}">${pct(v, 0)}</span></td>`;
  }

  const heatmaps = STRATS.map(({ key, label, color }) => {
    const monthly = strategies[key]?.stats?.monthly;
    if (!monthly) return "";
    const years = Object.keys(monthly).sort();
    const header = `<tr>
      <th class="text-left pb-1 pr-2 text-xs text-muted font-normal w-12"></th>
      ${MONTHS.map(m => `<th class="text-center pb-1 px-0.5 text-xs text-muted font-normal">${m}</th>`).join("")}
    </tr>`;
    const rows = years.map(yr => {
      const cells = Array.from({length: 12}, (_, i) => heatCell(monthly[yr]?.[String(i + 1)]));
      return `<tr><td class="pr-2 text-xs text-slate-400 py-0.5">${yr}</td>${cells.join("")}</tr>`;
    }).join("");
    return `
      <div>
        <p class="text-xs font-semibold mb-2" style="color:${color}">${label} — monthly returns</p>
        <div class="overflow-x-auto">
          <table class="w-full min-w-max border-collapse text-xs">
            <thead>${header}</thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`;
  }).join("");

  el.innerHTML = `
    <div class="space-y-5">
      <div class="grid grid-cols-1 xl:grid-cols-2 gap-5">${summaryCards}</div>
      ${annualSection}
      <div class="bg-panel border border-border rounded-lg p-4 space-y-8">${heatmaps}</div>
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
