# Investing.com sync (Chrome extension)

Feeds your Investing.com watchlist (the professor's list) and the latest Bloomberg and FT market headlines into the
Markets Briefing site. Everything is read in your own logged-in Chrome.

- **Headlines only:** the extension takes the headline, the link and the date (Bloomberg shows it in the link; FT
  headlines are stamped with the sync time). It never copies article text, because the site is public. Each headline
  links to the article, which opens with your subscription.
- **Turning sources on or off:** use the checkboxes in Options.
- **One commit per sync:** the prices and headlines are saved together, so the site rebuilds once.

**How it works:** you press **Update** on the site, or **Sync now** in the extension.

1. The extension opens your watchlist in this Chrome, where you're already logged in.
2. It reads the Price tab and the Performance tab (1W, 1M, YTD, 1Y, 3Y).
3. It saves them as `data/imports/investing_watchlist_<date>.csv` in your repo.
4. The repo's workflow rebuilds the site with those numbers. This takes about 3 minutes, and the page reloads by itself.

- **Your login stays in Chrome.** The extension never sees or stores your Investing.com password. If you're logged out, it opens the Investing.com tab and asks you to log in, then press Sync again. The same happens if Investing.com shows a "confirm you're human" check: you do it, not the extension.
- **The date follows the US close.** On a weekend, or before 09:30 New York time, the snapshot is dated to the previous trading day.
- **The close wins over an intraday snapshot.** If you sync during US trading hours, the evening run replaces that snapshot with closing prices from the regular feeds.

## Install (once, about 3 minutes)

1. In Chrome, open `chrome://extensions` and turn on **Developer mode** (top right).
2. Click **Load unpacked** and pick this `extension` folder.
3. Pin the extension (puzzle icon → pin). The Options page opens on first sync. If it doesn't, right-click the icon → Options.
4. Make a GitHub token yourself:
   - github.com → Settings → Developer settings → **Fine-grained tokens** → Generate new token.
   - Repository access: **Only select repositories → markets-briefing**.
   - Repository permissions: **Contents → Read and write**. Nothing else.
   - Paste it into Options, **Save**, then **Test GitHub connection**.
5. Open the site and press **Update**, or click the extension icon → **Sync now**.

The token is stored only in this extension, on this computer. To revoke it, delete the token on GitHub.

## If something breaks

- **"Couldn't find your watchlist table":** open your watchlist on Investing.com once. If you keep several watchlists, paste the professor's watchlist address into Options.
- **"GitHub token not accepted":** the token expired. Make a new one and paste it in Options.
- **Investing.com changes its page layout:** the reader is in `reader.js`. It finds columns by their header names (Last, Chg. %, 1 Week…), so small changes don't break it.
