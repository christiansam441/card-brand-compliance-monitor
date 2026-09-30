"use strict";

const app = document.getElementById("app");
const metaEl = document.getElementById("meta");

const STATUS_TEXT = { SAFE: "● SAFE", WATCH: "▲ WATCH", BREACH: "■ BREACH" };
const STATUS_RANK = { SAFE: 0, WATCH: 1, BREACH: 2 };
const SVG_NS = "http://www.w3.org/2000/svg";

const state = { data: null, sortKey: "worst", sortDir: "desc", search: "", vertical: "all", status: "all" };

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (r, d = 2) => (r === null || r === undefined ? "n/a" : (r * 100).toFixed(d) + "%");
const num = (n) => Number(n).toLocaleString("en-US");
const badge = (status, cls = "") => `<span class="badge s-${status.toLowerCase()} ${cls}">${STATUS_TEXT[status]}</span>`;

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

/* ------------------------------------------------------------ portfolio */

function visaSub(v) {
  if (v.below_floor) return `<span class="sub">below enforcement floor</span>`;
  return "";
}

function mcSub(m) {
  if (m.tier === "HECM") return `<span class="sub">HECM</span>`;
  if (m.near_hecm) return `<span class="sub">ECM, nearing HECM</span>`;
  if (m.tier === "ECM") return `<span class="sub">ECM</span>`;
  if (m.in_program) return `<span class="sub">in ECM program, ${m.clean_months}/3 clean months</span>`;
  return "";
}

function sortValue(m, key) {
  switch (key) {
    case "name": return m.name.toLowerCase();
    case "vertical": return m.vertical.toLowerCase();
    case "visa_ratio": return m.visa.ratio ?? -1;
    case "visa_events": return m.visa.events;
    case "visa_status": return STATUS_RANK[m.visa.status];
    case "mc_ratio": return m.mc.ratio ?? -1;
    case "mc_cb": return m.mc.chargebacks;
    case "mc_status": return STATUS_RANK[m.mc.status];
    default: return STATUS_RANK[m.worst] * 1000 + Math.max(m.visa.ratio ?? 0, m.mc.ratio ?? 0);
  }
}

function filteredMerchants() {
  const q = state.search.trim().toLowerCase();
  const rows = state.data.merchants.filter((m) =>
    (state.vertical === "all" || m.vertical === state.vertical) &&
    (state.status === "all" || m.worst === state.status) &&
    (!q || m.name.toLowerCase().includes(q) || m.id.toLowerCase().includes(q)));
  const dir = state.sortDir === "asc" ? 1 : -1;
  rows.sort((a, b) => {
    const x = sortValue(a, state.sortKey), y = sortValue(b, state.sortKey);
    return (x < y ? -1 : x > y ? 1 : a.name.localeCompare(b.name)) * dir;
  });
  return rows;
}

function bannerHTML(d) {
  const b = d.book, lines = d.lines;
  const scaleMax = Math.max(0.01, b.ratio * 1.2);
  const at = (r) => Math.min(100, (r / scaleMax) * 100);
  const over = b.ratio >= lines.above_standard;
  const status = b.label === "STANDARD" ? "SAFE" : b.label === "WATCH" ? "WATCH" : "BREACH";
  const head = b.headroom_events >= 0
    ? `<b>${num(b.headroom_events)}</b> events of headroom before ${pct(lines.above_standard, 2)}`
    : `<b>${num(-b.headroom_events)}</b> events over the ${pct(lines.above_standard, 2)} line`;
  const prev = d.book_history[d.book_history.length - 2];
  return `
  <section class="panel">
    <div class="panel-head"><span>Acquirer VAMP ratio · ${esc(d.month)}</span><span class="dim">all merchants combined</span></div>
    <div class="panel-body banner">
      <div>
        <div class="banner-ratio">${pct(b.ratio, 3)}</div>
        <div class="banner-label"><span class="badge s-${status.toLowerCase()} lg">${esc(b.label)}</span></div>
      </div>
      <div>
        <div class="gauge" role="img" aria-label="Acquirer ratio ${pct(b.ratio, 3)} against 0.50% and 0.70% lines">
          <div class="gauge-fill ${over ? "over" : ""}" style="width:${at(b.ratio)}%"></div>
          <div class="gauge-tick" style="left:${at(lines.above_standard)}%"><span>${pct(lines.above_standard)} above standard</span></div>
          <div class="gauge-tick ex" style="left:${at(lines.excessive)}%"><span>${pct(lines.excessive)} excessive</span></div>
        </div>
        <div class="banner-notes">
          <span>${head}</span>
          <span><b>${num(b.events)}</b> fraud + dispute events / <b>${num(b.sales)}</b> CNP transactions</span>
          ${prev ? `<span>prior month <b>${pct(prev.ratio, 3)}</b></span>` : ""}
        </div>
      </div>
    </div>
  </section>`;
}

