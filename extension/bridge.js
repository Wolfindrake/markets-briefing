// Runs on your Markets Briefing site only. Lets the site's Update button ask the extension to sync,
// and passes the progress messages back to the page.
document.documentElement.dataset.mbExt = "ready";
window.addEventListener("message", (e) => {
  if (e.source !== window || !e.data || e.data.source !== "mb-site") return;
  if (e.data.type === "sync") chrome.runtime.sendMessage({ type: "sync" }).catch(() => {});
});
chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "progress") window.postMessage({ source: "mb-ext", state: msg.state, text: msg.text, n: msg.n, date: msg.date }, location.origin);
});
