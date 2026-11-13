/* AutoV Trader - dashboard logic */
"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const fmtUsd = (v, d = 2) =>
  (v < 0 ? "-$" : "$") + Math.abs(Number(v || 0)).toLocaleString("en-US",
    { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtPct = (v) => (v > 0 ? "+" : "") + Number(v || 0).toFixed(2) + "%";
const fmtPrice = (p) => {
  p = Number(p || 0);
  if (p >= 1000) return p.toLocaleString("en-US", { maximumFractionDigits: 2 });
  if (p >= 1) return p.toFixed(4);
  if (p >= 0.01) return p.toFixed(5);
  return p.toPrecision(4);
};
const clsPct = (v) => (v >= 0 ? "up" : "down");

let scanData = null;
let chart = null, candleSeries = null, emaSeries = {};
let currentSymbol = "BTCUSDT";
let sortKey = "score", sortDir = -1;

function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (err ? " err" : "");
  clearTimeout(t._h);
  t._h = setTimeout(() => (t.className = "toast"), 4200);
}

async function api(path, opts) {
  try {
    const r = await fetch(path, opts);
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || r.statusText);
    return j;
  } catch (e) {
    if (!String(e).includes("Failed to fetch")) toast(e.message || String(e), true);
    throw e;
  }
}

/* ---------------- tabs ---------------- */
$$(".tab").forEach((b) =>
  b.addEventListener("click", () => activateTab(b.dataset.tab)));
function activateTab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + name));
  if (name === "charts" && !candleSeries) loadChart(currentSymbol);
  if (name === "scanner") loadScan();
  if (name === "planner") loadPlanner();
  if (name === "portfolio") loadPortfolio();
  if (name === "team") loadTeamRefs();
}
$$("[data-goto]").forEach((b) =>
  b.addEventListener("click", () => activateTab(b.dataset.goto)));

/* ---------------- status ---------------- */
async function loadStatus() {
  try {
    const s = await api("/api/status");
    const paper = s.tradingMode === "paper";
    $("#modeBadge").innerHTML =
      `<b style="color:${paper ? "#ffb020" : "#2fd48f"}">${paper ? "PAPER MODE" : "⚠ LIVE MODE"}</b>` +
      ` · $${s.settings.account_size} account · risk ${s.settings.risk_per_trade_pct}%/trade`;
    const chip = $("#dataChip");
    chip.textContent = (s.liveData ? "● LIVE DATA · " : "◌ DEMO DATA · ") + s.dataSource;
    chip.className = "chip " + (s.liveData ? "live" : "demo");
    $("#topEquity").textContent = fmtUsd(s.equity);
    $("#topDayPnl").textContent = fmtUsd(s.risk.dayPnl);
    $("#topDayPnl").className = clsPct(s.risk.dayPnl);
    $("#topMonthPnl").textContent = fmtUsd(s.risk.monthPnl);
    $("#topMonthPnl").className = clsPct(s.risk.monthPnl);
    $("#topRiskLeft").textContent = fmtUsd(s.risk.dailyRemainingUsd);
    $("#haltBanner").style.display = s.risk.halted ? "block" : "none";
    if (s.risk.halted)
      $("#haltBanner").textContent = "🛑 Trading halted — " + s.risk.haltReason;
    // risk gauges on dashboard
    const dPct = s.risk.dailyBudgetUsd
      ? Math.min(100, (s.risk.dailyUsedUsd / s.risk.dailyBudgetUsd) * 100) : 0;
    const mPct = s.risk.monthlyBudgetUsd
      ? Math.min(100, (s.risk.monthlyUsedUsd / s.risk.monthlyBudgetUsd) * 100) : 0;
    $("#dayGauge").style.width = dPct + "%";
    $("#monthGauge").style.width = mPct + "%";
    $("#dayBudget").textContent = fmtUsd(s.risk.dailyBudgetUsd);
    $("#dayUsed").textContent = fmtUsd(s.risk.dailyUsedUsd) + ` (${dPct.toFixed(0)}%)`;
    $("#monthBudget").textContent = fmtUsd(s.risk.monthlyBudgetUsd);
    $("#monthUsed").textContent = fmtUsd(s.risk.monthlyUsedUsd) + ` (${mPct.toFixed(0)}%)`;
    $("#keyStatus").textContent = s.apiKeysConfigured
      ? "keys loaded from .env (masked)" : "no keys configured (paper/demo still works)";
    $("#pfMode").textContent = paper ? "paper" : "live";
    if (scanData?.regime) $("#topRegime").textContent = scanData.regime.regime;
  } catch (e) { /* silent */ }
}

