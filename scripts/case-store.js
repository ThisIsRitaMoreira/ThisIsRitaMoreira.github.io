/* =========================================================
   Case 02 — Intermarché store operations (modules 2A, 2B, 2C)
   Data: window.DATA_STORE (84.51° Complete Journey + simulated stock)
   Order day = end of week W: week W sales are known, an order placed
   now arrives before week W+1 opens, and must last through W+2.
   ========================================================= */
(function () {
  const S = window.DATA_STORE;
  if (!S) return;
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const F = V.fmt;
  const SKUS = S.skus;
  const NW = S.weeks.length;
  const kpiHTML = (items) => items.map((k) => `
    <div class="kpi"><div class="kpi-lbl">${k.label}</div><div class="kpi-val num">${k.value}</div>${k.sub ? `<div class="kpi-sub">${k.sub}</div>` : ""}</div>`).join("");
  const finding = (i, html) => `<div class="finding"><span class="fi">${i}</span><div>${html}</div></div>`;
  const shortName = (sk) => (sk.name.length < 16 ? `${sk.cat} · ${sk.name}` : sk.name);
  const money = (v) => "$" + (v >= 100 ? F.int(v) : v.toFixed(2));

  /* ---------- the same forecast the Python simulation uses ---------- */
  // returns {base, sd, fc[]} after observing weeks 0..w (fc[i] = one-step forecast for week i)
  function ewma(sk, w) {
    const u = sk.units, pr = sk.promo, lift = sk.lift || 1;
    let base = (u[0] + u[1] + u[2] + u[3]) / 4;
    const resid = [], fc = [];
    for (let i = 0; i <= w; i++) {
      fc.push(base * (pr[i] ? lift : 1));
      const obs = u[i] / (pr[i] ? lift : 1);
      resid.push(obs - base);
      base = 0.3 * obs + 0.7 * base;
    }
    const r = resid.slice(-8), m = r.reduce((a, b) => a + b, 0) / r.length;
    const sd = r.length >= 3 ? Math.sqrt(r.reduce((a, b) => a + (b - m) * (b - m), 0) / r.length) : base * 0.3;
    return { base, sd, fc };
  }
  const onHandNow = (sk, w) => Math.max(0, sk.oh_legacy[w] - sk.units[w]);  // after this week's sales
  function shelfAvail(sk, w) {
    let d = 0, l = 0;
    for (let i = Math.max(0, w - 3); i <= w; i++) { d += sk.units[i]; l += sk.lost_legacy[i]; }
    return d ? 1 - l / d : 1;
  }
  function rowFor(sk, w) {
    const e = ewma(sk, w);
    const promoNext = !!sk.promo[w + 1], promoAfter = !!sk.promo[w + 2];
    const f1 = e.base * (promoNext ? sk.lift || 1 : 1);
    const oh = onHandNow(sk, w);
    const usual = Math.ceil(Math.max(0, 2 * sk.units[w] - oh) / sk.pack) * sk.pack;   // the habit: 2x last week
    const cover = f1 > 0 ? (oh + usual) / f1 : 9;                                      // weeks covered after the usual order
    const avail = shelfAvail(sk, w);
    let pr = 2;
    if (cover < 1) pr = 0;
    else if (cover < 1.25 || (promoAfter && cover < 1.6)) pr = 1;
    return { sk, e, f1, oh, usual, cover, promoNext, promoAfter, avail, pr, risk: Math.max(0, f1 - oh - usual) * sk.price };
  }
  const PRIO = [
    { cls: "critical", label: "Order more", ic: "!" },
    { cls: "warning", label: "Watch", ic: "~" },
    { cls: "good", label: "OK", ic: "✓" },
  ];

  /* ================================================== 2A */
  const secSel = $("#d2a-sec"), wkIn = $("#d2a-week");
  secSel.innerHTML = `<option value="all">All sections</option>` + S.sections.map((s) => `<option>${s}</option>`).join("");
  secSel.value = "all";
  let selected = null;

  function render2A() {
    const w = +wkIn.value - 1;
    $("#d2a-week-val").textContent = "W" + wkIn.value;
    const sec = secSel.value;
    const list = SKUS.filter((s) => sec === "all" || s.section === sec);
    const rows = list.map((sk) => rowFor(sk, w)).sort((a, b) => a.pr - b.pr || b.risk - a.risk || a.cover - b.cover);
    const end = new Date(2017, 0, 1 + 7 * (w + 1) - 1);
    $("#d2a-sub").textContent = `${sec === "all" ? "All sections" : sec} · ${list.length} top products · end of week ${w + 1} (${end.toLocaleDateString("en-US", { month: "short", day: "numeric" })}, 2017)`;
    const nNow = rows.filter((r) => r.pr === 0).length, nWatch = rows.filter((r) => r.pr === 1).length;
    const nPromo = rows.filter((r) => r.promoNext || r.promoAfter).length;
    let d = 0, l = 0;
    list.forEach((sk) => { for (let i = Math.max(0, w - 3); i <= w; i++) { d += sk.units[i]; l += sk.lost_legacy[i]; } });
    $("#d2a-kpis").innerHTML = kpiHTML([
      { label: "Usual order falls short", value: `<span class="status critical" style="font-size:inherit;font-weight:600"><span class="sr-only">critical:</span>${nNow}</span>`, sub: "won't cover next week's demand" },
      { label: "Watch", value: String(nWatch), sub: "thin cover, or a mailer in 2 weeks" },
      { label: "In the mailer next 2 weeks", value: String(nPromo), sub: "demand will jump" },
      { label: "Shelf availability, last 4 wks", value: F.pct1(d ? 1 - l / d : 1), sub: "share of demand served (sim.)" },
    ]);
    const tb = $("#d2a-table tbody");
    tb.innerHTML = rows.map((r, i) => {
      const p = PRIO[r.pr];
      const pct = Math.min(1, r.cover / 3);
      const mcol = r.pr === 0 ? "var(--critical)" : r.pr === 1 ? "var(--warning)" : "var(--good)";
      const promo = r.promoNext ? `<span class="pill">Next week</span>` : r.promoAfter ? `<span class="pill">In 2 weeks</span>` : `<span style="color:var(--muted)">—</span>`;
      return `<tr data-i="${SKUS.indexOf(r.sk)}" class="${selected === r.sk ? "sel" : ""}">
        <td><div class="pname" title="${r.sk.name}">${shortName(r.sk)}</div><div class="psub">${r.sk.section} · ${r.sk.supplier} · #${r.sk.id.slice(-4)}</div></td>
        <td><span class="status ${p.cls}">${p.label}</span></td>
        <td class="n">${F.int(r.oh)}</td><td class="n">${F.int(r.usual)}</td><td class="n">${F.int(r.f1)}</td>
        <td><span class="meter"><i style="width:${pct * 100}%;background:${mcol}"></i></span><span class="num">${r.cover > 8 ? "8+" : r.cover.toFixed(1)}</span></td>
        <td>${promo}</td><td class="n">${r.sk.lift ? r.sk.lift.toFixed(2) + "×" : "—"}</td>
        <td class="n">${F.pct(r.avail)}</td></tr>`;
    }).join("");
    $$("#d2a-table tbody tr").forEach((tr) => tr.addEventListener("click", () => { selected = SKUS[+tr.dataset.i]; render2A(); }));
    if (!selected || !list.includes(selected)) selected = rows[0].sk;
    $$("#d2a-table tbody tr").forEach((tr) => tr.classList.toggle("sel", SKUS[+tr.dataset.i] === selected));
    renderSku(selected, w);

    // findings for this view
    const first = rows[0];
    const promoRisk = rows.filter((r) => r.pr < 2 && (r.promoNext || r.promoAfter)).length;
    const leg = S.sim.legacy;
    $("#d2a-findings").innerHTML = [
      finding(1, `<b>Promotions are where shelves go empty.</b> Under the habit of ordering 2× last week's sales, shelf availability was <b>${F.pct1(leg.fill)}</b> overall but <b>${F.pct1(leg.promo_fill)}</b> in mailer weeks. The habit looks backward, and a promotion is a jump forward.`),
      finding(2, `<b>This week's list.</b> The usual order leaves <b>${nNow}</b> of ${rows.length} products short and ${nWatch} more thin, and <b>${promoRisk}</b> of those have a mailer coming. ${first && first.pr === 0 ? `Top of the list: <b>${shortName(first.sk)}</b>, where ${F.int(first.oh)} on hand plus a usual order of ${F.int(first.usual)} meets ~${F.int(first.f1)} expected.` : ""}`),
      finding(3, `<b>One lift doesn't fit all.</b> Median mailer lift ranges from <b>${Math.min(...Object.values(S.lift_by_section).map((x) => x.median_lift || 9)).toFixed(1)}×</b> to <b>${Math.max(...Object.values(S.lift_by_section).map((x) => x.median_lift || 0)).toFixed(1)}×</b> by section. A flat "+50% for promos" rule over-orders bakery and under-orders drinks and meat.`),
    ].join("");
  }

  function renderSku(sk, w) {
    $("#d2a-sku-title").textContent = shortName(sk);
    $("#d2a-sku-sub").textContent = `${sk.section} · ${sk.supplier} · ${money(sk.price)} avg price · pack of ${sk.pack}. Shaded = in the mailer, dark band = this week.`;
    const bands = [];
    sk.promo.forEach((p, i) => { if (p) bands.push({ from: i, to: i }); });
    bands.push({ from: w, to: w, color: "var(--surface-3)" });
    V.line($("#d2a-sku-chart"), {
      labels: S.weeks.map((x) => "W" + x), height: 210, bands,
      series: [
        { name: "Units sold (real)", values: sk.units, color: "var(--s1)" },
        { name: "On hand (sim.)", values: sk.oh_legacy, color: "var(--s2)" },
      ],
      markers: sk.lost_legacy.map((l, i) => (l > 0 ? { i, v: sk.units[i], color: "var(--critical)" } : null)).filter(Boolean),
      xLabel: (i) => (i % 8 === 0 ? "W" + (i + 1) : null),
      tipTitle: (i) => `Week ${i + 1}${sk.promo[i] ? " · in mailer" : ""}`,
      extraTip: (i) => (sk.lost_legacy[i] > 0 ? [{ label: "Lost sales (ran out)", value: F.int(sk.lost_legacy[i]), color: "var(--critical)" }] : []),
    });
  }

  V.hbars($("#d2a-lift"), S.sections.map((s) => {
    const x = S.lift_by_section[s];
    return { label: s, value: x.median_lift || 0, valueText: (x.median_lift || 0).toFixed(2) + "×", sub: `${x.n_promo_skus} products`,
      tip: V.tipRows(s, [{ label: "Median mailer lift", value: (x.median_lift || 0).toFixed(2) + "×" }, { label: "Products promoted", value: x.n_promo_skus }, { label: "Promo product-weeks", value: x.promo_weeks }]) };
  }).sort((a, b) => b.value - a.value), { labelWidth: 108 });

  secSel.addEventListener("change", () => { selected = null; render2A(); });
  wkIn.addEventListener("input", render2A);
  render2A();

  /* ================================================== 2B */
  const A = S.audit;
  $("#d2b-store").textContent = "#" + A.store;
  const mis = A.found.mismatch / A.found.checked;
  $("#d2b-audit-sub").textContent = `${F.int(A.found.mismatch)} of ${F.int(A.found.checked)} SKUs (${F.pct(mis)}) after a year without counts. Simulated, driven by each SKU's real sales activity.`;
  V.hbars($("#d2b-audit"), A.found.by_dept.map((d) => ({
    label: d.d, value: d.miss / d.n, valueText: F.pct(d.miss / d.n), sub: `${F.int(d.miss)} of ${F.int(d.n)}`,
    tip: V.tipRows(d.d, [{ label: "SKUs counted", value: F.int(d.n) }, { label: "Record ≠ shelf", value: F.int(d.miss) }, { label: "Mismatch rate", value: F.pct1(d.miss / d.n) }]),
  })), { max: 0.6, labelWidth: 108 });

  const ABC = ["A", "B", "C"], RAMP = ["var(--ramp-3)", "var(--ramp-2)", "var(--ramp-1)"], ONR = ["var(--on-ramp-3)", "var(--on-ramp-2)", "var(--on-ramp-1)"];
  const nTot = ABC.reduce((a, c) => a + A.abc[c].n, 0);
  const segBar = (vals, fmt) => `<div class="seg-bar">${vals.map((v, i) => `<div style="flex:${Math.max(v, 0.0001)};background:${RAMP[i]};color:${ONR[i]}" title="Class ${ABC[i]}: ${fmt(v)}">${v > 0.09 ? `${ABC[i]} · ${fmt(v)}` : ""}</div>`).join("")}</div>`;
  $("#d2b-abc").innerHTML = `
    <div class="legend">${ABC.map((c, i) => `<span><i style="background:${RAMP[i]}"></i>Class ${c}</span>`).join("")}</div>
    <div class="panel-sub" style="margin:10px 0 0">SKUs (${F.int(nTot)})</div>${segBar(ABC.map((c) => A.abc[c].n / nTot), F.pct)}
    <div class="panel-sub" style="margin:10px 0 0">Sales value</div>${segBar(ABC.map((c) => A.abc[c].sales_share), F.pct)}
    <p class="note">Class A is ${F.pct(A.abc.A.n / nTot)} of SKUs but 80% of sales. Those are the records that drive most ordering decisions, so they get counted most often.</p>`;

  function accuracy(T, weeks = 52) {
    // per-class accuracy curve for a rotating schedule: SKU with offset o is first counted at week o (1..T)
    const out = {};
    ABC.forEach((c) => {
      const bins = A.h_bins[c], n = A.abc[c].n;
      const curve = [];
      for (let t = 0; t <= weeks; t++) {
        let acc = 0;
        bins.forEach(([h, cnt]) => {
          if (!T[c]) { acc += cnt * Math.pow(1 - h, t); return; }
          let s = 0;
          for (let o = 1; o <= T[c]; o++) { const age = t < o ? t : (t - o) % T[c]; s += Math.pow(1 - h, age); }
          acc += cnt * (s / T[c]);
        });
        curve.push(acc / n);
      }
      out[c] = curve;
    });
    return out;
  }
  const none = accuracy({ A: 0, B: 0, C: 0 });
  function render2B() {
    const T = { A: +$("#d2b-a").value, B: +$("#d2b-b").value, C: +$("#d2b-c").value };
    const rate = +$("#d2b-rate").value;
    $("#d2b-rate-val").textContent = rate;
    const plan = accuracy(T);
    const perWeek = ABC.reduce((a, c) => a + A.abc[c].n / T[c], 0);
    const hours = perWeek / rate;
    const sku = (cur) => cur.A.map((_, t) => ABC.reduce((a, c) => a + cur[c][t] * A.abc[c].n, 0) / nTot);
    const sales = (cur) => cur.A.map((_, t) => ABC.reduce((a, c) => a + cur[c][t] * A.abc[c].sales_share, 0));
    const pSku = sku(plan), pSales = sales(plan), nSku = sku(none);
    const avg = (arr) => arr.slice(1).reduce((a, b) => a + b, 0) / (arr.length - 1);
    $("#d2b-kpis").innerHTML = kpiHTML([
      { label: "SKUs to count per week", value: F.int(perWeek), sub: `A ${F.int(A.abc.A.n / T.A)} · B ${F.int(A.abc.B.n / T.B)} · C ${F.int(A.abc.C.n / T.C)}` },
      { label: "Counting hours per week", value: F.one(hours), sub: `≈ ${F.one(hours / 7)} h per day, 7-day store` },
      { label: "Record accuracy, year average", value: F.pct1(avg(pSku)), sub: `vs ${F.pct1(avg(nSku))} with no counts` },
      { label: "Sales-weighted accuracy", value: F.pct1(avg(pSales)), sub: "what ordering decisions actually see" },
    ]);
    V.line($("#d2b-chart"), {
      labels: pSku.map((_, i) => i), height: 220, yTicks: [0.6, 0.7, 0.8, 0.9, 1.0], yFmt: (v) => F.pct(v),
      series: [
        { name: "Your plan", values: pSku, color: "var(--s1)" },
        { name: "No counts", values: nSku, color: "var(--s2)" },
      ],
      xLabel: (i) => (i % 13 === 0 ? (i === 0 ? "Audit" : "Week " + i) : null),
      tipTitle: (i) => (i === 0 ? "Right after the audit" : `${i} week${i === 1 ? "" : "s"} after the audit`),
      tipFmt: (v) => F.pct1(v),
    });
    $("#d2b-findings").innerHTML = [
      finding(1, `<b>The audit is a snapshot, not a fix.</b> Without counts, record accuracy falls from 100% to <b>${F.pct(nSku[52])}</b> within a year, close to the ${F.pct(1 - mis)} the audit found.`),
      finding(2, `<b>This plan</b> counts ~${F.int(perWeek)} SKUs a week (${F.one(hours)} h at ${rate}/h) and keeps records at <b>${F.pct1(avg(pSku))}</b> on average, <b>${F.pct1(avg(pSales))}</b> weighted by sales. Try counting C items less often: the hours drop, and the sales-weighted number barely moves.`),
    ].join("");
  }
  ["#d2b-a", "#d2b-b", "#d2b-c"].forEach((s) => $(s).addEventListener("change", render2B));
  $("#d2b-rate").addEventListener("input", render2B);
  render2B();

  /* ================================================== 2C */
  const skuSel = $("#d2c-sku"), wk2 = $("#d2c-week"), slSel = $("#d2c-sl");
  skuSel.innerHTML = S.sections.map((sec) => `<optgroup label="${sec}">${SKUS.map((s, i) => (s.section === sec ? `<option value="${i}">${shortName(s)}</option>` : "")).join("")}</optgroup>`).join("");
  // default: the product/week where the habit rule misses a coming mailer by the most (order value <= $400)
  let best = null;
  SKUS.forEach((s, i) => {
    for (let w = 14; w <= 40; w++) {
      if (!s.promo[w + 1] || s.promo[w]) continue;
      const r = recommend(s, w, 1.65);
      const score = (r.qty - r.habit) * s.price;
      if (r.qty > 0 && r.qty * s.price <= 400 && (!best || score > best.score)) best = { i, w, score };
    }
  });
  skuSel.value = String(best ? best.i : 0);
  if (best) wk2.value = best.w + 1;
  const VALUE_LIMIT = 200, CHANGE_LIMIT = 0.2;
  let flow;

  function recommend(sk, w, z) {
    const e = ewma(sk, w);
    const lift = sk.lift || 1;
    const pn = !!sk.promo[w + 1], pa = !!sk.promo[w + 2];
    const f1 = e.base * (pn ? lift : 1), f2 = e.base * (pa ? lift : 1);
    const ss = z * e.sd * Math.SQRT2;
    const oh = onHandNow(sk, w);
    const need = Math.max(0, f1 + f2 + ss - oh);
    let cases = Math.ceil(need / sk.pack);
    if (cases > 0 && cases < sk.moq_cases) cases = sk.moq_cases;
    const habit = Math.max(0, Math.ceil(Math.max(0, 2 * sk.units[w] - oh) / sk.pack) * sk.pack);
    return { e, lift, pn, pa, f1, f2, ss, oh, need, cases, qty: cases * sk.pack, habit };
  }

  function render2C() {
    const sk = SKUS[+skuSel.value], w = +wk2.value - 1, z = +slSel.value;
    $("#d2c-week-val").textContent = "W" + wk2.value;
    const r = recommend(sk, w, z);
    const row = (a, b, sub) => `<div class="calc-row"><span>${a}${sub ? `<small>${sub}</small>` : ""}</span><span>${b}</span></div>`;
    $("#d2c-calc").innerHTML = [
      row("Base weekly demand", F.one(r.e.base) + " u", "EWMA of past weeks, promo weeks scaled back by lift"),
      row(`Week ${w + 2}: ${r.pn ? "in the mailer" : "normal week"}`, r.pn ? `× ${r.lift.toFixed(2)} = ${F.one(r.f1)} u` : F.one(r.f1) + " u", r.pn ? "real mailer plan, lift learned from this product's history" : ""),
      row(`Week ${w + 3}: ${r.pa ? "in the mailer" : "normal week"}`, F.one(r.f2) + " u", "the order has to last until the next delivery"),
      row("Safety stock", "+ " + F.one(r.ss) + " u", `z ${slSel.options[slSel.selectedIndex].text} × σ ${F.one(r.e.sd)} × √2`),
      row("Stock on hand now", "− " + F.int(r.oh) + " u", "simulated store stock after this week's sales"),
      row("Units needed", F.one(r.need) + " u"),
      row(`Round up to case pack (${sk.pack})`, `${r.cases} case${r.cases === 1 ? "" : "s"}`, `${sk.supplier} · minimum ${sk.moq_cases} case`),
      `<div class="calc-row total"><span>Recommended order</span><span>${F.int(r.qty)} units · ${money(r.qty * sk.price)}</span></div>`,
      row("For comparison: the habit rule", F.int(r.habit) + " u", "2× last week's sales − stock on hand"),
    ].join("");
    $("#d2c-chart-sub").textContent = `${sk.section} · week ${w + 1} is today. Shaded = in the mailer.`;
    const bands = [];
    sk.promo.forEach((p, i) => { if (p) bands.push({ from: i, to: i }); });
    bands.push({ from: w, to: w, color: "var(--surface-3)" });
    const full = ewma(sk, NW - 1).fc;
    V.line($("#d2c-chart"), {
      labels: S.weeks.map((x) => "W" + x), height: 220, bands,
      series: [
        { name: "Units sold", values: sk.units, color: "var(--s1)" },
        { name: "Forecast", values: full.map((v, i) => (i <= w + 2 ? v : null)), color: "var(--s3)" },
      ],
      xLabel: (i) => (i % 8 === 0 ? "W" + (i + 1) : null),
      tipTitle: (i) => `Week ${i + 1}${sk.promo[i] ? " · in mailer" : ""}`,
      tipFmt: (v) => F.one(v),
    });
    flow = { sk, w, r, qty: r.qty, step: 2, adjusted: false, reason: "", log: [] };
    log(`08:00  System proposed ${F.int(r.qty)} u (${r.cases} × ${sk.pack}) for ${shortName(sk)}`);
    renderFlow();
    $("#d2c-findings").innerHTML = [
      finding(1, `<b>Same stock, fewer empty shelves.</b> Replayed over the full year on real demand, the recommended policy served <b>${F.pct1(S.sim.recommended.fill)}</b> of demand vs <b>${F.pct1(S.sim.legacy.fill)}</b>. In mailer weeks: <b>${F.pct1(S.sim.recommended.promo_fill)}</b> vs <b>${F.pct1(S.sim.legacy.promo_fill)}</b>. Average stock was the same: ${S.sim.recommended.cover_wks} weeks of cover in both.`),
      finding(2, `<b>The win comes from timing, not volume.</b> The habit rule orders after the spike. The recommender sees the mailer coming and builds stock the week before.`),
      finding(3, `<b>Why keep people in the loop?</b> Managers know what the data doesn't: a local event, a shelf reset, a supplier issue. The workflow captures their change and the reason, so the next forecast can learn from it.`),
    ].join("");
  }

  function log(msg) { flow.log.push(msg); $("#d2c-log").innerHTML = flow.log.map((m) => `<div>${m}</div>`).join(""); }
  function needsSignoff() {
    const change = Math.abs(flow.qty - flow.r.qty) / Math.max(1, flow.r.qty);
    return flow.qty * flow.sk.price > VALUE_LIMIT || change > CHANGE_LIMIT;
  }
  function renderFlow() {
    const f = flow, sk = f.sk;
    const st = (i) => (f.step > i ? "done" : f.step === i ? "active" : "todo");
    const sign = needsSignoff();
    const cards = [
      { k: "1 · SYSTEM", t: "Proposal", d: `${F.int(f.r.qty)} units from demand, stock, mailer plan, case pack and MOQ.`, s: "done", btns: "" },
      { k: "2 · SECTION MANAGER", t: "Review", d: f.step > 2 ? (f.adjusted ? `Changed to ${F.int(f.qty)} u · “${f.reason}”` : `Accepted ${F.int(f.qty)} u as proposed.`) : "Accept, or change the quantity and give a reason.",
        s: st(2), btns: f.step === 2 ? `<button class="btn btn-sm btn-primary" data-act="accept">Accept</button>
          <button class="btn btn-sm" data-act="adjust">Change…</button>` : "" },
      { k: "3 · STORE MANAGER", t: "Sign-off", d: f.step < 3 ? `Needed if the order is over $${VALUE_LIMIT} or changed by more than ${CHANGE_LIMIT * 100}%.` :
          f.step === 3 ? `Order of ${money(f.qty * sk.price)}${f.adjusted ? ", changed by the section manager" : ""}. Approve?` : f.signed === "skip" ? "Not needed: small, unchanged order." : "Approved.",
        s: f.step > 3 ? (f.signed === "skip" ? "skipped" : "done") : st(3), btns: f.step === 3 ? `<button class="btn btn-sm btn-primary" data-act="approve">Approve</button><button class="btn btn-sm" data-act="reject">Send back</button>` : "" },
      { k: "4 · SUPPLIER", t: "Order sent", d: f.step > 3 ? `EDI order to ${sk.supplier}: ${F.int(f.qty)} u, delivery before week ${f.w + 2}.` : "Sent automatically once approved.", s: f.step > 3 ? "done" : "todo", btns: f.step > 3 ? `<button class="btn btn-sm" data-act="reset">Start over</button>` : "" },
    ];
    $("#d2c-flow").innerHTML = cards.map((c) => `<div class="fcard ${c.s}"><div class="fcard-k"><span>${c.k}</span><span>${c.s === "done" ? "✓" : c.s === "skipped" ? "–" : ""}</span></div><div class="fcard-t">${c.t}</div><div class="fcard-d">${c.d}</div>${c.btns ? `<div class="btns">${c.btns}</div>` : ""}</div>`).join("");
    $$("#d2c-flow [data-act]").forEach((b) => b.addEventListener("click", () => act(b.dataset.act)));
  }
  function advanceFromReview() {
    if (needsSignoff()) { flow.step = 3; log(`08:${String(14 + flow.log.length).padStart(2, "0")}  Routed to store manager (${money(flow.qty * flow.sk.price)}${flow.adjusted ? ", changed" : ""})`); }
    else { flow.signed = "skip"; flow.step = 4; log(`08:${String(14 + flow.log.length).padStart(2, "0")}  Sign-off not needed, order released`); log(`08:${String(15 + flow.log.length).padStart(2, "0")}  EDI sent to ${flow.sk.supplier}: ${F.int(flow.qty)} u`); }
    renderFlow();
  }
  function act(a) {
    if (a === "accept") { log(`08:12  Section manager accepted ${F.int(flow.qty)} u`); advanceFromReview(); }
    if (a === "adjust") {
      const card = $$("#d2c-flow .fcard")[1];
      card.querySelector(".btns").innerHTML = `
        <input class="select" id="d2c-q" type="number" min="0" step="${flow.sk.pack}" value="${flow.qty + flow.sk.pack * 2}" style="width:84px;padding-right:8px">
        <select class="select" id="d2c-r"><option>Local event</option><option>Shelf space</option><option>Quality issue</option><option>Supplier delay</option></select>
        <button class="btn btn-sm btn-primary" data-act="save">Save</button>`;
      card.querySelector('[data-act="save"]').addEventListener("click", () => act("save"));
    }
    if (a === "save") {
      const q = Math.max(0, Math.round(+$("#d2c-q").value / flow.sk.pack) * flow.sk.pack);
      flow.reason = $("#d2c-r").value; flow.adjusted = q !== flow.r.qty; flow.qty = q;
      log(`08:12  Section manager changed ${F.int(flow.r.qty)} → ${F.int(q)} u (reason: ${flow.reason})`);
      advanceFromReview();
    }
    if (a === "approve") { flow.signed = "yes"; flow.step = 4; log(`09:40  Store manager approved`); log(`09:41  EDI sent to ${flow.sk.supplier}: ${F.int(flow.qty)} u`); renderFlow(); }
    if (a === "reject") { flow.step = 2; flow.qty = flow.r.qty; flow.adjusted = false; log(`09:40  Store manager sent it back for review`); renderFlow(); }
    if (a === "reset") render2C();
  }
  $("#d2c-sim").innerHTML = kpiHTML([
    { label: "Shelf availability, all weeks", value: `${F.pct1(S.sim.legacy.fill)} → ${F.pct1(S.sim.recommended.fill)}`, sub: "habit → recommended" },
    { label: "Shelf availability, mailer weeks", value: `${F.pct1(S.sim.legacy.promo_fill)} → ${F.pct1(S.sim.recommended.promo_fill)}`, sub: "where it matters most" },
    { label: "Lost sales, units / year", value: `−${F.pct((S.sim.legacy.lost - S.sim.recommended.lost) / S.sim.legacy.lost)}`, sub: `${F.int(S.sim.legacy.lost)} → ${F.int(S.sim.recommended.lost)}` },
    { label: "Average stock held", value: `${S.sim.recommended.cover_wks} wks`, sub: `same as habit (${S.sim.legacy.cover_wks} wks)` },
  ]);
  [skuSel, slSel].forEach((n) => n.addEventListener("change", render2C));
  wk2.addEventListener("input", render2C);
  render2C();
})();
