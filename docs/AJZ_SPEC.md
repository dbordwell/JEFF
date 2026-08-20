# AJZ Dashboard — Build Spec v1

**Status:** Phases 1–6 complete. Remaining: Windows CI build + first real install. · **Written:** 2026-08-19 · **Owner:** Dave · **User:** Jeff

This spec replaces `Spec Files/AJZ_Dashboard_v5.1 (1).xlsx` and the Copilot chat plans entirely.
Those are kept as *evidence and methodology source*, not as a starting point.

---

## 1. What we are building

A **single Excel file** on Jeff's Windows PC that is **already up to date every morning**, ranking
a universe of stocks by his own "AJZ Rule 3.0" methodology.

Jeff's job is to **open the file and read it**. That is the entire user manual.

### 1.1 Design principle — Tesler's Law

Complexity is conserved. Every piece of it that Jeff does not absorb, **we** absorb.

Explicit consequences, which override convenience at build time:

- No Power BI. He has never used it and would have to learn it. Cut.
- No Power Query. It is unmaintainable by him and it is what broke him the first time.
- No macro security prompts, no "enable content" banner, no add-ins.
- No terminal, no Python prompt, no scheduled-task console he can see.
- **No refresh button.** A button is a thing that can be forgotten, or clicked wrong, or fail
  silently. The file is simply correct when he opens it. "One-click refresh" becomes zero-click.
- If something breaks, the *file itself* tells him in plain English on the front sheet. He is never
  expected to read a log.

---

## 2. The user contract (this is the real deliverable)

What Jeff experiences, start to finish:

1. Dave sends him one installer. He double-clicks it once. It asks for nothing.
2. Forever after: he opens `AJZ Dashboard.xlsx` from his desktop.
3. The front sheet says either **"Data current as of <date/time>"** in green, or a plain-English
   problem statement in amber/red.
4. He reads his rankings.
5. Occasionally he opens the `Conviction` sheet and edits some 1–5 scores. That is the only place
   he is ever allowed to type. It is the only unlocked sheet.

Nothing else. No other action exists in the product.

---

## 3. Architecture

```
  Windows Task Scheduler (daily, user-level, hidden)
        |
        v
  ajz-refresh.exe   (single self-contained binary, no Python install)
        |
        +-- 1. read existing workbook -> lift Universe + Conviction (Jeff's hand edits)
        +-- 2. fetch market data from FMP
        +-- 3. compute AJZ Score, Value Score, Conviction, Matrix, Ranks, Alerts
        +-- 4. append today's row set to history store
        +-- 5. write a NEW workbook to temp, then atomically swap it in
        |
        v
  AJZ Dashboard.xlsx   (Jeff opens this)
```

### 3.1 Why local, not cloud

Considered and rejected: a cloud job (GitHub Actions etc.) that generates the file and drops it in
OneDrive. Rejected because **Conviction is Jeff's hand-entered data living inside the same file we
regenerate.** A cloud job cannot read his edits back without a two-way sync we would then have to
support. Running on his machine makes the read-modify-write trivially correct.

### 3.2 Why a compiled binary, not a script

Jeff must not install Python. `ajz-refresh.exe` is built with PyInstaller in CI on a Windows runner
(Dave is on macOS and cannot produce or test a Windows binary locally — this is a build-system
requirement, not a nice-to-have).

### 3.3 Install must require no access to Jeff's machine and no admin rights