/* ---------------- scan ---------------- */
async function loadScan(force = false) {
  const tf = $("#tfSelect").value;
  try {
    $("#scanMeta").textContent = "scanning…";
    const s = await api(`/api/scan?force=${force ? 1 : 0}&tf=${tf}`);
    scanData = s;
    renderScan(s);
    renderDashboard(s);
  } catch (e) {
    $("#scanMeta").textContent = "scan failed — check server log";
  }
}

function renderScan(s) {
  $("#scanMeta").textContent =
    `${s.stats.scanned} coins · ${s.dataSource} · ${new Date(s.generatedAt).toLocaleTimeString()}${s.cached ? " · cached" : ""}`;
  const tb = $("#scanTable tbody");
  const rows = [...s.coins].sort((a, b) => {
    const av = sortVal(a, sortKey), bv = sortVal(b, sortKey);
    return (av > bv ? 1 : av < bv ? -1 : 0) * sortDir;
  });
  tb.innerHTML = rows.map((c) => {
    const plan = c.plan || {};
    const tp1 = plan.targets?.[0];
    return `<tr>
      <td class="sym">${c.symbol}</td>
      <td>${fmtPrice(c.price)}</td>
      <td class="${clsPct(c.change24h)}">${fmtPct(c.change24h)}</td>
      <td><b class="${clsPct(c.score)}">${c.score > 0 ? "+" : ""}${c.score}</b></td>
      <td><span class="badge ${c.signal}">${c.signal.replace("_", " ")}</span></td>
      <td>${c.confidence}%</td>
      <td>${c.indicators.atrPct}%</td>
      <td>${plan.entry ? `<span class="price-entry">${fmtPrice(plan.entry)}</span>` : "—"}</td>
      <td>${plan.stopLoss ? `<span class="price-stop">${fmtPrice(plan.stopLoss)}</span> <small class="muted">-${plan.stopPct}%</small>` : "—"}</td>
      <td>${tp1 ? `<span class="price-tp">${fmtPrice(tp1.price)}</span> <small class="muted">1R</small>` : "—"}</td>
      <td><button class="btn tiny" onclick="openChart('${c.symbol}')">chart</button>
          ${plan.side === "LONG" ? ` <button class="btn tiny" onclick="openTrade('${c.symbol}')">trade</button>` : ""}</td>
    </tr>`;
  }).join("");
}

function sortVal(c, k) {
  if (k === "price") return c.price;
  if (k === "change24h") return c.change24h;
  if (k === "score") return c.score;
  if (k === "confidence") return c.confidence;
  if (k === "atrPct") return c.indicators.atrPct;
  return c[k];
}
$$("#scanTable th[data-k]").forEach((th) =>
  th.addEventListener("click", () => {
    const k = th.dataset.k;
    sortDir = sortKey === k ? -sortDir : -1;
    sortKey = k;
    if (scanData) renderScan(scanData);
  }));

