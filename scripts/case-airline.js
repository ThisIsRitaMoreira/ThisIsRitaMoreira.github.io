/* =========================================================
   Case 03 — Airline merger data platform (BUAN 6335).
   Content comes from the team's deck and paper (SkyRoam + Merit,
   fictional companies). Costs and value are illustrative estimates.
   ========================================================= */
(function () {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const F = V.fmt, el = V.svgEl;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const observeW = (node, fn) => { let w = node.clientWidth; new ResizeObserver(() => { if (Math.abs(node.clientWidth - w) > 4) { w = node.clientWidth; fn(); } }).observe(node); };

  /* ================================================== 3A · architecture */
  const SOURCES = [
    ["s1", 0, 0, "SkyRoam reservations", "mainframe · IBM MQ", "A 30-year-old mainframe passenger system. It already publishes booking and ticket changes over IBM MQ, so we consume those messages instead of querying it. Its capacity is billed by MIPS."],
    ["s2", 0, 1, "Merit reservations", "cloud PSS · BigQuery", "Merit's cloud reservation system and its BigQuery warehouse, on a different public cloud. Vendor event and API feeds."],
    ["s3", 0, 2, "Operations events", "ACARS · ADS-B · gates", "Out/off/on/in messages, aircraft positions, gate and turn events, baggage scans, crew check-ins. The events a controller needs in seconds."],
    ["s4", 0, 3, "Aircraft telemetry", "QAR · ARINC 717/767", "Gigabytes per flight in manufacturer-specific binary frames. A decoder service turns frames into engineering parameters; raw files are kept for re-decoding."],
    ["s5", 0, 4, "Loyalty · CRM · ERP", "databases · SaaS", "Loyalty, crew and maintenance databases, plus SaaS platforms: general ledger, HR, CRM, contact center, pricing."],
  ];
  const GRAPH = {
    after: {
      nodes: [...SOURCES,
        ["i1", 1, 0.5, "Change data capture", "MQ + logs · 1–5 min", "Log-based CDC on the mainframe's DB2/VSAM stores and Debezium on relational sources. Near real time with minimal load on the source."],
        ["i2", 1, 2, "Kafka (Confluent)", "streaming · seconds", "The event backbone. Every topic has a registered schema, which makes the schema the producer's data contract. Cluster linking spans both clouds."],
        ["i3", 1, 3.5, "APIs & files", "connectors · Auto Loader", "Managed connectors behind an API gateway for SaaS, and incremental file loading for telemetry, scanned logbooks and the 7-year history migration."],
        ["l1", 2, 0, "Bronze", "raw, per airline", "Raw data exactly as emitted, tagged with airline_of_record, so every number can be traced and re-processed."],
        ["l2", 2, 1, "Silver", "canonical model", "Both airlines mapped to one model for customers, flight legs, aircraft and airports (based on IATA's AIDM). This is the anti-corruption layer: a replaced source system changes one adapter, not every report."],
        ["l3", 2, 2, "Gold", "products · metrics", "Data products and certified metrics, e.g. on-time defined once as A14 (DOT standard), with each airline's legacy definition kept as a named variant."],
        ["l4", 2, 3.5, "Unity Catalog", "tags · lineage · ABAC", "One governance plane across both airlines and both clouds: owners, column-level lineage, classification tags and attribute-based access policies."],
        ["v1", 3, 0, "Live Flight State", "OCC · p95 ≤ 30 s", "A stateful stream joins each flight with its aircraft, its crew's legal duty limits and connecting passengers. Served from a low-latency store to the operations control center."],
        ["v2", 3, 1, "Power BI", "certified metrics", "Databricks SQL behind a Power BI semantic layer. One definition of each metric for both airlines."],
        ["v3", 3, 2, "AI & GenAI", "features · RAG", "Feature store and model registry, plus a vector index so GenAI agents answer from governed data."],
        ["v4", 3, 3, "Delta Sharing", "partners · clean room", "Governed sharing with partners and the pre-close clean room, without copying data."],
      ],
      edges: [["s1", "i1"], ["s2", "i1"], ["s5", "i1"], ["s3", "i2"], ["s4", "i3"], ["s5", "i3"], ["i1", "l1"], ["i2", "l1"], ["i3", "l1"],
        ["l1", "l2"], ["l2", "l3"], ["l4", "l3"], ["l3", "v2"], ["l3", "v3"], ["l3", "v4"], ["i2", "v1", "hot"]],
      start: "v1",
    },
    before: {
      nodes: [...SOURCES,
        ["b1", 1, 0.5, "Nightly extracts", "batch · SkyRoam", "Files land once a night. By the time anyone reads a report, it describes yesterday."],
        ["b2", 1, 2.5, "Merit ETL", "batch · its own cloud", "A separate pipeline into a separate warehouse, with its own definitions and its own catalog."],
        ["w1", 2, 0.5, "On-prem warehouse", "SkyRoam · 7 yrs history", "About 450 TB of history, loaded overnight. No streaming, no telemetry, no unstructured data."],
        ["w2", 2, 2.5, "Merit warehouse", "BigQuery · separate", "A second source of truth with different metric definitions, e.g. what counts as on-time."],
        ["r1", 3, 0.5, "Next-morning reports", "SkyRoam", "Yesterday's operation, today."],
        ["r2", 3, 1.75, "Phone & spreadsheets", "during storms", "In irregular operations, controllers call around and rebuild the picture by hand. This is the biggest capability gap in the brief."],
        ["r3", 3, 3, "Merit reports", "separate", "No combined view of the merged airline."],
      ],
      edges: [["s1", "b1"], ["s5", "b1"], ["s2", "b2"], ["b1", "w1"], ["b2", "w2"], ["w1", "r1"], ["w2", "r3"], ["s3", "r2", "manual"]],
      start: "r2",
    },
  };
  const LANES = ["Sources", "Ingest", "Store", "Serve"];
  let mode = "after", active = GRAPH.after.start;

  function drawArch() {
    const box = $("#d3-arch");
    box.innerHTML = "";
    box.style.overflowX = "auto";
    const G = GRAPH[mode];
    const W = Math.max(680, box.clientWidth), H = 360;
    const colX = [0, 0.265, 0.53, 0.795].map((f) => f * W);
    const nw = Math.min(176, W * 0.2), nh = 50, rowY = (r) => 34 + r * 64;
    const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, class: "arch", role: "img", "aria-label": mode === "after" ? "Target platform architecture" : "Today's two separate data estates" }, box);
    LANES.forEach((l, i) => el("text", { x: colX[i], y: 16, class: "lane-lbl", text: i === 2 && mode === "after" ? "Lakehouse · Azure Databricks" : l }, svg));
    const pos = {};
    G.nodes.forEach(([id, c, r]) => (pos[id] = { x: colX[c], y: rowY(r) }));
    const used = new Set(G.edges.flat());
    const paths = [];
    G.edges.forEach(([a, b, kind]) => {
      const p = pos[a], q = pos[b];
      const vertical = Math.abs(p.x - q.x) < 2;
      const d = vertical
        ? (p.y < q.y ? `M${p.x + nw / 2},${p.y + nh} L${q.x + nw / 2},${q.y}` : `M${p.x + nw / 2},${p.y} L${q.x + nw / 2},${q.y + nh}`)
        : `M${p.x + nw},${p.y + nh / 2} C${(p.x + nw + q.x) / 2},${p.y + nh / 2} ${(p.x + nw + q.x) / 2},${q.y + nh / 2} ${q.x},${q.y + nh / 2}`;
      const path = el("path", { d, class: "edge", style: kind === "hot" ? "stroke:var(--accent);stroke-width:2" : kind === "manual" ? "stroke-dasharray:3 4" : "" }, svg);
      paths.push([path, kind]);
    });
    G.nodes.forEach(([id, , , t, sub]) => {
      const g = el("g", { class: "node" + (id === active ? " on" : ""), tabindex: 0, role: "button", "aria-label": t, style: used.has(id) ? "" : "opacity:.45" }, svg);
      el("rect", { x: pos[id].x, y: pos[id].y, width: nw, height: nh, rx: 10 }, g);
      el("text", { x: pos[id].x + 12, y: pos[id].y + 21, text: t }, g);
      el("text", { x: pos[id].x + 12, y: pos[id].y + 38, class: "sub", text: sub }, g);
      const pick = () => { active = id; drawArch(); showDetail(); };
      g.addEventListener("click", pick);
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
    });
    if (!reduce) paths.forEach(([p, kind], i) => {
      if (kind === "manual") return;
      const dot = el("circle", { r: 3.5, class: "flow-dot" + (mode === "before" ? " slow" : "") }, svg);
      const dur = mode === "before" ? 8 : kind === "hot" ? 1.1 : 2.4;
      el("animateMotion", { dur: dur + "s", repeatCount: "indefinite", begin: "-" + ((i * 0.41) % dur).toFixed(2) + "s", path: p.getAttribute("d") }, dot);
    });
    if (mode === "before") el("text", { x: colX[1], y: rowY(4) + 30, class: "axis-t", text: "Telemetry and scanned logbooks: not integrated anywhere" }, svg);
  }
  function showDetail() {
    const n = GRAPH[mode].nodes.find((x) => x[0] === active) || GRAPH[mode].nodes[0];
    $("#d3-detail").innerHTML = `<div class="panel-title">${n[3]}</div><div class="panel-sub">${n[4]}</div><p style="font-size:14px;color:var(--ink-2);margin:6px 0 0">${n[5]}</p>`;
  }
  $$("#d3-mode button").forEach((b) => b.addEventListener("click", () => {
    mode = b.dataset.mode;
    $$("#d3-mode button").forEach((x) => x.setAttribute("aria-pressed", x === b));
    active = GRAPH[mode].start;
    drawArch(); showDetail();
  }));
  drawArch(); showDetail();
  observeW($("#d3-arch"), drawArch);

  // latency ladder, log scale
  const LAT = [
    ["Ops events reach Kafka", 1, 2, "after", "~2 seconds"],
    ["Live Flight State to the OCC", 2, 30, "after", "p95 ≤ 30 seconds"],
    ["Reservations via CDC", 60, 300, "after", "1–5 minutes"],
    ["APIs and SaaS", 900, 86400, "after", "15 minutes to daily"],
    ["Revenue and finance", 3600, 86400, "after", "hourly to daily"],
    ["Regulatory reporting", 2.6e6, 7.9e6, "after", "monthly / quarterly"],
    ["Today: every report", 43200, 86400, "before", "next morning"],
  ];
  function drawLatency() {
    const box = $("#d3-latency");
    box.innerHTML = "";
    const W = Math.max(280, box.clientWidth), rowH = 26, top = 4, H = top + LAT.length * rowH + 24;
    const lw = Math.min(170, W * 0.42), iw = W - lw - 10;
    const lo = Math.log10(0.8), hi = Math.log10(9e6), x = (s) => lw + ((Math.log10(s) - lo) / (hi - lo)) * iw;
    const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Latency targets by workload, log scale" }, box);
    [[1, "1 s"], [60, "1 min"], [3600, "1 h"], [86400, "1 day"], [2.6e6, "1 mo"]].forEach(([s, l]) => {
      el("line", { x1: x(s), x2: x(s), y1: top, y2: H - 18, class: "grid-l" }, svg);
      el("text", { x: x(s), y: H - 4, "text-anchor": "middle", class: "axis-t", text: l }, svg);
    });
    LAT.forEach(([lab, a, b, m, txt], i) => {
      const y = top + i * rowH;
      el("text", { x: lw - 8, y: y + 16, "text-anchor": "end", class: "axis-t", style: `fill:${m === "before" ? "var(--ink)" : "var(--ink-2)"};font-weight:${m === "before" ? 600 : 400}`, text: lab }, svg);
      const x0 = x(a), w = Math.max(8, x(b) - x(a));
      const r = el("rect", { x: x0, y: y + 6, width: w, height: 13, rx: 4, style: `fill:${m === "before" ? "var(--s2)" : "var(--s1)"}` }, svg);
      r.addEventListener("mousemove", (ev) => V.showTip(V.tipRows(lab, [{ label: "Latency", value: txt }]), ev.clientX, ev.clientY));
      r.addEventListener("mouseleave", V.hideTip);
    });
  }
  drawLatency();
  observeW($("#d3-latency"), drawLatency);

  /* ================================================== 3B · integration steps */
  const STEPS = [
    { k: "1 · SEPARATE", t: "Pre-close", when: "~12 months before close",
      rule: "No row-level customer, fare or route data between airlines. A clean team sees approved aggregates only.",
      does: ["SkyRoam builds its lakehouse: Azure foundation, Databricks, Kafka, mainframe CDC", "History migration waves 1–2, each reconciled and signed off by the data owner", "Neutral clean room for synergy sizing and loyalty-overlap counts", "Day-1 playbooks and the general-ledger crosswalk design"] },
    { k: "2 · CONNECT", t: "Day 1 → month 6", when: "Legal ownership changes",
      rule: "Internal data flow allowed, subject to privacy notices, consent and two operating certificates.",
      does: ["Merit's BigQuery warehouse federated read-only into the same catalog: zero copy", "General-ledger crosswalk → consolidated financial reporting on Day 1", "Reciprocal loyalty earn and burn through partner-style APIs", "Combined executive operations dashboard"] },
    { k: "3 · CONFORM", t: "Months 6 → 24", when: "Airlines run side by side",
      rule: "Full internal access under privacy rules. Consumers move only after reports dual-run and reconcile.",
      does: ["CDC from Merit's sources into Bronze, mapped with SkyRoam's to the canonical Silver model", "A Databricks workspace on Google Cloud processes Merit data in place (no egress) and shares via Delta Sharing", "Customer 360 and Live Flight State v1; member-confirmed account linking", "IROPS decision support v1; maintenance and agent-assist pilots"] },
    { k: "4 · CONVERGE", t: "Years 2 → 3", when: "One operating certificate",
      rule: "Combined reporting. Legacy retired only once every consumer has moved.",
      does: ["Source adapters swapped as reservations, loyalty and maintenance consolidate", "Retire Merit's warehouse and the Google Cloud workspace, then the on-prem warehouse", "Loyalty programs merge into one", "The canonical model becomes a reusable playbook for the next acquisition"] },
  ];
  let step = 0;
  function renderSteps() {
    $("#d3-steps").innerHTML = STEPS.map((s, i) => `<button type="button" class="fcard clickable ${i === step ? "active" : i < step ? "done" : ""}" data-i="${i}" aria-pressed="${i === step}">
      <div class="fcard-k"><span>${s.k}</span><span>${i < step ? "✓" : ""}</span></div><div class="fcard-t">${s.t}</div><div class="fcard-d" style="min-height:0">${s.when}</div></button>`).join("");
    $$("#d3-steps .fcard").forEach((b) => b.addEventListener("click", () => { step = +b.dataset.i; renderSteps(); }));
    const s = STEPS[step];
    $("#d3-step-detail").innerHTML = `<div class="panel-title">${s.k.split(" · ")[1][0] + s.k.split(" · ")[1].slice(1).toLowerCase()}: ${s.t}</div>
      <div class="callout" style="margin:8px 0 10px"><b>Data rule.</b> ${s.rule}</div>
      <div class="panel-sub" style="margin-bottom:4px">What the platform delivers</div>
      <ul style="margin:0;padding-left:18px;font-size:14px;color:var(--ink-2)">${s.does.map((d) => `<li style="margin-bottom:4px">${d}</li>`).join("")}</ul>`;
  }
  renderSteps();

  /* ================================================== 3C · identity + access */
  const scoreIn = $("#d3-score");
  function renderScore() {
    const v = +scoreIn.value / 100;
    $("#d3-score-val").textContent = v.toFixed(2);
    const pos = ((v - 0.5) / 0.5) * 100;
    $("#d3-score-bar").innerHTML = `<div style="position:relative">
      <div class="seg-bar" style="margin:4px 0 2px">
        <div style="flex:60;background:var(--surface-3);color:var(--ink-2)">No link</div>
        <div style="flex:30;background:var(--ramp-2);color:var(--on-ramp-2)">Review</div>
        <div style="flex:10;background:var(--ramp-3);color:var(--on-ramp-3)">Auto</div>
      </div>
      <div style="position:absolute;top:-2px;bottom:-2px;left:calc(${pos}% - 1px);width:3px;border-radius:2px;background:var(--ink)"></div>
      <div style="display:flex;justify-content:space-between" class="axis-t"><span style="font-size:11px;color:var(--axis-ink)">0.50</span><span style="font-size:11px;color:var(--axis-ink);margin-left:20%">0.80</span><span style="font-size:11px;color:var(--axis-ink)">0.95 · 1.00</span></div></div>`;
    const out = v >= 0.95
      ? "<b>Link automatically.</b> Deterministic or near-certain match, e.g. a loyalty number stored on a booking. The member is notified when the programs merge, and the merge can be reversed."
      : v >= 0.8
        ? "<b>Don't decide alone.</b> A data steward reviews the pair, or the app asks the member to confirm it's their account. Probabilistic matching (Fellegi-Sunter) on name, date of birth, contact details and travel patterns."
        : "<b>No link.</b> Similar names aren't enough. The cost of a false merge, one traveler seeing another's itinerary, is a privacy incident.";
    $("#d3-score-out").innerHTML = out;
  }
  scoreIn.addEventListener("input", renderScore);
  renderScore();

  const DOMAINS = ["Flight ops", "Customer PII", "Fares & revenue", "Safety reports", "Crew records"];
  const ROLES = {
    "OCC controller": ["Full", "Masked", "None", "None", "Ops fields"],
    "Revenue analyst": ["Full", "Masked", "Full", "None", "None"],
    "Marketing analyst": ["Aggregate", "Consented only", "Aggregate", "None", "None"],
    "Data scientist": ["Full", "Tokenized", "Full", "De-identified", "Masked"],
    "Safety office": ["Full", "None", "None", "Full (restricted)", "De-identified"],
    "Clean team, pre-close": ["Aggregate", "Counts only", "Aggregate", "None", "None"],
  };
  let role = "Marketing analyst";
  const lvl = (a) => (a.startsWith("Full") ? "var(--good)" : a === "None" ? "var(--axis)" : "var(--warning)");
  function renderAccess() {
    $("#d3-roles").innerHTML = Object.keys(ROLES).map((r) => `<button class="chip" aria-pressed="${r === role}" data-r="${r}">${r}</button>`).join("");
    $$("#d3-roles .chip").forEach((b) => b.addEventListener("click", () => { role = b.dataset.r; renderAccess(); }));
    $("#d3-access").innerHTML = `<div class="access-grid">${ROLES[role].map((a, i) => `<div class="access-cell"><b>${DOMAINS[i]}</b><span><i class="lvl" style="background:${lvl(a)}"></i>${a}</span></div>`).join("")}</div>
      <p class="note">Policies are written once against tags (airline, data class, residency, purpose, retention) and applied as row filters and column masks. Opening Merit's data at close is a policy change approved by counsel, not a rebuild.</p>`;
  }
  renderAccess();

  /* ================================================== 3D · platform scoring */
  const CRIT = [["Security & compliance", 20], ["Coexistence / multi-cloud", 20], ["Real-time streaming", 15], ["Unstructured data & AI", 15], ["Integration speed", 15], ["Four-year TCO", 15]];
  const OPTS = {
    "Azure + Databricks": { s: [5, 5, 5, 5, 4, 4], why: "With Confluent Kafka as the event backbone. Databricks runs on both Azure and Google Cloud, so Merit's data can be processed where it lives during coexistence, under one catalog. One engine for streaming, telemetry decoding, SQL and AI. Open formats limit lock-in." },
    "Snowflake": { s: [5, 4, 3, 3, 4, 3], why: "Runner-up. Excellent for SQL, sharing and clean rooms, but heavy telemetry decoding and stateful streaming would need extra tools and cost." },
    "Palantir Foundry": { s: [5, 3, 4, 4, 5, 1], why: "Strong operational track record in aviation, but the highest license cost, a proprietary model and a scarce talent pool." },
    "GCP-native": { s: [4, 3, 4, 4, 3, 4], why: "Would suit Merit, but SkyRoam's estate is about three times larger and Microsoft-centric." },
    "Microsoft Fabric": { s: [4, 2, 4, 3, 5, 4], why: "Fits Power BI (which we keep), but compute runs only in Azure, and capacity pricing suits always-on streaming plus a second cloud poorly." },
  };
  const OCOL = { "Azure + Databricks": "var(--s1)" };
  let W8 = CRIT.map((c) => c[1]);
  const score = (w) => { const t = w.reduce((a, b) => a + b, 0) || 1; return Object.fromEntries(Object.entries(OPTS).map(([k, o]) => [k, o.s.reduce((a, s, i) => a + s * w[i] / t, 0)])); };
  // robustness: in how many random weightings does each option win?
  let seed = 7; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const wins = Object.fromEntries(Object.keys(OPTS).map((k) => [k, 0]));
  const N = 2000;
  for (let n = 0; n < N; n++) { const w = CRIT.map(() => -Math.log(rnd())); const sc = score(w); const best = Object.entries(sc).sort((a, b) => b[1] - a[1])[0][0]; wins[best]++; }
  function renderWeights() {
    $("#d3-weights").innerHTML = CRIT.map((c, i) => `<div class="calc-row" style="align-items:center"><span>${c[0]}</span><span style="display:flex;align-items:center;gap:8px">
      <input type="range" min="0" max="40" value="${W8[i]}" data-i="${i}" style="width:120px" aria-label="${c[0]} weight"><span class="range-val" style="min-width:40px">${F.pct(W8[i] / W8.reduce((a, b) => a + b, 0))}</span></span></div>`).join("");
    $$("#d3-weights input").forEach((inp) => inp.addEventListener("input", () => { W8[+inp.dataset.i] = +inp.value; renderRank(); $$("#d3-weights .range-val").forEach((s, j) => (s.textContent = F.pct(W8[j] / (W8.reduce((a, b) => a + b, 0) || 1)))); }));
  }
  function renderRank() {
    const sc = score(W8);
    const items = Object.entries(sc).sort((a, b) => b[1] - a[1]);
    const team = W8.every((w, i) => w === CRIT[i][1]);
    $("#d3-rank-sub").textContent = team ? "The team's weights. Move any slider on the left." : "Your weights.";
    V.hbars($("#d3-rank"), items.map(([k, v]) => ({ label: k, value: v, valueText: v.toFixed(2), color: OCOL[k] || "var(--axis-ink)",
      tip: V.tipRows(k, CRIT.map((c, i) => ({ label: c[0], value: OPTS[k].s[i] + " / 5" }))) })), { labelWidth: 150, max: 5 });
    const [best] = items[0];
    $("#d3-why").innerHTML = `<b>${best}${team ? " (the team's choice)" : ""}.</b> ${OPTS[best].why}<br><span style="font-size:12.5px;color:var(--muted)">Robustness check: across ${F.int(N)} random weightings, Azure + Databricks ranks first in ${F.pct(wins["Azure + Databricks"] / N)} of them.</span>`;
  }
  $("#d3-reset").addEventListener("click", () => { W8 = CRIT.map((c) => c[1]); renderWeights(); renderRank(); });
  renderWeights(); renderRank();

  /* ================================================== 3E · cost and value */
  const PH = ["Pre-close", "Year 1", "Year 2", "Year 3"];
  V.columns($("#d3-cost"), {
    labels: PH, stacked: true, height: 220, yFmt: (v) => "$" + v + "M", tipFmt: (v) => "$" + v.toFixed(1) + "M", capLabels: true,
    series: [
      { name: "New platform run-rate", color: "var(--s1)", values: [3.5, 6.5, 8.0, 8.8] },
      { name: "Legacy estate", color: "var(--s2)", values: [7.0, 7.0, 4.5, 0.5] },
      { name: "One-time migration & dual-run", color: "var(--s3)", values: [4.0, 5.5, 3.5, 1.0] },
    ],
  });
  V.line($("#d3-payback"), {
    labels: PH, height: 220, yFmt: (v) => "$" + v + "M", tipFmt: (v) => "$" + v.toFixed(1) + "M",
    series: [
      { name: "Cumulative AI value", values: [0, 10, 55, 155], color: "var(--s1)", endLabel: true },
      { name: "Cumulative investment above baseline", values: [7.5, 19.5, 28.5, 31.8], color: "var(--s2)", endLabel: true },
    ],
    tipTitle: (i) => PH[i],
  });
  const UC = [
    ["IROPS decision support", 35, "5% lower disruption cost", "Year 1"],
    ["Predictive maintenance", 25, "1.5% lower maintenance spend", "Pilot Y1, scale Y2"],
    ["Customer 360 retention", 20, "~0.1% of revenue retained", "Years 1–2"],
    ["Fuel & turn efficiency", 12, "~0.3% fuel saving", "Year 2"],
    ["GenAI agent assist", 10, "~4% contact-center cost", "Pilot Y1"],
  ];
  V.hbars($("#d3-usecases"), UC.map(([k, v, a, w]) => ({ label: k, value: v, valueText: "~$" + v + "M", sub: w,
    tip: V.tipRows(k, [{ label: "Value at maturity", value: "~$" + v + "M / yr" }, { label: "Key assumption", value: a }, { label: "When", value: w }]) })), { labelWidth: 150 });
  $("#d3-products").innerHTML = [
    ["Customer 360", "Customer & Loyalty", ["Golden profile table · profile API (p95 < 100 ms)", "Consented audiences · ML features"], ["Fresh within 15 min · 99.9% API availability", "≥ 99.5% auto-link precision · < 2% duplicates"]],
    ["Live Flight State", "Flight Operations", ["Kafka topic flight.state.v1 · Gold flight_leg table", "OCC dashboard · DOT extract"], ["p95 ≤ 30 s event to view · 99.95% availability", "≥ 99.9% of scheduled legs · DOT reconciled within 0.1%"]],
  ].map(([n, own, outp, slo]) => `<div class="prod-card"><b>${n}</b> <span class="psub">· owned by ${own}</span>
      <ul>${outp.map((o) => `<li>${o}</li>`).join("")}<li><b style="font-size:13px">Service levels:</b> ${slo.join(" · ")}</li></ul></div>`).join("");
})();