function tableHTML(rows) {
  const th = (key, label, cls = "") => {
    const sorted = state.sortKey === key;
    return `<th class="${cls} ${sorted ? "sorted" : ""} ${sorted && state.sortDir === "asc" ? "asc" : ""}" data-sort="${key}" tabindex="0">${label}</th>`;
  };
  if (!rows.length) return `<div class="empty">No merchants match these filters.</div>`;
  const body = rows.map((m) => `
    <tr data-id="${esc(m.id)}" tabindex="0">
      <td>${esc(m.name)}<div class="id">${esc(m.id)}</div></td>
      <td>${esc(m.vertical)}</td>
      <td class="num">${pct(m.visa.ratio)}</td>
      <td class="num">${num(m.visa.events)}</td>
      <td>${badge(m.visa.status)}${visaSub(m.visa)}</td>
      <td class="num">${pct(m.mc.ratio)}</td>
      <td class="num">${num(m.mc.chargebacks)}</td>
      <td>${badge(m.mc.status)}${mcSub(m.mc)}</td>
      <td>${badge(m.worst)}</td>
    </tr>`).join("");
  return `
  <div class="table-wrap"><table>
    <thead>
      <tr><th class="group" colspan="2"></th><th class="group" colspan="3">Visa VAMP</th><th class="group" colspan="3">Mastercard ECM / HECM</th><th class="group"></th></tr>
      <tr>
        ${th("name", "Merchant")}${th("vertical", "Vertical")}
        ${th("visa_ratio", "Ratio", "num")}${th("visa_events", "Events", "num")}${th("visa_status", "Status")}
        ${th("mc_ratio", "Ratio", "num")}${th("mc_cb", "Chargebacks", "num")}${th("mc_status", "Status")}
        ${th("worst", "Worst")}
      </tr>
    </thead>
    <tbody>${body}</tbody>
  </table></div>`;
}

function renderPortfolio() {
  const d = state.data;
  const verticals = [...new Set(d.merchants.map((m) => m.vertical))].sort();
  app.innerHTML = `
    ${bannerHTML(d)}
    <div class="filters">
      <label for="f-search">Search</label><input id="f-search" type="search" placeholder="name or id" value="${esc(state.search)}">
      <label for="f-vertical">Vertical</label>
      <select id="f-vertical"><option value="all">all</option>${verticals.map((v) => `<option ${v === state.vertical ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
      <label for="f-status">Worst status</label>
      <select id="f-status">${["all", "BREACH", "WATCH", "SAFE"].map((s) => `<option value="${s}" ${s === state.status ? "selected" : ""}>${s === "all" ? "all" : s.toLowerCase()}</option>`).join("")}</select>
      <span class="count" id="count"></span>
    </div>
    <section class="panel" id="table-panel"></section>`;
  drawTable();
  document.getElementById("f-search").addEventListener("input", (e) => { state.search = e.target.value; drawTable(); });
  document.getElementById("f-vertical").addEventListener("change", (e) => { state.vertical = e.target.value; drawTable(); });
  document.getElementById("f-status").addEventListener("change", (e) => { state.status = e.target.value; drawTable(); });
}

function drawTable() {
  const rows = filteredMerchants();
  document.getElementById("table-panel").innerHTML = tableHTML(rows);
  document.getElementById("count").textContent = `showing ${rows.length} of ${state.data.merchants.length} merchants · ${state.data.month}`;
  const panel = document.getElementById("table-panel");
  panel.querySelectorAll("th[data-sort]").forEach((el) => {
    const go = () => {
      const key = el.dataset.sort;
      if (state.sortKey === key) state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
      else { state.sortKey = key; state.sortDir = key === "name" || key === "vertical" ? "asc" : "desc"; }
      drawTable();
    };
    el.addEventListener("click", go);
    el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
  });
  panel.querySelectorAll("tbody tr").forEach((tr) => {
    const open = () => { location.hash = `#/merchant/${tr.dataset.id}`; };
    tr.addEventListener("click", open);
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
  });
}

/* --------------------------------------------------------------- detail */

function svgEl(name, attrs = {}, text) {
  const el = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (text !== undefined) el.textContent = text;
  return el;
}