function renderDashboard(s) {
  const r = s.regime;
  $("#regimeValue").textContent = r.regime;
  $("#regimeValue").className = "big " +
    (r.regime === "RISK-ON" ? "up" : r.regime === "RISK-OFF" ? "down" : "");
  $("#regimeAdvice").textContent = r.advice;
  $("#breadth").textContent = `${r.breadth.pctUp}% up (${r.breadth.advancers}/${r.breadth.advancers + r.breadth.decliners})`;
  $("#avgChg").textContent = fmtPct(r.avgChange);
  $("#btcTrend").textContent = `${r.btc.trend} · RSI ${r.btc.rsi} · ${fmtPct(r.btc.change24h)}`;
  $("#topRegime").textContent = r.regime;
  $("#scanCount").textContent = s.stats.scanned;
  $("#buyCount").textContent = s.stats.buy;
  $("#weakBuyCount").textContent = s.stats.weakBuy;
  $("#sellCount").textContent = s.stats.sell;

  const tb = $("#topSignals tbody");  tb.innerHTML = s.coins.slice(0, 8).map((c) => `
    <tr><td class="sym">${c.symbol}</td>
    <td>${fmtPrice(c.price)}</td>
    <td class="${clsPct(c.change24h)}">${fmtPct(c.change24h)}</td>
    <td class="${clsPct(c.score)}">${c.score > 0 ? "+" : ""}${c.score}</td>
    <td><span class="badge ${c.signal}">${c.signal.replace("_", " ")}</span></td>
    <td><button class="btn tiny" onclick="openChart('${c.symbol}')">chart</button></td></tr>`).join("");

  loadPlanner(true);
  drawEquity();
}

/* ---------------- planner ---------------- */
async function loadPlanner(quiet = false) {
  try {
    const p = await api("/api/planner");
    $("#plTodayDate").textContent = p.today.date;
    $("#plTodayPnl").textContent = fmtUsd(p.today.pnl);
    $("#plTodayPnl").className = "big " + clsPct(p.today.pnl);
    $("#plTodayBudget").textContent = fmtUsd(p.today.budgetUsd);
    $("#plTodayRemaining").textContent = fmtUsd(p.today.remainingUsd);
    $("#plRisk").textContent = fmtUsd(p.today.suggestedRiskUsd);
    $("#plTradesLeft").textContent = p.today.tradesLeft;
    $("#plMonthLabel").textContent = p.month.label;
    $("#plMonthGauge").style.width = Math.min(100, p.month.usedPct) + "%";
    $("#plMonthPnl").textContent = fmtUsd(p.month.pnl);
    $("#plMonthBudget").textContent = fmtUsd(p.month.budgetUsd);
    $("#plMonthRemaining").textContent = fmtUsd(p.month.remainingUsd);
    $("#plOpenRisk").textContent = fmtUsd(p.openRiskUsd);

    $("#planDate").textContent = p.today.date;
    $("#planBudget").textContent = fmtUsd(p.today.budgetUsd);
    $("#planRemaining").textContent = fmtUsd(p.today.remainingUsd);
    $("#planRisk").textContent = fmtUsd(p.today.suggestedRiskUsd);
    $("#planTradesLeft").textContent = p.today.tradesLeft;
    $("#planNote").textContent = p.risk.halted
      ? "🛑 " + p.risk.haltReason
      : `Month ${p.month.label}: ${fmtUsd(p.month.pnl)} of ${fmtUsd(p.month.budgetUsd)} budget used. Rules: ${p.settings.daily_max_loss_pct}%/day, ${p.settings.monthly_max_loss_pct}%/month.`;

    const tb = $("#plannerTable tbody");
    tb.innerHTML = p.history.map((h) => `
      <tr><td>${h.date}</td><td>${fmtUsd(h.budget)}</td>
      <td class="${clsPct(h.pnl)}">${fmtUsd(h.pnl)}</td><td>${h.trades || ""}</td>
      <td>${h.pnl < 0 && Math.abs(h.pnl) >= h.budget
        ? '<span class="badge SELL">LIMIT HIT</span>'
        : h.pnl < 0 ? '<span class="badge WEAK_SELL">loss</span>'
        : h.pnl > 0 ? '<span class="badge BUY">profit</span>'
        : '<span class="badge NEUTRAL">flat</span>'}</td></tr>`).join("");
  } catch (e) { if (!quiet) toast("planner failed", true); }
}

