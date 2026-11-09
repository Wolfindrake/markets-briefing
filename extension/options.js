const $ = (s) => document.querySelector(s);
const D = { token: "", repo: "Wolfindrake/markets-briefing", watchlistUrl: "https://www.investing.com/portfolio/", closeTab: true,
  news_bloomberg: true, news_ft: true };
const say = (t, ok) => { const m = $("#msg"); m.textContent = t; m.className = ok ? "ok" : "bad"; };

chrome.storage.local.get(Object.keys(D)).then((v) => {
  const c = { ...D, ...v };
  $("#token").value = c.token; $("#repo").value = c.repo; $("#url").value = c.watchlistUrl; $("#close").checked = !!c.closeTab;
  $("#nb").checked = c.news_bloomberg !== false; $("#nf").checked = c.news_ft !== false;
});

$("#save").onclick = async () => {
  const url = $("#url").value.trim() || D.watchlistUrl;
  if (!/^https:\/\/www\.investing\.com\//.test(url)) return say("The watchlist page must be an https://www.investing.com/ address.");
  const repo = $("#repo").value.trim() || D.repo;
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) return say("Repository should look like owner/name.");
  await chrome.storage.local.set({ token: $("#token").value.trim(), repo, watchlistUrl: url, closeTab: $("#close").checked,
    news_bloomberg: $("#nb").checked, news_ft: $("#nf").checked });
  say("Saved.", true);
};

$("#test").onclick = async () => {
  const token = $("#token").value.trim(), repo = $("#repo").value.trim() || D.repo;
  if (!token) return say("Paste the token first.");
  say("Checking…", true);
  try {
    const r = await fetch(`https://api.github.com/repos/${repo}`, { headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" } });
    const j = await r.json().catch(() => ({}));
    if (r.status === 401) return say("GitHub didn't accept this token.");
    if (!r.ok) return say(`Can't see ${repo} with this token (${r.status}). Check the repository access.`);
    if (j.permissions && j.permissions.push) say(`Connected to ${j.full_name}. The extension can save files there.`, true);
    else say(`The token can read ${j.full_name} but not write. Set Contents: Read and write.`);
  } catch (e) { say("Couldn't reach GitHub: " + e.message); }
};
