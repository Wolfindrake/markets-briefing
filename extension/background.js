// Markets Briefing – Investing.com sync (background service worker)
// Press Sync (in the popup, or Update on the site): it opens/reuses your Investing.com watchlist tab in THIS Chrome
// (where you are already logged in), reads the table, writes it as data/imports/investing_watchlist_<date>.csv in
// your GitHub repo, and the repo's workflow rebuilds the site with those numbers (about 3 minutes).
// Your Investing.com login never leaves Chrome. If you are logged out, it shows you the login page and stops.
importScripts("reader.js");

const DEFAULTS = { token: "", repo: "Wolfindrake/markets-briefing", branch: "main",
  watchlistUrl: "https://www.investing.com/portfolio/", closeTab: true, news_bloomberg: true, news_ft: true };

// Investing.com page path -> instrument key in config/instruments.yaml (the importer prefers the key over names).
const KEYS = {
  "/indices/volatility-s-p-500": "vix", "/indices/us-spx-500": "spx", "/indices/nasdaq-composite": "ixic", "/indices/us-30": "dji",
  "/indices/smallcap-2000": "rut", "/indices/eu-stoxx50": "sx5e", "/indices/germany-30": "dax", "/indices/france-40": "cac",
  "/indices/spain-35": "ibex", "/indices/msci-world": "msciw", "/indices/msci-europe": "mscieu", "/indices/msci-emerging-markets": "msciem",
  "/indices/japan-ni225": "n225", "/indices/kospi": "kospi", "/indices/csi300": "csi300", "/indices/s-p-cnx-nifty": "nifty",
  "/indices/brazil-50": "ibx50", "/indices/ice-bofaml-move": "move", "/etfs/ishares-7-10-year-treasury-bond": "ief",
  "/rates-bonds/u.s.-30-year-bond-yield": "us30", "/rates-bonds/u.s.-10-year-bond-yield": "us10", "/rates-bonds/u.s.-2-year-bond-yield": "us2",
  "/rates-bonds/germany-10-year-bond-yield": "de10", "/rates-bonds/france-10-year-bond-yield": "fr10",
  "/rates-bonds/france-cds-5-years-usd": "frcds", "/rates-bonds/japan-10-year-bond-yield": "jp10",
  "/currencies/eur-usd": "eurusd", "/currencies/usd-chf": "usdchf", "/currencies/usd-jpy": "usdjpy", "/currencies/xau-usd": "xau",
  "/currencies/xag-usd": "xag", "/commodities/brent-oil": "brent", "/commodities/crude-oil": "wti", "/crypto/bitcoin/btc-usd": "btc",
  "/commodities/ice-dutch-ttf-gas-c1-futures": "ttf", "/commodities/dutch-ttf-gas-c1-futures": "ttf"
};

// The briefing follows the US close: on a weekend, or a weekday before the 09:30 New York open, the snapshot
// belongs to the previous trading day.
function marketDate(now = new Date()) {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", year: "numeric", month: "2-digit",
    day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false, weekday: "short" }).formatToParts(now).map((x) => [x.type, x.value]));
  let d = new Date(Date.UTC(+p.year, +p.month - 1, +p.day));
  const mins = (+p.hour % 24) * 60 + +p.minute;
  if (d.getUTCDay() >= 1 && d.getUTCDay() <= 5 && mins < 570) d = new Date(d - 864e5);
  while (d.getUTCDay() === 0 || d.getUTCDay() === 6) d = new Date(d - 864e5);
  return d.toISOString().slice(0, 10);
}

