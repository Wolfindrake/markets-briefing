// Runs inside your logged-in Investing.com watchlist tab (injected by background.js when you press Sync).
// Reads the Price tab and the Performance tab of the watchlist table, then puts the page back on the Price tab.
// It only reads what is on your screen; it never types, logs in or stores anything.
async function mbReadWatchlist() {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const visibleTable = (re) => [...document.querySelectorAll("table")].find(
    (t) => t.offsetParent !== null && t.tHead && re.test(t.tHead.textContent) && t.tBodies[0] && t.tBodies[0].rows.length);
  const waitFor = async (re, ms) => { for (let i = 0; i < ms / 250; i++) { const t = visibleTable(re); if (t) return t; await sleep(250); } return null; };
  const text = (c) => (c ? c.textContent.replace(/\s+/g, " ").trim() : "");

  if (/just a moment|attention required/i.test(document.title)) return { status: "check" };
  const price = await waitFor(/Chg\. %/, 15000);
  if (!price) {
    const loggedOut = !!document.querySelector('a[href*="login"], .login, [data-test*="login"], [class*="signIn"], [class*="sign-in"]') &&
      /sign in|log in|create.*account/i.test(document.body.innerText.slice(0, 20000));
    return { status: loggedOut ? "login" : "notable", title: document.title };
  }
  const head = (t) => [...t.tHead.rows[0].cells].map(text);
  const col = (h, name) => h.findIndex((x) => x.toLowerCase() === name.toLowerCase());

  const ph = head(price);
  const P = { last: col(ph, "Last"), open: col(ph, "Open"), prev: col(ph, "Prev."), chg: col(ph, "Chg."), pct: col(ph, "Chg. %"), sym: col(ph, "Symbol"), time: col(ph, "Time") };
  const rows = {};
  for (const r of price.tBodies[0].rows) {
    const a = r.querySelector("td.symbol a, td a[href^='/']");
    if (!a) continue;
    const c = r.cells, get = (i) => (i >= 0 && c[i] ? text(c[i]) : "");
    rows[r.id || a.getAttribute("href")] = {
      name: text(a), href: a.getAttribute("href"), symbol: get(P.sym), last: get(P.last), open: get(P.open), prev: get(P.prev),
      chg: get(P.chg), pct: get(P.pct), time: get(P.time) };
  }

  // Performance tab: Daily, 1 Week, 1 Month, YTD, 1 Year, 3 Years
  let perfOk = false;
  const tabPerf = document.querySelector("li#performance a, li#performance");
  if (tabPerf) {
    tabPerf.click();
    const perf = await waitFor(/3 Years/, 12000);
    if (perf) {
      const hh = head(perf), K = ["Daily", "1 Week", "1 Month", "YTD", "1 Year", "3 Years"].map((n) => [n, col(hh, n)]);
      for (const r of perf.tBodies[0].rows) {
        const a = r.querySelector("td.symbol a, td a[href^='/']");
        const row = rows[r.id] || (a && rows[a.getAttribute("href")]);
        if (!row) continue;
        row.perf = Object.fromEntries(K.map(([n, i]) => [n, i >= 0 && r.cells[i] ? text(r.cells[i]) : ""]));
      }
      perfOk = true;
    }
    const back = document.querySelector("li#overview a, li#overview");
    if (back) back.click();
  }
  return { status: "ok", rows: Object.values(rows), perfOk, url: location.href };
}

// Headlines from a publisher's markets page: headline, link and (when the page shows it) the date.
// Only headlines are taken, never article text: the site is public and links back to the publisher.
async function mbReadHeadlines(site) {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  if (/are you a robot|just a moment|access denied|attention required/i.test(document.title + " " + document.body.innerText.slice(0, 400)))
    return { status: "check" };
  const pick = {
    bloomberg: { sel: 'a[href*="/news/articles/"]', head: (a) => a.querySelector("h1,h2,h3,[class*='eadline']") || a,
      date: (u) => (u.match(/\/news\/articles\/(\d{4}-\d{2}-\d{2})\//) || [])[1] },
    ft: { sel: '.o-teaser__heading a[href*="/content/"], a[data-trackable="heading-link"][href*="/content/"]', head: (a) => a, date: () => null }
  }[site];
  if (!pick) return { status: "unknown" };
  for (let i = 0; i < 40 && !document.querySelector(pick.sel); i++) await sleep(250);
  const seen = new Set(), items = [];
  for (const a of document.querySelectorAll(pick.sel)) {
    const u = new URL(a.getAttribute("href"), location.href); u.search = ""; u.hash = "";
    const t = pick.head(a).textContent.replace(/\s+/g, " ").trim();
    if (seen.has(u.href) || t.length < 25 || t.length > 220) continue;
    seen.add(u.href);
    items.push({ headline: t, url: u.href, date: pick.date(u.href) || null });
    if (items.length >= 30) break;
  }
  return { status: items.length ? "ok" : "empty", items };
}
