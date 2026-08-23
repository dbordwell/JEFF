# AJZ Dashboard

[![Build Windows installer](https://github.com/dbordwell/JEFF/actions/workflows/build-windows.yml/badge.svg)](https://github.com/dbordwell/JEFF/actions/workflows/build-windows.yml)

A private investing dashboard, one click from current. Double-click one icon: it fetches
the latest figures, rewrites the workbook, and opens it.

It scores a watchlist against a fixed framework:

```
AJZ Score       = (2 x Revenue Growth) + Gross Margin + FCF Margin + (0.5 x ROIC)
AJZ Value Score = AJZ Score / Forward P/E
Conviction      = five hand-entered 1-5 scores
```

Everything except Conviction is pulled from a market-data vendor. Conviction is a
judgement call and stays hand-entered — the refresh preserves it.

## For the person using it

1. Double-click **AJZ Setup.exe** once, to install.
2. Then click **AJZ Dashboard** on the desktop whenever you want the latest numbers.

That is the whole thing. If a third step ever appears here, something has gone wrong with
the design.

**There is deliberately no background job.** An earlier version registered a 6am
scheduled task. `schtasks` skips a run outright when the machine is off, asleep, or on
battery and never catches up, so a PC that sleeps overnight would have refreshed exactly
never while still looking installed — and an unattended run cannot report its own absence,
because the status banner is written by the refresh itself. Running on demand deletes that
whole class of silent failure: the person clicking is present to see what happened.
[`docs/DEPLOY.md`](docs/DEPLOY.md) has the full reasoning and the trade-off it costs.

## For whoever maintains it

The shipped artefact is a Windows binary and this is developed on macOS, where
cross-building a PyInstaller executable is not possible. So **CI is the build**: push to
`main` and download the `ajz-refresh-windows` artefact from the run.

The same workflow runs the suite on Windows *and* Ubuntu. That is not belt-and-braces —
file locking, path handling, and the frozen-binary entry point all behave differently on
Windows, and those are exactly what a macOS machine cannot exercise. Three real bugs have
already been caught this way that every local test missed.

```bash
uv sync --dev
uv run pytest              # 196 tests
uv run python -m ajz --status
```

Diagnostics on the target machine:

```
ajz-refresh --status       what is installed, what is missing
ajz-refresh --verbose      run a refresh with full logging
ajz-refresh --uninstall    remove the schedule, keep all data
```

## How it is put together

| Module | Job |
|---|---|
| `calc.py` | the scoring maths — pure functions, no I/O |
| `fmp.py` | market-data adapter, behind an interface so the vendor can be swapped |
| `workbook.py`, `theme.py` | renders the .xlsx (static values, no formulas) |
| `history.py`, `store.py` | snapshots in SQLite, survives workbook regeneration |
| `refresh.py` | the fetch-score-write job that ties it together |
| `cli.py` | the launcher: refresh, report in plain English, open the workbook |
| `install.py` | one-time setup and the desktop shortcut |
| `lock.py` | one refresh at a time, because double-clicking twice is normal |

Three design rules do most of the work:

- **A missing number is `None`, never `0`.** A zero silently scores as a real result and
  drags an average down; a `None` refuses to produce a score at all. The predecessor
  spreadsheet shipped several silently-wrong values this prevents.
- **Never overwrite what cannot be verified.** If the existing workbook cannot be read,
  the refresh exits and leaves the file alone. A refresh that does not happen is an
  annoyance; one that blanks hand-entered scores is unrecoverable.
- **Always end with the dashboard open**, even when the refresh failed. A stale workbook
  with an honest banner is useful; nothing happening at all reads as "broken".

The API key lives in `%LOCALAPPDATA%\AJZ\config.json`, never in the workbook, so the
workbook is safe to send to anyone.

## Documentation

| Doc | For |
|---|---|
| [`docs/AJZ_SPEC.md`](docs/AJZ_SPEC.md) | the full specification and its reasoning |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | build, bundle, hand over, debug remotely |
| [`docs/FOR_JEFF_thresholds.md`](docs/FOR_JEFF_thresholds.md) | the open calibration questions, in plain English |

## Known limits

Tested on Windows CI: the full suite, and that the frozen binary starts. **Not** tested
anywhere: that PowerShell creates the `.lnk` on a real machine, that the registry Desktop
lookup returns the right folder under OneDrive redirection, and that a workbook locked
open by Excel behaves as expected. The unit tests assert we build the right command, not
that Windows accepts it — so the first real install is still the real test.

The difference from the previous design is that these failures are now *visible*. Setup
and refresh both run in front of someone who is waiting, and anything that goes wrong
prints a sentence they can read out. Nothing here can fail silently for weeks.
