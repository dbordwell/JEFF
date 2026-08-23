"""Reading Jeff's hand-entered data back out of the workbook (spec §7.3).

Conviction scores are the only thing in this system that cannot be regenerated. Four of
the five AJZ inputs come from an API; conviction is five human judgements per stock that
no endpoint can supply. Losing them means Jeff redoes work he may not remember.

So this module is written defensively and the invariant is absolute:

    NEVER write a workbook containing less conviction data than the one it replaces.

Every failure path here aborts rather than degrades. A refresh that does not happen is a
minor annoyance; a refresh that silently blanks his scores is unrecoverable.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from .models import Conviction

CONVICTION_SHEET = "Conviction"
UNIVERSE_SHEET = "Universe"
SETTINGS_SHEET = "Settings"
SETTINGS_KEY_COL = 4   # hidden column holding the field key
SETTINGS_VALUE_COL = 2

TICKER_COL = 1
FIRST_SCORE_COL = 3  # columns 3-7 are the five conviction components
UNIVERSE_ACTIVE_COL = 4
UNIVERSE_NOTES_COL = 5

BACKUPS_TO_KEEP = 30


class ConvictionReadError(RuntimeError):
    """Raised when existing conviction data cannot be read.

    Always fatal to a refresh. If we cannot prove what Jeff had, we must not overwrite it.
    """


@dataclass(frozen=True)
class UniverseEntry:
    ticker: str
    company: str | None = None
    sector: str | None = None
    active: bool = True
    notes: str | None = None


@dataclass(frozen=True)
class ReadResult:
    conviction: dict[str, Conviction]
    universe: list[UniverseEntry]
    warnings: tuple[str, ...] = ()
    settings: dict[str, object] = field(default_factory=dict)

    @property
    def scored_count(self) -> int:
        return sum(1 for c in self.conviction.values() if c.is_complete)


def _coerce_score(raw: object) -> tuple[int | None, str | None]:
    """Turn whatever is in a cell into a 1-5 int, or None plus a warning.

    Jeff may type "4", 4, 4.0, a stray space, or something else entirely. Data validation
    catches most of it at entry, but validation can be bypassed by pasting, so this
    never trusts the cell.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, None
    try:
        value = int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return None, f"ignored non-numeric score {raw!r}"
    if not 1 <= value <= 5:
        return None, f"ignored out-of-range score {raw!r}"
    return value, None


