/* ETF Rotation Dashboard — app.js */
"use strict";

// ── Palette ────────────────────────────────────────────────────────
const SERIES_CFG = {
  top1_top1:   { label: "D1 — top1/top1", color: "#5b6ef5", width: 2.2 },
  top2_top2:   { label: "D2 — top2/top2", color: "#a78bfa", width: 2.2 },
  "MSCI World":{ label: "MSCI World",      color: "#64748b", width: 1.4, dash: [4,3] },
  "OMXS30":    { label: "OMXS30",          color: "#38bdf8", width: 1.4, dash: [4,3] },
  "Nasdaq":    { label: "Nasdaq",           color: "#f59e0b", width: 1.4, dash: [4,3] },
  "S&P 500":   { label: "S&P 500",         color: "#10b981", width: 1.4, dash: [4,3] },
};

// Distinct colors for allocation area chart
const ALLOC_PALETTE = [
  "#5b6ef5","#a78bfa","#38bdf8","#10b981","#f59e0b",
  "#f43f5e","#6ee7b7","#93c5fd","#fca5a5","#c4b5fd",
  "#64748b",
];

// ── State ──────────────────────────────────────────────────────────
let DATA = null;
let CONFIG = null;
let activeKeys = new Set(["top1_top1", "top2_top2", "MSCI World"]);
let allocStrategy = "top1_top1";
let perfChart = null;
let allocChart = null;

// ── Init ───────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  perfChart  = echarts.init(document.getElementById("perf-chart"),  null, { renderer: "canvas" });
  allocChart = echarts.init(document.getElementById("alloc-chart"), null, { renderer: "canvas" });

  window.addEventListener("resize", () => {
    perfChart?.resize();
    allocChart?.resize();
  });

  document.getElementById("start-date").addEventListener("change", () => {
    if (DATA) renderPerfChart();
  });

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
  renderPerfChart();
  renderAllocChart();
  renderSignalCards();
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
    const cfg = SERIES_CFG[key] || {};
    const label = cfg.label || key;
    const color = cfg.color || "#64748b";
    const on = activeKeys.has(key);

    const btn = document.createElement("button");
    btn.dataset.key = key;
    btn.className = "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-all " +
      (on ? "border-transparent text-white" : "border-border text-muted");
    btn.style.background = on ? color + "33" : "";
    btn.style.borderColor = on ? color : "";
    btn.style.color = on ? color : "";

    const dot = document.createElement("span");
    dot.className = "w-2 h-2 rounded-full flex-shrink-0";
    dot.style.background = color;

    btn.appendChild(dot);
    btn.appendChild(document.createTextNode(label));
    btn.addEventListener("click", () => toggleSeries(key, btn, color));
    container.appendChild(btn);
  });
}

function toggleSeries(key, btn, color) {
  if (activeKeys.has(key)) {
    activeKeys.delete(key);
    btn.style.background = "";
    btn.style.borderColor = "";
    btn.style.color = "";
    btn.className = "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-all border-border text-muted";
  } else {
    activeKeys.add(key);
    btn.style.background = color + "33";
    btn.style.borderColor = color;
    btn.style.color = color;
    btn.className = "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-all";
  }
  renderPerfChart();
}