$("#btnResetAccount").addEventListener("click", async () => {
  if (!confirm("Reset paper account to start equity and clear all risk counters?")) return;
  const r = await api("/api/portfolio/reset", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  toast(`Account reset — equity ${fmtUsd(r.equity)}`);
  loadPlanner(); loadPortfolio(); loadStatus();
});

/* ---------------- chart ---------------- */
window.openChart = (sym) => {
  currentSymbol = sym;
  activateTab("charts");
  loadChart(sym);
};
window.openTrade = async (sym) => {
  if (!scanData) await loadScan();
  const c = scanData?.coins.find((x) => x.symbol === sym);
  if (!c || c.plan?.side !== "LONG") return toast("No LONG plan for " + sym, true);
  try {
    const res = await api("/api/portfolio/positions", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: sym, plan: c.plan, price: c.price,
                             score: c.score, confidence: c.confidence }),
    });
    toast(`Opened ${sym} — entry ${fmtPrice(res.position.entry)}, SL ${fmtPrice(res.position.stop)}`);
    if (res.liveError) toast("LIVE ORDER FAILED: " + res.liveError, true);
    loadPortfolio(); loadStatus();
  } catch (e) { /* toast handled */ }
};

function ensureChart() {
  if (chart) return chart;
  chart = LightweightCharts.createChart($("#candleChart"), {
    layout: { background: { color: "#0d1322" }, textColor: "#7f8db0" },
    grid: { vertLines: { color: "#182036" }, horzLines: { color: "#182036" } },
    crosshair: { mode: 0 },
    rightPriceScale: { borderColor: "#232e47" },
    timeScale: { borderColor: "#232e47", timeVisible: true, secondsVisible: false },
    autoSize: true,
  });
  candleSeries = chart.addCandlestickSeries({
    upColor: "#2fd48f", downColor: "#ff5c7a",
    wickUpColor: "#2fd48f", wickDownColor: "#ff5c7a",
    borderVisible: false,
  });
  ["ema9", "ema21", "ema50"].forEach((k, i) => {
    emaSeries[k] = chart.addLineSeries({
      color: ["#ffb020", "#4da3ff", "#c084fc"][i],
      lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
      title: k.toUpperCase(),
    });
  });
  return chart;
}

async function loadChart(sym) {
  currentSymbol = sym.toUpperCase();
  const tf = $("#chartTfSelect").value;
  $("#chartSymbol").textContent = currentSymbol;
  try {
    const a = await api(`/api/symbol/${currentSymbol}?tf=${tf}`);
    if (a.error) return toast(a.error, true);
    ensureChart();
    const kls = a.candles.map((c) => ({
      time: Math.floor(c.openTime / 1000),
      open: c.open, high: c.high, low: c.low, close: c.close,
    }));
    candleSeries.setData(kls);
    const closes = a.candles.map((c) => c.close);
    const paint = (k, period) => {
      const arr = emaArr(closes, period);
      emaSeries[k].setData(arr.map((v, i) => v == null ? null : ({
        time: Math.floor(a.candles[i].openTime / 1000), value: v,
      })).filter(Boolean));
    };
    paint("ema9", 9); paint("ema21", 21); paint("ema50", 50);
    // entry / SL / TP price lines
    clearPriceLines();
    const plan = a.plan || {};
    if (plan.entry) addPriceLine(plan.entry, "#2fd48f", "ENTRY", "solid");
    if (plan.stopLoss) addPriceLine(plan.stopLoss, "#ff5c7a", "SL", "dashed");
    (plan.targets || []).forEach((t) =>
      addPriceLine(t.price, "#4da3ff", "TP" + t.n, "dotted"));
    chart.timeScale().fitContent();

    $("#chartTf").textContent = `· ${tf} · ${a.dataSource}`;
    $("#chartLegend").innerHTML =
      `<span><i style="background:#ffb020"></i>EMA9</span>
       <span><i style="background:#4da3ff"></i>EMA21</span>
       <span><i style="background:#c084fc"></i>EMA50</span>
       <span style="color:#2fd48f">— Entry ${plan.entry ? fmtPrice(plan.entry) : "—"}</span>
       <span style="color:#ff5c7a">-- Stop ${plan.stopLoss ? fmtPrice(plan.stopLoss) : "—"}</span>
       <span style="color:#4da3ff">·· TP ${(plan.targets || []).map((t) => fmtPrice(t.price)).join(" / ") || "—"}</span>`;
    renderPlan(a);
    renderChecks(a);
    $("#quickSymbols").innerHTML =
      ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "LINKUSDT", "ADAUSDT"]
        .map((s) => `<button class="btn tiny" onclick="openChart('${s}')">${s}</button>`).join("");
  } catch (e) { /* toast handled */ }
}

