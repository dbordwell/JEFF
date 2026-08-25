"""Command-line entry point — what the Desktop shortcut runs.

    ajz-refresh              refresh, then open the dashboard   <- what Jeff clicks
    ajz-refresh --no-open    refresh without opening Excel
    ajz-refresh --dry-run    fetch and score, but write nothing
    ajz-refresh --out PATH   write somewhere other than the configured location

Jeff *does* see this. It is launched by a person who is watching, so it says what it is
doing in plain English and leaves the result on screen — that visibility is the whole
reason the design moved off an unattended scheduled task. Anything resembling jargon is
gated behind --verbose, which is Dave's mode.

The governing rule for the exit path: **always open the dashboard**, even when the
refresh failed. A stale workbook with an honest banner is useful; nothing happening at
all reads as "broken" and produces a phone call.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

from .config import Config, MissingApiKeyError, load
from .lock import AlreadyRunningError, single_instance
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

    Normally there is a console now. But the binary can still be launched in contexts
    with no usable stdout, where a bare print() raises, and losing the refresh because a
    progress line could not be printed would be absurd. Everything important also goes
    to the log file.
    """
    try:
        if sys.stdout is not None:
            print(text, flush=True)
    except (OSError, ValueError):
        pass


def open_workbook(path: Path) -> bool:
    """Open the dashboard in whatever handles .xlsx. Best-effort by design."""
    if not path.exists():
        return False
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606 - opening a file we just wrote
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except (OSError, AttributeError) as exc:
        log.warning("could not open the dashboard automatically: %s", exc)
        return False
    return True


def _hold_window_open(code: int) -> int:
    """Keep a double-clicked console window on screen when something went wrong.

    Windows destroys the console the instant the process exits, so a failure message
    appears for a fraction of a second and is gone — which is exactly how the first real
    install failed: "it flashes so quickly I think it says something about the key".
    An error nobody can read is the same as no error at all.

    Only on failure: a successful refresh opens Excel and should get out of the way.
    """
    if code == 0 or not sys.stdin or not sys.stdin.isatty():
        return code
    try:
        input("\nPress Enter to close this window...")
    except (EOFError, KeyboardInterrupt, OSError):
        pass
    return code


def main(argv: list[str] | None = None) -> int:
    return _hold_window_open(_main(argv))


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ajz-refresh", description=__doc__)
    parser.add_argument("--out", type=Path, help="workbook path override")
    parser.add_argument("--dry-run", action="store_true", help="fetch and score, write nothing")
    parser.add_argument("--no-open", action="store_true", help="do not open Excel afterwards")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--install", action="store_true", help="one-time setup on this PC")
    parser.add_argument("--uninstall", action="store_true", help="remove the desktop shortcut")
    parser.add_argument("--status", action="store_true", help="report what is installed")
    parser.add_argument("--key", help="FMP API key, for --install")
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
        emit("Desktop shortcut removed." if ok else "Could not remove the shortcut.")
        emit("Your dashboard, conviction scores and history were left in place.")
        return 0 if ok else 1

    # A double-click cannot pass a flag, so the no-argument path has to be whichever
    # action makes sense on this machine. Before setup that is "install"; after it,
    # "refresh". Requiring --install meant double-clicking the downloaded setup file
    # ran a refresh instead, which failed with "not set up yet" and closed instantly —
    # and could never succeed, because refresh only looks for the key in
    # %LOCALAPPDATA%, never beside the exe. Every instruction we wrote said
    # "double-click it", so that is what has to work.
    if args.install or not _is_set_up():
        return _do_install(args)

    return _do_refresh(args)


def _is_set_up() -> bool:
    """Has setup run on this machine? Judged by the key it installs."""
    from .config import ENV_VAR, app_dir

    if os.environ.get(ENV_VAR, "").strip():
        return True
    return (app_dir() / "config.json").exists()