// ── Performance chart ──────────────────────────────────────────────
function renderPerfChart() {
  const startDate = document.getElementById("start-date").value;

  function normalize(series) {
    if (!series || !series.length) return [];
    const idx = series.findIndex(p => p.date >= startDate);
    if (idx === -1) return [];
    const base = series[idx].value;
    if (!base || base === 0) return [];
    return series.slice(idx).map(p => [p.date, +(p.value / base * 100).toFixed(4)]);
  }

  const seriesList = [];

  // Strategy NAV series
  for (const [key, strat] of Object.entries(DATA.strategies || {})) {
    if (!activeKeys.has(key)) continue;
    const c = SERIES_CFG[key] || {};
    seriesList.push({
      name:      c.label || key,
      type:      "line",
      data:      normalize(strat.nav),
      smooth:    false,
      symbol:    "none",
      lineStyle: { color: c.color, width: c.width || 2, type: c.dash ? "dashed" : "solid" },
      itemStyle: { color: c.color },
      z:         10,
    });
  }

  // Benchmark series
  for (const [name, bench] of Object.entries(DATA.benchmarks || {})) {
    if (!activeKeys.has(name)) continue;
    const c = SERIES_CFG[name] || {};
    seriesList.push({
      name:      c.label || name,
      type:      "line",
      data:      normalize(bench.series),
      smooth:    false,
      symbol:    "none",
      lineStyle: { color: c.color, width: c.width || 1.5, type: "dashed" },
      itemStyle: { color: c.color },
      z:         5,
    });
  }

  perfChart.setOption({
    backgroundColor: "transparent",
    animation:       false,
    grid:   { top: 20, right: 20, bottom: 50, left: 55 },
    xAxis:  {
      type: "time",
      axisLabel:  { color: "#4a5170", fontSize: 11 },
      axisLine:   { lineStyle: { color: "#252a3d" } },
      splitLine:  { show: false },
      axisTick:   { lineStyle: { color: "#252a3d" } },
    },
    yAxis:  {
      type: "value",
      axisLabel:  { color: "#4a5170", fontSize: 11, formatter: v => v.toFixed(0) },
      axisLine:   { show: false },
      splitLine:  { lineStyle: { color: "#252a3d", type: "dashed" } },
      axisTick:   { show: false },
    },
    tooltip: {
      trigger:     "axis",
      backgroundColor: "#1a1e2e",
      borderColor: "#252a3d",
      textStyle:   { color: "#c9d1e0", fontSize: 12 },
      axisPointer: { type: "cross", crossStyle: { color: "#4a5170" } },
      formatter(params) {
        const date = params[0]?.axisValueLabel || "";
        const rows = params.map(p =>
          `<div style="display:flex;justify-content:space-between;gap:24px">
            <span style="color:${p.color}">${p.seriesName}</span>
            <span>${(+p.value[1]).toFixed(1)}</span>
          </div>`
        ).join("");
        return `<div style="font-size:11px"><div style="color:#4a5170;margin-bottom:4px">${date}</div>${rows}</div>`;
      },
    },
    series: seriesList,
  }, true);
}

