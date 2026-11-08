# Background: what the sheet must contain, and where this is going

## The course deliverable (Markets Briefing)
- One page, printed, handed in at the start of every session. Teamwork component of the grade.
- Written as notes for a managing director before a client meeting: report figures and how they compared
  with expectations; do not explain concepts.
- Three parts: market moves; what happened since the last session (US focus: growth, jobs, inflation,
  central banks, geopolitics); upcoming events.
- The guidelines' five steps: market picture → drivers → overshooting? → catalysts → S&P 500 view (connected
  to the Lords of Finance call). The handout should show **narrative, evidence, view**.

## The reference sheet layout (reproduced by `pipeline/sheet.py`)
- Header: MARKETS BRIEFING, date, "Data as of HH:MM CET (HH:MM New York)".
- Table of 35 instruments from an Investing.com watchlist export, columns Name, Symbol, Last, Open, Prev.,
  Chg., Chg. %, Daily, 1 Week, 1 Month, YTD, 1 Year, 3 Years. Yield and CDS changes in basis points.
- Market performance: short bullets under Equities, Fixed income, Others.
- Market commentary: Overview (2–3 lines) + Highlights bullets.
- Week ahead: Day, Region, Event, Consensus, Previous.

## Lords of Finance (real rules, used by the journal)
- Long or short the S&P 500 before 9:30 New York time on a class day; executed at the open;
  held until the close of the trading day before the next class. A missed round counts as wrong.
- Participation is graded, performance is not.

## Roadmap
1. **Done:** independent daily pipeline; dashboard with all the original sections in a Moneycontrol-style layout;
   official sources for US, German and Japanese yields; public news feeds; automatic or AI commentary; sheet download
   (PDF/XLSX); own price history and charts; Lords of Finance journal scored on the real rules.
2. **Next:** small admin page (upload CSV, edit commentary and log calls from the site); week-ahead calendar from an
   API with consensus figures; event reactions (how the S&P moves on CPI, payrolls, Fed days) from stored history.
3. **Learning layer:** tag each big move with its driver and track which drivers matter; hit rate of your calls by
   reason; store the professor's posted sheet next to yours and compare.
4. **Product (later):** licensed data feed, accounts (Supabase Auth), alerts, India angle (Nifty, Sensex, INR).

## Known data quirks
- Investing.com "Prev." is frequently stale: Prev = Last − Chg is used instead.
- The watchlist's change field occasionally re-bases late in the day; cross-check big rate moves against
  the US Treasury par curve.
- Brent on a watchlist can be a different contract month from the "front month" quoted in news.
- France CDS quotes are often a day old.