def _do_refresh(args) -> int:
    try:
        config = load(workbook_path=args.out)
    except MissingApiKeyError as exc:
        _setup_logging(None, args.verbose)
        log.error("%s", exc)
        emit("\nThis copy is not set up yet. Run the setup program first.")
        return 2

    _setup_logging(config, args.verbose)
    log.info("refreshing %s (key %s)", config.workbook_path, config.redacted_key)

    from .fmp import make_fetcher

    emit("Getting the latest numbers. This usually takes a few seconds…")

    try:
        with single_instance():
            outcome = refresh(
                workbook_path=config.workbook_path,
                fetch=make_fetcher(config.api_key),
                history_path=config.history_path,
                backup_dir=config.backup_dir,
                seed_universe=SEED_UNIVERSE,
                seed_conviction=SEED_CONVICTION,
            )
    except AlreadyRunningError as exc:
        emit(f"\n{exc}")
        return 5
    except ConvictionReadError as exc:
        # The one failure we never write through: we could not prove what Jeff had.
        log.error("ABORTED, nothing written: %s", exc)
        emit("\nSomething looked wrong with the dashboard file, so it was left exactly "
             "as it was. Nothing has been lost. Please call Dave.")
        _maybe_open(config.workbook_path, args)
        return 3
    except WorkbookLockedError as exc:
        log.warning("workbook is open in Excel: %s", exc)
        emit("\nThe dashboard is already open in Excel, so it was not changed. "
             "Close it and click again to get the latest numbers.")
        return 4

    for warning in outcome.warnings:
        log.warning("%s", warning)

    ranked = outcome.ranked
    log.info("status=%s  scored=%d  ranked=%d  written=%s",
             outcome.status.state.value, len(outcome.stocks), len(ranked), outcome.written)

    emit(f"\n{outcome.status.headline}")
    emit(f"{len(ranked)} of {len(outcome.stocks)} stocks scored and ranked.")

    if args.verbose and ranked:
        emit(f"\n{'rank':>4}  {'ticker':<7}{'AJZ':>8}{'value':>8}  {'rating':<10}"
              f"{'conv':>5}  category")
        for position, s in enumerate(ranked[:25], start=1):
            emit(f"{position:>4}  {s.ticker:<7}{s.ajz_score:>8.1f}{s.ajz_value_score:>8.2f}"
                  f"  {s.ajz_rating:<10}{s.conviction_score or 0:>5}  {s.category.value}")

    unrated = [s for s in outcome.stocks if not s.is_rankable]
    if unrated:
        emit(f"\nNot scored ({len(unrated)}): {', '.join(s.ticker for s in unrated)}")
        for s in unrated:
            log.info("unrated %s: %s", s.ticker, '; '.join(s.notes) or 'no reason recorded')

    _maybe_open(config.workbook_path, args)
    return 0


def _maybe_open(workbook_path: Path, args) -> None:
    if args.no_open or args.dry_run:
        return
    emit("\nOpening your dashboard…")
    if not open_workbook(workbook_path):
        emit(f"Could not open it automatically. The file is at:\n  {workbook_path}")


def _do_install(args) -> int:
    """One-time setup. Everything Jeff would have been asked, we decided in advance."""
    from .install import InstallError, install

    _setup_logging(None, args.verbose)
    emit("Setting up the AJZ Dashboard…")
    try:
        report = install(
            api_key=args.key,
            workbook_path=args.out,
            # _main, not main: the inner refresh must not pause for an Enter keypress
            # in the middle of setup.
            refresh_now=lambda: _main(
                (["--out", str(args.out)] if args.out else []) + ["--no-open"]
            ),
        )
    except InstallError as exc:
        log.error("%s", exc)
        emit(f"\nSetup could not finish: {exc}")
        return 2

    emit(report.summary())
    if report.shortcut_created:
        emit("\nDone. Open 'AJZ Dashboard' on your desktop whenever you want the "
             "latest numbers — it refreshes and opens in one click.")
        if report.launcher_is_a_bat:
            # Worth one line: the icon is a plain white document rather than the
            # program's icon, which otherwise looks like the wrong thing got installed.
            emit("(This PC would not let us make a normal shortcut, so it is a small "
                 "batch file. It works exactly the same, it just looks plainer.)")
    else:
        emit(f"\nDone, but nothing could be placed on your desktop. You can still run it "
             f"from here:\n  {report.exe_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