// ── Allocation chart ───────────────────────────────────────────────
function setAllocStrategy(key) {
  allocStrategy = key;
  document.getElementById("alloc-btn-top1").className =
    key === "top1_top1"
      ? "text-xs px-2 py-0.5 rounded border border-accent text-accent"
      : "text-xs px-2 py-0.5 rounded border border-border text-muted";
  document.getElementById("alloc-btn-top2").className =
    key === "top2_top2"
      ? "text-xs px-2 py-0.5 rounded border border-accent text-accent"
      : "text-xs px-2 py-0.5 rounded border border-border text-muted";
  renderAllocChart();
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

function renderAllocChart() {
  const alloc = DATA?.strategies?.[allocStrategy]?.allocation;
  if (!alloc || !alloc.dates?.length) return;

  const { tickers, dates, weights } = alloc;

  const series = tickers.map((t, i) => ({
    name:       tickerLabel(t),
    type:       "line",
    stack:      "total",
    areaStyle:  { color: ALLOC_PALETTE[i % ALLOC_PALETTE.length], opacity: 0.85 },
    lineStyle:  { width: 0 },
    symbol:     "none",
    emphasis:   { focus: "series" },
    data:       weights.map((row, ri) => [dates[ri], +(row[i] * 100).toFixed(1)]),
  }));

  allocChart.setOption({
    backgroundColor: "transparent",
    animation:       false,
    grid:    { top: 10, right: 10, bottom: 40, left: 40 },
    xAxis:   {
      type:      "time",
      axisLabel: { color: "#4a5170", fontSize: 10 },
      axisLine:  { lineStyle: { color: "#252a3d" } },
      splitLine: { show: false },
    },
    yAxis:   {
      type:     "value",
      max:      100,
      axisLabel:{ color: "#4a5170", fontSize: 10, formatter: v => v + "%" },
      axisLine: { show: false },
      splitLine:{ lineStyle: { color: "#252a3d", type: "dashed" } },
    },
    tooltip: {
      trigger:     "axis",
      backgroundColor: "#1a1e2e",
      borderColor: "#252a3d",
      textStyle:   { color: "#c9d1e0", fontSize: 11 },
    },
    legend: { show: false },
    series,
  }, true);
}

// ── Signal cards ───────────────────────────────────────────────────
function renderSignalCards() {
  renderSignalCard("signal-d1", DATA?.strategies?.top1_top1, "D1 — top1/top1");
  renderSignalCard("signal-d2", DATA?.strategies?.top2_top2, "D2 — top2/top2");
}

function renderSignalCard(elId, strat, title) {
  const el = document.getElementById(elId);
  if (!strat?.current_signal) { el.innerHTML = ""; return; }

  const { date, holdings } = strat.current_signal;

  const rows = (holdings || []).map(h => {
    const pct  = Math.round(h.weight * 100);
    const isna = !h.nordnet_name;
    return `
      <div class="flex items-start justify-between gap-3 py-2 border-b border-border last:border-0">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-xs font-medium text-slate-300">${h.label}</span>
            <span class="text-xs text-muted">${h.ticker}</span>
            <span class="text-xs px-1.5 py-0 rounded-sm ${
              h.sleeve === 'factor' ? 'bg-indigo-900/50 text-indigo-300' :
              h.sleeve === 'sector' ? 'bg-purple-900/50 text-purple-300' :
              'bg-slate-800 text-slate-400'
            }">${h.sleeve}</span>
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
    ${rows || '<p class="text-xs text-muted italic">Cash (regime off)</p>'}`;
}

function copyISIN(isin, btn) {
  navigator.clipboard.writeText(isin).then(() => {
    const orig = btn.textContent;
    btn.textContent = "Copied";
    btn.style.color = "#10b981";
    setTimeout(() => { btn.textContent = orig; btn.style.color = ""; }, 1500);
  });
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
        <td class="py-2 pr-4 text-xs font-medium text-slate-400 w-28">${label}</td>
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
        <td class="py-2">
          <input class="w-40 bg-surface border border-border rounded px-2 py-1 text-xs font-mono text-slate-300 focus:outline-none focus:border-accent"
                 data-sleeve="${sleeveKey}" data-label="${label}" data-field="isin"
                 value="${info.isin || ""}" placeholder="SE0012345678"/>
        </td>
      </tr>`).join("");

    return `
      <div>
        <p class="text-xs font-semibold text-muted uppercase tracking-widest mb-2">${title}</p>
        <div class="bg-panel border border-border rounded-lg overflow-hidden">
          <table class="w-full px-4">
            <thead>
              <tr class="border-b border-border">
                <th class="text-left text-xs text-muted py-2 px-4 w-28">Slot</th>
                <th class="text-left text-xs text-muted py-2 pr-3">Ticker</th>
                <th class="text-left text-xs text-muted py-2 pr-3">Nordnet Proxy Name</th>
                <th class="text-left text-xs text-muted py-2">ISIN</th>
              </tr>
            </thead>
            <tbody class="px-4">${rows}</tbody>
          </table>
        </div>
      </div>`;
  }

  form.innerHTML =
    sleeveTable("factor_sleeve", "Factor Sleeve") +
    sleeveTable("sector_sleeve", "Sector Sleeve");

  // Wire up live edits
  form.querySelectorAll("input[data-sleeve]").forEach(inp => {
    inp.addEventListener("input", () => {
      const { sleeve, label, field } = inp.dataset;
      if (!CONFIG[sleeve]?.[label]) return;
      CONFIG[sleeve][label][field] = inp.value;
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
    // Snapshot current generated_at to detect when recalc finishes
    const prevTs = DATA?.generated_at || "";

    const res = await fetch("/api/config", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(CONFIG),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || res.status);
    }

    status.textContent = "Saved. Waiting for engine…";
    label.textContent  = "Recalculating…";

    // Poll until data.json regenerated (max 120s)
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
    } catch (_) { /* keep polling */ }
  }
  throw new Error("Timed out waiting for recalculation");
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}