Assume Dave cannot sit at the PC. The installer therefore:
- unpacks to `%LOCALAPPDATA%\AJZ\` (no admin needed),
- registers a **user-level** scheduled task via `schtasks` (no admin needed),
- writes the API key to `%LOCALAPPDATA%\AJZ\config.json` (never into the workbook),
- places `AJZ Dashboard.xlsx` on the Desktop,
- runs one refresh immediately so the first open already works,
- prints one line: "Done. Open AJZ Dashboard on your desktop." and exits.

---

## 4. Refresh cadence — two-speed

An important efficiency point that also solves the API budget:

| Data | Changes | Fetch |
|---|---|---|
| Price / market cap | daily | **daily** |
| Revenue growth, margins, ROIC | quarterly | **weekly** (Sunday) |
| Forward EPS estimates | slowly | **weekly** (Sunday) |

Only price genuinely moves day to day, and price only enters the model through Forward P/E. So the
daily job is a **single batched quote call**; the heavy fundamentals pull happens once a week.

Fundamentals are cached to `%LOCALAPPDATA%\AJZ\cache\` so a failed weekly pull degrades to
"yesterday's fundamentals + today's prices" rather than to nothing.

---

## 5. Data source — FMP (decided 2026-08-19)

> **Provenance note.** FMP was never chosen. It arrives pre-decided in a chat we don't have —
> chat 2 opens with Jeff asking *"How do I put in the API key?"*. There is **zero evaluation of it
> anywhere** in the source material: no requirements, no comparison, no cost discussion. Everything
> downstream simply inherited it. It is not disqualified, but it carries no evidence either.

### 5.1 The five inputs are not equally hard

Decomposing by difficulty rather than by vendor collapses the whole question:

| Input | Difficulty | Free, permanent source? |
|---|---|---|
| Revenue growth % | trivial | **SEC EDGAR** — official, free, no key |
| Gross margin % | trivial | **SEC EDGAR** |
| FCF margin % | trivial | **SEC EDGAR** |
| ROIC % | derivable | **SEC EDGAR** (needs computing) |
| Price / market cap / sector | trivial | many free sources |
| **Forward P/E** | **hard** | **none — licensed analyst consensus** |

Four of five inputs are commodity data published by the companies themselves and available from the
US government forever, free, with no key. **Forward P/E is the only field that requires a paid
vendor.** The entire vendor question reduces to "who sells us forward EPS consensus."

### 5.2 The open methodology question — Forward P/E

**This is the highest-leverage open question in the project and it is Jeff's to answer.**

Forward P/E is the denominator of AJZ Value Score, so it drives every ranking. Keeping it costs us:

- the only reason for a paid subscription, an API key on his machine, and a failable quota;
- a dependency on the *least* reliable input in the model (analyst opinion, constantly revised);
- a **silent correctness hazard**: two vendors report different forward P/E for the same stock
  (different fiscal-year conventions, analyst panels, GAAP vs adjusted EPS). Change vendors and his
  rankings shift with nothing visibly wrong.

If he would accept **trailing P/E** or **P/FCF** instead, the data problem collapses to
free-and-permanent and the vendor question disappears entirely.

Do not decide this for him. It is his methodology. But ask before paying for a subscription.

### 5.3 Vendor decision — FMP, confirmed on evidence

**Decided 2026-08-19 (Dave).** Continue with FMP. Cost is not a constraint for Jeff, which removes
the only real argument against it. Confirmed by re-derivation rather than inherited — FMP is a
reasonable choice for this workload; it simply had never been checked.

Practical consequences:
- **Use the `stable` API.** Every URL in Jeff's Copilot chat is on the deprecated `/api/v3/` path.
- **Do not design around bulk endpoints** — they are Ultimate-tier only. Per-ticker fundamentals on
  a ~50-name universe with the §4 two-speed cadence sits comfortably inside a cheap tier.
- **Forward P/E stays** (Jeff's methodology as written, §5.2). Cost was the only thing that made
  substituting trailing P/E attractive, and cost is not an issue.

Rejected alternatives, recorded so this is not re-litigated:
- **Pure SEC EDGAR** — free, official, permanent, and covers four of five inputs. Rejected because
  XBRL tag heterogeneity is a maintenance sinkhole. Paying to not maintain a normalizer is correct.
- **yfinance / Yahoo scraping** — free, no key, has `forwardPE` directly; easiest on paper.
  Rejected because it is unofficial and breaks periodically. In a walk-away handoff, "breaks
  periodically" means Dave gets a phone call.

**The adapter seam in §5.5 stays anyway.** Not for a bake-off — that question is closed — but
because the calculation core should never import a vendor, and because it makes the fetch layer
testable without network access. It costs nothing and it is how the units guard gets enforced in
one place.

### 5.4 Why this does not block the build

The data source was previously written as Phase 0 and that was wrong — it made a decision we cannot
yet make on evidence into a prerequisite for work that does not depend on it.

| Phase | Depends on vendor? |
|---|---|
| 1 — calculation core | No |
| 2 — fetch adapter | **Yes** (~200 lines) |
| 3 — workbook generator | No |
| 4 — conviction round-trip + history | No |
| 5 — packaging / install | No |

**Build against the internal contract in §5.5, not against a vendor.** The vendor lives behind one
adapter with one function signature. Swapping it is an afternoon.

Choose it with a **one-day bake-off**: two adapters, the same 10 tickers, compare the numbers
side by side and against a known-good reference. That is a decision made on evidence, at the point
where we have something to test with — not by reading marketing pages now.

### 5.5 The internal data contract (this is what we actually build against)

One record per ticker. **All percentages are whole numbers.** All fields explicitly nullable.

```
ticker            str
company           str
sector            str
market_cap        float   USD
price             float   USD
revenue_growth    float?  percent, whole number   e.g. 114.2 not 1.142
gross_margin      float?  percent, whole number   e.g. 75.0  not 0.75
fcf_margin        float?  percent, whole number
roic              float?  percent, whole number
pe_ratio          float?
pe_basis          enum    "forward" | "trailing"   <- never silently mixed
as_of             date
source            str     which adapter produced this row
```

`pe_basis` is mandatory and must surface in the workbook. A row computed on trailing P/E must be
visibly flagged, never quietly blended with forward-P/E rows.

### 5.6 UNITS — the trap that would have cost days

AJZ Score assumes percentages as **whole numbers** (Copilot's own NVDA example scores 382).
**Essentially every provider returns margins and growth as decimals** (`0.75`, not `75`).

Wire them in raw and every score comes out ~100x too small and every stock reads "Weak" — looking
exactly like a data-loading failure rather than a units bug.

**Rule: normalise at the adapter boundary.** Each adapter is responsible for emitting the §5.5
contract in whole-number percent. Nothing downstream ever sees a decimal ratio. Ship a unit test
asserting a known ticker's gross margin lands between 1 and 100, not between 0 and 1 — and run it
against **every** adapter, so a vendor swap cannot reintroduce the bug.

### 5.7 P/E fallback ladder

1. Forward P/E from consensus estimates -> `pe_basis = "forward"`. Preferred.
2. No estimate for that ticker -> trailing P/E, `pe_basis = "trailing"`, flagged in the workbook.
3. EPS <= 0 (loss-making) -> P/E is meaningless. AJZ Value Score blank, category `Not Rated`,
   excluded from ranking and from every average. **Never output 0** — 0 is what produced v5.1's
   "everything reads Weak" behaviour.

### 5.8 Refresh budget

Whatever the vendor, the §4 two-speed cadence holds: one batched price call daily, full
fundamentals weekly for ~50 tickers. That is a trivial load for any provider on any tier, so
**rate limits should not drive the vendor choice.** Estimates coverage and durability should.

---

## 6. Calculations

Jeff's methodology, preserved exactly as written in `Spec Files/AI.docx`:

```
AJZ Score       = (2 x RevenueGrowth%) + GrossMargin% + FCFMargin% + (0.5 x ROIC%)
AJZ Value Score = AJZ Score / Forward P/E
Conviction      = Predictability + Moat + Management + BalanceSheet + Tailwind   (each 1-5)
```

Bands (unchanged from his framework):

```
AJZ Value Score:  15+ Elite | 10-15 Excellent | 7-10 Strong | 5-7 Good | 3-5 Fair | <3 Weak
Conviction:       21-25 Very High | 16-20 High | 11-15 Medium | 5-10 Low
```

### 6.1 Opportunity Matrix — corrected

v5.1's formula sent Low-AJZ + Conviction 16-20 to **"Avoid"**, even though Jeff's own scale calls
16-20 "High". A stock at AJZ 6 / Conviction 20 was being told to Avoid when the framework says
Defensive Compounder. Corrected rule:

```
AJZ Value >= 7  AND  Conviction >= 21   ->  Core Holding
AJZ Value >= 7  AND  Conviction 16-20   ->  Aggressive Position
AJZ Value <  7  AND  Conviction >= 16   ->  Defensive Compounder
otherwise                               ->  Avoid
Forward P/E unavailable / EPS <= 0      ->  Not Rated   (excluded from all ranking + averages)
```

### 6.2 Bugs from v5.1 that must not be reproduced

These are all confirmed present in the delivered workbook. Listed so the rebuild is checked
against them:

1. **Averages divided by 499 forever.** Empty rows held formulas returning `0`, and `AVERAGE`
   skips blanks but counts zeros. Every headline number read ~0 permanently.
   *Fix: the generator writes only real rows. No pre-filled empty formula rows, ever.*
2. **Portfolio Quality Index was 25% fabricated** — `(0.2*80) + (0.1*90)` hardcoded.
   *Fix: see §6.3. No constant may stand in for an uncomputed input.*
3. **Top25_Leaderboard was static** — column A literally typed 1..25, no formulas.
   *Fix: generated, sorted, real.*
4. **Rank_Movers / AJZ_History / Portfolio were headers only.**
5. **Alert_Center's Upgrade Alert column had no formula** (it needs history, which did not exist).
6. **No conditional formatting anywhere** — the whole heat-map layer from chat 1 was described and
   never built.

### 6.3 Portfolio Quality Index

v5.1 hardcoded two of its four inputs. Two options, and **we take the honest one**: ship the index
with only the components we actually compute, reweighted to sum to 100%, and label it for what it
is. If Allocation / Risk Control / Alert Health are later computed for real, they get added then.

```
Portfolio Quality Index = (0.60 x normalised avg AJZ Value) + (0.40 x normalised avg Conviction)
```
computed over **rated rows only**. Never over blank rows.

### 6.4 Alerts

```
BUY      : AJZ Value > 7  AND Conviction > 20
WARNING  : AJZ Value < 5
EXIT     : AJZ Value < 3  AND Conviction < 15
UPGRADE  : rank improved by 5+ vs last week, OR entered Top 10, OR moved into Core Holding
DOWNGRADE: rank fell by 5+
```

UPGRADE/DOWNGRADE require history; see §8. They are computed by the generator, not by formulas.

---

## 7. The Conviction problem — the real blocker

**This is why "one-click refresh" was never reachable in the original design, and nobody named it.**

Four of five AJZ Score inputs come from an API. **Conviction does not.** It is five subjective human
judgements per stock. There is no endpoint for "Moat = 5."

At Jeff's stated 500-stock target that is **2,500 hand-entered judgement calls**, re-reviewed as
things change. The v5.1 `Conviction_Engine` sheet is the proof: 499 rows, columns B–F blank, with
only the SUM pre-filled. The machine that adds the numbers was built; the impossible part was left
as an empty grid.

### 7.1 Decision

**The universe is what Jeff will actually score. Start at ~40–50 names.**

His own Copilot chat concedes this: 25–50 stocks "captures 90% of the value." A 500-name universe
with no Conviction scores is strictly worse than a 50-name universe with real ones, because
unscored rows pollute every average and ranking.

### 7.2 Handling unscored stocks

A stock with no Conviction scores is **`Not Rated`** — shown, ranked on AJZ Value only, visibly
flagged as needing scoring, and **excluded from every average and from the Opportunity Matrix.**
It must never be silently treated as Conviction 0, which is what v5.1 did.

### 7.3 Conviction is sacred data

It is the only thing in the system Jeff cannot regenerate. Therefore:

- Every refresh **reads Conviction out of the current workbook before writing the new one**, keyed
  by ticker, and carries it forward.
- A timestamped copy of Conviction is written to `%LOCALAPPDATA%\AJZ\backups\` on **every** run,
  keeping the last 30. Cheap insurance against a bad write.
- If the workbook is open/locked when the job runs, the job **aborts without writing** and retries
  later. It never partially writes.
- Adding a ticker to the `Universe` sheet is how Jeff adds a stock. It appears next refresh as
  `Not Rated` until he scores it.

---

## 8. History

Excel formulas fundamentally cannot snapshot themselves — this is why v5.1's `AJZ_History` was
empty. History is written by the generator, not the workbook.

- Store: `%LOCALAPPDATA%\AJZ\history.sqlite` (or `history.parquet`). **Outside** the workbook, so a
  workbook rewrite can never destroy it.
- One row per ticker per **weekly** snapshot (daily is noise for a fundamentals model).
- Powers: rank change, UPGRADE/DOWNGRADE alerts, and the Movers sheet.
- The workbook surfaces a readable slice of it; it is not the system of record.

---

## 9. Workbook layout

Seven sheets, down from thirteen. Everything is a plain static value written by the generator —
**no live formulas, no cross-sheet references, nothing that can go `#REF!` in his hands.**

