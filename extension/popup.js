const $ = (s) => document.querySelector(s);
function show(m) {
  if (!m) return;
  const st = $("#st"); st.className = "st " + (m.state || ""); st.textContent = m.text || "";
  if (m.at) { const w = document.createElement("div"); w.className = "when"; w.textContent = new Date(m.at).toLocaleString(); st.append(w); }
  $("#sync").disabled = ["reading", "saving"].includes(m.state);
}
chrome.storage.local.get("last").then(({ last }) => show(last || { text: "Not synced yet." }));
chrome.runtime.onMessage.addListener((m) => { if (m && m.type === "progress") show({ ...m, at: new Date().toISOString() }); });
$("#sync").onclick = () => { show({ state: "reading", text: "Starting…" }); chrome.runtime.sendMessage({ type: "sync" }); };
$("#opts").onclick = (e) => { e.preventDefault(); chrome.runtime.openOptionsPage(); };
$("#site").onclick = (e) => { e.preventDefault(); chrome.tabs.create({ url: "https://wolfindrake.github.io/markets-briefing/" }); };
