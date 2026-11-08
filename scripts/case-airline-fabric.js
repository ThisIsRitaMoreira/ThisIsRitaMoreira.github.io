/* =========================================================
   Capsule 03, chapter 11 — the medallion lakehouse (Microsoft Fabric notebooks)
   Data: window.DATA_FABRIC (fabric/tools/export_results.py, from a notebook run)
   ========================================================= */
(function () {
  const D = window.DATA_FABRIC;
  if (!D) return;
  const $ = (s) => document.querySelector(s);
  const int = (v) => Number(v).toLocaleString("en-US");
  const kpiHTML = (items) => items.map((k) => `<div class="kpi"><div class="kpi-lbl">${k.label}</div><div class="kpi-val num">${k.value}</div>${k.sub ? `<div class="kpi-sub">${k.sub}</div>` : ""}</div>`).join("");
  const finding = (i, html) => `<div class="finding"><span class="fi">${i}</span><div>${html}</div></div>`;
  const T = D.tables;
  const ingested = D.ingest_log.reduce((s, r) => s + r.rows, 0);
  const asha = D.ingest_log.reduce((s, r) => s + r.rows_as_ha, 0);
  const dqScored = D.dq_checks.filter((c) => c.passed !== null);
  const dqPassed = dqScored.filter((c) => c.passed).length;
  const recOk = D.reconciliation.filter((r) => r.matches).length;

  if (D.where === "fabric") $("#lh-status").textContent = "Run in Microsoft Fabric";

  $("#lh-kpis").innerHTML = kpiHTML([
    { label: "Rows landed in bronze", value: int(ingested), sub: `every 2024 flight, all carriers · ${D.ingest_log.length} monthly files` },
    { label: "Flight legs in silver", value: int(T.silver_flight_leg.rows), sub: `Alaska + Hawaiian (${int(asha)} in bronze)` },
    { label: "Quality checks passed", value: `${dqPassed} of ${dqScored.length}`, sub: `plus ${D.dq_checks.length - dqScored.length} informational` },
    { label: "Match this page", value: `${recOk} of ${D.reconciliation.length}`, sub: "gold vs. the pandas figures" },
  ]);

  const layer = (cls, name, text, tables) => `<div class="layer ${cls}"><span class="layer-chip">${name}</span><p>${text}</p><ul>${tables.map((t) => `<li><code>${t}</code><span>${int(T[t].rows)} rows</span></li>`).join("")}</ul></div>`;
  const arrow = `<div class="arrow" aria-hidden="true">→</div>`;
  $("#lh-flow").innerHTML = [
    layer("bronze", "Bronze", "Raw BTS files as published: all carriers, all columns, text only, plus the source file and load time.", ["bronze_bts_ontime", "bronze_ingest_log"]),
    arrow,
    layer("silver", "Silver", "Alaska + Hawaiian legs: typed, UTC times, the chapter 10 key, A14 flags, and the quality checks.", ["silver_flight_leg", "silver_airport", "silver_dq_checks"]),
    arrow,
    layer("gold", "Gold", "Business tables for Power BI and the SQL endpoint: reliability, disruption, overlap, delay causes.", ["gold_carrier_month_kpi", "gold_daily_disruption", "gold_market_overlap", "gold_delay_cause"]),
  ].join("");

  const mark = (p) => (p === null ? `<span class="info">info</span>` : p ? `<span class="ok">✓ pass</span>` : `<span class="critical-ink">✗ fail</span>`);
  $("#lh-dq tbody").innerHTML = D.dq_checks.map((c) => `<tr><td>${c.check}<div class="tbl-sub">${c.note}</div></td><td class="n num">${int(c.value)}</td><td class="n num">${c.expected === null ? "–" : int(c.expected)}</td><td>${mark(c.passed)}</td></tr>`).join("");

  const fmt = (name, v) => (/flights|markets/.test(name) ? int(v) : /delay/.test(name) ? `${v.toFixed(1)} min` : `${(v * 100).toFixed(2)}%`);
  $("#lh-rec tbody").innerHTML = D.reconciliation.map((r) => `<tr><td>${r.check}</td><td class="n num">${fmt(r.check, r.lakehouse)}</td><td class="n num">${fmt(r.check, r.portfolio)}</td><td>${r.matches ? `<span class="ok">✓ same</span>` : `<span class="critical-ink">✗ differs</span>`}</td></tr>`).join("");

  const dup = D.dq_checks.find((c) => /design key/.test(c.check));
  const elapsed = D.dq_checks.find((c) => /CRSElapsedTime/.test(c.check));
  $("#lh-findings").innerHTML = [
    finding(1, `<b>Bronze is untouched on purpose.</b> All ${int(ingested)} rows of 2024, every carrier, stay as published. If a rule in silver turns out to be wrong, silver is rebuilt from bronze without downloading anything again.`),
    finding(2, `<b>The pipeline tests itself.</b> The time-zone conversion is proved on every run: for all ${int(T.silver_flight_leg.rows)} legs, scheduled arrival minus scheduled departure equals the scheduled block time (${int(elapsed ? elapsed.value : 0)} mismatches). The chapter 10 key is unique; the original date-based key still collides ${dup ? dup.value : 2} times, and the check keeps reporting it.`),
    finding(3, `<b>Two pipelines, same answers.</b> ${recOk} of ${D.reconciliation.length} figures in gold equal the ones on this page, which come from separate pandas code. That's the test I'd want before a new platform replaces an old report.`),
  ].join("");
})();
