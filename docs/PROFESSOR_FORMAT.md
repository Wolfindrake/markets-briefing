# How the professor builds the Markets Briefing (analysis of his sheets, 21 Sep – 5 Nov 2026)

Source: his sheets posted on Blackboard (Market Briefings folder): 21, 22, 23, 24, 30 Sep; 6, 8, 14, 18, 28, 29 Oct;
3, 4, 5 Nov. Nine were read in full for this guide (21, 23, 24, 30 Sep; 6, 8, 14 Oct; 4, 5 Nov).

## Layout (one A4 page, printed)
1. **Header**: `MARKETS BRIEFING`, `Date dd/mm/yyyy`, `Data as of HH:MM CET (HH:MM New York)`. He takes the data around
   22:00–22:50 CET, i.e. during the US afternoon, from his Investing.com watchlist export.
2. **Table**: 35 instruments in three blocks (Equities, Fixed income, Others), columns Name, Symbol, Last, Open, Prev.,
   Chg., Chg. %, Daily, 1 Week, 1 Month, YTD, 1 Year, 3 Years. Yields and CDS in bp. Green/red colouring.
   Footer: `Source: Investing.com (bespoke Watchlist), file My Watchlist_Watchlist_MMDDYYYY.csv. Yields and CDS: changes in basis points (bp).`
3. **Market performance**: Equities / Fixed income / Others, about 4 dash bullets each.
4. **Market commentary: what happened since the last session**: `Overview` (one • bullet) then `Highlights` (7–10 • bullets).
5. **Week ahead**: Day | Region | Event | Consensus | Previous, 4–7 rows, plus an `Ahead` row for the next FOMC.

## How the style evolved
- **Sep (sessions 1–4)**: freer. Performance in sentences; commentary grouped by theme (Narrative, Central banks,
  Macro data (US), Rates/France/commodities); the week ahead long (8–10 rows) with consensus and previous filled.
- **From 6 Oct**: the fixed format above. Every performance bullet follows the same pattern; the overview is a single
  bullet; highlights are "Topic (date): fact"; the week ahead is shorter, often with consensus left blank.

## Sentence patterns he uses
- Equities lead: `US lower on inflation data: S&P 500 -1.1% to 7,720, -1.1% on the week, +12.8% YTD.`
  `Europe higher on the day and the week: CAC 40 +0.6% and +1.3%, DAX +0.2% and +0.8%.` `Asia weak / mixed: ...`
- Rates: `US 10Y 4.88%, -7 bp today and -16 bp on the week.` `Curve flattened on the CPI.` `France 5Y CDS 95 bp, +1 bp today ... quote dated 3 Nov.`
- Others: `Brent 94.76, -8.5% today and -17.8% on the week, the lowest in nearly two months, +56% YTD.`
- Context words: `highest since December 2022`, `worst day since March 2020`, `first 4% reading in three years`,
  `best session after a midterm election in 44 years`, `back above 4,000`, `in correction`.
- Overview: driver first, then reaction. `September CPI higher than expected; headline 3.7% and core 2.6%. December
  rate hike expected now, curve flattened. Equities fell, led by semiconductors.`
- Highlights: `US CPI (14 Oct): headline 3.7% YoY against 3.6% expected and 0.6% MoM; core 2.6% against 2.5%.`
  Topics he always covers: data vs expectations, central banks (votes, odds: "December hike ~83%"), earnings (EPS vs
  estimate, named stocks with %), sector moves, energy/geopolitics (Iran, Hormuz, OPEC+), France (debt, OAT-Bund,
  CDS), and anything unusual (records, worst/best since ...).
- Week ahead: one row per day/region, events joined with ". ", times in ET or GMT, the next FOMC as an `Ahead` row.

## How this repo reproduces it
- Table, colours, bp conventions, one page: `pipeline/sheet.py`.
- Performance bullets with "today and on the week" and YTD, regional lead words: `pipeline/narrative.py::sheet_text`.
- Overview from the reaction-map read of the day and the biggest data surprise; highlights from actual vs consensus
  (economic calendar) then the session's headlines (Bloomberg, FT).
- With an AI key the commentary is written in his house style (rules above are in the prompt).
- Week ahead from the economic calendar, grouped per day like his: `pipeline/calendar.py::sheet_rows`.
- Differences you should know: our numbers are the US **close** (refresh 23:30 Madrid), his are a ~22:00 CET intraday
  snapshot, so levels can differ slightly. Four instruments (MSCI Europe, MSCI EM, France 10Y, France CDS) need your
  Investing.com CSV.
