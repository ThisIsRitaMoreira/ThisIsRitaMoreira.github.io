/* =========================================================
   Capsule 02, chapters 4–6 — promotions, market basket, Solver
   Data: window.DATA_RETAIL_EXTRA (analysis/retail_promo_basket.py,
   analysis/build_solver_workbook.py). Weekly arrays = weeks 2–52.
   ========================================================= */
(function () {
  const R = window.DATA_RETAIL_EXTRA;
  if (!R) return;
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const F = V.fmt, el = V.svgEl;
  const kpiHTML = (items) => items.map((k) => `<div class="kpi"><div class="kpi-lbl">${k.label}</div><div class="kpi-val num">${k.value}</div>${k.sub ? `<div class="kpi-sub">${k.sub}</div>` : ""}</div>`).join("");
  const finding = (i, html) => `<div class="finding"><span class="fi">${i}</span><div>${html}</div></div>`;
  const usd = (v) => "$" + v.toFixed(2);
  const observe = (node, fn) => { let w = node.clientWidth; new ResizeObserver(() => { if (Math.abs(node.clientWidth - w) > 4) { w = node.clientWidth; fn(); } }).observe(node); };
  const P = R.promo, T = P.totals, CATS = P.categories;
  const WEEKS = R.source.week_start || P.weeks;
  const wkLabel = (i) => new Date(WEEKS[i] + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });

  /* ================================================== Chapter 4 · promotions */
  $("#rp-kpis").innerHTML = kpiHTML([
    { label: "Promotions analyzed", value: F.int(T.events), sub: "12 largest food categories" },
    { label: "Lift on the promoted product", value: "+" + F.pct(T.gross_pct), sub: "vs its own baseline" },
    { label: "Truly extra for the category", value: F.pct(T.net_pct), sub: "of that lift, after cannibalization and dips" },
    { label: "Would have sold anyway", value: F.pct(T.subsidised_share), sub: "of promo units, sold at a discount" },
    { label: "Discount per extra unit", value: usd(T.disc_per_net_unit), sub: `${F.pct(T.disc_per_net_vs_shelf)} of the average shelf price` },
  ]);
  const sel = $("#rp-cat");
  sel.innerHTML = CATS.map((c, i) => `<option value="${i}">${c.label}</option>`).join("");
  sel.value = String(Math.max(0, CATS.findIndex((c) => c.label === "Milk")));

  function drawWaterfall() {
    const c = CATS[+sel.value];
    const can = c.halo ? 0 : Math.max(0, c.cannib);
    const steps = [
      { label: "Extra units on promotion", v: c.gross, kind: "total", color: "var(--s1)", tip: `Sold ${F.int(c.promo_units)} on promotion; ${F.int(c.base_in_promo)} would have sold anyway` },
      { label: "Taken from sister products", v: -can, kind: "delta", color: "var(--s2)", tip: c.halo ? "Sister products sold more, not less (a halo). Not credited." : `${F.pct(c.cannib_rate)} of the lift (95% range ${F.pct(c.cannib_ci[0])}–${F.pct(c.cannib_ci[1])})` },
      { label: c.dip >= 0 ? "Pantry loading after" : "Bump after the promotion", v: -c.dip, kind: "delta", color: c.dip >= 0 ? "var(--s4)" : "var(--s3)", tip: c.dip >= 0 ? `Sales in the 2 weeks after sat ${F.pct(Math.abs(c.dip_pct_base))} below baseline` : `Sales in the 2 weeks after sat above baseline` },
      { label: "Truly extra for the category", v: c.net, kind: "total", color: "var(--s3)", tip: `${F.pct(c.net_pct)} of the lift` },
    ];
    const box = $("#rp-waterfall"); box.innerHTML = "";
    const W = Math.max(300, box.clientWidth), H = 230, m = { t: 20, b: 44, l: 46, r: 8 };
    const max = Math.max(c.gross, c.net) * 1.08;
    const ticks = V.niceTicks(max, 4), top = ticks[ticks.length - 1];
    const y = (v) => m.t + (1 - v / top) * (H - m.t - m.b);
    const band = (W - m.l - m.r) / steps.length, bw = Math.min(56, band * 0.55);
    const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Waterfall from promotion lift to truly extra units" }, box);
    ticks.forEach((t) => { el("line", { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), class: t ? "grid-l" : "base-l" }, svg); el("text", { x: m.l - 6, y: y(t) + 4, "text-anchor": "end", class: "axis-t", text: F.compact(t) }, svg); });
    let run = 0;
    steps.forEach((s, i) => {
      const x = m.l + band * i + (band - bw) / 2;
      let y0, y1;
      if (s.kind === "total") { y0 = 0; y1 = s.v; run = s.v; } else { y0 = run; y1 = run + s.v; run = y1; }
      const lo = Math.min(y0, y1), hi = Math.max(y0, y1);
      const h = Math.max(2, y(lo) - y(hi));
      const r = el("rect", { x, y: y(hi), width: bw, height: h, rx: 6, style: `fill:${s.color}` }, svg);
      el("text", { x: x + bw / 2, y: y(hi) - 6, "text-anchor": "middle", class: "axis-t", style: "fill:var(--ink);font-weight:700", text: (s.kind === "delta" ? (s.v > 0 ? "+" : s.v < 0 ? "−" : "") : "") + F.int(Math.abs(s.v)) }, svg);
      const words = s.label.split(" "), half = Math.ceil(words.length / 2);
      [words.slice(0, half).join(" "), words.slice(half).join(" ")].forEach((line, k) => el("text", { x: x + bw / 2, y: H - 26 + k * 13, "text-anchor": "middle", class: "axis-t", text: line }, svg));
      r.addEventListener("mousemove", (ev) => V.showTip(V.tipRows(s.label, [{ label: "Units", value: F.int(Math.abs(s.v)) }, { label: "Detail", value: s.tip }]), ev.clientX, ev.clientY));
      r.addEventListener("mouseleave", V.hideTip);
    });
    $("#rp-wf-sub").textContent = `${c.label}: ${F.int(c.events)} promotions · +${F.pct(c.gross_pct)} lift · ${usd(c.disc_per_net_unit)} of discount per extra unit (shelf price ${usd(c.shelf_price)})`;
    const w = P.weekly[c.label];
    const bands = [];
    w.promo_units.forEach((p, i) => { if (p > 0) bands.push({ from: i, to: i }); });
    V.line($("#rp-weekly"), {
      labels: WEEKS, height: 210, bands,
      series: [{ name: "Units sold", values: w.units, color: "var(--s1)" }, { name: "Baseline", values: w.base, color: "var(--axis-ink)", dash: "4 3", width: 1.5 }],
      xLabel: (i) => (new Date(WEEKS[i] + "T00:00:00").getDate() <= 7 && new Date(WEEKS[i] + "T00:00:00").getMonth() % 3 === 0 ? wkLabel(i) : null),
      tipTitle: (i) => "Week of " + wkLabel(i) + (w.promo_units[i] > 0 ? " · in the mailer" : ""),
      extraTip: (i) => [{ label: "Units on promotion", value: F.int(w.promo_units[i]) }],
    });
  }
  sel.addEventListener("change", drawWaterfall);
  drawWaterfall();
  observe($("#rp-waterfall"), drawWaterfall);

  // cost of an extra unit, with the ~30% margin line
  const costRows = CATS.slice().sort((a, b) => b.disc_per_net_vs_shelf - a.disc_per_net_vs_shelf);
  V.hbars($("#rp-cost"), costRows.map((c) => ({
    label: c.label, value: c.disc_per_net_vs_shelf, valueText: F.pct(c.disc_per_net_vs_shelf), sub: usd(c.disc_per_net_unit),
    color: c.disc_per_net_vs_shelf > 0.75 ? "var(--s2)" : "var(--s1)",
    tip: V.tipRows(c.label, [{ label: "Discount per extra unit", value: usd(c.disc_per_net_unit) }, { label: "Average shelf price", value: usd(c.shelf_price) }, { label: "Truly extra share of lift", value: F.pct(c.net_pct) }]),
  })), { max: 1.15, labelWidth: 108 });
  requestAnimationFrame(() => {
    const box = $("#rp-cost"), track = box.querySelector(".hbar-track"); if (!track) return;
    box.style.position = "relative";
    const line = document.createElement("div");
    line.style.cssText = `position:absolute;top:0;bottom:0;left:${track.offsetLeft + (0.3 / 1.15) * 0.78 * track.clientWidth}px;border-left:1.5px dashed var(--ink-2);opacity:.55;pointer-events:none`;
    box.appendChild(line);
  });
  V.cols($("#rp-depth"), P.depth_bands.map((b) => ({ label: b.band.replace("under ", "<").replace(/%/g, "%"), value: b.lift_pct, valueText: "+" + F.pct(b.lift_pct), color: "var(--s1)",
    tip: V.tipRows(`${b.band} off`, [{ label: "Average lift", value: "+" + F.pct(b.lift_pct) }, { label: "Promotions", value: F.int(b.events) }]) })), { height: 190 });

  // three example promotions
  const EX = P.examples;
  let ex = 0;
  $("#rp-ex-pick").innerHTML = EX.map((e, i) => `<button aria-pressed="${i === 0}" data-i="${i}">${e.cat}</button>`).join("");
  function drawExample() {
    const e = EX[ex];
    $$("#rp-ex-pick button").forEach((b) => b.setAttribute("aria-pressed", +b.dataset.i === ex));
    $("#rp-ex-title").textContent = e.title;
    $("#rp-ex-sub").textContent = `${e.name} · ${e.summary.events} promotions · +${F.pct(e.summary.gross_pct)} in mailer weeks · average ${F.pct(e.summary.depth)} off`;
    const bands = [];
    e.state.forEach((s, i) => { if (s === 1 || s === 2) bands.push({ from: i, to: i, color: s === 1 ? "var(--accent-wash)" : "color-mix(in srgb, var(--accent-wash) 50%, transparent)" }); if (s === 3) bands.push({ from: i, to: i, color: "var(--t-people)" }); });
    V.line($("#rp-example"), {
      labels: WEEKS, height: 220, bands,
      series: [
        { name: "This product", values: e.units, color: "var(--s1)" },
        { name: "Rest of category", values: e.rest_units, color: "var(--s2)" },
      ],
      xLabel: (i) => (new Date(WEEKS[i] + "T00:00:00").getDate() <= 7 && new Date(WEEKS[i] + "T00:00:00").getMonth() % 3 === 0 ? wkLabel(i) : null),
      tipTitle: (i) => "Week of " + wkLabel(i) + ["", " · in the mailer", " · price cut continues", " · weeks after"][e.state[i]],
      extraTip: (i) => [{ label: "Baseline (this product)", value: F.one(e.base[i]) }, { label: "Discount", value: F.pct(e.depth[i]) }],
    });
  }
  $$("#rp-ex-pick button").forEach((b) => b.addEventListener("click", () => { ex = +b.dataset.i; drawExample(); }));
  drawExample();

  const ins = Object.fromEntries(R.insights.map((i) => [i.id, i]));
  $("#rp-findings").innerHTML = ["subsidy", "cannib", "depth", "carryover"].filter((k) => ins[k]).map((k, i) => finding(i + 1, `<b>${ins[k].head}.</b> ${ins[k].body}`)).join("");

  /* ================================================== Chapter 5 · market basket */
  const B = R.basket;
  const food = (p) => !/litter|cat food|dog food|pet food|laundry|bleach|detergent|tissue|towel|soap|hair|diaper|paper|cleaning|trash|garbage bag|food bag|storage bag/i.test(p.a_label + " " + p.b_label);
  const topFood = B.pairs.filter(food).sort((a, b) => b.lift - a.lift)[0];
  $("#rb-kpis").innerHTML = kpiHTML([
    { label: "Baskets analyzed", value: F.int(B.n_baskets), sub: "a full year, ~2,500 households" },
    { label: "Categories", value: F.int(B.categories.length), sub: `each in ≥ ${F.pct1(B.min_cat_share)} of baskets` },
    { label: "Strongest food pair", value: `${topFood.lift.toFixed(1)}×`, sub: `${topFood.a_label} → ${topFood.b_label}` },
    { label: "Cereal baskets with milk", value: F.pct((B.pairs.find((p) => /cereal/i.test(p.a_label) && /milk/i.test(p.b_label)) || { conf_ab: 0.67 }).conf_ab), sub: "the classic pairing, measured" },
  ]);
  const ZC = { Pantry: "var(--s1)", Fresh: "var(--s2)", "Dairy & frozen": "var(--s3)" };
  function drawNetwork() {
    const box = $("#rb-network"); box.innerHTML = "";
    const N = B.network, W = Math.max(300, box.clientWidth), H = Math.round(W * 0.78), pad = 30;
    const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Network of categories bought together" }, box);
    const pos = Object.fromEntries(N.nodes.map((n) => [n.id, [pad + n.x * (W - 2 * pad), pad + (1 - n.y) * (H - 2 * pad)]]));
    const eg = el("g", {}, svg), ng = el("g", {}, svg);
    const edges = N.edges.map((e) => ({ e, line: el("line", { x1: pos[e.s][0], y1: pos[e.s][1], x2: pos[e.t][0], y2: pos[e.t][1], style: `stroke:var(--axis-ink);stroke-width:${(0.6 + Math.log(e.lift) * 0.9).toFixed(2)};opacity:.35` }, eg) }));
    const maxPen = Math.max(...N.nodes.map((n) => n.pen));
    N.nodes.forEach((n) => {
      const [x, y] = pos[n.id], r = 4 + 13 * Math.sqrt(n.pen / maxPen);
      const c = el("circle", { cx: x, cy: y, r, style: `fill:${ZC[n.zone] || "var(--axis-ink)"};stroke:var(--surface);stroke-width:2;cursor:default` }, ng);
      if (n.degree >= 4 || n.pen > 0.2) el("text", { x: x + r + 3, y: y + 4, class: "axis-t", style: "fill:var(--ink);font-weight:600", text: n.label }, ng);
      c.addEventListener("mousemove", (ev) => {
        const mine = edges.filter(({ e }) => e.s === n.id || e.t === n.id).sort((a, b) => b.e.lift - a.e.lift);
        edges.forEach(({ e, line }) => { const on = e.s === n.id || e.t === n.id; line.style.opacity = on ? 0.9 : 0.12; line.style.stroke = on ? ZC[n.zone] : "var(--axis-ink)"; });
        V.showTip(V.tipRows(n.label, [{ label: "In baskets", value: F.pct1(n.pen) }, ...mine.slice(0, 4).map(({ e }) => ({ label: "with " + (N.nodes.find((x) => x.id === (e.s === n.id ? e.t : e.s)) || {}).label, value: e.lift.toFixed(1) + "×" }))]), ev.clientX, ev.clientY);
      });
      c.addEventListener("mouseleave", () => { edges.forEach(({ line }) => { line.style.opacity = 0.35; line.style.stroke = "var(--axis-ink)"; }); V.hideTip(); });
    });
  }
  drawNetwork();
  observe($("#rb-network"), drawNetwork);
  let pf = "food";
  function renderPairs() {
    const list = B.pairs.filter((p) => pf === "all" || food(p)).sort((a, b) => b.lift - a.lift);
    $("#rb-pairs tbody").innerHTML = list.map((p) => `<tr style="cursor:default"><td>${p.a_label}</td><td>${p.b_label}</td><td class="n">${F.pct(p.conf_ab)}</td><td class="n"><b>${p.lift.toFixed(1)}×</b></td></tr>`).join("");
    $$("#rb-filter button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.f === pf));
  }
  $$("#rb-filter button").forEach((b) => b.addEventListener("click", () => { pf = b.dataset.f; renderPairs(); }));
  renderPairs();
  $("#rb-recos").innerHTML = B.recommendations.slice(0, 4).map((r) => `<div class="reco"><div><b>${r.head}</b><p>${r.body}</p></div></div>`).join("");

  /* ================================================== Chapter 6 · Solver */
  const OP = R.order_plan, RS = OP.result;
  $("#rs-kpis").innerHTML = kpiHTML([
    { label: "Margin, Solver plan", value: usd(RS.objective), sub: `vs ${usd(RS.naive_objective)} for the rule of thumb` },
    { label: "Better by", value: "+" + F.pct(RS.uplift_vs_naive / RS.naive_objective), sub: `${usd(RS.uplift_vs_naive)} more from the same budget` },
    { label: "Demand filled", value: `${F.pct(RS.naive_fill_rate)} → ${F.pct(RS.fill_rate)}`, sub: "rule of thumb → Solver" },
    { label: "Budget and space used", value: `${usd(RS.budget_used).replace(".00", "")} · ${RS.space_used} ft³`, sub: `of ${usd(OP.budget).replace(".00", "")} · ${OP.space} ft³: both limits bind` },
  ]);
  $("#rs-table tbody").innerHTML = OP.skus.map((s) => {
    const diff = s.opt_cases - s.naive_cases;
    return `<tr style="cursor:default"><td><div class="pname" title="${s.name}">${s.name}</div><div class="psub">${s.cat} · ${F.pct(s.depth)} off · ${s.supplier}</div></td>
      <td class="n">${F.int(s.forecast)}</td><td class="n">${s.pack}</td><td class="n">${s.naive_cases} cases</td>
      <td class="n"><b>${s.opt_cases} cases</b>${diff ? ` <span class="psub">(${diff > 0 ? "+" : ""}${diff})</span>` : ""}</td><td class="n">${usd(s.margin)}</td></tr>`;
  }).join("");

  /* ================================================== insights + recommendations into the capsule summary */
  const insBox = $("#retail-insight-cards");
  if (insBox && ins.subsidy) insBox.insertAdjacentHTML("beforeend", `<div class="insight"><span class="big">${F.pct(T.subsidised_share)}</span><b>Promotions subsidize sales that would happen anyway</b><p>${F.pct(T.subsidised_share)} of promo units would have sold at full price; each truly extra unit costs ${usd(T.disc_per_net_unit)} in discount.</p></div>
    <div class="insight"><span class="big">+${F.pct(RS.uplift_vs_naive / RS.naive_objective)}</span><b>Optimizing beats cutting evenly</b><p>With the same budget and space, the Solver plan earns ${usd(RS.uplift_vs_naive)} more on one promotion than the usual rule of thumb.</p></div>`);
  const recBox = $("#retail-recos");
  if (recBox) R.recommendations.filter((r) => ["rank", "orders", "milk"].includes(r.id)).forEach((r) => recBox.insertAdjacentHTML("beforeend", `<div class="reco"><div><b>${r.head}</b><p>${r.body}</p></div></div>`));
})();
