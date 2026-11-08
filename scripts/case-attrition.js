/* =========================================================
   Capsule 01, chapter 4 — attrition study in R
   Data: window.DATA_ATTRITION, written by analysis/people_attrition.R
   ========================================================= */
(function () {
  const A = window.DATA_ATTRITION;
  if (!A) return;
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const F = V.fmt, el = V.svgEl;
  const kpiHTML = (items) => items.map((k) => `<div class="kpi"><div class="kpi-lbl">${k.label}</div><div class="kpi-val num">${k.value}</div>${k.sub ? `<div class="kpi-sub">${k.sub}</div>` : ""}</div>`).join("");
  const finding = (i, html) => `<div class="finding"><span class="fi">${i}</span><div>${html}</div></div>`;
  const O = A.overview, VAL = A.logit.validation, SV = A.survival;
  const otYes = SV.by_overtime.groups.find((g) => g.group === "Yes"), otNo = SV.by_overtime.groups.find((g) => g.group === "No");

  $("#att-kpis").innerHTML = kpiHTML([
    { label: "Employees who left", value: F.pct1(O.attrition_rate), sub: `${F.int(O.leavers)} of ${F.int(O.employees)}` },
    { label: "With overtime vs without", value: `${F.pct(O.overtime_rate)} · ${F.pct(O.no_overtime_rate)}`, sub: "attrition rate" },
    { label: "Typical stay before leaving", value: `${SV.overall.median_years} yrs`, sub: `${otYes.median_years} with overtime, ${otNo.median_years} without` },
    { label: "Model accuracy (test AUC)", value: VAL.auc_test.toFixed(2), sub: `on ${VAL.test_n} held-out employees` },
  ]);

  /* who leaves: segment explorer */
  const vars = A.segments.variables;
  const sel = $("#att-var");
  sel.innerHTML = vars.map((v, i) => `<option value="${i}">${v.label}</option>`).join("");
  function renderSeg() {
    const v = vars[+sel.value];
    const max = Math.max(0.5, ...v.levels.map((l) => l.ci_high || l.rate));
    V.hbars($("#att-seg"), v.levels.map((l) => ({
      label: l.level, value: l.rate, valueText: F.pct(l.rate), sub: `n = ${F.int(l.n)}`,
      color: l.rate > O.attrition_rate * 1.25 ? "var(--s2)" : "var(--s1)",
      tip: V.tipRows(`${v.label}: ${l.level}`, [{ label: "Left", value: `${l.leavers} of ${l.n}` }, { label: "Attrition rate", value: F.pct1(l.rate) }, { label: "95% interval", value: `${F.pct(l.ci_low)}–${F.pct(l.ci_high)}` }, { label: "vs company average", value: l.lift.toFixed(1) + "×" }]),
    })), { max, labelWidth: 150 });
    // company-average reference line
    requestAnimationFrame(() => {
      const box = $("#att-seg"); box.style.position = "relative";
      const track = box.querySelector(".hbar-track"); if (!track) return;
      const left = track.offsetLeft + (O.attrition_rate / max) * 0.78 * track.clientWidth;
      const line = document.createElement("div");
      line.style.cssText = `position:absolute;top:0;bottom:0;left:${left}px;border-left:1.5px dashed var(--ink-2);opacity:.5;pointer-events:none`;
      box.appendChild(line);
    });
    $("#att-seg-note").textContent = `Coral = more than 25% above the ${F.pct1(O.attrition_rate)} average. Chi-square p ${v.p_value < 0.001 ? "< 0.001" : "= " + v.p_value.toFixed(3)} · strength of association (Cramér's V) ${v.cramers_v.toFixed(2)}.`;
  }
  sel.addEventListener("change", renderSeg);
  renderSeg();

  /* what drives it: odds-ratio forest plot, log scale */
  function drawOR() {
    const box = $("#att-or"); box.innerHTML = "";
    const ors = A.logit.odds_ratios.slice().sort((a, b) => b.odds_ratio - a.odds_ratio);
    const W = Math.max(300, box.clientWidth), rowH = 21, top = 4, lw = Math.min(210, W * 0.5), H = top + ors.length * rowH + 22;
    const lo = Math.log(0.4), hi = Math.log(12), x = (v) => lw + ((Math.log(v) - lo) / (hi - lo)) * (W - lw - 12);
    const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Odds ratios with 95% intervals" }, box);
    [0.5, 1, 2, 5, 10].forEach((t) => {
      el("line", { x1: x(t), x2: x(t), y1: top, y2: H - 18, class: t === 1 ? "base-l" : "grid-l", style: t === 1 ? "stroke:var(--ink-2)" : "" }, svg);
      el("text", { x: x(t), y: H - 4, "text-anchor": "middle", class: "axis-t", text: t + "×" }, svg);
    });
    ors.forEach((o, i) => {
      const y = top + i * rowH + rowH / 2, c = o.significant ? (o.odds_ratio >= 1 ? "var(--s2)" : "var(--s1)") : "var(--axis-ink)";
      el("text", { x: lw - 8, y: y + 4, "text-anchor": "end", class: "axis-t", style: `fill:${o.significant ? "var(--ink)" : "var(--axis-ink)"}`, text: o.label.length > 34 ? o.label.slice(0, 33) + "…" : o.label }, svg);
      el("line", { x1: x(Math.max(0.4, o.ci_low)), x2: x(Math.min(12, o.ci_high)), y1: y, y2: y, style: `stroke:${c};stroke-width:2;stroke-linecap:round;opacity:.55` }, svg);
      const dot = el("circle", { cx: x(o.odds_ratio), cy: y, r: 4.5, style: `fill:${c};stroke:var(--surface);stroke-width:2` }, svg);
      const hit = el("rect", { x: 0, y: y - rowH / 2, width: W, height: rowH, style: "fill:transparent" }, svg);
      hit.addEventListener("mousemove", (ev) => V.showTip(V.tipRows(o.label, [{ label: "Odds ratio", value: o.odds_ratio.toFixed(2) + "×" }, { label: "95% interval", value: `${o.ci_low.toFixed(2)}–${o.ci_high.toFixed(2)}` }, { label: "p-value", value: o.p_value < 0.001 ? "< 0.001" : o.p_value.toFixed(3) }]), ev.clientX, ev.clientY));
      hit.addEventListener("mouseleave", V.hideTip);
    });
  }
  drawOR();
  let ow = $("#att-or").clientWidth;
  new ResizeObserver(() => { const w = $("#att-or").clientWidth; if (Math.abs(w - ow) > 4) { ow = w; drawOR(); } }).observe($("#att-or"));

  /* when they leave: retention curves */
  let survKey = "by_overtime";
  const NAMES = { Yes: "Works overtime", No: "No overtime" };
  function renderSurv() {
    const groups = SV[survKey].groups;
    const colors = ["var(--s2)", "var(--s1)", "var(--s3)"];
    const gs = survKey === "by_overtime" ? [groups.find((g) => g.group === "Yes"), groups.find((g) => g.group === "No")] : groups;
    $("#att-surv-legend").innerHTML = gs.map((g, i) => `<span><i class="line" style="background:${colors[i]}"></i>${NAMES[g.group] || g.group.replace("Level 3–5", "Level 3–5").replace(/Level 3.5/, "Level 3–5")}</span>`).join("");
    const T = 10;
    const labels = Array.from({ length: T + 1 }, (_, t) => t);
    V.line($("#att-surv"), {
      labels, height: 220, yTicks: [0, 0.25, 0.5, 0.75, 1], yFmt: (v) => F.pct(v),
      series: gs.map((g, i) => ({ name: NAMES[g.group] || g.group, color: colors[i], values: labels.map((t) => { const p = g.curve.filter((c) => c.time <= t).pop(); return p && t <= g.display_max_time ? p.surv : null; }) })),
      xLabel: (i) => (i % 2 === 0 ? (i === 0 ? "Hired" : `Year ${i}`) : null),
      tipTitle: (i) => (i === 0 ? "At hire" : `After ${i} year${i > 1 ? "s" : ""}`), tipFmt: (v) => F.pct(v),
    });
    $$("#att-surv-by button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.k === survKey));
  }
  $$("#att-surv-by button").forEach((b) => b.addEventListener("click", () => { survKey = b.dataset.k; renderSurv(); }));
  renderSurv();

  /* groups to watch: decision-tree leaves */
  const leaves = A.tree.leaves.slice().sort((a, b) => b.rate - a.rate);
  $("#att-tree").innerHTML = leaves.map((l) => `
    <div class="calc-row" style="align-items:center">
      <span style="color:var(--ink)">${l.conditions.join(" · ")}<small>${F.int(l.n)} employees</small></span>
      <span style="display:flex;align-items:center;gap:8px"><span class="meter" style="width:84px"><i style="width:${l.rate * 100}%;background:${l.rate > O.attrition_rate * 1.25 ? "var(--s2)" : "var(--s1)"}"></i></span>${F.pct(l.rate)} leave</span>
    </div>`).join("");

  /* what-if: overtime */
  const WI = A.whatif, E = WI.employees;
  const drops = E.p_now.map((p, i) => p - E.p_no_ot[i]);           // already sorted by drop, largest first
  const cum = drops.reduce((acc, d) => (acc.push((acc.length ? acc[acc.length - 1] : 0) + d), acc), []);
  const total = cum[cum.length - 1];
  let who = "targeted";
  function renderWhatIf() {
    const s = +$("#att-share").value / 100;
    $("#att-share-val").textContent = Math.round(s * 100) + "%";
    const k = Math.round(s * E.p_now.length);
    const saved = who === "targeted" ? (k ? cum[k - 1] : 0) : s * total;
    const after = WI.base_expected_leavers - saved;
    $("#att-whatif").innerHTML = kpiHTML([
      { label: "Overtime workers moved", value: F.int(k), sub: `of ${F.int(WI.overtime_workers)}` },
      { label: "Expected leavers", value: `${F.int(WI.base_expected_leavers)} → ${F.int(after)}`, sub: "per year, all employees" },
      { label: "Exits avoided", value: F.int(saved), sub: who === "targeted" ? "highest-risk people first" : "people chosen at random" },
      { label: "Attrition rate", value: `${F.pct1(WI.base_expected_leavers / O.employees)} → ${F.pct1(after / O.employees)}` },
    ]);
  }
  $("#att-share").addEventListener("input", renderWhatIf);
  $$("#att-who button").forEach((b) => b.addEventListener("click", () => { who = b.dataset.w; $$("#att-who button").forEach((x) => x.setAttribute("aria-pressed", x === b)); renderWhatIf(); }));
  renderWhatIf();

  const or = A.logit.odds_ratios, ot = or.find((o) => /overtime/i.test(o.label)), lvl = or.find((o) => /Job level 1/i.test(o.label));
  const top = leaves[0], t20 = VAL.top20;
  const r1 = (g) => g.retention.find((r) => r.year === 1).surv;
  $("#att-findings").innerHTML = [
    finding(1, `<b>Overtime is the strongest signal.</b> All else equal, people who work overtime are <b>${ot.odds_ratio.toFixed(1)}×</b> as likely to leave (95% CI ${ot.ci_low.toFixed(1)}–${ot.ci_high.toFixed(1)}). Entry-level roles follow at ${lvl.odds_ratio.toFixed(1)}×.`),
    finding(2, `<b>The first years decide it.</b> At this year's exit rates, ${F.pct(r1(otYes))} of new hires who work overtime are still here after a year, against ${F.pct(r1(otNo))} of those who don't.`),
    finding(3, `<b>A short list, not a blanket policy.</b> The riskiest segment (${top.conditions.join(" and ").toLowerCase()}) loses ${F.pct(top.rate)} of its people. Talking to the riskiest 20% would reach ${F.pct(t20.recall)} of next year's leavers.`),
  ].join("");
  $("#att-caveat").textContent = "Caveats: IBM's sample is fictional and a single snapshot, so these are associations to test, not causes. Gender is left out of the model; age and marital status are controls only. Risk scores should start stay conversations, never decide anything about a person.";

  /* insight card + recommendations from the R output */
  const ins = document.querySelector("#people-insight-cards");
  if (ins) ins.insertAdjacentHTML("beforeend", `<div class="insight"><span class="big">${ot.odds_ratio.toFixed(1)}×</span><b>Overtime predicts leaving</b><p>In the attrition model, overtime is the strongest driver. Moving the highest-risk half of overtime workers off it would avoid about ${F.int(WI.scenarios.find((s) => s.share === 0.5).reduction_targeted)} exits a year.</p></div>`);
  const rec = document.querySelector("#people-recos");
  if (rec) A.recommendations.slice(0, 2).forEach((r) => rec.insertAdjacentHTML("beforeend", `<div class="reco"><div><b>${r.title}</b><p>${r.action}${r.measure ? ` Measure: ${r.measure.charAt(0).toLowerCase() + r.measure.slice(1)}` : ""}</p></div></div>`));
})();