function buildCsv(rows, takenIso) {
  const q = (v) => '"' + String(v ?? "").replace(/"/g, '""') + '"';
  const head = ["Key", "Name", "Symbol", "Last", "Open", "Prev.", "Chg.", "Chg. %", "Daily", "1 Week", "1 Month", "YTD", "1 Year", "3 Years", "Time", "Taken"];
  const lines = [head.map(q).join(",")];
  for (const r of rows) {
    const p = r.perf || {};
    lines.push([KEYS[r.href] || "", r.name, r.symbol, r.last, r.open, r.prev, r.chg, r.pct, p["Daily"], p["1 Week"], p["1 Month"], p["YTD"],
      p["1 Year"], p["3 Years"], r.time, takenIso].map(q).join(","));
  }
  return lines.join("\n") + "\n";
}

// ------------------------------------------------------------------ progress to the popup and the site
let running = false, lastStart = 0, siteTab = null;
function report(state, text, extra = {}) {
  const msg = { type: "progress", state, text, ...extra };
  chrome.storage.local.set({ last: { ...msg, at: new Date().toISOString() } });
  chrome.runtime.sendMessage(msg).catch(() => {});
  if (siteTab != null) chrome.tabs.sendMessage(siteTab, msg).catch(() => {});
}

function waitComplete(tabId, ms = 30000) {
  return new Promise((resolve) => {
    const done = () => { chrome.tabs.onUpdated.removeListener(fn); clearTimeout(t); resolve(); };
    const fn = (id, info) => { if (id === tabId && info.status === "complete") done(); };
    const t = setTimeout(done, ms);
    chrome.tabs.onUpdated.addListener(fn);
    chrome.tabs.get(tabId).then((tab) => { if (tab.status === "complete") done(); }).catch(done);
  });
}

async function focus(tab) {
  await chrome.tabs.update(tab.id, { active: true });
  await chrome.windows.update(tab.windowId, { focused: true });
}

// ------------------------------------------------------------------ GitHub (your own token, entered in Options)
const b64 = (s) => { const u = new TextEncoder().encode(s); let b = ""; u.forEach((c) => { b += String.fromCharCode(c); }); return btoa(b); };
async function gh(cfg, path, opts = {}) {
  const r = await fetch(`https://api.github.com/repos/${cfg.repo}/${path}`, { ...opts, headers: {
    Authorization: `Bearer ${cfg.token}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
    ...(opts.body ? { "Content-Type": "application/json" } : {}) } });
  let j = null; try { j = await r.json(); } catch (e) { /* empty body */ }
  return { status: r.status, ok: r.ok, json: j };
}
function ghFail(res, step) {
  if (res.status === 401) throw new Error("GitHub token not accepted. Paste a new one in the extension's Options.");
  if (res.status === 403 || res.status === 404) throw new Error("The GitHub token can't write to the repository. Give it Contents: Read and write on markets-briefing.");
  throw new Error(`GitHub (${step}) said ${res.status}: ${(res.json && res.json.message) || "unknown error"}`);
}
// All files in ONE commit, so the site rebuilds once.
async function commitFiles(cfg, files, message) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const ref = await gh(cfg, `git/ref/heads/${encodeURIComponent(cfg.branch)}`); if (!ref.ok) ghFail(ref, "branch");
    const parent = ref.json.object.sha;
    const pc = await gh(cfg, `git/commits/${parent}`); if (!pc.ok) ghFail(pc, "commit");
    const tree = await gh(cfg, "git/trees", { method: "POST", body: JSON.stringify({ base_tree: pc.json.tree.sha,
      tree: files.map((f) => ({ path: f.path, mode: "100644", type: "blob", content: f.content })) }) });
    if (!tree.ok) ghFail(tree, "files");
    const c = await gh(cfg, "git/commits", { method: "POST", body: JSON.stringify({ message, tree: tree.json.sha, parents: [parent] }) });
    if (!c.ok) ghFail(c, "commit");
    const up = await gh(cfg, `git/refs/heads/${encodeURIComponent(cfg.branch)}`, { method: "PATCH", body: JSON.stringify({ sha: c.json.sha }) });
    if (up.ok) return c.json.html_url;
    if (up.status !== 422) ghFail(up, "save");          // 422 = the site's own run saved meanwhile: retry on top of it
  }
  throw new Error("The repository kept changing while saving. Press Sync again in a minute.");
}

// ------------------------------------------------------------------ headlines (Bloomberg, Financial Times)
const NEWS = [
  { id: "bloomberg", source: "Bloomberg", url: "https://www.bloomberg.com/markets" },
  { id: "ft", source: "Financial Times", url: "https://www.ft.com/markets" }
];
async function readHeadlines(cfg, takenIso) {
  const items = [], notes = [];
  for (const s of NEWS) {
    if (cfg["news_" + s.id] === false) continue;
    let tab = null;
    try {
      tab = await chrome.tabs.create({ url: s.url, active: false });
      await waitComplete(tab.id);
      const [{ result: r } = {}] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: mbReadHeadlines, args: [s.id] });
      if (!r || r.status === "check") { notes.push(`${s.source} asked to confirm you're human (open it once yourself)`); continue; }
      if (r.status !== "ok") { notes.push(`no ${s.source} headlines found`); continue; }
      r.items.forEach((it) => items.push({ ...it, source: s.source, taken: takenIso }));
    } catch (e) {
      notes.push(`${s.source}: ${(e && e.message) || e}`);
    } finally {
      if (tab) chrome.tabs.remove(tab.id).catch(() => {});
    }
  }
  return { items, notes };
}

// ------------------------------------------------------------------ the sync
async function sync() {
  if (running) { report("busy", "A sync is already running."); return; }
  if (Date.now() - lastStart < 60000) { report("busy", "Synced less than a minute ago. Try again shortly."); return; }
  running = true; lastStart = Date.now();
  let tab = null, created = false;
  try {
    const cfg = { ...DEFAULTS, ...(await chrome.storage.local.get(Object.keys(DEFAULTS))) };
    if (!cfg.token) { report("setup", "One-time setup: open the extension's Options and paste your GitHub token."); chrome.runtime.openOptionsPage(); return; }

    report("reading", "Reading your Investing.com watchlist…");
    [tab] = await chrome.tabs.query({ url: "https://www.investing.com/portfolio/*" });
    if (!tab) { tab = await chrome.tabs.create({ url: cfg.watchlistUrl, active: false }); created = true; }
    else { await chrome.tabs.reload(tab.id); }
    await waitComplete(tab.id);

    const [{ result: res } = {}] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: mbReadWatchlist });
    if (!res || res.status === "check") { await focus(tab); created = false;
      report("login", "Investing.com wants to confirm you're human. Finish that in the tab, then press Sync again."); return; }
    if (res.status === "login") { await focus(tab); created = false;
      report("login", "You're logged out of Investing.com. Log in in the tab that just opened, then press Sync again."); return; }
    if (res.status !== "ok") { await focus(tab); created = false;
      report("error", "Couldn't find your watchlist table on that page. Open the watchlist once, then press Sync again."); return; }

    const good = res.rows.filter((r) => /\d/.test(r.last));
    if (good.length < 10) throw new Error(`Only ${good.length} prices found on the watchlist; nothing saved.`);
    const date = marketDate(), taken = new Date().toISOString();
    const files = [{ path: `data/imports/investing_watchlist_${date}.csv`, content: buildCsv(good, taken) }];
    if (created && cfg.closeTab) { chrome.tabs.remove(tab.id).catch(() => {}); tab = null; }

    report("reading", `Read ${good.length} instruments. Reading Bloomberg and FT headlines…`);
    const news = await readHeadlines(cfg, taken);
    if (news.items.length)
      files.push({ path: `data/imports/news_${date}.json`, content: JSON.stringify({ taken, items: news.items }, null, 1) + "\n" });

    report("saving", `Saving ${good.length} prices and ${news.items.length} headlines to the site…`);
    const url = await commitFiles(cfg, files, `Browser sync ${date}: ${good.length} Investing.com prices, ${news.items.length} headlines`);
    const extra = news.notes.length ? ` (${news.notes.join("; ")})` : "";
    report("done", `Saved ${good.length} Investing.com prices and ${news.items.length} Bloomberg/FT headlines for ${date}${extra}. The site rebuilds in about 3 minutes.`,
      { n: good.length, date, commit: url, unknown: good.filter((r) => !KEYS[r.href]).map((r) => r.name) });
  } catch (e) {
    report("error", String((e && e.message) || e));
  } finally {
    running = false;
    const cfg = await chrome.storage.local.get({ closeTab: true });
    if (tab && created && cfg.closeTab) chrome.tabs.remove(tab.id).catch(() => {});
  }
}

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (!msg || msg.type !== "sync") return;
  siteTab = sender.tab ? sender.tab.id : null;   // the site asked: send progress back to that tab
  sync();
});
