# AJZ Dashboard

[![Build Windows installer](https://github.com/dbordwell/JEFF/actions/workflows/build-windows.yml/badge.svg)](https://github.com/dbordwell/JEFF/actions/workflows/build-windows.yml)

A private investing dashboard, one click from current. Double-click one icon: it fetches
the latest figures, rewrites the workbook, and opens it.

It scores a watchlist against a fixed framework:

```
AJZ Score       = (2 x Revenue Growth) + Gross Margin + FCF Margin + (0.5 x ROIC)
AJZ Value Score = AJZ Score / Forward P/E        <- the Primary Screen
Forward P/E     = AJZ Score / AJZ Value Score
```

Every input is pulled from a market-data vendor, so there is nothing to fill in by hand
before the numbers mean something.

The three formulas produce numbers. Three **category tables** turn each number into a
word — `Legendary`, `Bubble`, `Generational` — and those tables live on the Settings
sheet, where the owner edits them. The maths is fixed; the judgement is not.

## For the person using it

1. Double-click **AJZ Setup.exe** once, to install.
2. Then click **AJZ Dashboard** on the desktop whenever you want the latest numbers.

That is the whole thing. If a third step ever appears here, something has gone wrong with
the design.

Two sheets are yours to type in:

| Sheet | What you change |
|---|---|
| **Universe** | which stocks are tracked; set Active to NO to park one |
| **Settings** | the movement alert percentages, and all three category tables |

On the Settings sheet each category is one row: a name you choose and the number it
starts at. The `Range` column beside it recalculates as you type, so moving one number
visibly reshapes the band above it before you refresh. Blank rows at the foot of each
table are spare — type into one to add a category, clear a row's two cells to remove one,
and it sorts into place by its number. Clear a whole table to get the shipped one back.

**There is deliberately no background job.** A 6am scheduled task was tried and removed:
it failed silently whenever the PC was off, and an unattended run cannot report its own
absence. Reasoning in [spec §3.3a](docs/AJZ_SPEC.md).

## For whoever maintains it

The shipped artefact is a Windows binary and this is developed on macOS, where
cross-building a PyInstaller executable is not possible. So **CI is the build**: push to
`main` and download the `ajz-refresh-windows` artefact from the run.

The same workflow runs the suite on Windows *and* Ubuntu, then installs the built exe on
a real Windows runner by the same gesture Jeff uses — double-click, no flags — and
resolves the resulting `.lnk` back through COM to confirm where it points. That is not
belt-and-braces: file locking, path handling, the registry Desktop lookup and the frozen
`_MEIPASS` entry point all behave differently on Windows, and none of them can be
exercised from a Mac. Several real bugs have been caught this way that every local test
missed, including one where the job stayed green while the real first install failed.

```bash
uv sync --dev
uv run pytest              # 268 tests
uv run python -m ajz --status
```

Diagnostics on the target machine:

```
ajz-refresh --status       version, what is installed, what is missing
ajz-refresh --verbose      run a refresh with full logging
ajz-refresh --dry-run      fetch and score, write nothing
ajz-refresh --uninstall    remove the desktop shortcut, keep all data
```

`--status` reports the version first, and the version is also printed at the foot of the
Dashboard sheet — so "which build are you on?" is answerable from the file itself.

## How it is put together

| Module | Job |
|---|---|
| `calc.py` | the scoring maths — pure functions, no I/O |
| `bands.py` | the category tables: one floor per band, ranges derived |
| `settings.py` | what the owner may change, and what is off limits |
| `fmp.py` | market-data adapter, behind an interface so the vendor can be swapped |
| `workbook.py`, `theme.py` | renders the .xlsx |
| `history.py` | snapshots in SQLite, survive workbook regeneration |
| `store.py` | reads the owner's edits back out before the file is rewritten |
| `refresh.py` | the fetch-score-write job that ties it together |
| `cli.py` | the launcher: refresh, report in plain English, open the workbook |
| `install.py` | one-time setup and the desktop shortcut |
| `lock.py` | one refresh at a time, because double-clicking twice is normal |

Four design rules do most of the work:

- **A missing number is `None`, never `0`.** A zero silently scores as a real result and
  drags an average down; a `None` refuses to produce a score at all. The predecessor
  spreadsheet shipped several silently-wrong values this prevents.
- **Never overwrite what cannot be verified.** If the existing workbook cannot be read,
  the refresh exits and leaves the file alone. A refresh that does not happen is an
  annoyance; one that blanks hand-entered work is unrecoverable.
- **A bad category cannot be expressed.** Bands store one floor each and the ranges are
  derived, so there is no way to type a gap that would leave a stock uncategorised.
- **Always end with the dashboard open**, even when the refresh failed. A stale workbook
  with an honest banner is useful; nothing happening at all reads as "broken".

Every number is written as a static value. The single exception is the `Range` column on
the Settings sheet, which is a live formula so an edit shows its effect immediately —
nothing reads it back, and a test enforces that no other formula exists anywhere.

The API key lives in `%LOCALAPPDATA%\AJZ\config.json`, never in the workbook, so the
workbook is safe to send to anyone.

## Documentation

| Doc | For |
|---|---|
| [`docs/AJZ_SPEC.md`](docs/AJZ_SPEC.md) | the full specification and its reasoning |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | build, bundle, hand over, debug remotely |
| [`docs/FOR_JEFF.md`](docs/FOR_JEFF.md) | what changed in v2.0 and how to retune it, in plain English |

## Known limits

- **The AJZ Score categories are top-heavy.** On the seeded 50-name universe, 19 land in
  `Legendary` and `Weak to Dead` is empty. Widening from 24 to 50 improved it — the lower
  bands now hold real names — but the top band still takes nearly two in five. The numbers
  are the owner's, shipped verbatim; the Settings sheet shows a live count beside each
  category so the imbalance is visible in the file rather than described in an email.
- **Three ADRs fall back to trailing P/E.** TSM, ASML and NVO have no forward estimate in
  the vendor's analyst coverage, so their Forward P/E column is a trailing figure. Each
  says so in its Notes cell rather than blending in silently.
- **A Windows-locked workbook is still unverified.** Setup and shortcut creation are
  exercised for real in CI; a workbook held open by Excel during a refresh is not. It
  fails visibly by design — the refresh aborts and says so — but nothing has yet proved
  that on a real machine.
- **History samples irregularly.** With no scheduled job, snapshots happen only when
  someone clicks, so "since last refresh" is not "since last week".
