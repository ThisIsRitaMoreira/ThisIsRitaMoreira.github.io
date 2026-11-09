/* =========================================================
   Capsule 04, chapter 5 — where the abnormal events happen
   Data: window.DATA_GEO.west (projected states + 27 fleet cities)
   ========================================================= */
(function () {
  const G = window.DATA_GEO && window.DATA_GEO.west, D = window.DATA_FLEET;
  if (!G) return;
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const F = V.fmt, el = V.svgEl;
  const cities = G.cities.slice();
  let mode = "events";

  function draw() {
    const box = $("#fm-map"); box.innerHTML = "";
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", G.viewBox); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Map of abnormal driving events by city");
    box.appendChild(svg);
    G.states.forEach((s) => {
      const p = el("path", { d: s.d, class: "state", style: s.fleet ? "fill:var(--t-fleet)" : "" }, svg);
      p.appendChild(Object.assign(document.createElementNS("http://www.w3.org/2000/svg", "title"), { textContent: s.name }));
    });
    const val = (c) => (mode === "events" ? c.abnormal : c.rate);
    const max = Math.max(...cities.map(val));
    cities.slice().sort((a, b) => val(b) - val(a)).forEach((c) => {
      const v = val(c);
      const r = v > 0 ? 4 + 18 * Math.sqrt(v / max) : 3;
      const dot = el("circle", { cx: c.x, cy: c.y, r: r.toFixed(1), style: v > 0 ? "fill:var(--s2);fill-opacity:.55;stroke:var(--s2);stroke-width:1.5" : "fill:var(--axis-ink);opacity:.6" }, svg);
      dot.addEventListener("mousemove", (ev) => V.showTip(V.tipRows(`${c.city}, ${c.state}`, [
        { label: "Abnormal events", value: c.abnormal }, { label: "GPS pings", value: F.int(c.pings) }, { label: "Per 1,000 pings", value: c.rate.toFixed(1) }]), ev.clientX, ev.clientY));
      dot.addEventListener("mouseleave", V.hideTip);
    });
    const top = cities.slice().sort((a, b) => val(b) - val(a)).slice(0, 4);
    top.forEach((c) => el("text", { x: c.x + 10, y: c.y - 8, class: "axis-t", style: "fill:var(--ink);font-weight:700;font-size:15px", text: c.city }, svg));

    const ranked = cities.filter((c) => val(c) > 0).sort((a, b) => val(b) - val(a)).slice(0, 10);
    $("#fm-rank-title").textContent = mode === "events" ? "Most abnormal events" : "Highest rate per 1,000 pings";
    $("#fm-rank-sub").textContent = mode === "events" ? "Raw counts favour the busiest cities." : "Rates adjust for how much the fleet drives there.";
    V.hbars($("#fm-rank"), ranked.map((c) => ({
      label: c.city, value: val(c), valueText: mode === "events" ? String(c.abnormal) : c.rate.toFixed(1),
      sub: mode === "events" ? `${F.int(c.pings)} pings` : `${c.abnormal} events`, color: "var(--s2)",
      tip: V.tipRows(`${c.city}, ${c.state}`, [{ label: "Abnormal events", value: c.abnormal }, { label: "Per 1,000 pings", value: c.rate.toFixed(1) }]),
    })), { labelWidth: 150 });
  }
  $$("#fm-mode button").forEach((b) => b.addEventListener("click", () => { mode = b.dataset.m; $$("#fm-mode button").forEach((x) => x.setAttribute("aria-pressed", x === b)); draw(); }));
  draw();

  const ca = D && D.states ? D.states.find((s) => s.state === "California") : null;
  const zero = cities.filter((c) => c.abnormal === 0).map((c) => c.city);
  $("#fm-findings").innerHTML = [
    `<div class="finding"><span class="fi">1</span><div><b>Counts and rates tell different stories.</b> Stockton and Holtville have the most events, but Reno has the highest rate: ${cities.find((c) => c.city === "Reno").rate.toFixed(1)} per 1,000 pings.</div></div>`,
    ca ? `<div class="finding"><span class="fi">2</span><div><b>California is where the driving is.</b> It holds ${F.pct(ca.share)} of all events, in line with how much of the fleet's driving happens there, so it isn't riskier for the amount of driving done there.</div></div>` : "",
    zero.length ? `<div class="finding"><span class="fi">3</span><div><b>Some places are clean.</b> ${zero.slice(0, 3).join(", ")}${zero.length > 3 ? " and others" : ""} logged pings but no abnormal events. Place matters less than the driver, which fits chapter 3.</div></div>` : "",
  ].join("");
})();