/* Line chart with drawn threshold lines. values are ratios (0.015 = 1.5%). */
function lineChart({ months, values, statuses, lines, label }) {
  const W = 560, H = 250, L = 46, R = 92, T = 14, B = 30;
  const maxData = Math.max(...values.filter((v) => v !== null));
  const yMax = Math.max(maxData, ...lines.map((l) => l.y)) * 1.18;
  const x = (i) => L + (i * (W - L - R)) / Math.max(1, months.length - 1);
  const y = (v) => T + (1 - v / yMax) * (H - T - B);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": label });

  const step = [0.0025, 0.005, 0.01, 0.0125, 0.02].find((s) => yMax / s <= 7) || 0.025;
  for (let v = 0; v <= yMax; v += step) {
    svg.append(svgEl("line", { class: "grid", x1: L, x2: W - R, y1: y(v), y2: y(v) }));
    svg.append(svgEl("text", { class: "tick", x: L - 6, y: y(v) + 4, "text-anchor": "end" }, (v * 100).toFixed(step < 0.005 ? 2 : 1) + "%"));
  }
  months.forEach((m, i) => svg.append(svgEl("text", { class: "tick", x: x(i), y: H - 9, "text-anchor": "middle" }, m.slice(5))));
  svg.append(svgEl("line", { class: "axis", x1: L, x2: W - R, y1: y(0), y2: y(0) }));

  lines.forEach((l) => {
    svg.append(svgEl("line", { class: "thr", x1: L, x2: W - R + 6, y1: y(l.y), y2: y(l.y), stroke: l.color }));
    svg.append(svgEl("text", { class: "thr-label", x: W - R + 10, y: y(l.y) + 4, fill: l.color }, l.text));
  });

  svg.append(svgEl("polyline", { class: "series", points: values.map((v, i) => `${x(i)},${y(v ?? 0)}`).join(" ") }));
  values.forEach((v, i) => {
    const c = svgEl("circle", { class: `dot-${statuses[i].toLowerCase()}`, cx: x(i), cy: y(v ?? 0), r: 5 });
    c.append(svgEl("title", {}, `${months[i]}: ${pct(v)} (${statuses[i].toLowerCase()})`));
    svg.append(c);
  });
  return svg;
}

function chartPanel(title, sub, svg) {
  const wrap = document.createElement("section");
  wrap.className = "panel chart";
  wrap.innerHTML = `<div class="panel-head"><span>${esc(title)}</span><span class="dim">${esc(sub)}</span></div><div class="panel-body"></div>`;
  const body = wrap.querySelector(".panel-body");
  body.append(svg);
  body.insertAdjacentHTML("beforeend", `<div class="legend"><span><i style="background:var(--safe)"></i>safe</span><span><i style="background:var(--watch)"></i>watch</span><span><i style="background:var(--breach)"></i>breach</span></div>`);
  return wrap;
}

function whatIfHTML(d) {
  const { visa, mc } = d.what_if;
  const lt = d.latest;
  const visaMsg = visa.cut > 0
    ? `<div class="big">${num(visa.cut)} fewer events</div><div class="note">next month, at the same volume (${num(lt.visa.sales)} CNP transactions): ${num(visa.events_now)} → ${num(visa.target_events)} or fewer, i.e. ${esc(visa.route)}.</div>`
    : `<div class="big">0 · already under</div><div class="note">${lt.visa.status === "SAFE" ? "Not over either enforcement condition at this volume." : "Not enforceable at this volume."}</div>${lt.visa.below_floor ? `<div class="note warn">Ratio is at or above ${pct(d.thresholds.visa_ratio)} but events are below the ${num(d.thresholds.visa_floor)} floor. Growth in events would make it enforceable.</div>` : ""}`;

  const one = (w, name) => w.cut > 0
    ? `<div class="big">${num(w.cut)} fewer chargebacks</div><div class="note">${name}: ${num(mc.chargebacks_now)} → ${num(w.target_chargebacks)} or fewer next month (${esc(w.route)}), measured against this month's ${num(lt.mc.sales)} sales.</div>`
    : `<div class="big">${lt.mc.tier ? "0 · volume alone gets it under" : "0 · already under"}</div><div class="note">${name}: if volume holds, ${num(mc.chargebacks_now)} chargebacks next month would be below the line, because next month is measured against this month's ${num(lt.mc.sales)} sales.</div>`;
  const exitNote = lt.mc.in_program
    ? `<div class="note warn">Currently in the ECM program (${lt.mc.clean_months} of ${mc.exit_months} clean months). Exit needs ${mc.exit_months} consecutive months under the ECM thresholds, so one clean month is not enough.</div>`
    : "";
  const growth = lt.mc.tier && lt.mc.same_month_ratio !== null && lt.mc.same_month_ratio < d.thresholds.mc_ecm_ratio
    ? `<div class="note warn">Growth effect: against same-month sales this ratio would be ${pct(lt.mc.same_month_ratio)}. The rule divides by PRIOR month sales (${num(lt.mc.prior_sales)}), which inflates it for fast-growing merchants.</div>`
    : "";

  return `
    <div class="whatif-row"><div class="k">Visa VAMP</div><div>${visaMsg}</div></div>
    <div class="whatif-row"><div class="k">Mastercard ECM</div><div>${one(mc.ecm, "ECM")}${growth}${exitNote}</div></div>
    <div class="whatif-row"><div class="k">Mastercard HECM</div><div>${one(mc.hecm, "HECM")}</div></div>`;
}

