"""Command-line entry point — what the scheduled task runs each morning.

    ajz-refresh              refresh using the configured key and paths
    ajz-refresh --dry-run    fetch and score, but write nothing
    ajz-refresh --out PATH   write somewhere other than the configured location

Jeff never sees this. It runs hidden on a schedule; its whole job is to leave a correct
workbook on his desktop. All human-facing status lives in the workbook's banner, not
here — this output is for Dave and for the log file.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import Config, MissingApiKeyError, load
from .refresh import ConvictionReadError, WorkbookLockedError, refresh
from .seed import SEED_CONVICTION, SEED_UNIVERSE

log = logging.getLogger("ajz")


def _setup_logging(config: Config | None, verbose: bool) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if config is not None:
        config.log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(config.log_dir / "refresh.log", encoding="utf-8"))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=handlers,
    )


def emit(text: str) -> None:
    """Print if there is anywhere to print to.

    The shipped Windows binary is built --noconsole so no console window flashes on
    Jeff's screen each morning. With no console, stdout can be absent entirely and a
    bare print() raises. Everything important also goes to the log file.
    """
    try:
        if sys.stdout is not None:
            print(text)
    except (OSError, ValueError):
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ajz-refresh", description=__doc__)
    parser.add_argument("--out", type=Path, help="workbook path override")
    parser.add_argument("--dry-run", action="store_true", help="fetch and score, write nothing")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--install", action="store_true", help="one-time setup on this PC")
    parser.add_argument("--uninstall", action="store_true", help="remove the scheduled task")
    parser.add_argument("--status", action="store_true", help="report what is installed")
    parser.add_argument("--key", help="FMP API key, for --install")
    parser.add_argument("--at", default=None, help="daily refresh time, e.g. 06:00")
    args = parser.parse_args(argv)

    if args.status:
        from .install import status as install_status

        _setup_logging(None, args.verbose)
        for key, value in install_status().items():
            emit(f"  {key:22} {value}")
        return 0

    if args.uninstall:
        from .install import uninstall

        _setup_logging(None, args.verbose)
        ok = uninstall()
        emit("Scheduled refresh removed." if ok else "Could not remove the scheduled task.")
        emit("Your dashboard, conviction scores and history were left in place.")
        return 0 if ok else 1

    if args.install:
        return _do_install(args)

    try:
        config = load(workbook_path=args.out)
    except MissingApiKeyError as exc:
        _setup_logging(None, args.verbose)
        log.error("%s", exc)
        return 2

    _setup_logging(config, args.verbose)
    log.info("refreshing %s (key %s)", config.workbook_path, config.redacted_key)

    from .fmp import make_fetcher

    try:
        outcome = refresh(
            workbook_path=config.workbook_path,
            fetch=make_fetcher(config.api_key),
            history_path=config.history_path,
            backup_dir=config.backup_dir,
            seed_universe=SEED_UNIVERSE,
            seed_conviction=SEED_CONVICTION,
        )
    except ConvictionReadError as exc:
        # The one failure we never write through: we could not prove what Jeff had.
        log.error("ABORTED, nothing written: %s", exc)
        return 3
    except WorkbookLockedError as exc:
        log.warning("workbook is open in Excel; will retry on the next run: %s", exc)
        return 4

    for warning in outcome.warnings:
        log.warning("%s", warning)

    ranked = outcome.ranked
    log.info("status=%s  scored=%d  ranked=%d  written=%s",
             outcome.status.state.value, len(outcome.stocks), len(ranked), outcome.written)

    if ranked:
        emit(f"\n{'rank':>4}  {'ticker':<7}{'AJZ':>8}{'value':>8}  {'rating':<10}"
              f"{'conv':>5}  category")
        for position, s in enumerate(ranked[:25], start=1):
            emit(f"{position:>4}  {s.ticker:<7}{s.ajz_score:>8.1f}{s.ajz_value_score:>8.2f}"
                  f"  {s.ajz_rating:<10}{s.conviction_score or 0:>5}  {s.category.value}")

    unrated = [s for s in outcome.stocks if not s.is_rankable]
    if unrated:
        emit(f"\nnot rated ({len(unrated)}):")
        for s in unrated:
            emit(f"  {s.ticker:<7} {'; '.join(s.notes) or 'no reason recorded'}")

    return 0



def _do_install(args) -> int:
    """One-time setup. Everything Jeff would have been asked, we decided in advance."""
    from .install import DEFAULT_TIME, InstallError, install

    _setup_logging(None, args.verbose)
    try:
        report = install(
            api_key=args.key,
            when=args.at or DEFAULT_TIME,
            workbook_path=args.out,
            refresh_now=lambda: main(["--out", str(args.out)] if args.out else []),
        )
    except InstallError as exc:
        log.error("%s", exc)
        return 2

    emit(report.summary())
    emit("\nOpen 'AJZ Dashboard' on your desktop. It updates itself every morning.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
