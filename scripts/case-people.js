/* =========================================================
   Case 01 — ALTEN People Services (modules 1A, 1B, 1C)
   Data: window.DATA_PEOPLE (UCI #498), window.DATA_INTEGRATION
   ========================================================= */
(function () {
  const P = window.DATA_PEOPLE, I = window.DATA_INTEGRATION;
  if (!P) return;
  const $ = (s) => document.querySelector(s);
  const F = V.fmt;
  const DEFAULT_TEAM = P.teams[1];
  let team = DEFAULT_TEAM;

  const teamLabel = (t) => {
    const k = P.data[t].kpi;
    return `${t} · ${F.int(k.per_month)}/mo${t === DEFAULT_TEAM ? " (my desk's size)" : ""}`;
  };
  const kpiHTML = (items) => items.map((k) => `
    <div class="kpi${k.hero ? " hero-kpi" : ""}"><div class="kpi-lbl">${k.label}</div><div class="kpi-val num">${k.value}</div>${k.sub ? `<div class="kpi-sub">${k.sub}</div>` : ""}</div>`).join("");
  const finding = (i, html) => `<div class="finding"><span class="fi">${i}</span><div>${html}</div></div>`;
  const rolling = (arr, w) => arr.map((_, i) => { const s = arr.slice(Math.max(0, i - w + 1), i + 1); return s.reduce((a, b) => a + b, 0) / s.length; });

  /* ------------------------------------------------ 1A */
  const sel = $("#d1a-team");
  sel.innerHTML = P.teams.map((t) => `<option value="${t}"${t === team ? " selected" : ""}>${teamLabel(t)}</option>`).join("");
  sel.addEventListener("change", () => { team = sel.value; render1A(); render1B(); });

  const AGE = [["0–2 days", "var(--ramp-1)"], ["3–7 days", "var(--ramp-2)"], ["8–30 days", "var(--ramp-3)"], ["30+ days", "var(--ramp-4)"]];
  $("#d1a-age-legend").innerHTML = AGE.map((a) => `<span><i style="background:${a[1]}"></i>${a[0]}</span>`).join("");

  function render1A() {
    const D = P.data[team], k = D.kpi;
    $("#d1a-kpis").innerHTML = kpiHTML([
      { label: "Tickets per month", value: F.int(k.per_month), sub: `${F.int(k.tickets)} in 3 months` },
      { label: "SLA met", value: F.pct1(k.sla), sub: "resolved within target" },
      { label: "Median time to resolve", value: F.hours(k.median_res_h), sub: "opened → resolved" },
      { label: "Repeat tickets", value: F.pct1(k.repeat), sub: "same person + topic ≤14 d, or reopened" },
      { label: "Reassigned at least once", value: F.pct(k.reassigned), sub: "handed to another resolver" },
    ]);
    const days = D.days;
    V.line($("#d1a-flow"), {
      labels: days, height: 210,
      series: [
        { name: "Opened (7-day avg)", values: rolling(D.opened, 7), color: "var(--s1)" },
        { name: "Resolved (7-day avg)", values: rolling(D.resolved, 7), color: "var(--s2)" },
      ],
      xLabel: (i) => (new Date(days[i] + "T00:00:00").getDate() === 1 ? F.date(days[i]) : null),
      tipTitle: (i) => new Date(days[i] + "T00:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }),
      tipFmt: (v) => F.one(v),
      extraTip: (i) => [{ label: "Backlog at day end", value: F.int(D.backlog[i]) }],
    });
    // weekly snapshots of aging (every 7th day, ending on the last day)
    const idx = [];
    for (let i = D.days.length - 1; i >= 0; i -= 7) idx.unshift(i);
    V.columns($("#d1a-aging"), {
      labels: idx.map((i) => D.days[i]), stacked: true, height: 210,
      series: AGE.map((a, j) => ({ name: a[0], color: a[1], values: idx.map((i) => D.aging[i][j]) })),
      xLabel: (n) => F.date(D.days[idx[n]]),
      tipTitle: (n) => "Open on " + F.date(D.days[idx[n]]),
    });
    V.hbars($("#d1a-prio"), D.priority.map((p) => ({
      label: p.p, value: p.sla, valueText: F.pct1(p.sla), sub: `${F.int(p.n)} tickets`,
      tip: V.tipRows(p.p + " priority", [{ label: "SLA met", value: F.pct1(p.sla) }, { label: "Tickets", value: F.int(p.n) }, { label: "Median to resolve", value: F.hours(p.mres) }]),
    })), { max: 1, labelWidth: 78 });
    V.cols($("#d1a-reassign"), D.reassign.map((r) => ({
      label: r.b === 4 ? "4+" : r.b === 0 ? "None" : String(r.b), value: r.sla, valueText: F.pct(r.sla),
      tip: V.tipRows(`${r.b === 4 ? "4 or more" : r.b} reassignment${r.b === 1 ? "" : "s"}`, [{ label: "SLA met", value: F.pct1(r.sla) }, { label: "Tickets", value: F.int(r.n) }, { label: "Median to resolve", value: F.hours(r.mres) }]),
    })), { max: 1, height: 160 });

    // findings, computed from the data on screen
    const r0 = D.reassign[0], rN = D.reassign[D.reassign.length - 1];
    const lastAge = D.aging[D.aging.length - 1], open = lastAge.reduce((a, b) => a + b, 0);
    const old = lastAge[3] / Math.max(1, open);
    const peakIdx = D.backlog.indexOf(Math.max(...D.backlog));
    const lowPrio = D.priority.find((p) => p.p === "Low"), modPrio = D.priority.find((p) => p.p === "Moderate");
    $("#d1a-findings").innerHTML = [
      finding(1, `<b>Handoffs are the biggest SLA lever.</b> Tickets solved by the first resolver met SLA <b>${F.pct(r0.sla)}</b> of the time. With ${rN.b === 4 ? "4+" : rN.b} reassignments it falls to <b>${F.pct(rN.sla)}</b>. Better routing at intake does more than asking people to work faster.`),
      finding(2, `<b>Old tickets pile up quietly.</b> At the end of the window, <b>${F.pct(old)}</b> of the ${F.int(open)} open tickets were over 30 days old. The daily volume chart can't show this; the aging view can. Backlog peaked at <b>${F.int(D.backlog[peakIdx])}</b> on ${F.date(D.days[peakIdx])}.`),
      modPrio && lowPrio ? finding(3, `<b>Moderate tickets set the SLA number.</b> They're the bulk of the volume and meet SLA ${F.pct(modPrio.sla)} of the time, against ${F.pct(lowPrio.sla)} for low priority. A weekly review of moderate tickets close to breach is where the KPI moves.`) : "",
    ].join("");
  }

  /* ------------------------------------------------ 1B */
  const nIn = $("#d1b-n"), aIn = $("#d1b-adopt");
  $("#d1b-team-note").innerHTML = `<label class="control">Team <select class="select" id="d1b-team">${P.teams.map((t) => `<option value="${t}">${teamLabel(t)}</option>`).join("")}</select></label>`;
  const sel2 = $("#d1b-team");
  sel2.value = team;
  sel2.addEventListener("change", () => { team = sel2.value; sel.value = team; render1A(); render1B(); });

  function simulate(D, n, adoption) {
    const k = D.kpi;
    const kbTeam = k.rep_kb;
    const totalRep = D.categories.reduce((a, c) => a + c.rep, 0) + D.other.rep;
    let saved = 0;
    D.categories.slice(0, n).forEach((c) => {
      const without = c.n_nokb ? c.rep_nokb / c.n_nokb : 0;
      const withKB = c.n_kb >= 30 ? c.rep_kb / c.n_kb : kbTeam;
      saved += c.n_nokb * adoption * Math.max(0, without - withKB);
    });
    const covered = D.categories.slice(0, n).reduce((a, c) => a + c.rep, 0) / totalRep;
    return { totalRep, saved, share: saved / totalRep, covered };
  }

  function render1B() {
    sel2.value = team;
    const D = P.data[team], k = D.kpi;
    $("#d1b-sub").textContent = `${team} · ${F.int(k.tickets)} tickets · ${F.pct1(k.repeat)} were repeats`;
    const total = D.categories.reduce((a, c) => a + c.rep, 0) + D.other.rep;
    let cum = 0;
    const items = D.categories.map((c) => {
      cum += c.rep;
      return {
        label: c.c, value: c.rep, valueText: F.int(c.rep), sub: `${F.pct(cum / total)} cum.`,
        tip: V.tipRows(c.c, [{ label: "Repeat tickets", value: F.int(c.rep) }, { label: "Repeat rate", value: F.pct1(c.rep / c.n) }, { label: "Running share", value: F.pct(cum / total) }, { label: "Article used", value: F.pct((c.n_kb) / c.n) }]),
      };
    });
    items.push({ label: "All other", value: D.other.rep, valueText: F.int(D.other.rep), color: "var(--axis)", sub: "100% cum.",
      tip: V.tipRows("All other categories", [{ label: "Repeat tickets", value: F.int(D.other.rep) }]) });
    V.hbars($("#d1b-pareto"), items, { labelWidth: 70 });
    V.cols($("#d1b-kb"), [
      { label: "No article used", value: k.rep_nokb, valueText: F.pct1(k.rep_nokb), color: "var(--s2)", tip: V.tipRows("No article used", [{ label: "Repeat rate", value: F.pct1(k.rep_nokb) }]) },
      { label: "Article used", value: k.rep_kb, valueText: F.pct1(k.rep_kb), color: "var(--s1)", tip: V.tipRows("Knowledge article used", [{ label: "Repeat rate", value: F.pct1(k.rep_kb) }]) },
    ], { max: Math.max(k.rep_nokb, k.rep_kb) * 1.15, height: 150 });
    const rel = 1 - k.rep_kb / k.rep_nokb;
    $("#d1b-kb-note").innerHTML = `When the resolver used an article, the ticket came back <b>${F.pct(rel)} less often</b>. But articles were used on only <b>${F.pct(k.kb_rate)}</b> of tickets. That gap is the opportunity.`;
    updateSim();
  }

  function updateSim() {
    const D = P.data[team];
    const n = +nIn.value, a = +aIn.value / 100;
    $("#d1b-n-val").textContent = n;
    $("#d1b-adopt-val").textContent = aIn.value + "%";
    const s = simulate(D, n, a);
    const months = 3;
    $("#d1b-sim-kpis").innerHTML = kpiHTML([
      { label: "Repeat tickets / month today", value: F.int(s.totalRep / months) },
      { label: "Repeats in covered categories", value: F.pct(s.covered), sub: `top ${n} categor${n === 1 ? "y" : "ies"}` },
      { label: "Avoided repeats / month", value: F.int(s.saved / months) },
      { label: "Change in repeat tickets", value: "−" + F.pct1(s.share), sub: "projected" },
    ]);
    const s4 = simulate(D, 4, 0.6);
    $("#d1b-findings").innerHTML = [
      finding(1, `<b>Repeats are concentrated.</b> The top 4 categories hold <b>${F.pct(s4.covered)}</b> of all repeat tickets, so a focused fix beats a desk-wide campaign.`),
      finding(2, `<b>A realistic target.</b> Articles for those 4 categories, used on 60% of their tickets, project a <b>${F.pct1(s4.share)}</b> drop in repeats. For scale, at ALTEN repeat tickets fell 15% once we tracked them: a cut of that size is within reach of a few focused fixes.`),
      finding(3, `<b>What a manager gets.</b> Instead of a general push to "reduce repeats", a short list: which categories, which articles to write, and which number to watch each week.`),
    ].join("");
  }
  nIn.addEventListener("input", updateSim);
  aIn.addEventListener("input", updateSim);

  render1A();
  render1B();

  /* ------------------------------------------------ 1C */
  if (!I) return;
  const reasons = {
    "Duplicates removed": `${I.issues.duplicates} duplicates: the same person exported twice under a changed department code`,
    "Mandatory fields complete": `${I.issues.missing_hire_date} missing hire dates go back to the acquired company's HR`,
    "Codes mapped to standard": `all ${I.issues.dept_spellings} department spellings mapped to 3 standard departments`,
    "Manager links valid": `${I.issues.broken_manager_links} point to managers who have left; HRBP reassigns them`,
  };
  function renderFunnel() {
    const first = I.funnel[0][1];
    $("#d1c-funnel").innerHTML = I.funnel.map((s) => `
      <div class="fstep"><div class="fstep-lbl">${s[0]}</div>
      <div class="fstep-bar"><div class="fstep-fill" style="width:0" data-w="${(s[1] / first) * 70}"></div>
      <span class="fstep-val num"><b>${F.int(s[1])}</b>${s[2] ? `<small>−${s[2]}</small>` : ""}</span></div></div>
      ${reasons[s[0]] ? `<div class="note" style="margin:-4px 0 4px">${reasons[s[0]]}</div>` : ""}`).join("");
    requestAnimationFrame(() => setTimeout(() => document.querySelectorAll("#d1c-funnel .fstep-fill").forEach((f) => (f.style.width = f.dataset.w + "%")), 30));
  }
  renderFunnel();
  $("#d1c-run").addEventListener("click", renderFunnel);
  const fmts = I.issues.date_formats;
  $("#d1c-issues").innerHTML = kpiHTML([
    { label: "Date formats in one column", value: String(Object.keys(fmts).filter((x) => x !== "missing").length), sub: `${F.int(I.issues.ambiguous_dates)} dates could be dd/mm or mm/dd` },
    { label: "Department spellings", value: `${I.issues.dept_spellings} → 3`, sub: "PT / EN / upper case" },
    { label: "Contractors in the file", value: F.int(I.issues.contractors), sub: "out of HRIS scope, routed to procurement" },
    { label: "Duplicate records", value: F.int(I.issues.duplicates) },
    { label: "Blank health plan", value: F.int(I.issues.health_blank), sub: "confirmed with the insurer list" },
    { label: "Broken manager links", value: F.int(I.issues.broken_manager_links) },
  ]);
  const order = ["match", "lookup", "transform", "gap"];
  let filt = "all";
  const counts = order.reduce((a, s) => ((a[s] = I.crosswalk.filter((c) => c.status === s).length), a), {});
  $("#d1c-filter").innerHTML = [["all", `All ${I.crosswalk.length}`], ...order.map((s) => [s, `${s[0].toUpperCase() + s.slice(1)} ${counts[s]}`])]
    .map(([k, l]) => `<button class="chip" data-st="${k}" aria-pressed="${k === filt}">${l}</button>`).join("");
  function renderTable() {
    $("#d1c-table tbody").innerHTML = I.crosswalk.filter((c) => filt === "all" || c.status === filt).map((c) => `
      <tr style="cursor:default"><td class="mono" style="font-size:12.5px">${c.src}</td><td class="mono" style="font-size:12.5px">${c.dst}</td><td><span class="st ${c.status}">${c.status}</span></td><td style="color:var(--ink-2);min-width:280px">${c.rule}</td></tr>`).join("");
  }
  document.querySelectorAll("#d1c-filter .chip").forEach((b) => b.addEventListener("click", () => {
    filt = b.dataset.st;
    document.querySelectorAll("#d1c-filter .chip").forEach((x) => x.setAttribute("aria-pressed", x === b));
    renderTable();
  }));
  renderTable();
  const over = 14 / 12 - 1;   // 14 payments a year instead of 12: the same factor the insight card uses
  $("#d1c-pay").innerHTML = `<b>The trap a field-to-field copy misses:</b> the acquired file stores annual salary as 12 payments, and Portuguese payroll pays 14 (holiday and Christmas months). Median monthly base is <b>€${F.int(I.pay.median_monthly_12)}</b> in the source but <b>€${F.int(I.pay.median_monthly_14)}</b> under the standard. Copying it straight across would overstate monthly pay by <b>${F.pct1(over)}</b> on every payslip-based report.`;
})();
