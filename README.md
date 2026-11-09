# Markets Briefing

A self-running global markets dashboard (Moneycontrol-style) with the same sections as the original
dashboard, plus a one-page briefing sheet (PDF and Excel) in the Financial Markets course format.

**Sections:** live ticker · Today/Yesterday in one look · Markets tables (equities, bonds & rates, FX/commodities/crypto)
with "what happened & why" · Why markets moved · Week ahead · Top movers · Market map · Last 7 sessions ·
Explained (big picture, how it connects, key numbers, what to watch, around the world, glossary) · News ·
Macro & Data · Reading the tape · Today's lessons · Trump Impact · Lords of Finance (scored on the real game rules) · Briefing sheet download and archive ·
Sources & verification. Tap any market for its chart.

Every weekday after the US close a GitHub Actions job:

1. downloads prices and yields: Yahoo Finance, US Treasury, Deutsche Bundesbank, Japan Ministry of Finance;
2. reads publishers' public news feeds (FT, Yahoo Finance, MarketWatch, CNBC): headline, summary, link;
3. writes the commentary: an automatic summary of the numbers, or, with an AI key, the full "why it moved",
   plain-English cards and Trump Impact, built only from those numbers and linked headlines;
4. rebuilds the website and the sheet, keeps its own price history, and publishes everything.

It does not depend on Claude or any chat session. Hosting is free.

---

## 1. Set it up (about 15 minutes, once)

1. **GitHub account** (free) → *New repository* → name `markets-briefing` → *Public* → *Create*.
2. **Upload the files**: on the new repo page click *uploading an existing file*, drag in the **contents** of this
   folder (on a Mac press `Cmd + Shift + .` in Finder to see the hidden `.github` folder and include it) → *Commit changes*.
3. **Settings → Pages** → Source: **GitHub Actions**.
4. **Settings → Actions → General** → Workflow permissions: **Read and write** → Save.
5. **For the full commentary** (recommended): get an API key at console.anthropic.com (pay-as-you-go, a few cents
   per day), then **Settings → Secrets and variables → Actions → New repository secret**: name `ANTHROPIC_API_KEY`.
   Without it the site still works and shows an automatic summary of the numbers.
6. **Actions tab → Daily refresh → Run workflow.** In 2–4 minutes the site is live at
   `https://<your-username>.github.io/markets-briefing/`.

It then runs by itself every weekday at 22:30 UTC. *Run workflow* refreshes on demand at any time.
On the live site, the **↻ Update** button (top right) links straight to Refresh now, Edit briefing.yaml, Upload CSV
and the run history. It finds your repository from the site address automatically.

Prefer Cloudflare? Keep the GitHub job, then in Cloudflare *Workers & Pages → Create → Pages → connect the repo*,
build command none, output directory `site`.

---

## 2. What you do (optional, about 5 minutes on class days)

Everything you type goes in **one file: `content/briefing.yaml`** (edit on GitHub, pencil icon, Commit).

1. **Calendar:** upcoming releases with their consensus. After a release, type the `actual`: the
   *Macro & Data* page then answers the professor's four questions (surprise, hawkish or dovish, what it means
   for the central bank, did markets react as the reaction map says) and it goes into the sheet's highlights.
2. **`sp500_view`:** your Lords of Finance call with its `session_date`. It is logged and scored automatically.
3. *(Optional)* your own words for the sheet, with `date:` set to the market date.

For the professor's exact numbers plus Brazil 50, MSCI World/Europe/EM, France 10Y and France CDS, also upload your
Investing.com watchlist CSV into `data/imports/`. If you do nothing, the site and sheet still update every day.

**The method built in (M4S4, top-down):** a 7-indicator macro dashboard, real rates, the business-cycle phase,
"markets trade the surprise", the market reaction map applied to each day ("Reading the tape"), market internals
(breadth, chips, dollar, VIX), today's lessons, and the briefing's five steps pre-filled on the *Briefing Sheet* page.

---

## 2b. Lords of Finance meter, Fed odds, alerts

- **Long / Short meter** (Lords of Finance page, and small on Markets): about ten signals (trend, momentum, overshoot,
  VIX, 10Y yield, dollar, breadth, news mood, data surprises, Fed odds, reaction-map pattern) scored -1 to +1 and
  combined. The needle goes to the extremes only when strong signals agree, and is pulled to the middle when they
  conflict or CPI / FOMC / payrolls is due before the next close. Every call is logged in `data/history/meter.csv` and
  scored on the next session, so the page shows its real hit rate. Rule-based, for the class game, not advice.
