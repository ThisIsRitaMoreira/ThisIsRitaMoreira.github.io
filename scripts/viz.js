/* =========================================================
   viz.js — tiny chart kit for this portfolio. No libraries.
   Colors come from CSS custom properties, so light/dark
   switch without re-rendering. Every chart has a hover layer.
   ========================================================= */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const V = {};

  /* ---------- formatting ---------- */
  const nf0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
  V.fmt = {
    int: (v) => nf0.format(Math.round(v)),
    pct: (v, d = 0) => (v == null ? "—" : (v * 100).toFixed(d) + "%"),
    pct1: (v) => (v == null ? "—" : (v * 100).toFixed(1) + "%"),
    one: (v) => nf1.format(v),
    compact: (v) => (Math.abs(v) >= 10000 ? (v / 1000).toFixed(0) + "K" : nf0.format(v)),
    eur: (v) => "€" + nf0.format(Math.round(v)),
    usd: (v) => "$" + nf0.format(Math.round(v)),
    hours: (v) => (v < 1 ? Math.round(v * 60) + " min" : v < 48 ? nf1.format(v) + " h" : nf1.format(v / 24) + " d"),
    date: (s) => new Date(s + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" }),
  };

  /* ---------- tooltip singleton ---------- */
  let tipEl;
  function tip() {
    if (!tipEl) { tipEl = document.createElement("div"); tipEl.className = "tip"; tipEl.setAttribute("role", "status"); document.body.appendChild(tipEl); }
    return tipEl;
  }
  V.showTip = function (html, x, y) {
    const t = tip();
    t.innerHTML = html;
    t.classList.add("on");
    const r = t.getBoundingClientRect();
    let left = x + 14, top = y + 14;
    if (left + r.width > window.innerWidth - 8) left = x - r.width - 14;
    if (top + r.height > window.innerHeight - 8) top = y - r.height - 14;
    t.style.left = Math.max(8, left) + "px";
    t.style.top = Math.max(8, top) + "px";
  };
  V.hideTip = () => tipEl && tipEl.classList.remove("on");
  V.tipRows = (title, rows) =>
    `<div class="tip-t">${title}</div>` +
    rows.map((r) => `<div class="tip-r"><span>${r.color ? `<i style="background:${r.color}"></i>` : ""}${r.label}</span><b>${r.value}</b></div>`).join("");

  /* ---------- helpers ---------- */
  function el(tag, attrs = {}, parent) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) {
      if (k === "style") n.setAttribute("style", attrs[k]);
      else if (k === "text") n.textContent = attrs[k];
      else n.setAttribute(k, attrs[k]);
    }
    if (parent) parent.appendChild(n);
    return n;
  }
  V.svgEl = el;
  function niceTicks(max, count = 4) {
    if (max <= 0) return [0, 1];
    const raw = max / count;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || 10 * mag;
    const top = Math.ceil(max / step) * step;
    const out = [];
    for (let v = 0; v <= top + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }
  V.niceTicks = niceTicks;
  const observers = new WeakMap();
  function observe(node, fn) {
    if (observers.has(node)) observers.get(node).disconnect();
    let w = node.clientWidth;
    const ro = new ResizeObserver(() => { if (Math.abs(node.clientWidth - w) > 4) { w = node.clientWidth; fn(); } });
    ro.observe(node);
    observers.set(node, ro);
  }
  const cssVar = (name) => `var(${name})`;
  V.color = cssVar;

  /* =========================================================
     LINE / AREA CHART with crosshair
     o = { labels:[], series:[{name, values, color, area?, dash?}],
           yFmt, xLabel(i)->string|null, tipTitle(i), height, yMax, yMin, bands:[{from,to,label}] }
     ========================================================= */
  V.line = function (node, o) {
    const draw = () => {
      node.innerHTML = "";
      const W = Math.max(280, node.clientWidth), H = o.height || 220;
      const m = { t: 10, r: o.right || 12, b: 26, l: o.left || 40 };
      const iw = W - m.l - m.r, ih = H - m.t - m.b;
      const n = o.labels.length;
      const allV = o.series.flatMap((s) => s.values.filter((v) => v != null));
      const maxV = o.yMax != null ? o.yMax : Math.max(...allV, 0);
      const minV = o.yMin != null ? o.yMin : 0;
      const ticks = o.yTicks || (minV === 0 ? niceTicks(maxV, o.tickCount || 4) : null);
      const top = ticks ? ticks[ticks.length - 1] : maxV;
      const bottom = ticks ? ticks[0] : minV;
      const x = (i) => m.l + (n === 1 ? iw / 2 : (i / (n - 1)) * iw);
      const y = (v) => m.t + ih - ((v - bottom) / (top - bottom || 1)) * ih;
      const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": o.aria || "line chart" }, node);
      // bands (e.g. promo weeks)
      (o.bands || []).forEach((b) => {
        const x0 = x(b.from) - (iw / (n - 1)) / 2, x1 = x(b.to) + (iw / (n - 1)) / 2;
        el("rect", { x: Math.max(m.l, x0), y: m.t, width: Math.min(m.l + iw, x1) - Math.max(m.l, x0), height: ih, style: `fill:${b.color || "var(--accent-wash)"}` }, svg);
      });
      // grid + y labels
      (ticks || [bottom, top]).forEach((t) => {
        el("line", { x1: m.l, x2: m.l + iw, y1: y(t), y2: y(t), class: t === bottom ? "base-l" : "grid-l" }, svg);
        el("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end", class: "axis-t", text: (o.yFmt || V.fmt.int)(t) }, svg);
      });
      // x labels
      const step = o.xLabel ? 1 : Math.max(1, Math.ceil(n / Math.max(2, Math.floor(iw / 70))));
      for (let i = 0; i < n; i += step) {
        const lab = o.xLabel ? o.xLabel(i) : o.labels[i];
        if (lab != null) el("text", { x: x(i), y: H - 6, "text-anchor": i === 0 ? "start" : "middle", class: "axis-t", text: lab }, svg);
      }
      // series
      o.series.forEach((s) => {
        const pts = s.values.map((v, i) => (v == null ? null : [x(i), y(v)]));
        let d = "", started = false;
        pts.forEach((p) => { if (!p) { started = false; return; } d += (started ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1); started = true; });
        if (s.area) {
          const valid = pts.filter(Boolean);
          if (valid.length) {
            const ad = d + `L${valid[valid.length - 1][0].toFixed(1)},${y(bottom)}L${valid[0][0].toFixed(1)},${y(bottom)}Z`;
            el("path", { d: ad, style: `fill:${s.color};opacity:${s.areaOpacity || 0.1}` }, svg);
          }
        }
        el("path", { d, style: `fill:none;stroke:${s.color};stroke-width:${s.width || 2};stroke-linejoin:round;stroke-linecap:round;${s.dash ? "stroke-dasharray:" + s.dash : ""}` }, svg);
        if (s.endLabel) {
          const last = pts.map((p, i) => [p, i]).filter((q) => q[0]).pop();
          if (last) el("circle", { cx: last[0][0], cy: last[0][1], r: 4, style: `fill:${s.color};stroke:var(--surface);stroke-width:2` }, svg);
        }
      });
      // markers (e.g. stockouts)
      (o.markers || []).forEach((mk) => {
        el("circle", { cx: x(mk.i), cy: y(mk.v), r: mk.r || 4.5, style: `fill:${mk.color};stroke:var(--surface);stroke-width:2` }, svg);
      });
      // hover layer
      const cross = el("line", { x1: 0, x2: 0, y1: m.t, y2: m.t + ih, class: "cross", style: "display:none" }, svg);
      const dots = o.series.map((s) => el("circle", { r: 4.5, style: `fill:${s.color};stroke:var(--surface);stroke-width:2;display:none` }, svg));
      const hit = el("rect", { x: m.l, y: m.t, width: iw, height: ih, style: "fill:transparent;cursor:crosshair" }, svg);
      const move = (ev) => {
        const r = svg.getBoundingClientRect();
        const px = (ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left;
        const i = Math.max(0, Math.min(n - 1, Math.round(((px - m.l) / iw) * (n - 1))));
        cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.style.display = "";
        o.series.forEach((s, k) => {
          const v = s.values[i];
          if (v == null) { dots[k].style.display = "none"; return; }
          dots[k].setAttribute("cx", x(i)); dots[k].setAttribute("cy", y(v)); dots[k].style.display = "";
        });
        const rows = o.series.map((s) => ({ label: s.name, value: s.values[i] == null ? "—" : (o.tipFmt || o.yFmt || V.fmt.int)(s.values[i]), color: s.color }));
        if (o.extraTip) rows.push(...o.extraTip(i));
        V.showTip(V.tipRows(o.tipTitle ? o.tipTitle(i) : o.labels[i], rows), ev.touches ? ev.touches[0].clientX : ev.clientX, ev.touches ? ev.touches[0].clientY : ev.clientY);
        if (o.onHover) o.onHover(i);
      };
      const leave = () => { cross.style.display = "none"; dots.forEach((d) => (d.style.display = "none")); V.hideTip(); };
      hit.addEventListener("mousemove", move);
      hit.addEventListener("touchstart", move, { passive: true });
      hit.addEventListener("touchmove", move, { passive: true });
      hit.addEventListener("mouseleave", leave);
      hit.addEventListener("touchend", leave);
      if (o.onClick) hit.addEventListener("click", (ev) => {
        const r = svg.getBoundingClientRect();
        const i = Math.max(0, Math.min(n - 1, Math.round(((ev.clientX - r.left - m.l) / iw) * (n - 1))));
        o.onClick(i);
      });
    };
    draw();
    observe(node, draw);
  };

  /* =========================================================
     STACKED / GROUPED COLUMNS (SVG)
     o = { labels:[], series:[{name, values, color}], stacked:true, yFmt, height, xLabel(i) }
     ========================================================= */
  V.columns = function (node, o) {
    const draw = () => {
      node.innerHTML = "";
      const W = Math.max(280, node.clientWidth), H = o.height || 220;
      const m = { t: 18, r: 8, b: 26, l: o.left || 40 };
      const iw = W - m.l - m.r, ih = H - m.t - m.b;
      const n = o.labels.length;
      const totals = o.labels.map((_, i) => o.series.reduce((a, s) => a + (s.values[i] || 0), 0));
      const maxV = o.stacked ? Math.max(...totals) : Math.max(...o.series.flatMap((s) => s.values));
      const ticks = niceTicks(maxV, 4);
      const top = ticks[ticks.length - 1];
      const y = (v) => m.t + ih - (v / top) * ih;
      const band = iw / n;
      const bw = Math.min(24, band * 0.62);
      const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": o.aria || "column chart" }, node);
      ticks.forEach((t) => {
        el("line", { x1: m.l, x2: m.l + iw, y1: y(t), y2: y(t), class: t === 0 ? "base-l" : "grid-l" }, svg);
        el("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end", class: "axis-t", text: (o.yFmt || V.fmt.int)(t) }, svg);
      });
      const step = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(iw / 56))));
      o.labels.forEach((lab, i) => {
        const cx = m.l + band * i + band / 2;
        if (i % step === 0) el("text", { x: cx, y: H - 6, "text-anchor": "middle", class: "axis-t", text: o.xLabel ? o.xLabel(i) : lab }, svg);
        let acc = 0;
        const g = el("g", {}, svg);
        o.series.forEach((s, k) => {
          const v = s.values[i] || 0;
          if (v <= 0) return;
          const y0 = y(acc), y1 = y(acc + v);
          const isTop = k === o.series.length - 1 || o.series.slice(k + 1).every((ss) => !(ss.values[i] > 0));
          const h = Math.max(0, y0 - y1 - (acc > 0 ? 2 : 0));       // 2px surface gap between segments
          const yy = y1;
          if (isTop) {
            const r = Math.min(4, h);
            el("path", { d: `M${cx - bw / 2},${yy + h}V${yy + r}Q${cx - bw / 2},${yy} ${cx - bw / 2 + r},${yy}H${cx + bw / 2 - r}Q${cx + bw / 2},${yy} ${cx + bw / 2},${yy + r}V${yy + h}Z`, style: `fill:${s.color}` }, g);
          } else {
            el("rect", { x: cx - bw / 2, y: yy, width: bw, height: h, style: `fill:${s.color}` }, g);
          }
          acc += v;
        });
        if (o.capLabels) el("text", { x: cx, y: y(totals[i]) - 6, "text-anchor": "middle", class: "axis-t", style: "fill:var(--ink)", text: (o.capFmt || o.yFmt || V.fmt.int)(o.capValue ? o.capValue(i) : totals[i]) }, svg);
        const hit = el("rect", { x: m.l + band * i, y: m.t, width: band, height: ih, style: "fill:transparent" }, svg);
        hit.addEventListener("mousemove", (ev) => {
          g.style.opacity = 0.85;
          const rows = o.series.slice().reverse().map((s) => ({ label: s.name, value: (o.tipFmt || o.yFmt || V.fmt.int)(s.values[i] || 0), color: s.color }));
          if (o.stacked && o.series.length > 1) rows.push({ label: "Total", value: (o.tipFmt || o.yFmt || V.fmt.int)(totals[i]) });
          V.showTip(V.tipRows(o.tipTitle ? o.tipTitle(i) : lab, rows), ev.clientX, ev.clientY);
        });
        hit.addEventListener("mouseleave", () => { g.style.opacity = 1; V.hideTip(); });
      });
    };
    draw();
    observe(node, draw);
  };

  /* =========================================================
     HORIZONTAL BARS (HTML) — labels left, value at the tip
     items = [{label, value, color?, valueText?, sub?, tip?}]
     ========================================================= */
  V.hbars = function (node, items, o = {}) {
    const max = o.max || Math.max(...items.map((d) => d.value), 1e-9);
    node.className = "hbars";
    if (o.labelWidth) node.style.setProperty("--lbl-w", o.labelWidth + "px");
    node.innerHTML = items.map((d, i) => `
      <div class="hbar" data-i="${i}">
        <div class="hbar-lbl" title="${d.label}">${d.label}</div>
        <div class="hbar-track"><div class="hbar-fill" style="width:0;background:${d.color || "var(--s1)"}"></div>
        <span class="hbar-val">${d.valueText != null ? d.valueText : (o.fmt || V.fmt.int)(d.value)}${d.sub ? `<small>${d.sub}</small>` : ""}</span></div>
      </div>`).join("");
    requestAnimationFrame(() => {
      node.querySelectorAll(".hbar").forEach((row, i) => {
        const track = row.querySelector(".hbar-track");
        const room = 0.78; // leave space for the value label
        row.querySelector(".hbar-fill").style.width = `calc(${(items[i].value / max) * room * 100}% )`;
        row.addEventListener("mousemove", (ev) => { if (items[i].tip) V.showTip(items[i].tip, ev.clientX, ev.clientY); });
        row.addEventListener("mouseleave", V.hideTip);
        if (o.onClick) { row.style.cursor = "pointer"; row.addEventListener("click", () => o.onClick(items[i], i)); }
      });
    });
  };

  /* =========================================================
     COLUMNS (HTML) — small categorical columns, value on cap
     ========================================================= */
  V.cols = function (node, items, o = {}) {
    const max = o.max || Math.max(...items.map((d) => d.value), 1e-9);
    node.innerHTML = `<div class="cols" style="height:${o.height || 170}px">${items.map((d) => `
      <div class="col"><span class="col-val">${d.valueText != null ? d.valueText : (o.fmt || V.fmt.int)(d.value)}</span>
      <div class="col-fill" style="height:0;background:${d.color || "var(--s1)"}"></div></div>`).join("")}</div>
      <div class="col-lbls">${items.map((d) => `<span>${d.label}</span>`).join("")}</div>`;
    requestAnimationFrame(() => {
      node.querySelectorAll(".col").forEach((c, i) => {
        c.querySelector(".col-fill").style.height = ((items[i].value / max) * 82) + "%";
        c.addEventListener("mousemove", (ev) => items[i].tip && V.showTip(items[i].tip, ev.clientX, ev.clientY));
        c.addEventListener("mouseleave", V.hideTip);
      });
    });
  };

  /* =========================================================
     SPARKLINE
     ========================================================= */
  V.spark = function (node, values, o = {}) {
    const draw = () => {
      node.innerHTML = "";
      const W = Math.max(80, node.clientWidth), H = node.clientHeight || 40;
      const min = o.min != null ? o.min : Math.min(...values), max = o.max != null ? o.max : Math.max(...values);
      const x = (i) => 2 + (i / (values.length - 1)) * (W - 8);
      const y = (v) => 3 + (1 - (v - min) / (max - min || 1)) * (H - 6);
      const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, "aria-hidden": "true" }, node);
      const d = values.map((v, i) => (i ? "L" : "M") + x(i).toFixed(1) + "," + y(v).toFixed(1)).join("");
      el("path", { d: d + `L${x(values.length - 1)},${H}L${x(0)},${H}Z`, style: `fill:${o.color || "var(--s1)"};opacity:.1` }, svg);
      const p = el("path", { d, style: `fill:none;stroke:${o.color || "var(--s1)"};stroke-width:2;stroke-linejoin:round;stroke-linecap:round` }, svg);
      el("circle", { cx: x(values.length - 1), cy: y(values[values.length - 1]), r: 4, style: `fill:${o.color || "var(--s1)"};stroke:var(--surface-2);stroke-width:2` }, svg);
      if (o.animate && p.getTotalLength) {
        const L = p.getTotalLength();
        p.style.strokeDasharray = L; p.style.strokeDashoffset = L;
        p.getBoundingClientRect();
        p.style.transition = "stroke-dashoffset 1.4s cubic-bezier(.2,.8,.2,1)";
        p.style.strokeDashoffset = 0;
      }
      if (o.tip) {
        const hit = el("rect", { x: 0, y: 0, width: W, height: H, style: "fill:transparent" }, svg);
        hit.addEventListener("mousemove", (ev) => {
          const r = svg.getBoundingClientRect();
          const i = Math.max(0, Math.min(values.length - 1, Math.round(((ev.clientX - r.left - 2) / (W - 8)) * (values.length - 1))));
          V.showTip(o.tip(i), ev.clientX, ev.clientY);
        });
        hit.addEventListener("mouseleave", V.hideTip);
      }
    };
    draw();
    observe(node, draw);
  };

  /* count-up animation for headline numbers */
  V.countUp = function (node, to, fmt, ms = 900) {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { node.textContent = fmt(to); return; }
    const from = 0, t0 = performance.now();
    const tick = (t) => {
      const k = Math.min(1, (t - t0) / ms);
      const e = 1 - Math.pow(1 - k, 3);
      node.textContent = fmt(from + (to - from) * e);
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  };

  window.V = V;
})();