let priceLines = [];
function addPriceLine(price, color, title, style) {
  const pl = candleSeries.createPriceLine({
    price, color, lineWidth: 1, lineStyle: style === "solid" ? 0 : style === "dashed" ? 1 : 2,
    axisLabelVisible: true, title,
  });
  priceLines.push(pl);
}
function clearPriceLines() {
  priceLines.forEach((pl) => { try { candleSeries.removePriceLine(pl); } catch (e) {} });
  priceLines = [];
}
function emaArr(values, period) {
  const out = new Array(values.length).fill(null);
  if (values.length < period) return out;
  const k = 2 / (period + 1);
  let prev = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = prev;
  for (let i = period; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

function renderPlan(a) {
  const p = a.plan || {};
  const box = $("#planBox");
  if (p.side === "LONG") {
    const pos = p.position || {};
    box.innerHTML = `
      <div class="row"><span class="badge LONG">LONG PLAN</span>
        <b class="${clsPct(a.score)}">score ${a.score > 0 ? "+" : ""}${a.score}</b></div>
      <p class="muted" style="margin:8px 0">${p.reason}</p>
      <div class="prow"><span>Entry</span><b class="price-entry">${fmtPrice(p.entry)} <small class="muted">${p.entryType}</small></b></div>
      <div class="prow"><span>Stop-loss</span><b class="price-stop">${fmtPrice(p.stopLoss)} <small class="muted">-${p.stopPct}%</small></b></div>
      ${(p.targets || []).map((t) => `
        <div class="prow"><span>TP${t.n} (R ${t.rr}) ${t.note}</span>
        <b class="price-tp">${fmtPrice(t.price)} <small class="muted">${fmtPct(t.pct)} · ${fmtUsd(t.usd)}</small></b></div>`).join("")}
      <div class="prow"><span>Position size</span><b>${pos.qty} ≈ ${fmtUsd(pos.notionalUsd)}</b></div>
      <div class="prow"><span>Risk on this trade</span><b class="down">${fmtUsd(pos.riskUsd)} (${pos.riskPct}% eq)</b></div>
      <div class="plan-actions">
        <button class="btn" onclick="openTrade('${a.symbol}')">▶ Take this trade</button>
      </div>`;
  } else if (p.side === "SHORT_WATCH") {
    box.innerHTML = `<div class="row"><span class="badge SHORT_WATCH">SELL / AVOID</span></div>
      <p class="muted" style="margin-top:8px">${p.reason}</p>`;
  } else {
    box.innerHTML = `<div class="row"><span class="badge NONE">NO TRADE</span></div>
      <p class="muted" style="margin-top:8px">${p.reason || "Wait for a clearer setup."}</p>`;
  }
}

function renderChecks(a) {
  const b = $("#signalBadge");
  b.textContent = a.signal.replace("_", " ");
  b.className = "badge " + a.signal;
  $("#scoreFill").style.width = ((a.score + 100) / 2) + "%";
  $("#checksTable tbody").innerHTML = (a.checks || []).map((c) => `
    <tr><td>${c.name}</td>
    <td class="${clsPct(c.points)}" style="width:52px">${c.points > 0 ? "+" : ""}${c.points}</td>
    <td class="muted">${c.note}</td></tr>`).join("");
  const i = a.indicators;
  $("#indLine1").textContent =
    `RSI ${i.rsi} / ADX ${i.adx} / ATR ${i.atrPct}% / StochK ${i.stochK} / Vol×${i.volRatio}`;
  $("#patternLine").textContent = (a.patterns || []).join(", ") || "none";
  $("#srLine").textContent = `S ${fmtPrice(a.levels.support)} · R ${fmtPrice(a.levels.resistance)}`;
}
$("#btnLoadChart").addEventListener("click", () =>
  loadChart($("#symbolInput").value.trim() || "BTCUSDT"));
$("#symbolInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") loadChart($("#symbolInput").value.trim());
});