- **Fed meeting odds** (Macro & Data): from 30-day fed funds futures on Yahoo, the CME FedWatch arithmetic.
- **News mood**: finance word lists applied to the session's FT, Bloomberg, MarketWatch and CNBC headlines.
- **Alerts**: big moves (S&P ±2%, VIX +20%, 10Y ±10 bp), a Strong meter reading, a large Fed-odds swing or a
  hawkish/dovish data surprise open a GitHub issue in the repo, and GitHub emails it to you.

## 3. Where everything comes from

| What | Source |
|---|---|
| Indices (US, Europe, Japan, Korea, China, India), VIX, MOVE, IEF, FX, Brent, WTI, gold/silver futures, Bitcoin, Dutch gas | Yahoo Finance (free) |
| US 2Y, 10Y, 30Y | US Treasury daily par yield curve (official) |
| Germany 10Y | Deutsche Bundesbank, 10-year yield from the federal securities term structure (official) |
| Japan 10Y | Japan Ministry of Finance benchmark JGB yields (official) |
| Brazil 50, MSCI World/Europe/EM, France 10Y, France 5Y CDS | Your Investing.com CSV (no free source) |
| GDP, jobs, CPI, core PCE, Fed and ECB rates, wages | FRED, Federal Reserve Bank of St. Louis (free, no key) |
| S&P equal-weight (RSP), semiconductors (SOX), dollar index (DXY): dashboard only | Yahoo Finance |
| Fed funds futures (meeting odds) | Yahoo Finance (ZQ contracts) |
| News | Publishers' public RSS feeds (FT, Bloomberg, MarketWatch, CNBC): headline, summary and link only (`config/settings.yaml`) |

**Why no FT/Bloomberg logins.** The job never signs in with your FT, Bloomberg or Investing.com password.
Paid sites block automated logins (Bloomberg's robot check), their terms forbid automated access and republishing,
and a public site must not copy paywalled articles. Storing your passwords in a cloud job would also put the
accounts at risk. Headlines and links from public feeds give the same "what happened" signal; read the full
articles yourself with your subscription.

Checks applied automatically: Investing.com's stale "Prev." is recomputed as Last − Chg; yields and CDS changes
in basis points; values older than 4 days, missing rows and unusually large moves are listed under *data checks*.

---

## 4. Optional database (Supabase)

Create a free project at supabase.com, run `supabase/schema.sql` in its SQL editor, then add repository secrets
`SUPABASE_URL` and `SUPABASE_SERVICE_KEY` (Project settings → API → service_role). Each run then also stores prices
in the `prices` table, ready for future features (accounts, analytics). Free projects pause after about a week
without activity; the daily job keeps it active.

---

## 5. Good to know

- The repository is public: keep grades, IDs and anything private out of it.
- Yahoo Finance data is for personal and educational use; a commercial product would need a licensed data feed.
- GitHub may start scheduled runs late and pauses schedules after ~60 days without repository activity;
  *Run workflow* always works.
- Gold and silver use futures unless your CSV provides spot. Germany's 10Y is the Bundesbank curve estimate and can
  differ from the benchmark bond by a few bp.
- AI commentary is a draft from headlines: check it before quoting or handing in.

## 6. Run it on your own computer (optional)

```
python -m pip install -r requirements.txt
python -m pipeline.run              # full refresh
python -m pipeline.run --offline    # rebuild from saved files only
python tests/test_pipeline.py       # self-checks
cd site && python -m http.server 8000   # open http://localhost:8000
```

## 7. Layout

```
config/       instruments.yaml (the 35 markets), settings.yaml (feeds, AI, timezones)
content/      briefing.yaml (your words for the sheet, week ahead)
data/         imports/ (Investing.com CSVs), manual/, journal.csv, history/, snapshots.json
pipeline/     fetch, news, macro (FRED + surprises), method (tape, lessons, 5 steps), narrative, dashboard, sheet, journal, run.py
site/         the website (index.html, app.js, style.css) + generated data/ and downloads/
supabase/     optional database schema
docs/         course format and roadmap
```
