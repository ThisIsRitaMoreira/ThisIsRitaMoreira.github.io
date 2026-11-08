/* =========================================================
   Case 04 — Fleet driver risk (BUAN 6346). Data: window.DATA_FLEET,
   built by analysis/fleet_risk.py from the project's own files.
   ========================================================= */
(function () {
  const D = window.DATA_FLEET;
  if (!D) return;
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const F = V.fmt, el = V.svgEl;
  const T = D.threshold;
  const EVC = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"];   // event types, fixed order
  const PROF = { Safe: "var(--s1)", Moderate: "var(--s3)", Aggressive: "var(--s2)" };
  const TIER = { "Act now": "critical", "Monitor closely": "warning", "Standard monitoring": "good" };
  const kpiHTML = (items) => items.map((k) => `<div class="kpi"><div class="kpi-lbl">${k.label}</div><div class="kpi-val num">${k.value}</div>${k.sub ? `<div class="kpi-sub">${k.sub}</div>` : ""}</div>`).join("");
  const finding = (i, html) => `<div class="finding"><span class="fi">${i}</span><div>${html}</div></div>`;
  const byId = Object.fromEntries(D.drivers.map((d) => [d.id, d]));
  const observeW = (node, fn) => { let w = node.clientWidth; new ResizeObserver(() => { if (Math.abs(node.clientWidth - w) > 4) { w = node.clientWidth; fn(); } }).observe(node); };
  const flagged = D.drivers.filter((d) => d.alert);

  /* ================================================== 4A */
  $("#d4-pipe").innerHTML = [
    ["01", "CSV", "5 files, 9,420 rows"], ["02", "SCP", "copy to the Hadoop VM"], ["03", "Hive", "8 tables, mileage rollups"],
    ["04", "Pig", "abnormal events ÷ miles via HCatalog"], ["05", "Impala", "fast interactive queries"],
    ["06", "Power BI", "one-page risk dashboard"], ["07", "Python", "Bayesian, K-Means, random forest"],
  ].map(([n, t, s], i) => `<div class="pipe-step${i === 3 || i === 6 ? " hl" : ""}"><i>${n}</i><b>${t}</b><span>${s}</span></div>`).join("");

  $("#d4-kpis").innerHTML = kpiHTML([
    { label: "Drivers on alert", value: `${flagged.length} of ${D.totals.drivers}`, sub: "risk ≥ 7.0" },
    { label: "Abnormal events", value: F.int(D.totals.events), sub: `in ${F.int(D.totals.pings)} pings (${F.pct1(D.totals.events / D.totals.pings)})` },
    { label: "Miles driven", value: (D.totals.miles / 1e6).toFixed(1) + "M", sub: "Jan 2009 – Jun 2013" },
    { label: "Fleet-wide rate", value: (D.totals.events / D.totals.miles * 1e6).toFixed(2), sub: "events per million miles" },
  ]);

  let current = flagged[0].id;
  function drawRank() {
    const box = $("#d4-rank");
    box.innerHTML = "";
    const W = Math.max(280, box.clientWidth), rowH = 17, top = 6, H = top + D.drivers.length * rowH + 22;
    const lw = 40, rw = 44, iw = W - lw - rw;
    const max = 35, x = (v) => lw + (v / max) * iw;
    const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Driver risk ranking with 7.0 threshold" }, box);
    [0, 10, 20, 30].forEach((t) => {
      el("line", { x1: x(t), x2: x(t), y1: top, y2: H - 18, class: t ? "grid-l" : "base-l" }, svg);
      el("text", { x: x(t), y: H - 4, "text-anchor": "middle", class: "axis-t", text: t }, svg);
    });
    D.drivers.forEach((d, i) => {
      const y = top + i * rowH;
      const g = el("g", { style: "cursor:pointer", tabindex: 0, role: "button", "aria-label": `${d.id}, risk ${d.rf}` }, svg);
      el("rect", { x: 0, y, width: W, height: rowH, style: `fill:${d.id === current ? "var(--accent-wash)" : "transparent"}` }, g);
      el("text", { x: lw - 8, y: y + 12, "text-anchor": "end", class: "axis-t", style: `fill:${d.alert ? "var(--ink)" : "var(--axis-ink)"};font-weight:${d.alert ? 600 : 400}`, text: d.id }, g);
      const w = Math.max(2, x(d.rf) - lw);
      el("path", { d: `M${lw},${y + 3}h${w - 3}q3,0 3,3v5q0,3 -3,3h${-(w - 3)}z`, style: `fill:${d.alert ? "var(--critical)" : "var(--s1)"}` }, g);
      el("text", { x: x(d.rf) + 5, y: y + 12, class: "axis-t", style: "fill:var(--ink)", text: d.rf.toFixed(1) }, g);
      const pick = () => { current = d.id; drawRank(); drawDriver(); };
      g.addEventListener("click", pick);
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
      g.addEventListener("mousemove", (ev) => V.showTip(V.tipRows(d.id + (d.alert ? " · ALERT" : ""), [
        { label: "Risk score", value: d.rf.toFixed(2) }, { label: "Abnormal events", value: d.events }, { label: "Miles", value: F.int(d.miles) }]), ev.clientX, ev.clientY));
      g.addEventListener("mouseleave", V.hideTip);
    });
    el("line", { x1: x(T), x2: x(T), y1: top - 4, y2: H - 18, style: "stroke:var(--critical);stroke-width:1.5;stroke-dasharray:4 3" }, svg);
    el("text", { x: x(T) + 5, y: H - 24, class: "axis-t", style: "fill:var(--critical-ink);font-weight:600", text: "7.0 alert threshold" }, svg);
  }
  function drawDriver() {
    const d = byId[current];
    $("#d4-driver-title").textContent = `Driver ${d.id}` + (d.alert ? " · on alert" : "");
    $("#d4-driver-sub").textContent = `${d.events} abnormal events in ${F.int(d.miles)} miles → ${d.rf.toFixed(2)} per million`;
    const ev = D.events.map((e, i) => ({ label: e, value: d.ev[e], color: EVC[i], tip: V.tipRows(e, [{ label: "Events", value: d.ev[e] }]) }));
    const tierCls = TIER[d.tier];
    $("#d4-driver").innerHTML = `<div id="d4-driver-ev"></div>
      <div class="calc" style="margin-top:10px">
        <div class="calc-row"><span>Truck</span><span>${d.truck} · ${d.model}, ${d.truck_age} yrs old</span></div>
        <div class="calc-row"><span>Contract · licence held</span><span>${d.wage} · ${d.cdl} yrs</span></div>
        <div class="calc-row"><span>Driving profile (K-Means)</span><span>${d.profile}</span></div>
        <div class="calc-row"><span>Bayesian estimate (90% range)</span><span>${d.post.toFixed(1)} (${d.lo.toFixed(1)}–${d.hi.toFixed(1)})</span></div>
        <div class="calc-row"><span>P(true rate ≥ 7.0)</span><span>${F.pct(d.p7)} · <span class="status ${tierCls}">${d.tier}</span></span></div>
      </div>`;
    V.hbars($("#d4-driver-ev"), ev, { labelWidth: 130, max: Math.max(4, ...ev.map((e) => e.value)) });
  }
  drawRank(); drawDriver();
  observeW($("#d4-rank"), drawRank);

  $("#d4-ev-legend").innerHTML = D.events.map((e, i) => `<span><i style="background:${EVC[i]}"></i>${e}</span>`).join("");
  const maxModel = Math.max(...D.by_model.map((m) => D.events.reduce((a, e) => a + m[e], 0)));
  $("#d4-models").innerHTML = '<div class="hbars" style="--lbl-w:96px">' + D.by_model.map((m, r) => {
    const tot = D.events.reduce((a, e) => a + m[e], 0);
    const lastI = Math.max(...D.events.map((e, i) => (m[e] ? i : -1)));
    const segs = D.events.map((e, i) => (m[e] ? '<div style="flex:' + m[e] + ';background:' + EVC[i] + ';' + (i === lastI ? 'border-radius:0 4px 4px 0' : '') + '"></div>' : '')).join('');
    return '<div class="hbar" data-r="' + r + '"><div class="hbar-lbl">' + m.model + '</div><div class="hbar-track">' +
      '<div style="display:flex;gap:2px;width:' + ((tot / maxModel) * 82) + '%;height:14px">' + segs + '</div>' +
      '<span class="hbar-val">' + tot + '</span></div></div>';
  }).join('') + '</div>';
  $$("#d4-models .hbar").forEach((row) => {
    const m = D.by_model[+row.dataset.r];
    row.addEventListener("mousemove", (ev) => V.showTip(V.tipRows(m.model, D.events.map((e, i) => ({ label: e, value: m[e], color: EVC[i] }))), ev.clientX, ev.clientY));
    row.addEventListener("mouseleave", V.hideTip);
  });

  const hist = D.monthly, fc = D.forecast, nH = hist.length;
  const labels = hist.map((h) => h.m).concat(fc.map((f) => f.m));
  const xLab = (i) => (labels[i].endsWith("-01") ? labels[i].slice(0, 4) : null);
  const fcBand = [{ from: nH, to: labels.length - 1, color: "var(--accent-wash)" }];
  V.line($("#d4-miles"), {
    labels, height: 150, bands: fcBand, yFmt: (v) => (v / 1000).toFixed(0) + "K",
    series: [
      { name: "Fleet miles", values: hist.map((h) => h.miles).concat(fc.map(() => null)), color: "var(--s1)" },
      { name: "Forecast", values: hist.map((_, i) => (i === nH - 1 ? hist[i].miles : null)).concat(fc.map((f) => f.miles)), color: "var(--s1)", dash: "4 3" },
    ],
    xLabel: xLab, tipTitle: (i) => labels[i], tipFmt: (v) => F.int(v),
    extraTip: (i) => (i >= nH ? [{ label: "80% range", value: `${F.int(fc[i - nH].lo)}–${F.int(fc[i - nH].hi)}` }] : []),
  });
  V.line($("#d4-mpg"), {
    labels, height: 130, bands: fcBand, yTicks: [5, 6, 7, 8], yFmt: (v) => v.toFixed(0),
    series: [
      { name: "Avg MPG", values: hist.map((h) => h.mpg).concat(fc.map(() => null)), color: "var(--s3)" },
      { name: "Forecast", values: hist.map((_, i) => (i === nH - 1 ? hist[i].mpg : null)).concat(fc.map((f) => f.mpg)), color: "var(--s3)", dash: "4 3" },
    ],
    xLabel: xLab, tipTitle: (i) => labels[i], tipFmt: (v) => v.toFixed(2),
  });

  /* ================================================== 4B */
  let mode = "flagged";
  function drawForest() {
    const box = $("#d4b-forest");
    box.innerHTML = "";
    const list = (mode === "all" ? D.drivers : D.drivers.slice(0, flagged.length + 3)).slice().sort((a, b) => b.post - a.post);
    const W = Math.max(300, box.clientWidth), rowH = 24, top = 8, H = top + list.length * rowH + 24;
    const lw = 44, iw = W - lw - 16, max = 35, x = (v) => lw + (v / max) * iw;
    const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Raw risk score and Bayesian estimate per driver" }, box);
    [0, 5, 10, 15, 20, 25, 30, 35].forEach((t) => {
      el("line", { x1: x(t), x2: x(t), y1: top, y2: H - 20, class: t ? "grid-l" : "base-l" }, svg);
      el("text", { x: x(t), y: H - 5, "text-anchor": "middle", class: "axis-t", text: t }, svg);
    });
    el("line", { x1: x(T), x2: x(T), y1: top - 4, y2: H - 20, style: "stroke:var(--critical);stroke-width:1.5;stroke-dasharray:4 3" }, svg);
    list.forEach((d, i) => {
      const y = top + i * rowH + rowH / 2;
      const g = el("g", {}, svg);
      el("rect", { x: 0, y: y - rowH / 2, width: W, height: rowH, style: "fill:transparent" }, g);
      el("text", { x: lw - 8, y: y + 4, "text-anchor": "end", class: "axis-t", style: `fill:${d.alert ? "var(--ink)" : "var(--axis-ink)"};font-weight:${d.alert ? 600 : 400}`, text: d.id }, g);
      el("line", { x1: x(d.lo), x2: x(d.hi), y1: y, y2: y, style: "stroke:var(--s1);stroke-width:2;stroke-linecap:round;opacity:.55" }, g);
      el("line", { x1: x(d.rf), x2: x(d.post), y1: y, y2: y, style: "stroke:var(--axis-ink);stroke-width:1;stroke-dasharray:2 2" }, g);
      el("circle", { cx: x(d.rf), cy: y, r: 4.5, style: "fill:var(--s2);stroke:var(--surface);stroke-width:2" }, g);
      el("circle", { cx: x(d.post), cy: y, r: 5, style: "fill:var(--s1);stroke:var(--surface);stroke-width:2" }, g);
      g.addEventListener("mousemove", (ev) => V.showTip(V.tipRows(d.id, [
        { label: "Raw score", value: d.rf.toFixed(1), color: "var(--s2)" }, { label: "Bayesian estimate", value: d.post.toFixed(1), color: "var(--s1)" },
        { label: "90% range", value: `${d.lo.toFixed(1)}–${d.hi.toFixed(1)}` }, { label: "P(true ≥ 7.0)", value: F.pct(d.p7) }]), ev.clientX, ev.clientY));
      g.addEventListener("mouseleave", V.hideTip);
    });
  }
  $$("#d4b-filter button").forEach((b) => b.addEventListener("click", () => {
    mode = b.dataset.f;
    $$("#d4b-filter button").forEach((x) => x.setAttribute("aria-pressed", x === b));
    drawForest();
  }));
  drawForest();
  observeW($("#d4b-forest"), drawForest);

  $("#d4b-table tbody").innerHTML = D.drivers.slice(0, flagged.length + 1).map((d) => `
    <tr style="cursor:default"><td><b>${d.id}</b>${d.alert ? "" : ' <span class="psub">(not flagged)</span>'}</td><td class="n">${d.rf.toFixed(1)}</td><td class="n">${d.post.toFixed(1)}</td>
    <td><span class="meter"><i style="width:${d.p7 * 100}%;background:var(--s1)"></i></span><span class="num">${F.pct(d.p7)}</span></td>
    <td class="n">${d.exp12.toFixed(1)}</td><td><span class="status ${TIER[d.tier]}">${d.tier}</span></td></tr>`).join("");
  const sure = flagged.filter((d) => d.p7 >= 0.9), unsure = flagged.filter((d) => d.p7 < 0.9);
  $("#d4b-findings").innerHTML = [
    finding(1, `<b>4 of 7 hold up.</b> ${sure.map((d) => d.id).join(", ")} are at least ${F.pct(Math.min(...sure.map((d) => d.p7)))} likely to be truly at or above 7.0. Those are the drivers to act on now.`),
    finding(2, `<b>The other 3 are not certain.</b> ${unsure.map((d) => `${d.id} (${F.pct(d.p7)})`).join(", ")}. A54 and A20 are close to a coin flip, so they get monitored and re-scored instead of sent to training on a single score.`),
    finding(3, `<b>Looking ahead.</b> At current mileage, ${D.drivers[0].id} is expected to log about ${D.drivers[0].exp12.toFixed(1)} more abnormal events in the next 12 months. The model turns a ranking into an expected cost of waiting.`),
  ].join("");

  /* ================================================== 4C */
  function drawDumbbell() {
    const box = $("#d4c-dumbbell");
    box.innerHTML = "";
    const rows = D.shared.slice().sort((a, b) => b.ratio - a.ratio);
    const W = Math.max(300, box.clientWidth), rowH = 48, top = 12, H = top + rows.length * rowH + 24;
    const lw = 112, rw = 44, iw = W - lw - rw, max = 35, x = (v) => lw + (v / max) * iw;
    const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Risk of two drivers sharing the same truck" }, box);
    [0, 10, 20, 30].forEach((t) => {
      el("line", { x1: x(t), x2: x(t), y1: top, y2: H - 20, class: t ? "grid-l" : "base-l" }, svg);
      el("text", { x: x(t), y: H - 5, "text-anchor": "middle", class: "axis-t", text: t }, svg);
    });
    el("line", { x1: x(T), x2: x(T), y1: top - 4, y2: H - 20, style: "stroke:var(--critical);stroke-width:1.5;stroke-dasharray:4 3" }, svg);
    rows.forEach((r, i) => {
      const y = top + i * rowH + rowH / 2;
      const [hi, lo] = r.drivers.slice().sort((a, b) => b.rf - a.rf);
      el("text", { x: 0, y: y - 2, class: "axis-t", style: "fill:var(--ink);font-weight:600", text: r.truck }, svg);
      el("text", { x: 0, y: y + 11, class: "axis-t", text: r.model }, svg);
      el("line", { x1: x(lo.rf), x2: x(hi.rf), y1: y, y2: y, style: "stroke:var(--axis);stroke-width:2" }, svg);
      [[lo, "var(--s1)", 19], [hi, "var(--s2)", -10]].forEach(([d, c, dy]) => {
        const dot = el("circle", { cx: x(d.rf), cy: y, r: 6, style: `fill:${c};stroke:var(--surface);stroke-width:2;cursor:default` }, svg);
        el("text", { x: x(d.rf), y: y + dy, "text-anchor": "middle", class: "axis-t", text: d.id }, svg);
        dot.addEventListener("mousemove", (ev) => V.showTip(V.tipRows(`${d.id} in ${r.truck}`, [{ label: "Risk score", value: d.rf.toFixed(1) }]), ev.clientX, ev.clientY));
        dot.addEventListener("mouseleave", V.hideTip);
      });
      el("text", { x: W - 4, y: y + 4, "text-anchor": "end", class: "axis-t", style: "fill:var(--ink);font-weight:600", text: r.ratio.toFixed(1) + "×" }, svg);
    });
  }
  drawDumbbell();
  observeW($("#d4c-dumbbell"), drawDumbbell);
  const q2 = D.q2;
  $("#d4c-stats").innerHTML = kpiHTML([
    { label: "Truck age vs. risk", value: "ρ = " + q2.spearman_truck_age_vs_risk.toFixed(2), sub: `p = ${q2.p_truck_age.toFixed(2)}, no link` },
    { label: "Truck MPG vs. risk", value: "ρ = " + q2.spearman_mpg_vs_risk.toFixed(2), sub: `p = ${q2.p_mpg.toFixed(2)}, no link` },
    { label: "Licence tenure vs. risk", value: "ρ = " + D.q4.spearman_cdl_years_vs_risk.toFixed(2), sub: "a driver trait: newer licence, more risk" },
    { label: "Gap on the same truck", value: `${q2.min_same_truck_ratio}–${q2.max_same_truck_ratio}×`, sub: "between its two drivers" },
  ]);
  $("#d4c-findings").innerHTML = [
    finding(1, `<b>Same truck, very different drivers.</b> On T105, A97 scores 8.7× A19. On T102, A73 scores 6.5× A07. The truck can't explain a gap that size.`),
    finding(2, `<b>So the fix is people, not equipment.</b> Spending on fleet-wide maintenance or newer trucks wouldn't move the score. Targeted coaching for a few drivers would.`),
  ].join("");

  /* ================================================== 4D */
  $("#d4d-legend").innerHTML = Object.entries(PROF).map(([k, c]) => {
    const s = D.clusters.summary.find((x) => x.profile === k);
    return `<span><i style="background:${c};border-radius:50%"></i>${k} (${s.drivers}) · avg risk ${s.avg_risk.toFixed(1)}</span>`;
  }).join("");
  function drawScatter() {
    const box = $("#d4d-scatter");
    box.innerHTML = "";
    const W = Math.max(280, box.clientWidth), H = 250, m = { t: 12, r: 16, b: 26, l: 30 };
    const xs = D.drivers.map((d) => d.pc1), ys = D.drivers.map((d) => d.pc2);
    const x0 = Math.floor(Math.min(...xs)), x1 = Math.ceil(Math.max(...xs)), y0 = Math.floor(Math.min(...ys)), y1 = Math.ceil(Math.max(...ys));
    const x = (v) => m.l + ((v - x0) / (x1 - x0)) * (W - m.l - m.r), y = (v) => m.t + (1 - (v - y0) / (y1 - y0)) * (H - m.t - m.b);
    const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Driver clusters on two principal components" }, box);
    for (let v = y0; v <= y1; v++) el("line", { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), class: v === y0 ? "base-l" : "grid-l" }, svg);
    el("text", { x: W - m.r, y: H - 6, "text-anchor": "end", class: "axis-t", text: "PC1 → more events overall" }, svg);
    el("text", { x: m.l, y: m.t + 2, class: "axis-t", text: "PC2 ↑ lane departures" }, svg);
    D.drivers.slice().reverse().forEach((d) => {
      const c = el("circle", { cx: x(d.pc1), cy: y(d.pc2), r: 6, style: `fill:${PROF[d.profile]};stroke:var(--surface);stroke-width:2;cursor:default` }, svg);
      if (d.profile !== "Safe") el("text", { x: x(d.pc1) + 9, y: y(d.pc2) + 4, class: "axis-t", style: "fill:var(--ink)", text: d.id }, svg);
      c.addEventListener("mousemove", (ev) => V.showTip(V.tipRows(`${d.id} · ${d.profile}`, [
        { label: "Risk score", value: d.rf.toFixed(1) }, ...D.events.map((e, i) => ({ label: e, value: d.ev[e], color: EVC[i] })),
        { label: "Licence held", value: d.cdl + " yrs" }]), ev.clientX, ev.clientY));
      c.addEventListener("mouseleave", V.hideTip);
    });
  }
  drawScatter();
  observeW($("#d4d-scatter"), drawScatter);

  const grp = [
    ...D.q4.wage.map((w) => ({ label: w.k === "1099" ? "1099 contractors" : "W2 employees", n: w.n, avg: w.avg, alert: w.alert })),
    ...D.q4.tenure.map((t) => ({ label: "Licence " + t.k.replace("-", "–"), n: t.n, avg: t.avg, alert: t.alert })),
  ];
  V.hbars($("#d4d-groups"), grp.map((g, i) => ({
    label: g.label, value: g.avg, valueText: g.avg.toFixed(1), sub: `${g.alert} of ${g.n} on alert`, color: i < 2 ? "var(--s1)" : "var(--s3)",
    tip: V.tipRows(g.label, [{ label: "Drivers", value: g.n }, { label: "Average risk", value: g.avg.toFixed(1) }, { label: "On alert", value: g.alert }]),
  })), { labelWidth: 120, max: 25 });

  const RF = D.classifier["Random forest"], LR = D.classifier["Logistic regression"];
  const gx = D.gains.map((g) => g[0]), gy = D.gains.map((g) => g[1] / D.base_events);
  const NAMES = { velocity: "Speed", model: "Truck make", cdl_years: "Licence tenure", state: "State", wage: "Contract type", truck_age: "Truck age", idling_ind: "Idling" };
  V.hbars($("#d4d-imp"), Object.entries(D.importance).map(([k, v]) => ({ label: NAMES[k] || k, value: v, valueText: F.pct(v), tip: V.tipRows(NAMES[k] || k, [{ label: "Importance", value: F.pct1(v) }]) })), { labelWidth: 100 });
  function updateGains() {
    const share = +$("#d4d-share").value / 100;
    $("#d4d-share-val").textContent = $("#d4d-share").value + "%";
    let k = 0;
    gx.forEach((v, i) => { if (Math.abs(v - share) < Math.abs(gx[k] - share)) k = i; });
    const caught = D.gains[k][1], pings = Math.round(gx[k] * D.totals.pings);
    $("#d4d-kpis").innerHTML = kpiHTML([
      { label: "Pings reviewed", value: F.int(pings), sub: `of ${F.int(D.totals.pings)}` },
      { label: "Events caught", value: `${caught} of ${D.base_events}`, sub: F.pct(caught / D.base_events) },
      { label: "vs. random review", value: (caught / D.base_events / gx[k]).toFixed(1) + "×", sub: "more events per ping" },
    ]);
    V.line($("#d4d-gains"), {
      labels: gx, height: 190, yTicks: [0, 0.25, 0.5, 0.75, 1], yFmt: (v) => F.pct(v),
      series: [
        { name: "Random forest", values: gy, color: "var(--s1)" },
        { name: "Random review", values: gx, color: "var(--axis-ink)", dash: "4 3", width: 1.5 },
      ],
      markers: [{ i: k, v: gy[k], color: "var(--s1)" }],
      xLabel: (i) => { const p = Math.round(gx[i] * 100); const prev = i ? Math.round(gx[i - 1] * 100) : -1; return p % 25 === 0 && p !== prev ? p + "%" : null; },
      tipTitle: (i) => `Review the top ${F.pct1(gx[i])} of pings`, tipFmt: (v) => F.pct(v),
    });
  }
  $("#d4d-share").addEventListener("input", updateGains);
  updateGains();
  const agg = D.drivers.filter((d) => d.profile === "Aggressive");
  const v65 = D.velocity_rule.velocity_ge_65;
  $("#d4d-findings").innerHTML = [
    finding(1, `<b>The aggressive profile is new licence holders.</b> ${agg.map((d) => d.id).join(", ")} speed and tailgate, and all ${agg.length} have held a licence for under 2.5 years (${agg.map((d) => d.cdl).join(", ")} yrs).`),
    finding(2, `<b>Both contractors are on the alert list.</b> 1099 drivers average ${D.q4.wage[0].avg} against ${D.q4.wage[1].avg} for W2. With only 2 contractors that's a signal, not proof: the chance of it happening at random is ${F.pct(D.q4.p_both_contractors_flagged_by_chance)}.`),
    finding(3, `<b>Speed is the early-warning signal.</b> The random forest (AUC ${RF.roc_auc.toFixed(2)}, vs ${LR.roc_auc.toFixed(2)} for logistic regression) catches ${F.pct(RF.recall_at_top5pct)} of events by flagging 5% of pings. A plain rule, "alert at 65 mph or more", flags ${F.pct1(v65.share_of_pings_flagged)} of pings and still catches ${F.pct(v65.share_of_events_caught)} of events.`),
  ].join("");
})();
