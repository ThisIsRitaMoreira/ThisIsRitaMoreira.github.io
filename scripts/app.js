/* =========================================================
   app.js — routing between the home page and the four capsule
   pages (#/people, #/retail, #/airline, #/fleet), plus theme,
   menu, chapter navigation, toolkit, code tabs and reveals.
   ========================================================= */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- theme ---------- */
  const root = document.documentElement;
  const isDark = () => (root.dataset.theme ? root.dataset.theme === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches);
  $("#theme-btn").addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem("rm-theme", next); } catch (e) {}
    $('meta[name="theme-color"]').setAttribute("content", next === "dark" ? "#0E1729" : "#F3F7FC");
  });

  /* ---------- mobile menu ---------- */
  const menuBtn = $("#menu-btn"), menu = $("#mobile-menu");
  menuBtn.addEventListener("click", () => { const open = menu.classList.toggle("open"); menuBtn.setAttribute("aria-expanded", open); });
  $$("a", menu).forEach((a) => a.addEventListener("click", () => { menu.classList.remove("open"); menuBtn.setAttribute("aria-expanded", false); }));

  /* ---------- scroll progress ---------- */
  const prog = $("#progress");
  const onScroll = () => { const h = document.documentElement.scrollHeight - innerHeight; prog.style.width = (h > 0 ? (scrollY / h) * 100 : 0) + "%"; };
  addEventListener("scroll", onScroll, { passive: true });

  /* ---------- router ---------- */
  const CAPSULES = ["people", "retail", "airline", "fleet"];
  const TITLES = { home: "Rita Moreira · Business Analyst", people: "People analytics · Rita Moreira", retail: "Retail & grocery operations · Rita Moreira", airline: "Airlines & data platforms · Rita Moreira", fleet: "Fleet safety & big data · Rita Moreira" };
  let current = null;
  function route() {
    const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
    const view = CAPSULES.includes(parts[0]) ? parts[0] : "home";
    const target = view === "home" ? parts[0] : parts[1] ? `${view}-${parts[1]}` : null;
    if (view !== current) {
      $$(".view").forEach((v) => v.classList.toggle("active", v.dataset.view === view));
      current = view;
      document.title = TITLES[view];
      $$(".nav-links a").forEach((a) => a.classList.toggle("active", view !== "home" && a.getAttribute("href") === "#/capsules"));
      if (!target) window.scrollTo({ top: 0, behavior: "instant" });
      observeChapters(view);
      document.dispatchEvent(new CustomEvent("view", { detail: view }));
    }
    if (target) {
      const el = document.getElementById(target);
      const go = (smooth) => {
        const nav = $(".nav").offsetHeight, chap = view === "home" ? 0 : ($(`.view[data-view="${view}"] .chapnav`)?.offsetHeight || 0);
        window.scrollTo({ top: el.getBoundingClientRect().top + scrollY - nav - chap - 8, behavior: smooth && !reduce ? "smooth" : "auto" });
      };
      if (el) {
        requestAnimationFrame(() => go(!firstRoute));
        if (firstRoute) setTimeout(() => go(false), 600);   // charts finish laying out after load
      }
    }
    onScroll();
    firstRoute = false;
  }
  let firstRoute = true;
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  addEventListener("hashchange", route);
  window.goto = (hash) => { if (location.hash === hash) route(); else location.hash = hash; };

  /* ---------- chapter nav: highlight the chapter in view ---------- */
  let chapterIO;
  function observeChapters(view) {
    if (chapterIO) chapterIO.disconnect();
    if (view === "home" || !("IntersectionObserver" in window)) return;
    const page = $(`.view[data-view="${view}"]`);
    const links = $$(".chapnav a", page);
    chapterIO = new IntersectionObserver((ents) => ents.forEach((e) => {
      if (!e.isIntersecting) return;
      const key = e.target.id.replace(view + "-", "");
      links.forEach((a) => {
        const on = a.getAttribute("href") === `#/${view}/${key}`;
        a.classList.toggle("on", on);
        if (on) { const bar = a.parentElement; bar.scrollTo({ left: a.offsetLeft - bar.clientWidth / 2 + a.clientWidth / 2, behavior: "smooth" }); }
      });
    }), { rootMargin: "-35% 0px -60% 0px" });
    $$(".chapter", page).forEach((c) => chapterIO.observe(c));
  }

  /* ---------- toolkit (every tool points to its proof) ---------- */
  const TOOLS = [
    { group: "Analysis & BI", items: [
      { name: "Excel", sub: "Power Query · PivotTables · Solver", state: ["work", "here"], text: "KPI workbooks for SLA, backlog and repeat tickets at ALTEN; a Solver model for promotion orders in this portfolio.", proofs: [["People · SLA monitor", "#/people/desk"], ["Solver model", null, "solver"]] },
      { name: "Power BI", sub: "DAX · data modelling", state: ["work", "class"], text: "The order-day priority dashboard at Intermarché, and the fleet risk dashboard in class.", proofs: [["Retail · priority board", "#/retail/board"], ["Fleet · dashboard", "#/fleet/pipeline"]] },
      { name: "Tableau", sub: "Tableau Public · calculated fields · dashboard actions", state: ["class", "here"], text: "Practised in class labs; in this portfolio, a published promotions dashboard where clicking a category filters the KPIs, the weekly trend and the scatter.", proofs: [["Tableau Public dashboard", null, "tableau"], ["Retail · promotions", "#/retail/promo"]] },
    ] },
    { group: "Programming & statistics", items: [
      { name: "SQL", sub: "KPIs · window functions · HiveQL", state: ["class", "here"], text: "Business-question queries in Hive and Impala in my Big Data course; SLA and repeat-ticket logic in this portfolio.", proofs: [["People · SLA monitor", "#/people/desk"], ["People · repeats", "#/people/repeat"], ["Fleet · HiveQL", "#/fleet/pipeline"]] },
      { name: "Python", sub: "pandas · scikit-learn · SciPy", state: ["class", "here"], text: "The fleet models in my Big Data course (Bayesian, K-Means, random forest); the data pipelines and simulations in this portfolio.", proofs: [["Fleet · Bayesian model", "#/fleet/bayes"], ["Fleet · random forest", "#/fleet/profiles"], ["Retail · recommender", "#/retail/order"]] },
      { name: "R", sub: "dplyr · ggplot2 · survival", state: ["class", "here"], text: "Learned in my MS; in this portfolio, who leaves and why: logistic regression, survival curves and a decision tree.", proofs: [["People · attrition in R", "#/people/attrition", "attrition"], ["R report", null, "rreport"]] },
    ] },
    { group: "Data platforms", items: [
      { name: "Hadoop", sub: "HDFS · Hive · Pig · Impala", state: "class", text: "The fleet risk pipeline, from raw CSVs to a risk score per driver.", proofs: [["Fleet · pipeline", "#/fleet/pipeline"]] },
      { name: "Azure Databricks · Kafka", sub: "Delta Lake · Unity Catalog", state: "class", text: "The lakehouse and streaming backbone we designed for the airline merger (a design, not a live deployment).", proofs: [["Airline · architecture", "#/airline/arch"], ["Airline · platform choice", "#/airline/platform"]] },
      { name: "Microsoft Fabric", sub: "Lakehouse · PySpark notebooks · SQL endpoint", state: "class", text: "Practised in class labs. For the real 2024 flight data, I wrote bronze-silver-gold lakehouse notebooks for Fabric and tested them on Spark 3.5, the engine Fabric runs.", proofs: [["Airline · lakehouse notebooks", "#/airline/lakehouse"]] },
    ] },
    { group: "Business systems & workflow", items: [
      { name: "SAP", sub: "HR administration", state: "work", text: "Employee records and HR administration at ALTEN.", proofs: [["At ALTEN (no public demo)", null]] },
      { name: "ServiceNow", sub: "HR tickets · reports · employee documents", state: "work", text: "At ALTEN: answering employee tickets, running reports and managing employee documents. Chapters 1–2 of People analyze a real ServiceNow log.", proofs: [["People · desk health", "#/people/desk"], ["People · repeats", "#/people/repeat"]] },
      { name: "Git · GitHub", sub: "version control", state: "soon", text: "The code behind every capsule, in public repositories.", proofs: [["Repositories", null, "github"]] },
    ] },
  ];
  // links that become live as their files/sections are added (window.PROOF_LINKS can override)
  const LIVE = Object.assign({}, window.PROOF_LINKS || {});
  const STATE = { work: "At work", class: "In class", here: "In this portfolio", soon: "Being added" };
  $("#toolkit-groups").innerHTML = TOOLS.map((g) => `<div class="tool-group"><h3>${g.group}</h3><div class="tool-grid">${g.items.map((t) => `
    <div class="tool reveal"><div class="tool-top"><div class="tool-name">${t.name}<small>${t.sub}</small></div><span class="tool-states">${[].concat(t.state).map((st) => `<span class="tool-state ${st}">${STATE[st]}</span>`).join("")}</span></div>
    <p>${t.text}</p><div class="proofs">${t.proofs.map(([label, href, key]) => {
      const live = key && LIVE[key];
      const url = href || (live ? live : null);
      if (!url) return `<span class="proof pending">${label}${key ? " · soon" : ""}</span>`;
      const ext = !url.startsWith("#");
      return `<a class="proof" href="${url}"${ext ? ' target="_blank" rel="noopener"' : ""}>${label} ${ext ? "↗" : "→"}</a>`;
    }).join("")}</div></div>`).join("")}</div></div>`).join("");

  /* ---------- code tabs + light syntax colouring ---------- */
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const KW = {
    sql: /\b(WITH|AS|SELECT|FROM|WHERE|AND|OR|GROUP BY|ORDER BY|CASE|WHEN|THEN|ELSE|END|OVER|PARTITION BY|ROW_NUMBER|COUNT|AVG|COALESCE|LAG|INTERVAL|WITHIN GROUP|PERCENTILE_CONT|EXTRACT|DATE_TRUNC|LOAD|USING|FILTER|BY|FOREACH|GENERATE|GROUP|JOIN|STORE|INTO|LIMIT|ROUND)\b/g,
    python: /\b(def|return|for|in|if|else|max|import|and|not)\b/g,
    r: /\b(function|library|glm|survfit|coxph|rpart|if|else|for|in|return)\b/g,
    dax: /\b(VAR|RETURN|IF|CALCULATE|MAX|DIVIDE|COUNTROWS|SWITCH|TRUE|DATEADD|DATESINPERIOD|DAY)\b/g,
  };
  $$("pre.code").forEach((pre) => {
    const lang = pre.dataset.lang;
    const comment = lang === "sql" || lang === "dax" ? /(--[^\n]*)/ : lang === "excel" ? /('[^\n]*)/ : /(#[^\n]*)/;
    pre.innerHTML = pre.textContent.split("\n").map((line) => {
      const m = line.match(comment);
      let code = m ? line.slice(0, m.index) : line, com = m ? line.slice(m.index) : "";
      code = esc(code).replace(/("[^"]*"|'[^']*')/g, '<span class="s">$1</span>');
      if (KW[lang]) code = code.replace(KW[lang], '<span class="k">$1</span>');
      return code + (com ? `<span class="c">${esc(com)}</span>` : "");
    }).join("\n");
  });
  $$("[data-tabs]").forEach((box) => {
    const btns = $$(".code-tabs-bar button", box), pres = $$("pre", box);
    btns.forEach((b, i) => b.addEventListener("click", () => {
      btns.forEach((x, j) => x.setAttribute("aria-selected", i === j));
      pres.forEach((p, j) => (p.hidden = i !== j));
    }));
  });

  /* ---------- reveal on scroll ---------- */
  const revealAll = () => $$(".reveal").forEach((n) => n.classList.add("in"));
  if ("IntersectionObserver" in window && !reduce) {
    const io = new IntersectionObserver((ents) => ents.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { rootMargin: "0px 0px -6% 0px" });
    $$(".reveal").forEach((n) => io.observe(n));
    const lio = new IntersectionObserver((ents) => ents.forEach((e) => {
      if (e.isIntersecting) { $$("i[data-w]", e.target).forEach((i) => (i.style.width = i.dataset.w + "%")); lio.unobserve(e.target); }
    }), { threshold: 0.3 });
    lio.observe($("#langs"));
  } else {
    revealAll();
    $$("#langs i[data-w]").forEach((i) => (i.style.width = i.dataset.w + "%"));
  }

  route();
})();