/* ---------------- portfolio ---------------- */
async function loadPortfolio() {
  try {
    const p = await api("/api/portfolio");
    $("#pfEquity").textContent = fmtUsd(p.equity);
    $("#pfCash").textContent = fmtUsd(p.cash);
    $("#pfStart").textContent = fmtUsd(p.startEquity);
    $("#pfUnreal").textContent = fmtUsd(p.unrealized);
    $("#pfUnreal").className = "big " + clsPct(p.unrealized);
    $("#pfOpenRisk").textContent = fmtUsd(p.openRiskUsd);
    $("#pfOpen").textContent = p.openPositions.length;
    $("#pfWinRate").textContent = p.stats.winRate + "%";
    $("#pfPF").textContent = p.stats.profitFactor ?? "∞";
    $("#pfTrades").textContent = p.stats.totalTrades;
    $("#pfNet").textContent = fmtUsd(p.stats.netPnl);
    $("#pfNet").className = "big " + clsPct(p.stats.netPnl);
    $("#pfReturn").textContent = fmtPct(p.stats.returnPct);
    $("#topEquity").textContent = fmtUsd(p.equity);
    $("#openCount").textContent = p.openPositions.length;

    $("#posTable tbody").innerHTML = p.openPositions.map((o) => `
      <tr>
        <td class="sym">${o.symbol}</td><td>${o.qty}</td>
        <td>${fmtPrice(o.entry)}</td><td>${fmtPrice(o.mark)}</td>
        <td class="${clsPct(o.upnl)}">${fmtUsd(o.upnl)} <small>${fmtPct(o.upnlPct)}</small></td>
        <td class="price-stop">${fmtPrice(o.stop)}</td>
        <td>${(o.targets || []).map((t) =>
          `<small class="${t.hit ? "muted" : "price-tp"}">${t.label}${t.hit ? "✓" : " " + fmtPrice(t.price)}</small>`).join(" · ")}</td>
        <td>${fmtUsd(o.riskUsd)}</td>
        <td><button class="btn tiny danger" onclick="closePos('${o.id}')">close</button></td>
      </tr>`).join("") || `<tr><td colspan="9" class="muted">No open positions. Run a scan and take a plan.</td></tr>`;

    $("#tradeTable tbody").innerHTML = p.trades.slice(0, 50).map((t) => `
      <tr><td>${new Date(t.closedAt).toLocaleString()}</td>
      <td class="sym">${t.symbol}</td><td>${fmtPrice(t.entry)}</td>
      <td>${fmtPrice(t.exit)}</td>
      <td class="${clsPct(t.pnl)}">${fmtUsd(t.pnl)}</td>
      <td class="${clsPct(t.pnl)}">${fmtPct(t.pct)}</td>
      <td class="muted">${t.reason}</td></tr>`).join("")
      || `<tr><td colspan="7" class="muted">No closed trades yet.</td></tr>`;

    drawEquity(p.equityCurve);
  } catch (e) { /* silent */ }
}
window.closePos = async (id) => {
  if (!confirm("Close this position at market?")) return;
  try {
    const r = await api("/api/portfolio/close", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ positionId: id }),
    });
    toast(`Closed at ${fmtPrice(r.closed.exit)} · PnL ${fmtUsd(r.closed.pnl)}`);
    loadPortfolio(); loadStatus(); loadPlanner(true);
  } catch (e) {}
};