function monthTableHTML(d) {
  const rows = d.months.map((m) => `
    <tr style="cursor:default">
      <td>${esc(m.month)}</td>
      <td class="num">${num(m.visa.events)}</td><td class="num">${pct(m.visa.ratio)}</td><td>${badge(m.visa.status)}${visaSub(m.visa)}</td>
      <td class="num">${num(m.mc.chargebacks)}</td><td class="num">${pct(m.mc.ratio)}</td><td>${badge(m.mc.status)}${mcSub(m.mc)}</td>
      <td class="num">$${num(m.mc.chargeback_dollars)}</td>
    </tr>`).join("");
  return `<div class="table-wrap"><table>
    <thead><tr><th>Month</th><th class="num">Visa events</th><th class="num">Visa ratio</th><th>Visa</th><th class="num">MC chargebacks</th><th class="num">MC ratio</th><th>MC</th><th class="num">MC chargeback $</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

async function renderDetail(id) {
  app.innerHTML = `<div class="empty">loading…</div>`;
  let d;
  try { d = await getJSON(`/api/merchants/${encodeURIComponent(id)}`); }
  catch { app.innerHTML = `<div class="crumb"><a href="#/">&lt; portfolio</a></div><div class="empty">Merchant not found.</div>`; return; }

  const months = d.months.map((m) => m.month);
  const t = d.thresholds;
  app.innerHTML = `
    <div class="crumb"><a href="#/">&lt; portfolio</a></div>
    <div class="detail-head"><h1>${esc(d.name)}</h1><span class="dim">${esc(d.id)} · ${esc(d.vertical)}</span>${badge(d.latest.worst, "lg")}</div>
    <div class="grid-2" id="charts"></div>
    <section class="panel" style="margin-top:16px"><div class="panel-head"><span>What-if · next month</span><span class="dim">how many fewer to get under each line</span></div><div class="panel-body">${whatIfHTML(d)}</div></section>
    <section class="panel" style="margin-top:16px"><div class="panel-head"><span>Monthly detail</span><span class="dim">6 evaluated months</span></div>${monthTableHTML(d)}</section>`;

  const charts = document.getElementById("charts");
  charts.append(chartPanel("Visa VAMP ratio", `line at ${pct(t.visa_ratio)} · enforceable at ${num(t.visa_floor)}+ events`, lineChart({
    months, values: d.months.map((m) => m.visa.ratio), statuses: d.months.map((m) => m.visa.status),
    label: "Visa VAMP ratio by month with the 1.5 percent threshold",
    lines: [{ y: t.visa_ratio, text: `${pct(t.visa_ratio)} VAMP`, color: "var(--breach)" }],
  })));
  charts.append(chartPanel("Mastercard chargeback ratio", "chargebacks ÷ prior-month sales", lineChart({
    months, values: d.months.map((m) => m.mc.ratio), statuses: d.months.map((m) => m.mc.status),
    label: "Mastercard ratio by month with ECM and HECM thresholds",
    lines: [
      { y: t.mc_ecm_ratio, text: `${pct(t.mc_ecm_ratio)} ECM`, color: "var(--amber)" },
      { y: t.mc_hecm_ratio, text: `${pct(t.mc_hecm_ratio)} HECM`, color: "var(--breach)" },
    ],
  })));
}

/* --------------------------------------------------------------- router */

async function route() {
  const m = location.hash.match(/^#\/merchant\/(.+)$/);
  window.scrollTo(0, 0);
  if (m) return renderDetail(decodeURIComponent(m[1]));
  if (!state.data) {
    try { state.data = await getJSON("/api/portfolio"); }
    catch { app.innerHTML = `<div class="empty">Could not load portfolio data.</div>`; return; }
    metaEl.textContent = `data: synthetic · evaluated month ${state.data.month} · ${state.data.merchants.length} merchants`;
  }
  renderPortfolio();
}

window.addEventListener("hashchange", route);
route();
