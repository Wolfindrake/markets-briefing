/* Markets Briefing — renders site/data/dashboard.json. Plain JavaScript, no build step. */
(function () {
  "use strict";
  var D = null;
  var S = { when: "today", page: "markets", group: "equities", mover: "gainers", chartKey: null, range: 365 };
  var chart = null;

  // ------------------------------------------------------------------ helpers
  function $(s) { return document.querySelector(s); }
  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); return n; }
  function tone(s) {
    if (typeof s !== "string") return "flat";
    var digits = s.replace(/[^0-9]/g, "");
    if (!digits || /^0+$/.test(digits)) return "flat";
    return s.charAt(0) === "+" ? "up" : s.charAt(0) === "-" ? "down" : "flat";
  }
  function link(href, text) {
    if (!href || !/^https?:\/\//.test(href)) return el("span", null, text);
    var a = el("a", null, text); a.href = href; a.target = "_blank"; a.rel = "noopener"; return a;
  }
  function isToday() { return S.when === "today"; }
  function ov() { return isToday() ? D.overview : D.overviewYesterday; }
  function simple() { return (isToday() ? D.simple : D.simpleYesterday) || {}; }
  function newsList() { return (isToday() ? D.news : D.newsYesterday) || []; }
  function snapKey() { return isToday() ? D.currentKey : (D.previousKey || D.currentKey); }
  function fmtTime(iso) { try { return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); } catch (e) { return iso; } }
  var NAME_TO_KEY = {};

  // ------------------------------------------------------------------ chrome
  function renderTicker() {
    var t = clear($("#ticker"));
    var items = D.ticker || [];
    for (var pass = 0; pass < 2; pass++) {
      items.forEach(function (x) {
        var s = el("span", "tk"); s.append(x.name.replace(/ - .*/, ""));
        s.append(el("b", null, x.last));
        s.append(el("span", tone(x.unit === "yield" || x.unit === "cds" ? x.chg : x.chgPct), x.unit === "yield" || x.unit === "cds" ? x.chg : x.chgPct));
        if (pass === 1) s.setAttribute("aria-hidden", "true");
        t.append(s);
      });
    }
  }
  function renderFresh() {
    var f = $("#fresh"); clear(f);
    var h = (Date.now() - new Date(D.updatedAt).getTime()) / 36e5;
    var cls = h < 18 ? "g" : h < 72 ? "y" : "r";
    var md = D.marketDate ? new Date(D.marketDate + "T12:00:00") : null;
    var mdTxt = md ? md.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" }) : "";
    var cc = D.crosscheck || {};
    f.append(el("span", "dot " + cls), "Market close " + mdTxt + " · refreshed " + fmtTime(D.updatedAt));
    if (cc.total) { var b = el("a", "ccbadge " + (cc.passed === cc.total ? "ok" : "warn"), (cc.passed === cc.total ? "✓ " : "! ") + cc.passed + "/" + cc.total + " checks"); b.href = "#sourcesCard"; b.addEventListener("click", function () { var m = document.querySelector('.nav button[data-page="markets"]'); if (m) m.click(); setTimeout(function () { $("#sourcesCard").scrollIntoView({ behavior: "smooth" }); }, 50); }); f.append(" ", b); }
  }
  function renderChecks() {
    var box = $("#checks"); var u = (D.verification && D.verification.unverifiedItems) || [];
    if (!u.length) { box.hidden = true; return; }
    box.hidden = false; clear(box);
    var d = el("details"); d.append(el("summary", null, u.length + " data check" + (u.length > 1 ? "s" : "") + " — tap to see"));
    var ul = el("ul"); u.forEach(function (x) { ul.append(el("li", null, x)); }); d.append(ul); box.append(d);
  }

  // ------------------------------------------------------------------ markets page
  function renderHero() {
    var o = ov() || { items: [] };
    $("#heroTitle").textContent = (isToday() ? "Today" : "Yesterday") + " in one look" + (o.date ? " — " + o.date : "");
    $("#heroAsOf").textContent = o.asOf || "";
    var h = clear($("#hero"));
    if (!(o.items || []).length) { h.append(el("p", "muted", "No summary for this day.")); return; }
    o.items.forEach(function (it) {
      var c = el("div", "hc " + (it.direction === "up" ? "up" : it.direction === "down" ? "down" : ""));
      c.append(el("div", "l", it.label), el("div", "t", (it.direction === "up" ? "▲ " : it.direction === "down" ? "▼ " : "■ ") + it.directionText), el("div", "d", it.detail));
      h.append(c);
    });
  }
  var COLS = { symbol: "Symbol", last: "Last", open: "Open", prev: "Prev.", chg: "Chg.", chgPct: "Chg. %", daily: "Daily", week: "1W", month: "1M", ytd: "YTD", year: "1Y", y3: "3Y" };
  var SHOW = ["last", "chg", "chgPct", "week", "month", "ytd", "year", "y3", "open", "prev"];
  function renderMarket() {
    var snap = D.snapshots[snapKey()];
    var t = clear($("#mktTable"));
    if (!snap) { t.append(el("caption", null, "No data.")); return; }
    $("#snapNote").textContent = (isToday() ? "Today" : "Previous session") + " — " + snap.label + " · " + snap.asOf;
    var idx = {}; snap.columns.forEach(function (c, i) { idx[c] = i + 1; });
    var thead = el("thead"), hr = el("tr"); hr.append(el("th", null, "Name"));
    SHOW.forEach(function (c) { hr.append(el("th", null, COLS[c])); }); thead.append(hr); t.append(thead);
    var tb = el("tbody");
    (snap[S.group] || []).forEach(function (r) {
      var tr = el("tr"), nm = el("td", "nm"); nm.append(el("b", null, r[0]));
      var sm = el("small", null, r[idx.symbol]); var lk = (D.links || {})[r[0]];
      if (lk && /^https:\/\/www\.investing\.com\//.test(lk)) { var a = el("a", "inv", "Investing ↗"); a.href = lk; a.target = "_blank"; a.rel = "noopener"; a.title = "Open on Investing.com"; a.addEventListener("click", function (e) { e.stopPropagation(); }); sm.append(" · ", a); }
      nm.append(sm);
      tr.append(nm);
      SHOW.forEach(function (c) {
        var v = r[idx[c]];
        var td = el("td");
        if (c === "chg" || c === "chgPct") { td.append(el("span", "pill " + tone(v), v)); }
        else { td.textContent = v; if (c !== "last" && c !== "open" && c !== "prev") td.className = tone(v); }
        tr.append(td);
      });
      tr.tabIndex = 0;
      tr.addEventListener("click", function () { openChart(NAME_TO_KEY[r[0]]); });
      tr.addEventListener("keydown", function (e) { if (e.key === "Enter") openChart(NAME_TO_KEY[r[0]]); });
      tb.append(tr);
    });
    t.append(tb);
    var dn = simple().driverNotes || {};
    $("#driverNote").textContent = dn[S.group] || "—";
  }
  function forceCard(f) {
    var c = el("div", "force"); c.append(el("h3", null, f.title));
    var st = el("div", "fstats");
    (f.stats || []).forEach(function (s) { var x = el("div", "fstat"); x.append(el("div", "v", s.value), el("div", "k", s.label)); st.append(x); });
    c.append(st);
    if (f.analogy) { var p = el("div", "plain"); p.append(el("b", null, "In plain English: "), f.analogy); c.append(p); }
    if (f.explanation) { var e = el("p"); e.append(el("b", null, "What happened & why: "), f.explanation); c.append(e); }
    if (f.whyItMatters) { var w = el("p"); w.append(el("b", null, "Impact: "), f.whyItMatters); c.append(w); }
    if (f.source) { var s2 = el("p", "src"); s2.append("Source: ", link(f.sourceUrl, f.source)); c.append(s2); }
    return c;
  }
  function renderForces(target) {
    var box = clear($(target)); var fs = simple().forces || [];
    if (!fs.length) { box.append(el("p", "muted", "No explanations for this day.")); return; }
    fs.forEach(function (f) { box.append(forceCard(f)); });
  }
  function renderWeek() {
    var ul = clear($("#week"));
    if (!(D.weekAhead || []).length) { ul.append(el("li", "muted", "Add upcoming events in content/briefing.yaml (week_ahead).")); return; }
    D.weekAhead.forEach(function (r) {
      var li = el("li"); li.append(el("span", "d", r[0]), el("span", "r", r[1]));
      var ev = el("span"); ev.append(r[7] ? link(r[7], r[2]) : r[2]); li.append(ev);
      var extra = [];
      if (r[3] && r[3] !== "—") extra.push("Consensus " + r[3]);
      if (r[4] && r[4] !== "—") extra.push("Previous " + r[4]);
      if (r[6]) extra.push(r[6]);
      if (extra.length) li.append(el("span", "c", extra.join(" · ")));
      ul.append(li);
    });
  }
  function renderSources() {
    var v = D.verification || {}; var box = clear($("#verify"));
    box.append(el("p", null, v.note || ""));
    var cc = D.crosscheck || {};
    if ((cc.items || []).length) {
      box.append(el("p", "cc-score", "Cross-checks: " + cc.passed + " of " + cc.total + " passed"));
      var ul0 = el("ul", "cc");
      cc.items.forEach(function (i) { var li = el("li", i.ok ? "ok" : "warn"); li.append(el("b", null, (i.ok ? "✓ " : "! ") + i.group + ": " + i.check), el("small", null, i.detail)); ul0.append(li); });
      box.append(ul0);
    }
    if ((v.verifiedItems || []).length) box.append(el("p", "muted", "Data sources used today: " + v.verifiedItems.join(", ")));
    var ul = clear($("#sources"));
    (D.sources || []).forEach(function (s) { var li = el("li"); li.append(link(s.url, s.name)); ul.append(li); });
  }
  function renderMovers() {
    var ul = clear($("#movers"));
    ((D.movers || {})[S.mover] || []).forEach(function (m) {
      var li = el("li"); li.append(el("span", null, m.name), el("span", tone(m.chgPct), m.last + "  " + m.chgPct)); ul.append(li);
    });
  }
  function heatColor(v, rate) {
    if (v == null || isNaN(v)) return "#8a94a3";
    var x = rate ? v / 15 : v / 2.5; x = Math.max(-1, Math.min(1, x));
    var a = 0.38 + 0.62 * Math.abs(x);
    var css = getComputedStyle(document.documentElement);
    var rgb = (x >= 0 ? css.getPropertyValue("--heat-up") : css.getPropertyValue("--heat-down")).trim() || (x >= 0 ? "12,118,81" : "180,35,24");
    return "rgba(" + rgb + "," + a.toFixed(2) + ")";
  }
  function renderHeat() {
    var box = clear($("#heat"));
    (D.heatmap || []).forEach(function (h) {
      var rate = h.unit === "yield" || h.unit === "cds";
      var t = el("div", "ht"); t.style.background = heatColor(rate ? h.chgBp : h.chgPct, rate);
      t.title = h.name + ": " + h.last + " (" + h.label + ")";
      t.append(el("b", null, h.name.replace(/ - .*/, "").replace("United States", "US").slice(0, 18)), h.label);
      t.addEventListener("click", function () { openChart(h.key); });
      box.append(t);
    });
  }
  var SEVEN = [["spx", "S&P 500"], ["ixic", "Nasdaq"], ["us10", "US 10Y"], ["us2", "US 2Y"], ["eurusd", "EUR/USD"], ["brent", "Brent"], ["xau", "Gold"], ["btc", "Bitcoin"]];
  function spark(vals) {
    var nums = vals.filter(function (v) { return v != null && !isNaN(v); });
    if (nums.length < 2) return el("span", "muted", "—");
    var min = Math.min.apply(null, nums), max = Math.max.apply(null, nums), rg = (max - min) || 1, w = 70, h = 20;
    var pts = nums.map(function (v, i) { return (2 + i * (w - 4) / (nums.length - 1)).toFixed(1) + "," + (h - 2 - (v - min) / rg * (h - 4)).toFixed(1); }).join(" ");
    var ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
    svg.setAttribute("width", w); svg.setAttribute("height", h); svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    var pl = document.createElementNS(ns, "polyline"); pl.setAttribute("points", pts); pl.setAttribute("fill", "none");
    pl.setAttribute("stroke", getComputedStyle(document.documentElement).getPropertyValue(nums[nums.length - 1] >= nums[0] ? "--up" : "--down").trim()); pl.setAttribute("stroke-width", "1.6");
    svg.append(pl); return svg;
  }
  function renderSeven() {
    var t = clear($("#seven")); var H = D.history || {};
    var dates = {};
    SEVEN.forEach(function (m) { ((H[m[0]] || {}).points || []).slice(-7).forEach(function (p) { dates[p[0]] = 1; }); });
    var ds = Object.keys(dates).sort().slice(-5);
    var hr = el("tr"); hr.append(el("th", null, ""));
    ds.forEach(function (d) { hr.append(el("th", null, d.slice(5))); }); hr.append(el("th", null, "7d"));
    var th = el("thead"); th.append(hr); t.append(th);
    var tb = el("tbody");
    SEVEN.forEach(function (m) {
      var pts = (H[m[0]] || {}).points || []; var map = {}; pts.forEach(function (p) { map[p[0]] = p[1]; });
      var tr = el("tr"); tr.append(el("td", null, m[1]));
      ds.forEach(function (d) { var v = map[d]; tr.append(el("td", null, v == null ? "—" : (Math.abs(v) >= 1000 ? Math.round(v).toLocaleString() : v.toFixed(v < 10 ? 3 : 2)))); });
      var td = el("td"); td.append(spark(pts.slice(-7).map(function (p) { return p[1]; }))); tr.append(td);
      tb.append(tr);
    });
    t.append(tb);
  }
  function renderDownloads() {
    var dl = D.downloads || {};
    ["#dlPdf", "#dlPdf2"].forEach(function (s) { $(s).href = dl.pdf || "#"; });
    ["#dlXlsx", "#dlXlsx2"].forEach(function (s) { $(s).href = dl.xlsx || "#"; });
    $("#sheetNote").textContent = "Sheet for the " + D.marketDate + " close. Commentary on the sheet: " +
      (D.briefingCurrent ? "your own text (content/briefing.yaml)." : D.aiUsed ? "AI draft from today's headlines; check before handing in." : "automatic summary; edit content/briefing.yaml for your own words.");
    var ul = clear($("#archive"));
    (dl.archive || []).forEach(function (f) { var li = el("li"); var a = el("a", null, f.replace(/\.pdf$/, "")); a.href = "downloads/" + f; a.setAttribute("download", ""); li.append(a); ul.append(li); });
  }

  // ------------------------------------------------------------------ explained page
  function renderExplained() {
    var s = simple();
    $("#bigPicture").textContent = s.bigPicture || "—";
    var ch = clear($("#chain")); var steps = (s.chain && s.chain.steps) || [];
    steps.forEach(function (st, i) { ch.append(el("span", "s", st)); if (i < steps.length - 1) ch.append(el("span", "a", "→")); });
    $("#chainNote").textContent = (s.chain && s.chain.explanation) || "";
    var kn = clear($("#keyNumbers")); (s.keyNumbers || []).forEach(function (k) { var d = el("div"); d.append(el("b", null, k.value), el("small", null, k.label)); kn.append(d); });
    var w = clear($("#watch")); (s.whatToWatch || []).forEach(function (x) { var li = el("li"); li.append(el("b", null, x.title), el("small", null, x.detail)); w.append(li); });
    if (!(s.whatToWatch || []).length) w.append(el("li", "muted", "Nothing listed."));
    renderForces("#forcesSimple");
    var wa = clear($("#world")); (s.worldAround || []).forEach(function (x) { var d = el("div"); d.append(el("h3", null, x.region), el("div", "muted", x.direction), el("p", null, x.detail)); if (x.note) d.append(el("p", "muted", x.note)); wa.append(d); });
    var g = clear($("#glossary")); ((D.simple || {}).glossary || []).forEach(function (x) { g.append(el("dt", null, x.term), el("dd", null, x.def)); });
  }

  // ------------------------------------------------------------------ news page
  function renderNews() {
    var ul = clear($("#newsList")); var items = newsList();
    if (!items.length) { ul.append(el("li", "muted", "No headlines for this day.")); return; }
    items.forEach(function (n) {
      var li = el("li"); li.append(link(n.url, n.headline), el("div", "m", n.source + " · " + n.dateISO + (n.session ? " · session day" : " · after the close")));
      if (n.blurb) li.append(el("p", null, n.blurb)); ul.append(li);
    });
  }

  // ------------------------------------------------------------------ trump page
  function renderTrump() {
    var t = D.trumpImpact || {};
    $("#tiTitle").textContent = "Trump market impact — week of " + (t.weekOf || "");
    $("#tiUpdated").textContent = t.lastUpdated ? "Updated " + fmtTime(t.lastUpdated) : "";
    var b = clear($("#tiBullets")); (t.summaryBullets || []).forEach(function (x) { b.append(el("li", null, x)); });
    $("#tiSummary").textContent = t.weeklySummary || "";
    var mv = clear($("#tiMoves"));
    (t.majorMoves || []).forEach(function (m) {
      var c = el("article", "card tmove"); var hd = el("div", "card-head"); hd.append(el("h3", null, m.title), el("span", "muted", m.dateRange || "")); c.append(hd);
      if (m.background) c.append(el("p", null, m.background));
      var g = el("div", "tgrid"); var imp = m.impact || {};
      [["Equities", imp.equities], ["Bonds & yields", imp.bonds], ["Commodities", imp.commodities], ["Crypto", imp.crypto], ["Defense", imp.defense]].forEach(function (p) {
        if (!p[1]) return; var d = el("div"); d.append(el("b", null, p[0]), p[1]); g.append(d); });
      c.append(g);
      if (m.why) { var w = el("p"); w.append(el("b", null, "Why it moved the market: "), m.why); c.append(w); }
      var wl = el("div", "wl"), wi = el("div"), lo = el("div");
      wi.append(el("b", "up", "Winners")); var u1 = el("ul"); (m.winners || []).forEach(function (x) { u1.append(el("li", null, x)); }); wi.append(u1);
      lo.append(el("b", "down", "Losers")); var u2 = el("ul"); (m.losers || []).forEach(function (x) { u2.append(el("li", null, x)); }); lo.append(u2);
      wl.append(wi, lo); c.append(wl);
      if (m.source && m.source.name) { var s = el("p", "src"); s.append("Source: ", link(m.source.url, m.source.name)); c.append(s); }
      mv.append(c);
    });
    var f = clear($("#tiForward")); (t.forwardLook || []).forEach(function (x) { var d = el("div", "fwd"); d.append(el("b", null, (x.date ? x.date + " — " : "") + x.title), x.text || ""); f.append(d); });
    if (!(t.forwardLook || []).length) f.append(el("p", "muted", "—"));
    var sc = clear($("#tiScenarios")); (t.scenarios || []).forEach(function (x) { var d = el("div", "fwd"); d.append(el("b", null, x.label), x.text || ""); sc.append(d); });
    if (!(t.scenarios || []).length) sc.append(el("p", "muted", "—"));
    var so = clear($("#tiSources")); (t.sources || []).forEach(function (x) { var li = el("li"); li.append(link(x.url, x.name)); so.append(li); });
    $("#tiDisclaimer").textContent = t.disclaimer || "";
  }

  // ------------------------------------------------------------------ lords of finance
  function renderLof() {
    var L = D.lordsOfFinance || {}; var cur = clear($("#lofCurrent"));
    if (L.currentCall) {
      var c = L.currentCall; var call = String(c.call || "").toLowerCase();
      var row = el("div", "lofcall"); row.append(el("span", "badge " + (call === "long" ? "long" : call === "short" ? "short" : "none"), (c.call || "—").toUpperCase()));
      var info = el("div"); info.append(el("div", null, "Session " + c.weekOf + (c.status ? " · " + c.status : "")), el("div", "muted", c.keyLevels || ""));
      row.append(info); cur.append(row);
      if (c.rationale) cur.append(el("p", null, c.rationale));
    } else { cur.append(el("p", "muted", L.howTo || "No call logged yet.")); }
    var k = clear($("#lofKpis"));
    function kpi(a, b) { var d = el("div", "kpi"); d.append(el("small", null, a), el("b", null, b)); k.append(d); }
    if (L.balance != null) kpi("Balance (closed rounds)", "$" + Math.round(L.balance).toLocaleString());
    if (L.closed) kpi("Hit rate", Math.round(100 * L.hits / L.closed) + "% of " + L.closed);
    var t = clear($("#lofHistory"));
    if (!(L.history || []).length) { t.append(el("caption", "muted", "No closed rounds yet.")); return; }
    var hr = el("tr"); ["#", "Session", "Call → result", "Reason", "Status"].forEach(function (h) { hr.append(el("th", null, h)); });
    var th = el("thead"); th.append(hr); t.append(th); var tb = el("tbody");
    L.history.forEach(function (h) { var tr = el("tr"); [h.session, h.weekOf, h.call, h.rationale, h.status].forEach(function (v) { tr.append(el("td", null, v == null ? "" : String(v))); }); tb.append(tr); });
    t.append(tb);
  }


  // ------------------------------------------------------------------ the professor's method
  var ARROW = { up: "▲ up", down: "▼ down", flat: "■ flat", mixed: "◆ mixed" };
  function renderTape() {
    var R = D.reading || {}, t = R.tape, box = clear($("#tape"));
    if (!t || !t.name) { box.append(el("p", "muted", "Not enough data to read the day.")); return; }
    box.append(el("p", "tape-name", t.name), el("p", "tape-map", t.map));
    var g = el("div", "checks");
    (t.checks || []).forEach(function (c) {
      var d = el("div", "chk"); d.append(el("b", null, c.asset));
      d.append(el("div", "v " + tone(c.value), c.value));
      var m = c.match === true ? el("span", "ok", "✓ ") : c.match === false ? el("span", "no", "✗ ") : el("span", null, "");
      var line = el("small"); line.append(m, (c.expected && c.expected !== "—" ? "Map expects " + (ARROW[c.expected] || c.expected) + ", got " : "Moved ") + (ARROW[c.actual] || c.actual));
      d.append(line); g.append(d);
    });
    box.append(g);
    if (t.curve) box.append(el("p", "muted", t.curve));
    if (t.verdict) box.append(el("p", "verdict", t.verdict));
    var o = R.overshoot; if (o && o.text) box.append(el("p", null, "Overshooting? " + o.text));
  }
  function renderInternals() {
    var ul = clear($("#internals")); var xs = (D.reading || {}).internals || [];
    if (!xs.length) { ul.append(el("li", "muted", "—")); return; }
    xs.forEach(function (x) { var li = el("li"); li.append(el("b", null, x.label + ": " + x.value)); if (x.note) li.append(el("small", null, x.note)); ul.append(li); });
  }
  function renderMacro() {
    var M = D.macro || {};
    var cy = clear($("#cycle"));
    if (M.cycle) { cy.append(el("p", "phase", M.cycle.phase), el("p", null, M.cycle.text), el("p", "muted", "Rule of thumb from: " + M.cycle.inputs.join(" · "))); }
    else cy.append(el("p", "muted", "Needs FRED data (filled in on the daily run)."));
    var rr = clear($("#realRate")); var r = M.realRate;
    if (r) {
      rr.append(el("div", "big-num", (r.real_headline >= 0 ? "+" : "") + r.real_headline.toFixed(1) + "%"));
      rr.append(el("p", null, "Effective fed funds " + r.effr.toFixed(2) + "% minus CPI " + r.cpi.toFixed(1) + "%" + (r.core != null ? " (against core " + r.core.toFixed(1) + "%: " + (r.real_core >= 0 ? "+" : "") + r.real_core.toFixed(1) + "%)" : "") + "."));
      rr.append(el("p", "muted", r.read));
    } else rr.append(el("p", "muted", "—"));
    $("#macroAsOf").textContent = M.asOf ? "FRED data to " + M.asOf : "";
    var t = clear($("#macroTable")); var ind = M.indicators || [];
    if (!ind.length) { t.append(el("caption", "muted", "No macro data yet.")); }
    else {
      var hr = el("tr"); ["Indicator", "Latest reading", "Previous", "What it measures", "Typical market impact"].forEach(function (h) { hr.append(el("th", null, h)); });
      var th = el("thead"); th.append(hr); t.append(th); var tb = el("tbody");
      ind.forEach(function (i) { var tr = el("tr"); var n = el("td"); n.append(el("b", null, i.name)); tr.append(n);
        [i.latest, i.previous, i.measures, i.impact].forEach(function (v) { tr.append(el("td", null, v || "")); }); tb.append(tr); });
      t.append(tb);
    }
    var sb = clear($("#surprises")); var ss = D.surprises || [];
    if (!ss.length) sb.append(el("p", "muted", "No releases with an actual in the last week."));
    var Q = ["What was released vs consensus?", "Hawkish, dovish or growth surprise?", "What does it change for the central bank?", "What moved, and does it match the map?"];
    ss.forEach(function (x) {
      var c = el("div", "surp"); var h = el("h3", null, (x.day ? x.day + " · " : "") + (x.region ? x.region + " · " : "") + x.event);
      h.append(el("span", "tag " + (x.signal || ""), x.label)); c.append(h);
      c.append(el("p", "muted", "Actual " + x.actual + " · Consensus " + x.consensus + " · Previous " + x.previous));
      if ((x.q || []).length) { var ol = el("ol"); x.q.forEach(function (a, i) { var li = el("li"); li.append(el("b", null, Q[i] + " "), a); ol.append(li); }); c.append(ol); }
      if (x.expected && x.expected.outperform) c.append(el("p", "muted", "Usually outperform: " + x.expected.outperform));
      sb.append(c);
    });
    var m = clear($("#reactMap"));
    var rows = [["Data surprise", "Bond yields", "USD", "Equities", "Usually outperform"],
      ["Inflation above consensus", "▲", "▲", "▼", "Value, energy, banks; growth and tech lag"],
      ["Jobs or GDP below consensus", "▼", "▼", "Mixed", "Bonds, defensives (utilities, staples)"],
      ["Growth above consensus (PMI, GDP)", "▲", "▲", "▲ if inflation is contained", "Cyclicals, small caps"],
      ["Hawkish central bank surprise", "▲ (short end most)", "▲", "▼", "Short-duration sectors"],
      ["Oil supply shock", "▲ inflation fear / ▼ growth fear", "▲", "▼", "Energy, defence"],
      ["Geopolitical risk-off", "▼ (flight to quality)", "▲ (also CHF, JPY)", "▼", "Treasuries, gold"]];
    var mh = el("thead"), mr = el("tr"); rows[0].forEach(function (h) { mr.append(el("th", null, h)); }); mh.append(mr); m.append(mh);
    var mb = el("tbody"); rows.slice(1).forEach(function (r0) { var tr = el("tr"); r0.forEach(function (v, i) { tr.append(el("td", i ? null : null, v)); }); mb.append(tr); }); m.append(mb);
  }
  function lessonCard(l) {
    var d = el("div", "lesson"); d.append(el("h3", null, l.title), el("p", null, l.text));
    if (l.today) d.append(el("p", "today", "Today: " + l.today)); return d;
  }
  function renderLessons() {
    var R = D.reading || {};
    var a = clear($("#lessons")); (R.lessons || []).forEach(function (l) { a.append(lessonCard(l)); });
    if (!(R.lessons || []).length) a.append(el("p", "muted", "—"));
    var b = clear($("#library")); (R.library || []).forEach(function (l) { b.append(lessonCard(l)); });
  }
  function renderSteps() {
    var ol = clear($("#steps")); ((D.reading || {}).steps || []).forEach(function (s) {
      var li = el("li"); li.append(el("b", null, s.title + (/[?.]$/.test(s.title) ? " " : ". ")), el("span", "q", s.q)); li.append(el("div", null, s.auto)); ol.append(li); });
  }


  // ------------------------------------------------------------------ update menu: links to the GitHub repo
  function repoUrl() {
    var cfg = (D.site && D.site.repo_url) || "";
    if (/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/.test(cfg)) return cfg.replace(/\/$/, "");
    var m = location.hostname.match(/^([\w-]+)\.github\.io$/);   // https://USER.github.io/REPO/ -> github.com/USER/REPO
    if (!m) return "";
    var repo = location.pathname.split("/").filter(Boolean)[0] || (m[1] + ".github.io");
    return "https://github.com/" + m[1] + "/" + repo;
  }
  function renderUpdate() {
    var r = repoUrl(); if (!r) return;
    $("#updRun").href = r + "/actions/workflows/daily.yml";
    $("#updEdit").href = r + "/edit/main/content/briefing.yaml";
    $("#updCsv").href = r + "/upload/main/data/imports";
    $("#updLog").href = r + "/actions";
    var inv = (D.site && D.site.investing_watchlist) || "https://www.investing.com/portfolio/";
    $("#updInv").href = /^https:\/\/www\.investing\.com\//.test(inv) ? inv : "https://www.investing.com/portfolio/";
    $("#upd").hidden = false;
  }
  document.addEventListener("click", function (e) { var u = $("#upd"); if (u && u.open && !u.contains(e.target)) u.open = false; });


  // ------------------------------------------------------------------ Long / Short meter
  function gaugeSVG(needle, small) {
    var ns = "http://www.w3.org/2000/svg", w = 240, h = 140, cx = 120, cy = 124, R = 100;
    var svg = document.createElementNS(ns, "svg"); svg.setAttribute("viewBox", "0 0 " + w + " " + h); svg.setAttribute("class", "gsvg");
    svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Meter from short to long");
    function arc(a0, a1, color) {
      var p0 = [cx + R * Math.cos(a0), cy - R * Math.sin(a0)], p1 = [cx + R * Math.cos(a1), cy - R * Math.sin(a1)];
      var path = document.createElementNS(ns, "path");
      path.setAttribute("d", "M" + p0[0].toFixed(1) + " " + p0[1].toFixed(1) + " A " + R + " " + R + " 0 0 1 " + p1[0].toFixed(1) + " " + p1[1].toFixed(1));
      path.setAttribute("stroke", color); path.setAttribute("stroke-width", small ? 16 : 18); path.setAttribute("fill", "none"); svg.append(path);
    }
    var segs = [["var(--down)", 0.85], ["var(--down)", 0.45], ["var(--gold)", 0.25], ["var(--up)", 0.45], ["var(--up)", 0.85]];
    for (var i = 0; i < 5; i++) { var a0 = Math.PI - i * Math.PI / 5 - 0.012, a1 = Math.PI - (i + 1) * Math.PI / 5 + 0.012; arc(a0, a1, segs[i][0]); svg.lastChild.setAttribute("opacity", segs[i][1]); }
    [["SHORT", 22], ["LONG", 218]].forEach(function (t) { var tx = document.createElementNS(ns, "text"); tx.setAttribute("x", t[1]); tx.setAttribute("y", 138); tx.setAttribute("text-anchor", "middle"); tx.setAttribute("class", "glab"); tx.textContent = t[0]; svg.append(tx); });
    var g = document.createElementNS(ns, "g"); g.setAttribute("class", "gneedle");
    var ln = document.createElementNS(ns, "line"); ln.setAttribute("x1", cx); ln.setAttribute("y1", cy); ln.setAttribute("x2", cx); ln.setAttribute("y2", cy - R + 14);
    ln.setAttribute("stroke", "var(--ink)"); ln.setAttribute("stroke-width", 4); ln.setAttribute("stroke-linecap", "round");
    var hub = document.createElementNS(ns, "circle"); hub.setAttribute("cx", cx); hub.setAttribute("cy", cy); hub.setAttribute("r", 8); hub.setAttribute("fill", "var(--gold)");
    g.append(ln, hub); svg.append(g);
    var deg = Math.max(-1, Math.min(1, needle || 0)) * 90;
    g.style.transformOrigin = cx + "px " + cy + "px"; g.style.transform = "rotate(-90deg)";
    requestAnimationFrame(function () { requestAnimationFrame(function () { g.style.transform = "rotate(" + deg.toFixed(1) + "deg)"; }); });
    return svg;
  }
  function renderMeter() {
    var M = D.meter; if (!M) { $("#meterMini").hidden = true; return; }
    var cls = M.needle > 0.2 ? "up" : M.needle < -0.2 ? "down" : "flat";
    clear($("#gauge")).append(gaugeSVG(M.needle, false)); clear($("#gaugeMini")).append(gaugeSVG(M.needle, true));
    var r = clear($("#meterRead")); r.append(el("div", "zone " + cls, M.zone), el("div", "conv", M.conviction + "% conviction"), el("p", "muted", M.note || ""));
    $("#meterMiniRead").textContent = M.zone + " · " + M.conviction + "% conviction";
    $("#meterHorizon").textContent = M.horizon || "";
    var f = clear($("#factors"));
    (M.signals || []).forEach(function (s) {
      var row = el("div", "factor"); var lab = el("div", "fl"); lab.append(el("b", null, s.name), el("small", null, s.why)); row.append(lab);
      var bar = el("div", "fbar"); var fill = el("span", s.score >= 0 ? "pos" : "neg"); fill.style.width = Math.round(Math.abs(s.score) * 50) + "%";
      if (s.score >= 0) fill.style.left = "50%"; else fill.style.right = "50%"; bar.append(fill); row.append(bar);
      row.append(el("div", "fv " + (s.score > 0 ? "up" : s.score < 0 ? "down" : ""), (s.score > 0 ? "+" : "") + s.score.toFixed(2)));
      f.append(row);
    });
    var t = M.track || {};
    $("#meterTrack").textContent = t.calls ? "Track record: right on " + t.hits + " of " + t.calls + " directional calls (" + t.rate + "%), scored on the next session's S&P close." : "Track record: builds up from today; each call is scored on the next session's S&P close.";
    $("#meterMini").onclick = function () { var b = document.querySelector('.nav button[data-page="lof"]'); if (b) b.click(); };
    $("#meterMini").onkeydown = function (e) { if (e.key === "Enter") this.onclick(); };
  }
  function renderFedMood() {
    var F = D.fed, box = clear($("#fedOdds"));
    if (F) {
      var big = F.hike >= F.cut ? F.hike : F.cut, word = F.hike >= F.cut ? "hike" : "cut";
      box.append(el("div", "big-num", big + "%"), el("p", null, F.text));
      box.append(el("p", "muted", "Rate before the meeting " + F.pre.toFixed(2) + "%, priced after it " + F.post.toFixed(2) + "% (" + (F.implied_bp >= 0 ? "+" : "") + F.implied_bp + " bp). Probability of a 25 bp " + word + "."));
    } else box.append(el("p", "muted", "Futures data not available in this run."));
    var S = D.sentiment, mb = clear($("#mood"));
    if (S) {
      mb.append(el("div", "big-num " + (S.score > 0.15 ? "up" : S.score < -0.15 ? "down" : ""), S.label.charAt(0).toUpperCase() + S.label.slice(1)));
      mb.append(el("p", null, S.positive + " positive, " + S.negative + " negative, " + S.neutral + " neutral headlines (score " + S.score.toFixed(2) + ")."));
      var ul = el("ul", "srcs"); (S.top || []).slice(0, 4).forEach(function (h) { var li = el("li"); li.append(el("span", h.score > 0 ? "up" : "down", (h.score > 0 ? "▲ " : "▼ ")), link(h.url, h.headline)); ul.append(li); }); mb.append(ul);
    }
  }

  // ------------------------------------------------------------------ chart modal
  function openChart(key) {
    if (!key || !D.history || !D.history[key]) return;
    S.chartKey = key; $("#chartModal").hidden = false; $("#chartTitle").textContent = D.history[key].name; drawChart();
  }
  function drawChart() {
    var h = D.history[S.chartKey]; var pts = h.points || [];
    var cut = new Date(D.marketDate); cut.setDate(cut.getDate() - S.range);
    pts = pts.filter(function (p) { return new Date(p[0]) >= cut; });
    $("#chartNote").textContent = pts.length < 2 ? "Not enough history yet; it builds up with every daily run." : pts.length + " daily closes, " + pts[0][0] + " to " + pts[pts.length - 1][0] + (h.unit === "yield" ? " (yield, %)" : "");
    if (typeof Chart === "undefined") return;
    var css = getComputedStyle(document.documentElement);
    var up = pts.length > 1 && pts[pts.length - 1][1] >= pts[0][1];
    if (chart) chart.destroy();
    chart = new Chart($("#chart"), {
      type: "line",
      data: { labels: pts.map(function (p) { return p[0]; }), datasets: [{ data: pts.map(function (p) { return p[1]; }), borderColor: up ? css.getPropertyValue("--up").trim() : css.getPropertyValue("--down").trim(), borderWidth: 1.8, pointRadius: 0, tension: 0.1, fill: false }] },
      options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } }, interaction: { mode: "index", intersect: false },
        scales: { x: { ticks: { color: css.getPropertyValue("--muted").trim(), maxTicksLimit: 7 }, grid: { color: css.getPropertyValue("--line").trim() } },
                  y: { ticks: { color: css.getPropertyValue("--muted").trim() }, grid: { color: css.getPropertyValue("--line").trim() } } } }
    });
  }
  $("#chartClose").addEventListener("click", function () { $("#chartModal").hidden = true; });
  $("#chartModal").addEventListener("click", function (e) { if (e.target.id === "chartModal") $("#chartModal").hidden = true; });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") $("#chartModal").hidden = true; });
  document.querySelectorAll("#rangeTabs button").forEach(function (b) { b.addEventListener("click", function () {
    document.querySelectorAll("#rangeTabs button").forEach(function (x) { x.classList.toggle("on", x === b); }); S.range = +b.dataset.r; drawChart(); }); });

  // ------------------------------------------------------------------ wiring
  function renderDay() { renderHero(); renderMarket(); renderForces("#forces"); renderExplained(); renderNews();
    $("#commentaryNote").textContent = (ov() && ov().date) || ""; }
  function renderAll() {
    renderTicker(); renderFresh(); renderChecks(); renderDay(); renderWeek(); renderSources(); renderMovers(); renderHeat(); renderSeven();
    renderDownloads(); renderTrump(); renderLof();
    renderTape(); renderInternals(); renderMacro(); renderLessons(); renderSteps(); renderUpdate(); renderMeter(); renderFedMood();
  }
  function bindTabs(sel, attr, fn) {
    document.querySelectorAll(sel + " button").forEach(function (b) { b.addEventListener("click", function () {
      document.querySelectorAll(sel + " button").forEach(function (x) { x.classList.toggle("on", x === b); }); fn(b.getAttribute(attr)); }); });
  }
  bindTabs(".nav", "data-page", function (p) {
    S.page = p; document.querySelectorAll(".page").forEach(function (x) { x.hidden = x.id !== "page-" + p; });
    try { localStorage.setItem("mb-page", p); } catch (e) { /* storage unavailable */ }
    window.scrollTo(0, 0);
  });
  bindTabs(".when", "data-when", function (w) { S.when = w; renderDay(); });
  bindTabs("#mktTabs", "data-g", function (g) { S.group = g; renderMarket(); });
  bindTabs("#moverTabs", "data-m", function (m) { S.mover = m; renderMovers(); });

  (window.__DASH ? Promise.resolve(window.__DASH) : fetch("data/dashboard.json?v=" + Date.now()).then(function (r) { return r.ok ? r.json() : null; })).then(function (data) {
    if (!data) { $("#fresh").textContent = "No data yet — run the daily job once."; return; }
    D = data;
    Object.keys(D.history || {}).forEach(function (k) { NAME_TO_KEY[D.history[k].name] = k; });
    if (D.site && D.site.title) { $("#siteTitle").textContent = D.site.title; document.title = D.site.title; }
    renderAll();
    var p = null; try { p = localStorage.getItem("mb-page"); } catch (e) { /* ignore */ }
    if (p) { var b = document.querySelector('.nav button[data-page="' + p + '"]'); if (b) b.click(); }
  }).catch(function () { $("#fresh").textContent = "Could not load data."; });
})();