let lastCurve = null;
function drawEquity(curve) {
  const cv = $("#equityCanvas");
  if (!cv) return;
  const data = curve || lastCurve;
  if (curve) lastCurve = curve;
  const ctx = cv.getContext("2d");
  ctx.clearRect(0, 0, cv.width, cv.height);
  if (!data || data.length < 2) {
    ctx.fillStyle = "#7f8db0";
    ctx.font = "12px sans-serif";
    ctx.fillText("equity curve appears after activity", 16, 70);
    return;
  }
  const vals = data.map((d) => d.equity);
  const min = Math.min(...vals), max = Math.max(...vals);
  const pad = (max - min) * 0.15 || 1;
  const y = (v) => cv.height - 10 - ((v - min + pad) / (max - min + 2 * pad)) * (cv.height - 20);
  const x = (i) => (i / (data.length - 1)) * (cv.width - 10) + 5;
  const up = vals[vals.length - 1] >= vals[0];
  ctx.beginPath();
  vals.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))));
  ctx.strokeStyle = up ? "#2fd48f" : "#ff5c7a";
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.lineTo(x(vals.length - 1), cv.height);
  ctx.lineTo(x(0), cv.height);
  ctx.closePath();
  ctx.fillStyle = up ? "#2fd48f22" : "#ff5c7a22";
  ctx.fill();
  $("#equityReturn").textContent = fmtPct((vals[vals.length - 1] / vals[0] - 1) * 100);
  $("#equityReturn").className = clsPct(vals[vals.length - 1] - vals[0]);
}

/* ---------------- backtest ---------------- */
$("#btnBacktest").addEventListener("click", async () => {
  const btn = $("#btnBacktest");
  btn.disabled = true;
  btn.textContent = "⏳ running…";
  try {
    const r = await api("/api/backtest", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: $("#btSymbol").value.trim().toUpperCase() || "BTCUSDT",
        timeframe: $("#btTf").value,
        limit: parseInt($("#btLimit").value, 10),
      }),
    });
    if (r.error) return toast(r.error, true);
    $("#btResults").style.display = "grid";
    $("#btNet").textContent = fmtUsd(r.netPnl);
    $("#btNet").className = "big " + clsPct(r.netPnl);
    $("#btReturn").textContent = fmtPct(r.returnPct) + " on " + fmtUsd(r.startEquity);
    $("#btWin").textContent = r.winRate + "%";
    $("#btTradesN").textContent = r.trades + " trades";
    $("#btPF").textContent = r.profitFactor ?? "∞";
    $("#btDD").textContent = r.maxDrawdownPct + "%";
    $("#btDD").className = "big down";
    $("#btNote").textContent = r.note;
    // equity curve
    const cv = $("#btCanvas");
    cv.style.display = "block";
    const ctx = cv.getContext("2d");
    ctx.clearRect(0, 0, cv.width, cv.height);
    const c = r.equityCurve;
    if (c.length > 1) {
      const mn = Math.min(...c), mx = Math.max(...c);
      const yy = (v) => cv.height - 8 - ((v - mn) / (mx - mn || 1)) * (cv.height - 16);
      const xx = (i) => (i / (c.length - 1)) * (cv.width - 10) + 5;
      ctx.beginPath();
      c.forEach((v, i) => (i ? ctx.lineTo(xx(i), yy(v)) : ctx.moveTo(xx(i), yy(v))));
      ctx.strokeStyle = c[c.length - 1] >= c[0] ? "#2fd48f" : "#ff5c7a";
      ctx.lineWidth = 2;
      ctx.stroke();
    }
    $("#btTrades tbody").innerHTML = `<tr><th>closed@bar</th><th>entry</th><th>exit</th><th>pnl</th><th>reason</th></tr>` +
      r.lastTrades.map((t) => `<tr><td>#${t.closedBar}</td><td>${fmtPrice(t.entry)}</td>
        <td>${fmtPrice(t.exit)}</td><td class="${clsPct(t.pnl)}">${fmtUsd(t.pnl)}</td>
        <td class="muted">${t.reason}</td></tr>`).join("");
  } catch (e) {}
  btn.disabled = false;
  btn.textContent = "▶ Run backtest";
});