def read_existing(path: Path) -> ReadResult:
    """Read conviction scores and the universe out of an existing workbook.

    On first run the file does not exist yet, which is a legitimate empty result rather
    than an error. Any *other* failure raises, because a workbook that exists but cannot
    be read is exactly the case where overwriting would destroy data.
    """
    if not path.exists():
        return ReadResult(conviction={}, universe=[])

    try:
        wb = load_workbook(path, data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001 - any failure here must abort the refresh
        raise ConvictionReadError(
            f"Could not open the existing workbook at {path}: {exc}. "
            "Refusing to overwrite it."
        ) from exc

    warnings: list[str] = []
    try:
        conviction = _read_conviction_sheet(wb, warnings)
        universe = _read_universe_sheet(wb, warnings)
        settings = _read_settings_sheet(wb, warnings)
    except ConvictionReadError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ConvictionReadError(
            f"Could not read saved data from {path}: {exc}. Refusing to overwrite it."
        ) from exc
    finally:
        wb.close()

    return ReadResult(conviction=conviction, universe=universe,
                      warnings=tuple(warnings), settings=settings)


def _read_conviction_sheet(wb, warnings: list[str]) -> dict[str, Conviction]:
    if CONVICTION_SHEET not in wb.sheetnames:
        raise ConvictionReadError(
            f"The workbook has no '{CONVICTION_SHEET}' sheet. This is not a workbook "
            "this tool produced; refusing to overwrite it."
        )

    ws = wb[CONVICTION_SHEET]
    out: dict[str, Conviction] = {}

    for row in ws.iter_rows(min_row=2):
        if not row:
            continue
        raw_ticker = row[TICKER_COL - 1].value if len(row) >= TICKER_COL else None
        if raw_ticker is None or not str(raw_ticker).strip():
            continue
        ticker = str(raw_ticker).strip().upper()

        if ticker in out:
            warnings.append(f"{ticker}: duplicate row in Conviction sheet; kept the first")
            continue

        scores: list[int | None] = []
        for offset in range(len(Conviction.COMPONENTS)):
            index = FIRST_SCORE_COL - 1 + offset
            raw = row[index].value if len(row) > index else None
            value, warning = _coerce_score(raw)
            if warning:
                warnings.append(f"{ticker}: {warning}")
            scores.append(value)

        out[ticker] = Conviction(*scores)

    return out


def _read_universe_sheet(wb, warnings: list[str]) -> list[UniverseEntry]:
    if UNIVERSE_SHEET not in wb.sheetnames:
        warnings.append(f"No '{UNIVERSE_SHEET}' sheet found; universe left unchanged.")
        return []

    ws = wb[UNIVERSE_SHEET]
    seen: set[str] = set()
    out: list[UniverseEntry] = []

    for row in ws.iter_rows(min_row=2):
        if not row:
            continue
        raw_ticker = row[0].value if row else None
        if raw_ticker is None or not str(raw_ticker).strip():
            continue
        ticker = str(raw_ticker).strip().upper()
        if ticker in seen:
            warnings.append(f"{ticker}: duplicate row in Universe sheet; kept the first")
            continue
        seen.add(ticker)

        def cell(index: int):
            return row[index].value if len(row) > index else None

        active_raw = cell(UNIVERSE_ACTIVE_COL - 1)
        # Default to active: a blank Active cell should include the stock, not silently
        # drop it. Only an explicit "NO"/"FALSE"/0 removes one.
        active = str(active_raw).strip().upper() not in {"NO", "FALSE", "0", "N"} if active_raw is not None else True

        out.append(
            UniverseEntry(
                ticker=ticker,
                company=(str(cell(1)).strip() if cell(1) else None),
                sector=(str(cell(2)).strip() if cell(2) else None),
                active=active,
                notes=(str(cell(UNIVERSE_NOTES_COL - 1)).strip() if cell(UNIVERSE_NOTES_COL - 1) else None),
            )
        )

    return out


# --- Backups --------------------------------------------------------------------------


def backup_workbook(path: Path, backup_dir: Path, now: datetime) -> Path | None:
    """Copy the current workbook aside before it is replaced.

    Cheap insurance on the only irreplaceable data in the system. Runs on every refresh,
    not just risky ones, because the risky ones are the ones we did not predict.
    """
    if not path.exists():
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"{path.stem}-{stamp}.xlsx"
    shutil.copy2(path, target)
    _prune_backups(backup_dir)
    return target


def _prune_backups(backup_dir: Path, keep: int = BACKUPS_TO_KEEP) -> None:
    backups = sorted(backup_dir.glob("*.xlsx"), key=lambda p: p.name, reverse=True)
    for stale in backups[keep:]:
        stale.unlink(missing_ok=True)


# --- Safe write -----------------------------------------------------------------------


class WorkbookLockedError(RuntimeError):
    """The workbook is open in Excel. Retry later; never write around it."""


def atomic_save(wb, path: Path) -> None:
    """Write to a temp file in the same directory, then swap it in.

    Two failure modes this protects against:

    * A crash mid-write leaving a truncated workbook. The swap is atomic, so the file
      Jeff opens is always either the old one or the new one, never a partial one.
    * Excel holding the file open on Windows, which makes the replace fail with
      PermissionError. We abort and keep the good file rather than writing around it.

    The temp name carries the process id. A fixed name would be shared by two refreshes
    running at once, and they would interleave their writes into a single temp file that
    then gets atomically swapped into place — an atomic swap of a corrupt file. The
    lock in `lock.py` should stop that happening; this makes it harmless if it ever does.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")

    try:
        wb.save(temp)
    except PermissionError as exc:
        temp.unlink(missing_ok=True)
        raise WorkbookLockedError(
            f"Could not write to {temp}. Is the dashboard open in Excel?"
        ) from exc

    try:
        temp.replace(path)
    except PermissionError as exc:
        temp.unlink(missing_ok=True)
        raise WorkbookLockedError(
            f"Could not replace {path}. The dashboard is probably open in Excel; "
            "the previous version has been left untouched."
        ) from exc


def _read_settings_sheet(wb, warnings: list[str]) -> dict[str, object]:
    """Read Jeff's threshold edits (spec §6.5).

    Matches on the hidden key column rather than the visible label, so re-wording a
    label in a future version cannot silently orphan a setting he has changed.

    A missing sheet is NOT an error: workbooks written before Settings existed are still
    perfectly valid, and defaults are the right answer for them.
    """
    if SETTINGS_SHEET not in wb.sheetnames:
        return {}

    ws = wb[SETTINGS_SHEET]
    out: dict[str, object] = {}

    for row in ws.iter_rows(min_row=2):
        if len(row) < SETTINGS_KEY_COL:
            continue
        key = row[SETTINGS_KEY_COL - 1].value
        if key is None or not str(key).strip():
            continue
        value = row[SETTINGS_VALUE_COL - 1].value
        if value is None or (isinstance(value, str) and not value.strip()):
            continue  # cleared cell -> fall back to the default for that field
        out[str(key).strip()] = value

    return out
