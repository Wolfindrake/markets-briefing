/**
 * Markets Briefing: one-tap "Refresh" without exposing GitHub.
 * A free Cloudflare Worker holds the GitHub token; the site only calls this Worker.
 *
 *   POST /refresh   start the daily workflow now (refused if one ran in the last 10 minutes)
 *   GET  /status    state of the latest run: queued | in_progress | completed (+ conclusion, times)
 *
 * Secrets / variables (Cloudflare dashboard → Worker → Settings → Variables):
 *   GITHUB_TOKEN    fine-grained token, ONLY this repository, permission "Actions: Read and write"   (secret)
 *   REPO            Wolfindrake/markets-briefing
 *   WORKFLOW        daily.yml
 *   ALLOWED_ORIGIN  https://wolfindrake.github.io
 *   PASSCODE        optional; if set, the site asks for it once and remembers it on that device   (secret)
 */
const GH = "https://api.github.com";

function cors(env, extra = {}) {
  return { "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
           "Access-Control-Allow-Headers": "Content-Type, X-Passcode", "Content-Type": "application/json", ...extra };
}
function json(env, body, status = 200) { return new Response(JSON.stringify(body), { status, headers: cors(env) }); }
async function gh(env, path, init = {}) {
  return fetch(GH + path, { ...init, headers: { "Authorization": `Bearer ${env.GITHUB_TOKEN}`, "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "markets-briefing-refresh", ...(init.headers || {}) } });
}
async function latestRun(env) {
  const r = await gh(env, `/repos/${env.REPO}/actions/workflows/${env.WORKFLOW}/runs?per_page=1`);
  if (!r.ok) return null;
  const run = (await r.json()).workflow_runs?.[0];
  return run ? { status: run.status, conclusion: run.conclusion, created: run.created_at, updated: run.updated_at } : null;
}

export default {
  async fetch(req, env) {
    if (req.method === "OPTIONS") return new Response(null, { headers: cors(env) });
    const url = new URL(req.url);
    const origin = req.headers.get("Origin");
    if (env.ALLOWED_ORIGIN && origin && origin !== env.ALLOWED_ORIGIN) return json(env, { error: "origin not allowed" }, 403);

    if (url.pathname === "/status" && req.method === "GET") return json(env, { run: await latestRun(env) });

    if (url.pathname === "/refresh" && req.method === "POST") {
      if (env.PASSCODE && req.headers.get("X-Passcode") !== env.PASSCODE) return json(env, { error: "passcode" }, 401);
      const last = await latestRun(env);
      if (last && last.status !== "completed") return json(env, { started: false, reason: "already running", run: last });
      if (last && Date.now() - Date.parse(last.created) < 10 * 60 * 1000)
        return json(env, { started: false, reason: "refreshed less than 10 minutes ago", run: last });
      const r = await gh(env, `/repos/${env.REPO}/actions/workflows/${env.WORKFLOW}/dispatches`,
                         { method: "POST", body: JSON.stringify({ ref: "main" }), headers: { "Content-Type": "application/json" } });
      return r.status === 204 ? json(env, { started: true }) : json(env, { started: false, reason: `GitHub ${r.status}` }, 502);
    }
    return json(env, { error: "not found" }, 404);
  },
};