| # | Sheet | Contents | Editable |
|---|---|---|---|
| 1 | **Dashboard** | Status banner, as-of timestamp, Portfolio Quality Index, counts by category, alert counts | No |
| 2 | **Top Rankings** | Full universe sorted by AJZ Value: rank, ticker, company, sector, AJZ Score, AJZ Value, Conviction, Category, rank change | No |
| 3 | **Opportunity Matrix** | The four buckets laid out as the 2x2 he designed | No |
| 4 | **Alerts** | BUY / UPGRADE / WARNING / EXIT / DOWNGRADE, each with the ticker and the reason in words | No |
| 5 | **Movers** | Biggest weekly rank changes both directions | No |
| 6 | **Conviction** | Ticker, company, and the five 1–5 score columns | **YES — the only unlocked sheet** |
| 7 | **Universe** | Ticker list + Active flag + notes | **YES** |

Rules:
- Sheets 1–5 are protected (no password prompt; just not accidentally typeable).
- `Conviction` and `Universe` have **data validation**: scores restricted to 1–5, so a typo is
  refused at entry rather than silently corrupting a score.
- **Conditional formatting** implements the heat-map bands from chat 1 that were never built.
- Column widths, freeze panes, and number formats are set by the generator. It should look
  finished, because it is the product.

