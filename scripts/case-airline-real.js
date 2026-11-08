/* =========================================================
   Capsule 03, part 2 — real 2024 flights (Alaska + Hawaiian, BTS)
   Data: window.DATA_AIRLINE_REAL (analysis/airline_bts.py),
         window.DATA_GEO (analysis/geo_basemaps.py)
   ========================================================= */
(function () {
  const D = window.DATA_AIRLINE_REAL, G = window.DATA_GEO;
  if (!D || !G) return;
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const F = V.fmt, el = V.svgEl;
  const NS = "http://www.w3.org/2000/svg";
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const kpiHTML = (items) => items.map((k) => `<div class="kpi"><div class="kpi-lbl">${k.label}</div><div class="kpi-val num">${k.value}</div>${k.sub ? `<div class="kpi-sub">${k.sub}</div>` : ""}</div>`).join("");
  const finding = (i, html) => `<div class="finding"><span class="fi">${i}</span><div>${html}</div></div>`;
  const rows = (t) => t.rows.map((r) => Object.fromEntries(t.cols.map((c, i) => [c, r[i]])));
  const CAR = { AS: { name: "Alaska", color: "var(--s1)" }, HA: { name: "Hawaiian", color: "var(--s2)" } };
  const P = G.pacific;
  const VB = P.viewBoxMain || P.viewBox;
  const XY = P.airports;
  const airports = rows(D.network.airports);
  const apIndex = Object.fromEntries(airports.map((a) => [a.code, a]));
  const markets = rows(D.network.markets);

  /* ---------- shared map helpers ---------- */
  function baseMap(box, label) {
    box.innerHTML = "";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", VB); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", label);
    box.appendChild(svg);
    P.land.forEach((d) => el("path", { d, class: "land" }, svg));
    const g = el("g", { style: "fill:none;stroke:var(--surface);stroke-width:.7;opacity:.9" }, svg);
    (P.states || []).forEach((d) => el("path", { d }, g));
    (P.borders || []).forEach((d) => el("path", { d, style: "stroke:var(--axis);stroke-width:.8" }, g));
    return svg;
  }
  function ctrl(a, b) {   // control point for a gentle arc between two airports
    const [x1, y1] = XY[a], [x2, y2] = XY[b];
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, dx = x2 - x1, dy = y2 - y1;
    const k = 0.18;
    return [mx - dy * k, my + dx * k];
  }
  function arcD(a, b) { const [x1, y1] = XY[a], [x2, y2] = XY[b], [cx, cy] = ctrl(a, b); return `M${x1},${y1}Q${cx},${cy} ${x2},${y2}`; }
  function along(a, b, t) {
    const [x1, y1] = XY[a], [x2, y2] = XY[b], [cx, cy] = ctrl(a, b), u = 1 - t;
    return [u * u * x1 + 2 * u * t * cx + t * t * x2, u * u * y1 + 2 * u * t * cy + t * t * y2];
  }

  /* ================================================== Chapter 6 · networks */
  const O = D.network.overlap;
  const sharedSet = new Set(O.overlap_markets.map((m) => m[0]));
  const mkey = (m) => [m.a, m.b].sort().join("-");
  let netMode = "both";
  function drawNetwork() {
    const svg = baseMap($("#ar-map"), "Map of Alaska and Hawaiian Airlines routes in 2024");
    const show = (m) => (netMode === "both" ? true : netMode === "shared" ? sharedSet.has(mkey(m)) : m[netMode] > 0);
    const maxF = Math.max(...markets.map((m) => m.AS + m.HA));
    const routes = el("g", {}, svg);
    markets.filter((m) => XY[m.a] && XY[m.b] && show(m)).sort((x, y) => (x.AS + x.HA) - (y.AS + y.HA)).forEach((m) => {
      const both = m.AS > 0 && m.HA > 0;
      const color = netMode === "shared" || (netMode === "both" && both) ? "var(--s3)" : m.HA > m.AS && netMode !== "AS" ? CAR.HA.color : CAR.AS.color;
      const f = netMode === "AS" ? m.AS : netMode === "HA" ? m.HA : m.AS + m.HA;
      const w = 0.6 + 3.2 * Math.sqrt(f / maxF);
      const p = el("path", { d: arcD(m.a, m.b), style: `fill:none;stroke:${color};stroke-width:${w.toFixed(2)};opacity:${both ? 0.9 : 0.55};stroke-linecap:round` }, routes);
      p.addEventListener("mousemove", (ev) => V.showTip(V.tipRows(`${m.a} ↔ ${m.b} · ${F.int(m.miles)} mi`, [
        { label: "Alaska flights", value: F.int(m.AS), color: CAR.AS.color }, { label: "Hawaiian flights", value: F.int(m.HA), color: CAR.HA.color }]), ev.clientX, ev.clientY));
      p.addEventListener("mouseleave", V.hideTip);
    });
    const dots = el("g", {}, svg);
    airports.filter((a) => XY[a.code]).forEach((a) => {
      const n = netMode === "AS" ? a.AS : netMode === "HA" ? a.HA : a.AS + a.HA;
      if (!n && netMode !== "both") return;
      const [x, y] = XY[a.code];
      const r = 1.6 + 7 * Math.sqrt(n / 80000);
      const c = el("circle", { cx: x, cy: y, r: r.toFixed(2), style: "fill:var(--surface);stroke:var(--ink-2);stroke-width:1.2;cursor:default" }, dots);
      if (n > 9000) el("text", { x: x + r + 3, y: y + 3, class: "axis-t", style: "fill:var(--ink);font-weight:600;font-size:10px", text: a.code }, dots);
      c.addEventListener("mousemove", (ev) => V.showTip(V.tipRows(`${a.code} · ${a.city}, ${a.state}`, [
        { label: "Alaska flights", value: F.int(a.AS), color: CAR.AS.color }, { label: "Hawaiian flights", value: F.int(a.HA), color: CAR.HA.color }]), ev.clientX, ev.clientY));
      c.addEventListener("mouseleave", V.hideTip);
    });
    const sub = { both: "Both airlines. Mint = routes both fly.", AS: "Alaska Airlines only.", HA: "Hawaiian Airlines only.", shared: "The 12 routes both airlines fly, all Hawaii to the West Coast." };
    $("#ar-net-sub").textContent = `${F.int(D.meta.flights)} flights · line width = flights · ${sub[netMode]}`;
  }
  $("#ar-net-legend").innerHTML = `<span><i class="line" style="background:var(--s1)"></i>Alaska</span><span><i class="line" style="background:var(--s2)"></i>Hawaiian</span><span><i class="line" style="background:var(--s3)"></i>Flown by both</span><span><i style="background:var(--surface);border:1.5px solid var(--ink-2);border-radius:50%"></i>Airport (size = flights)</span>`;
  $$("#ar-net-mode button").forEach((b) => b.addEventListener("click", () => {
    netMode = b.dataset.m; $$("#ar-net-mode button").forEach((x) => x.setAttribute("aria-pressed", x === b)); drawNetwork();
  }));
  drawNetwork();
  const C = D.carriers;
  $("#ar-net-kpis").innerHTML = kpiHTML([
    { label: "Alaska Airlines", value: F.int(C.AS.flights), sub: `flights · ${C.AS.airports} airports · ${C.AS.tails} aircraft` },
    { label: "Hawaiian Airlines", value: F.int(C.HA.flights), sub: `flights · ${C.HA.airports} airports · ${C.HA.tails} aircraft` },
    { label: "Routes flown by both", value: `${O.markets_both} of ${O.markets_total}`, sub: "airport pairs" },
    { label: "Flights on shared routes", value: `${F.pct1(O.share_in_overlap.AS)} · ${F.pct1(O.share_in_overlap.HA)}`, sub: "of Alaska's · of Hawaiian's" },
  ]);
  const geo = D.network.geography, hubs = D.network.hubs;
  $("#ar-net-findings").innerHTML = [
    finding(1, `<b>A network extension, not a consolidation.</b> Only ${O.markets_both} of ${O.markets_total} routes are flown by both, all between Hawaii and the West Coast. Everything else is new reach for the combined airline.`),
    finding(2, `<b>Two very different operations.</b> Alaska is a hub network: ${hubs.AS[0][0]} alone handles ${F.pct(hubs.AS[0][2])} of its departures. ${F.pct(geo.HA.segments["inter-island"] / C.HA.flights)} of Hawaiian's flights are short inter-island hops, which behave nothing like a 5-hour mainland flight.`),
    finding(3, `<b>What this means for the data platform.</b> The canonical model has to handle both shapes in one flight-leg table. Hawaii is also where the loyalty overlap will be, since those shared routes are where customers fly both airlines.`),
  ].join("");

  /* ================================================== Chapter 7 · on-time */
  V.line($("#ar-otp"), {
    labels: ["A0", "A14", "A30"], height: 220, yTicks: [0.5, 0.6, 0.7, 0.8, 0.9, 1], yFmt: (v) => F.pct(v),
    series: ["AS", "HA"].map((k) => ({ name: CAR[k].name, color: CAR[k].color, values: [C[k].otp.A0, C[k].otp.A14, C[k].otp.A30], endLabel: true })),
    markers: ["AS", "HA"].flatMap((k) => ["A0", "A14", "A30"].map((d, i) => ({ i, v: C[k].otp[d], color: CAR[k].color }))),
    tipTitle: (i) => ["A0 · at or before schedule", "A14 · within 14 minutes", "A30 · within 30 minutes"][i], tipFmt: (v) => F.pct1(v),
  });
  const CAUSES = [["late_aircraft", "Late aircraft", "var(--s1)"], ["carrier", "Airline", "var(--s2)"], ["nas", "Air traffic system", "var(--s3)"], ["weather", "Weather", "var(--s4)"], ["security", "Security", "var(--s5)"]];
  $("#ar-cause-legend").innerHTML = CAUSES.map(([, l, c]) => `<span><i style="background:${c}"></i>${l}</span>`).join("");
  $("#ar-causes").innerHTML = ["AS", "HA"].map((k) => `<div style="margin:10px 0 4px;font-size:13px;font-weight:600">${CAR[k].name}</div>
    <div class="seg-bar" style="height:30px">${CAUSES.map(([key, l, c]) => { const v = C[k].cause_share[key]; return `<div style="flex:${v};background:${c};color:${key === "late_aircraft" ? "#fff" : "#14243F"}" title="${l}: ${F.pct1(v)}">${v > 0.12 ? F.pct(v) : ""}</div>`; }).join("")}</div>`).join("");
  const monthly = rows(D.monthly);
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  V.line($("#ar-monthly"), {
    labels: MONTHS, height: 210, yTicks: [0.6, 0.7, 0.8, 0.9, 1], yFmt: (v) => F.pct(v),
    bands: [{ from: D.monthly.merger_close_month - 1, to: D.monthly.merger_close_month - 1, color: "var(--accent-wash)" }],
    series: ["AS", "HA"].map((k) => ({ name: CAR[k].name, color: CAR[k].color, values: MONTHS.map((_, i) => (monthly.find((r) => r.month === i + 1 && r.carrier === k) || {}).A14) })),
    tipTitle: (i) => MONTHS[i] + " 2024" + (i === D.monthly.merger_close_month - 1 ? " · merger closed" : ""), tipFmt: (v) => F.pct1(v),
    extraTip: (i) => ["AS", "HA"].map((k) => { const r = monthly.find((x) => x.month === i + 1 && x.carrier === k); return { label: `${CAR[k].name} cancelled`, value: F.pct1(r.cancel_rate) }; }),
  });
  const jan = monthly.find((r) => r.month === 1 && r.carrier === "AS");
  $("#ar-otp-findings").innerHTML = [
    finding(1, `<b>The ranking flips with the definition.</b> Under A0, Alaska looks better (${F.pct1(C.AS.otp.A0)} vs ${F.pct1(C.HA.otp.A0)}). Under A14, Hawaiian leads by almost 7 points (${F.pct1(C.HA.otp.A14)} vs ${F.pct1(C.AS.otp.A14)}). A merged airline that lets each side keep its own definition can't compare its own operations.`),
    finding(2, `<b>Different problems, different fixes.</b> ${F.pct(C.HA.cause_share.carrier)} of Hawaiian's delay minutes are the airline's own (crew, maintenance, ground). For Alaska, ${F.pct(C.AS.cause_share.nas)} come from the air traffic system and ${F.pct(C.AS.cause_share.late_aircraft)} from late aircraft, a network problem.`),
    finding(3, `<b>January was the outlier.</b> Alaska cancelled ${F.pct1(jan.cancel_rate)} of its January flights (${F.int(jan.cancelled)}). The worst single day is next.`),
  ].join("");

  /* ================================================== Chapter 8 · worst-day replay */
  const W = D.worst_day;
  const FL = rows(W.flights).filter((f) => XY[f.origin] && XY[f.dest]);
  const tMin = Math.min(...FL.map((f) => f.sched_dep)) - 20;
  const tMax = Math.max(...FL.map((f) => f.act_arr || f.sched_arr)) + 10;
  const slider = $("#ar-time");
  slider.min = tMin; slider.max = tMax; slider.value = tMin + 300;
  const PST = -8 * 60;
  const clock = (t) => {
    const m = t + PST, day = Math.floor(m / 1440), mm = ((m % 1440) + 1440) % 1440;
    const h = Math.floor(mm / 60), mi = Math.round(mm % 60);
    const h12 = ((h + 11) % 12) + 1, ap = h < 12 ? "AM" : "PM";
    return { txt: `${["Tue Jan 16", "Wed Jan 17", "Thu Jan 18"][day + 1] || ""}, ${h12}:${String(mi).padStart(2, "0")} ${ap} PST`, utc: `${String(Math.floor(((t % 1440) + 1440) % 1440 / 60)).padStart(2, "0")}:${String(Math.round(((t % 60) + 60) % 60)).padStart(2, "0")} UTC` };
  };
  let rSvg, planes = [], apRings = {};
  function setupReplay() {
    rSvg = baseMap($("#ar-replay-map"), "Replay of every Alaska and Hawaiian flight on January 17, 2024");
    const used = new Set(FL.flatMap((f) => [f.origin, f.dest]));
    const g = el("g", {}, rSvg);
    used.forEach((code) => {
      const [x, y] = XY[code];
      apRings[code] = el("circle", { cx: x, cy: y, r: 0, style: "fill:none;stroke:var(--critical);stroke-width:1.6;opacity:.85" }, g);
      el("circle", { cx: x, cy: y, r: 2, style: "fill:var(--ink-2)" }, g);
    });
    ["SEA", "PDX", "HNL", "ANC", "LAX", "SFO"].forEach((c) => { if (XY[c]) el("text", { x: XY[c][0] + 6, y: XY[c][1] - 5, class: "axis-t", style: "fill:var(--ink);font-weight:600;font-size:10px", text: c }, g); });
    const pg = el("g", {}, rSvg);
    planes = FL.map((f) => el("circle", { r: 3.2, style: `fill:${f.dep_delay >= 15 ? "var(--s2)" : "var(--s1)"};stroke:var(--surface);stroke-width:1;display:none` }, pg));
  }
  function renderReplay(t) {
    t = +t;
    const c = clock(t);
    $("#ar-clock").firstChild.textContent = c.txt;
    $("#ar-clock-utc").textContent = `${c.utc} · replaying real BTS times`;
    let air = 0, dep = 0, late = 0, canc = 0, div = 0;
    const cancAt = {}, events = [];
    FL.forEach((f, i) => {
      const off = f.wheels_off ?? f.act_dep, on = f.wheels_on ?? f.act_arr;
      const p = planes[i];
      if (f.cancelled) {
        if (f.sched_dep <= t) { canc++; cancAt[f.origin] = (cancAt[f.origin] || 0) + 1; events.push([f.sched_dep, `${f.carrier} ${f.flight} ${f.origin}→${f.dest} cancelled${f.cancel_code === "B" ? " (weather)" : f.cancel_code === "A" ? " (airline)" : ""}`]); }
        p.style.display = "none"; return;
      }
      if (f.act_dep != null && f.act_dep <= t) {
        dep++;
        if (f.dep_delay >= 15) late++;
        if (f.dep_delay >= 60) events.push([f.act_dep, `${f.carrier} ${f.flight} ${f.origin}→${f.dest} left ${f.dep_delay} min late`]);
      }
      const dest = f.diverted && f.div_airport && XY[f.div_airport] ? f.div_airport : f.dest;
      const end = on ?? (f.diverted ? (off != null ? off + 90 : null) : null);
      if (f.diverted && off != null && off <= t) { div++; if (end != null) events.push([end, `${f.carrier} ${f.flight} ${f.origin}→${f.dest} diverted to ${f.div_airport || "?"}`]); }
      if (off != null && end != null && t >= off && t < end) {
        air++;
        const [x, y] = along(f.origin, dest, (t - off) / Math.max(1, end - off));
        p.setAttribute("cx", x.toFixed(1)); p.setAttribute("cy", y.toFixed(1)); p.style.display = "";
      } else p.style.display = "none";
    });
    Object.entries(apRings).forEach(([code, ring]) => ring.setAttribute("r", cancAt[code] ? (3 + 2.2 * Math.sqrt(cancAt[code])).toFixed(1) : 0));
    const worst = Object.entries(cancAt).sort((a, b) => b[1] - a[1])[0];
    $("#ar-live-kpis").innerHTML = kpiHTML([
      { label: "In the air now", value: F.int(air) },
      { label: "Departed so far", value: F.int(dep), sub: `of ${F.int(FL.length)} scheduled` },
      { label: "Left 15+ min late", value: F.int(late), sub: dep ? F.pct(late / dep) + " of departures" : "" },
      { label: "Cancelled so far", value: F.int(canc), sub: div ? `${div} diverted` : "" },
      { label: "Most cancellations", value: worst ? worst[0] : "—", sub: worst ? `${worst[1]} so far` : "" },
    ]);
    events.sort((a, b) => b[0] - a[0]);
    $("#ar-feed").innerHTML = events.filter((e) => e[0] <= t).slice(0, 9).map((e) => `<div><b style="color:var(--ink)">${clock(e[0]).txt.split(", ")[1].replace(" PST", "")}</b> ${e[1]}</div>`).join("") || `<div>Quiet so far.</div>`;
  }
  setupReplay();
  renderReplay(slider.value);
  slider.addEventListener("input", () => { stop(); renderReplay(slider.value); });
  let speed = 110, playing = false, last = 0, raf;
  $$("#ar-speed button").forEach((b) => b.addEventListener("click", () => { speed = +b.dataset.s; $$("#ar-speed button").forEach((x) => x.setAttribute("aria-pressed", x === b)); }));
  function tick(ts) {
    if (!playing) return;
    const dt = last ? (ts - last) / 1000 : 0; last = ts;
    let t = +slider.value + dt * speed;
    if (t >= tMax) { t = tMax; stop(); }
    slider.value = t; renderReplay(t);
    if (playing) raf = requestAnimationFrame(tick);
  }
  function stop() { playing = false; last = 0; cancelAnimationFrame(raf); $("#ar-play").textContent = "▶ Play"; }
  $("#ar-play").addEventListener("click", () => {
    if (playing) return stop();
    if (+slider.value >= tMax - 1) slider.value = tMin;
    playing = true; $("#ar-play").textContent = "❚❚ Pause"; raf = requestAnimationFrame(tick);
  });
  document.addEventListener("view", (e) => { if (e.detail !== "airline") stop(); });
  // hourly departures in Pacific time
  const byHour = {};
  FL.forEach((f) => {
    const h = Math.floor((f.sched_dep + PST) / 60);
    byHour[h] = byHour[h] || [0, 0, 0];
    if (f.cancelled) byHour[h][2]++; else if (f.dep_delay >= 15) byHour[h][1]++; else byHour[h][0]++;
  });
  const hours = Object.keys(byHour).map(Number).sort((a, b) => a - b);
  const hLabel = (h) => { const hh = ((h % 24) + 24) % 24; return `${((hh + 11) % 12) + 1}${hh < 12 ? "a" : "p"}`; };
  V.columns($("#ar-hourly"), {
    labels: hours.map(hLabel), stacked: true, height: 190,
    series: [["On time", "var(--s1)", 0], ["15+ min late", "var(--s2)", 1], ["Cancelled", "var(--s4)", 2]].map(([n, c, j]) => ({ name: n, color: c, values: hours.map((h) => byHour[h][j]) })),
    tipTitle: (i) => `Scheduled ${hLabel(hours[i])}–${hLabel(hours[i] + 1)} PST`,
  });
  const ASd = W.by_carrier.AS, HAd = W.by_carrier.HA, pdx = W.top_airports.find((a) => a.airport === "PDX"), sea = W.top_airports.find((a) => a.airport === "SEA");
  const wd = W.ranking[0];
  $("#ar-replay-findings").innerHTML = [
    finding(1, `<b>${F.pct(wd.share)} of flights disrupted</b> (cancelled, diverted or 15+ minutes late), against ${F.pct(W.year_median_share)} on a normal day of 2024. Alaska cancelled ${ASd.cancelled} flights; Hawaiian, ${HAd.cancelled}.`),
    finding(2, `<b>Portland went down completely.</b> All ${pdx.departures} PDX departures were disrupted (${pdx.cancelled} cancelled), and the ones that left averaged ${Math.round(pdx.avg_dep_delay)} minutes late. Seattle, Alaska's main hub, had ${sea.disrupted} of ${sea.departures} departures disrupted.`),
    finding(3, `<b>Why "within 30 seconds" matters.</b> With an overnight warehouse, this day shows up in tomorrow's report. With a Live Flight State, a controller sees PDX cancellations piling up and the aircraft and crews they strand, while there's still time to swap aircraft or protect connections. The data records cancellation codes (airline vs weather), not the event behind them.`),
  ].join("");

  /* ================================================== Chapter 9 · delay chains */
  const CH = D.propagation.chains;
  let chainIdx = 0;
  $("#ar-chain-pick").innerHTML = CH.map((c, i) => `<button aria-pressed="${i === 0}" data-i="${i}">${c.tail}</button>`).join("");
  function drawGantt() {
    const ch = CH[chainIdx], legs = rows(ch.legs);
    $$("#ar-chain-pick button").forEach((b) => b.setAttribute("aria-pressed", +b.dataset.i === chainIdx));
    $("#ar-chain-sub").textContent = `${CAR[ch.carrier].name} aircraft ${ch.tail} on January 17, 2024 · times in Pacific time`;
    $("#ar-chain-kpis").innerHTML = kpiHTML([
      { label: "Legs flown that day", value: String(legs.length) },
      { label: "Legs that inherited the delay", value: String(ch.cascade_legs) },
      { label: "Late-aircraft minutes", value: F.int(ch.late_aircraft_min), sub: "delay passed down the chain" },
      { label: "First delay", value: `+${legs[0].dep_delay ?? 0} min`, sub: `${legs[0].origin}→${legs[0].dest}` },
    ]);
    const box = $("#ar-gantt"); box.innerHTML = "";
    const Wd = Math.max(320, box.clientWidth), rowH = 34, top = 6, lw = 120, H = top + legs.length * rowH + 26;
    const t0 = Math.min(...legs.map((l) => l.sched_dep)) - 20, t1 = Math.max(...legs.map((l) => l.act_arr || l.sched_arr)) + 20;
    const x = (t) => lw + ((t - t0) / (t1 - t0)) * (Wd - lw - 10);
    const svg = el("svg", { width: Wd, height: H, viewBox: `0 0 ${Wd} ${H}`, role: "img", "aria-label": "Scheduled and actual times of each leg" }, box);
    for (let h = Math.ceil((t0 + PST) / 120) * 120 - PST; h < t1; h += 120) {
      el("line", { x1: x(h), x2: x(h), y1: top, y2: H - 20, class: "grid-l" }, svg);
      el("text", { x: x(h), y: H - 6, "text-anchor": "middle", class: "axis-t", text: clock(h).txt.split(", ")[1].replace(":00", "").replace(" PST", "") }, svg);
    }
    legs.forEach((l, i) => {
      const y = top + i * rowH;
      el("text", { x: 0, y: y + 14, class: "axis-t", style: "fill:var(--ink);font-weight:600", text: `${l.origin}→${l.dest}` }, svg);
      el("text", { x: 0, y: y + 27, class: "axis-t", text: `${ch.carrier} ${l.flight}${l.arr_delay != null ? ` · ${l.arr_delay >= 0 ? "+" : ""}${l.arr_delay} min` : ""}` }, svg);
      el("rect", { x: x(l.sched_dep), y: y + 4, width: Math.max(3, x(l.sched_arr) - x(l.sched_dep)), height: 10, rx: 4, style: "fill:var(--surface-3);stroke:var(--axis)" }, svg);
      if (l.act_dep != null && l.act_arr != null) {
        const r = el("rect", { x: x(l.act_dep), y: y + 17, width: Math.max(3, x(l.act_arr) - x(l.act_dep)), height: 10, rx: 4, style: `fill:${l.arr_delay >= 15 ? "var(--s2)" : "var(--s1)"}` }, svg);
        r.addEventListener("mousemove", (ev) => V.showTip(V.tipRows(`${ch.carrier} ${l.flight} ${l.origin}→${l.dest}`, [
          { label: "Departure delay", value: `${l.dep_delay} min` }, { label: "Arrival delay", value: `${l.arr_delay} min` },
          { label: "Late-aircraft part", value: `${l.late_aircraft_delay || 0} min` }, { label: "Turn time (sched / actual)", value: l.sched_turn != null ? `${l.sched_turn} / ${l.actual_turn} min` : "first leg" }]), ev.clientX, ev.clientY));
        r.addEventListener("mouseleave", V.hideTip);
      }
    });
  }
  $$("#ar-chain-pick button").forEach((b) => b.addEventListener("click", () => { chainIdx = +b.dataset.i; drawGantt(); }));
  drawGantt();
  let gw = $("#ar-gantt").clientWidth;
  new ResizeObserver(() => { const w = $("#ar-gantt").clientWidth; if (Math.abs(w - gw) > 4) { gw = w; drawGantt(); } }).observe($("#ar-gantt"));
  const PR = D.propagation;
  $("#ar-chain-findings").innerHTML = [
    finding(1, `<b>Late aircraft is the biggest delay cause.</b> ${F.pct(PR.late_aircraft_share_year.AS)} of Alaska's and ${F.pct(PR.late_aircraft_share_year.HA)} of Hawaiian's delay minutes in 2024. On the worst day, ${F.pct(PR.late_aircraft_share_worst_day.AS)} for Alaska.`),
    finding(2, `<b>Short turns can't absorb delay.</b> Once a plane is late, a tight turn passes most of the delay to the next leg. That day, ${PR.tails_with_cascade_3plus.AS} Alaska and ${PR.tails_with_cascade_3plus.HA} Hawaiian aircraft had three or more late legs in a row.`),
    finding(3, `<b>The data product follows from this.</b> Joining each flight to its aircraft's next legs is how the control center sees a delay coming hours ahead. That's a join on tail number and time, so the canonical model needs both.`),
  ].join("");

  /* ================================================== Chapter 10 · canonical key test */
  const K = D.canonical;
  $("#ar-key-kpis").innerHTML = kpiHTML([
    { label: "Flights tested", value: F.int(K.key_collisions.flights_tested) },
    { label: "Duplicate keys found", value: `${K.key_collisions.utc_date_key.groups}`, sub: `${K.key_collisions.utc_date_key.flights} flights share a key` },
    { label: "UTC date ≠ local date", value: `${F.pct(K.share_local_date_ne_utc_date.AS)} · ${F.pct(K.share_local_date_ne_utc_date.HA)}`, sub: "of Alaska's · of Hawaiian's flights" },
  ]);
  const col = rows(K.key_collisions.utc_date_key);
  $("#ar-collide tbody").innerHTML = col.map((r) => `<tr style="cursor:default"><td><b>${r.carrier} ${r.flight}</b></td><td>${r.local_date} · ${r.local_dep.slice(0, 2)}:${r.local_dep.slice(2)}</td><td>${r.origin}→${r.dest}</td><td class="mono" style="font-size:12px">${r.sched_dep_utc.replace("T", " ").replace("Z", "")}</td><td><b>${r.sched_dep_date_utc}</b></td></tr>`).join("");
  const exSel = $("#ar-ex");
  exSel.innerHTML = K.examples.map((e, i) => `<option value="${i}">${e.canonical.operating_carrier} ${e.canonical.flight_number} · ${e.canonical.origin}→${e.canonical.dest} · ${e.source.FlightDate}${e.canonical.local_date_differs ? " (UTC date differs)" : ""}</option>`).join("");
  function showEx() {
    const e = K.examples[+exSel.value], s = e.source, c = e.canonical;
    const row = (a, b, sub) => `<div class="calc-row"><span>${a}${sub ? `<small>${sub}</small>` : ""}</span><span>${b}</span></div>`;
    $("#ar-ex-map").innerHTML = [
      row("FlightDate · CRSDepTime (local)", `${s.FlightDate} · ${s.CRSDepTime}`, `${s.Origin} is in ${c.origin_tz} (UTC ${c.origin_utc_offset_h >= 0 ? "+" : ""}${c.origin_utc_offset_h})`),
      row("→ Scheduled departure (UTC)", c.sched_dep_utc.replace("T", " ")),
      row("→ Actual arrival (UTC)", c.act_arr_utc ? c.act_arr_utc.replace("T", " ") : "—", c.status),
      row("ArrDelay → A14 on-time", `${s.ArrDelay ?? "—"} min → ${c.a14 ? "on time" : "late"}`),
      `<div class="calc-row total"><span>Canonical leg key</span><span class="mono" style="font-size:13px">${c.leg_key}</span></div>`,
    ].join("");
  }
  exSel.addEventListener("change", showEx);
  exSel.value = String(Math.max(0, K.examples.findIndex((e) => e.canonical.local_date_differs)));
  showEx();
  $("#ar-key-findings").innerHTML = [
    finding(1, `<b>Our key isn't unique.</b> Hawaiian flight 1102 leaves HNL at 2:10 PM on August 25 and again at 5:15 AM on August 26. In UTC both are August 26, so they get the same key. A date-only key breaks on real schedules.`),
    finding(2, `<b>The fix is cheap if you find it early.</b> Key on the scheduled departure timestamp in UTC, not the date. Keep the local date as an attribute, because airlines and the DOT report by local date.`),
    finding(3, `<b>Time zones are everywhere.</b> More than a quarter of these flights have a UTC date different from their local date. Every daily report needs to say which date it means.`),
  ].join("");
})();