/* ---------------- team & references ---------------- */
let teamLoaded = false;
async function loadTeamRefs() {
  if (teamLoaded) return;
  teamLoaded = true;
  try {
    const [team, refs] = await Promise.all([api("/api/team"), api("/api/references")]);
    $("#teamList").innerHTML = team.map((r) => `
      <div class="role"><div class="ico">${r.icon}</div>
      <div><b>${r.role}</b> <span class="muted">— ${r.name}</span>
      <p>${r.contribution}</p></div></div>`).join("");
    $("#refList").innerHTML = refs.map((r) => `
      <div class="ref"><div class="ico">${r.icon}</div>
      <div><b>${r.name}</b>
      <p>${r.summary}</p>
      <div class="tags">${(r.borrowed || []).map((t) => `<span class="tag">✓ ${t}</span>`).join("")}</div>
      <a href="${r.url}" target="_blank" rel="noopener">${r.url}</a></div></div>`).join("");
  } catch (e) { teamLoaded = false; }
}

/* ---------------- settings ---------------- */
$("#btnSettings").addEventListener("click", async () => {
  const s = await api("/api/settings");
  $("#setMode").value = s.trading_mode;
  $("#setDataMode").value = s.data_mode;
  $("#setAccount").value = s.account_size;
  $("#setRisk").value = s.risk_per_trade_pct;
  $("#setDaily").value = s.daily_max_loss_pct;
  $("#setMonthly").value = s.monthly_max_loss_pct;
  $("#setMaxPos").value = s.max_open_positions;
  $("#setMaxSym").value = s.max_per_symbol_pct;
  $("#setAtr").value = s.atr_sl_mult;
  $("#setScan").value = s.scan_limit;
  $("#settingsModal").classList.add("open");
});
$("#btnCloseSettings").addEventListener("click", () =>
  $("#settingsModal").classList.remove("open"));
$("#btnCancelSettings").addEventListener("click", () =>
  $("#settingsModal").classList.remove("open"));
$("#btnSaveSettings").addEventListener("click", async () => {
  const body = {
    trading_mode: $("#setMode").value,
    data_mode: $("#setDataMode").value,
    account_size: parseFloat($("#setAccount").value),
    risk_per_trade_pct: parseFloat($("#setRisk").value),
    daily_max_loss_pct: parseFloat($("#setDaily").value),
    monthly_max_loss_pct: parseFloat($("#setMonthly").value),
    max_open_positions: parseInt($("#setMaxPos").value, 10),
    max_per_symbol_pct: parseFloat($("#setMaxSym").value),
    atr_sl_mult: parseFloat($("#setAtr").value),
    scan_limit: parseInt($("#setScan").value, 10),
  };
  await api("/api/settings", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (body.trading_mode === "live" &&
      !confirm("LIVE MODE sends real orders on Binance. Continue?"))
    { $("#setMode").value = "paper"; return; }
  toast("Settings saved");
  $("#settingsModal").classList.remove("open");
  loadStatus();
  loadScan(true);
});

/* ---------------- misc ---------------- */
$("#btnRefresh").addEventListener("click", () => loadScan(true));
$("#btnForceScan").addEventListener("click", () => loadScan(true));
$("#tfSelect").addEventListener("change", () => loadScan(true));

/* boot */
loadStatus();
loadScan();
loadPortfolio();
loadPlanner(true);
setInterval(loadStatus, 20000);
setInterval(loadPortfolio, 30000);