---

## 10. Failure behaviour

The front sheet is the entire error-reporting surface. In plain English, never a code:

| Situation | Dashboard banner |
|---|---|
| All good | 🟢 `Data current as of Tue 19 Aug 2026, 6:05 AM` |
| Refresh failed, data is stale | 🟠 `Could not reach the data provider this morning. Showing Monday's numbers.` |
| API key rejected | 🔴 `The data subscription needs attention — call Dave.` |
| Over quota | 🟠 `Daily data limit reached. Numbers are from <date>.` |
| Some tickers missing | 🟢 banner + a `Notes` line: `3 tickers had no data today: XYZ, ABC, DEF` |

**Stale-but-labelled always beats blank or wrong.** The file must never show a number without
showing how old it is.

Full technical logs go to `%LOCALAPPDATA%\AJZ\logs\` for Dave, and Jeff is never told they exist.

---

## 11. Security

`Spec Files/AJZ_Dashboard_v5.1 (1).xlsx` shipped an **FMP API key in plaintext** in `Settings!B1`,
readable without opening Excel. Copilot advised handing that file plus the key to an Upwork
freelancer.

- The original key has been rotated; the exposed one is dead.
- The new key lives in `%LOCALAPPDATA%\AJZ\config.json`, never in the workbook.
- Consequence: the workbook is now safe to email to anyone.

---

## 12. Build order

**Phases 1–3 do not touch the vendor at all.** Build order is deliberately arranged so the
majority of the work carries no dependency on FMP, and the calculation core never imports it.


- **Phase 1 — Calculation core.** Pure functions, no I/O: §5.5 contract in, AJZ Score / Value /
  Category / Alerts out. Unit-tested against Copilot's own worked examples (NVDA 382, TSM 25/25
  conviction) — including the units assertion from §5.6. **DONE** — `ajz/calc.py`, `ajz/models.py`,
  49 tests in `ajz/tests/test_calc.py`, each v5.1 bug pinned by a named regression test.
- **Phase 2 — Workbook generator. DONE** — `ajz/workbook.py`, `ajz/theme.py`, `ajz/status.py`,
  `ajz/fixtures.py`. 19 tests. Formatting, protection, validation, status banner. Driven off
  hand-written fixture data. **A believable, fully-formatted dashboard exists before a single API
  call is made** — which is also the fastest way to put something in front of Jeff.
- **Phase 3 — Conviction round-trip + history store. DONE** — `ajz/store.py`, `ajz/history.py`,
  `ajz/refresh.py`. 42 tests. Verify by hand-editing scores and confirming
  they survive a refresh. Highest-risk correctness path in the system.
- **Phase 4 — FMP adapter. DONE & LIVE-VERIFIED** — `ajz/fmp.py`, `ajz/config.py`, `ajz/probe.py`,
  `ajz/cli.py`, `ajz/seed.py`. 44 tests. Four live-data bugs caught and fixed; see §5.9.
  Build against §5.5. Validate field names and units against real
  responses for 3 tickers before trusting it. Add caching, retries, and the
  §5.7 fallback ladder.
- **Phase 5 — Packaging. DONE (unverified on real Windows)** — `ajz/install.py`, `ajz/cli.py`,
  `ajz/__main__.py`, `.github/workflows/build-windows.yml`, `docs/DEPLOY.md`. 21 tests.
  PyInstaller on a Windows CI runner, scheduled-task registration,
  first-run bootstrap.
- **Phase 6 — Seed the universe** (~40–50 tickers from his chat) and pre-fill the Conviction scores
  Copilot already worked out with him, so he opens a file that is *already useful* rather than a
  homework assignment.

Two notes on ordering:

**Phases 1–3 are the majority of the work and are entirely vendor-independent.** If the vendor
question stalls, the build does not.

**Phase 6 matters more than it looks.** His chats already contain scored examples — NVDA 24,
TSM 25, AVGO 23, BE 18, HOOD 18. Shipping those pre-filled is the difference between a working
dashboard and an empty grid, which is exactly what he received last time.

---

## 13. Non-goals

- Power BI, web dashboards, mobile, sharing, multi-user.
- Real-time or intraday anything. Daily is the promise.
- Brokerage integration or live portfolio positions. (v5.1 had a `Portfolio` sheet; it was empty.
  Deferred until the core is proven.)
- Backtesting the AJZ methodology. We are implementing his method, not validating it.
- Changing his formulas. The methodology is his IP. The one question we *ask* rather than decide is
  Forward vs trailing P/E (§5.2) — because it determines whether a paid subscription is needed at
  all.

---

## 14. Open questions

**Resolved 2026-08-19:** vendor = FMP (§5.3) · Forward P/E stays as Jeff wrote it (§5.2) ·
budget is not a constraint.

**For Jeff:**

1. **Confirm the ~40–50 starting tickers** for the universe.

**For Dave (delivery):**

3. **Does Jeff have OneDrive?** If yes, put the workbook in a synced folder and Dave gets a live
   copy for remote debugging without ever asking Jeff for anything.
4. **What time should it be fresh by?** Default 6:00 AM local — after US close the prior day and
   before he'd look.
5. **Can Dave get onto Jeff's PC even once?** Spec currently assumes **no** (user-level install, no
   admin rights, one double-click). If yes, several things get simpler.
6. ~~Which FMP tier?~~ **RESOLVED 2026-08-19: Jeff purchased Premium.** Estimates endpoint
   (Forward P/E) should be reachable; confirm with `uv run python -m ajz.probe`.

---

## 15. Live-data findings (probed + first end-to-end run, 2026-08-19)

All eight endpoints are reachable on Jeff's Premium tier. Four bugs surfaced only against
real data — every one of them would have shipped a plausible-looking but wrong dashboard,
which is the exact failure mode this project exists to eliminate.

**1. Analyst estimates are ordered furthest-future first, and ignore `sort=asc`.**
`limit=1` returned NVDA's **FY2031** estimate (epsAvg 20, 12 analysts) rather than FY2027
(epsAvg 9.00, 32 analysts). Forward P/E read **10.9 instead of 24.2** — NVDA would have
sat at rank 1 permanently with nothing appearing broken.
*Fix: fetch 12 rows, filter to dates after today, take the nearest. See `pick_forward_estimate`.*

**2. No endpoint reports FCF margin.** It is derived from
`cash-flow-statement.freeCashFlow / income-statement.revenue`.

**3. Cross-currency listings (foreign ADRs) break two different calculations.**
TSM trades in **USD** (412.09) but reports in **TWD**; `analyst-estimates` carries no
currency field at all.
- FCF margin via the TTM route mixed USD and TWD -> **0.88%** for a company whose real
  margin is **28.5%**. *Fix: annual statements are primary — both figures share
  `reportedCurrency`, so the ratio cancels currency.*
- Forward P/E divided USD price by TWD EPS -> P/E **0.77**, AJZ Value **222.66**, parking
  TSM at rank 1 ahead of everything. *Fix: when `reportedCurrency != profile.currency`,
  drop to trailing P/E (which FMP computes correctly: 27.24) and flag the row. Guessing an
  FX rate would be worse than an honestly-labelled trailing figure.*

**4. The heuristic units guard was unsound in both directions.**
It converted only values that "looked like" ratios (abs < 1.5).
- DDOG's **real** ROIC is 0.0023 -> 0.23%. The guard rejected it as unconverted and
  dropped the row. A true value, lost.
- A company growing 200% reports `2.0`. The heuristic would have recorded **2%**.
*Fix: conversion is now deterministic (always x100 — the probe established FMP's
convention). A convention change is caught by plausibility bounds instead, with gross
margin as the sentinel since it cannot exceed 100%.*

### 15.1 Threshold calibration — CONFIRMED, needs Jeff's input

Flagged as a fixture artefact in Phase 2; real data confirms it. Of 24 live names, only
**3 clear AJZ Value >= 7** (NVDA 11.6, CRM 9.4, META 9.2). Consequences:

- **"Aggressive Position" is nearly unreachable** — it needs AJZ Value >= 7 *and*
  conviction 16-20, but Jeff's quality names score 21+.
- Most good businesses land in **Defensive Compounder**.
- **WARNING fires below AJZ Value 5**, which is ~13 of 24 names.

An alert that fires on half the portfolio trains him to ignore alerts. His 7 / 5 / 3
cutoffs look calibrated for a different scale than live forward P/Es produce.

**This is his methodology, so it is his call, not ours.** Bring him the real numbers and
ask whether the cutoffs should move — a good first conversation, because it is about the
part he is expert in.

---

## 16. Tunable thresholds (added 2026-08-19)

A line is drawn deliberately down the middle of "adjustable":

**The FORMULA is fixed.** AJZ Score's weights (2x revenue growth, 0.5x ROIC) are AJZ
Rule 3.0 itself. Jeff wrote "Keep Unchanged" beside them, and altering them changes what a
score *means*, breaking comparability with every stored snapshot. Not exposed.

**The DECISION thresholds are Jeff's.** Where "high AJZ" starts, what fires a warning,
which conviction level counts as Core — those are investment judgements. Nine of them live
on an editable **Settings** sheet, read back on every refresh exactly like conviction.

Without this, every tuning request is a phone call to Dave, and a walk-away handoff that
needs Dave is not a walk-away handoff.

### 16.1 Why it was needed

Live data showed **Aggressive Position is unreachable**: it requires AJZ Value >= 7 AND
conviction 16-20, but only 3 of 24 names clear 7, and the only 16-20 conviction names
(BE 18, HOOD 18) score 1.4 and 4.7.

There is also a **contradiction inside Jeff's own framework**, visible only on
implementation:

| Source | "Aggressive Position" means |
|---|---|
| His prose | "High AJZ + **Medium** Conviction" -> Medium is **11-15** |
| His examples | BE 18, HOOD 18, MELI 19 -> that is **High**, 16-20 |

v5.1 followed the examples, and so do our defaults. `test_settings.py` proves the prose
reading is one setting away if that is what he meant.

### 16.2 Safety properties

- Defaults reproduce his original framework exactly — all 171 pre-existing tests passed
  unchanged after the refactor.
- `Thresholds` validates *combinations*, not just values: `core_conviction <
  aggressive_conviction` is rejected, and `aggressive_is_reachable` detects a zero-width
  band — the machine-checkable form of the very bug above.
- Bad input falls back to that field's default with a warning rather than stopping the
  refresh. A dashboard using one default beats no dashboard.
- A cleared cell restores that field's default.
- The read-back matches on a **hidden key column**, not the visible label, so re-wording a
  label can never orphan a setting he has changed.
- The Settings sheet shows current bucket counts, so an empty bucket is visible where he
  is making the change rather than something he has to go hunting for.
