# One-tap Refresh (optional, free, ~10 minutes once)

Without this, the site's **Refresh** button reloads the latest published data and tells you when the next automatic
update is. With it, Refresh starts a brand-new data run (about 3 minutes) and shows progress, without ever opening GitHub.

1. **GitHub token** (only for this repo): github.com → Settings → Developer settings → Fine-grained tokens → Generate.
   Repository access: *Only select repositories* → `markets-briefing`. Permissions: **Actions: Read and write**. Copy it.
2. **Cloudflare** (free account): dash.cloudflare.com → Workers & Pages → Create → *Hello World* Worker → Deploy →
   *Edit code* → paste `refresh-worker.js` → Deploy.
3. Worker → Settings → Variables and secrets:
   `GITHUB_TOKEN` (secret, the token), `REPO` = `Wolfindrake/markets-briefing`, `WORKFLOW` = `daily.yml`,
   `ALLOWED_ORIGIN` = `https://wolfindrake.github.io`, optional `PASSCODE` (secret).
4. Copy the Worker URL (e.g. `https://mb-refresh.<you>.workers.dev`) into `config/settings.yaml` → `site.refresh_endpoint`.

Free tier: 100,000 requests a day, far more than needed. The token never reaches the browser.
