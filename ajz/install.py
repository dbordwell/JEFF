"""One-time setup on Jeff's PC (spec §3.3).

    AJZ Setup.exe            install: copy, configure, put a shortcut on the Desktop
    ajz-refresh --uninstall  remove the shortcut (all data stays)
    ajz-refresh --status     report what is installed, for Dave

Design constraints, all downstream of "assume no access to the machine and no admin
rights":

* Installs to %LOCALAPPDATA%\\AJZ — a per-user directory, so no elevation prompt.
* Puts a single shortcut on the Desktop. Clicking it refreshes and then opens the
  dashboard, so there is one thing to click and no stale second copy to open by mistake.
* Runs one refresh immediately, so the first open already shows real numbers rather than
  an empty file that "will fill in later".

**There is deliberately no scheduled task.** An earlier design registered one with
`schtasks` to refresh at 06:00 unattended. It was removed, for reasons worth keeping
written down:

* `schtasks` defaults skip a run entirely if the machine is off, asleep, or on battery
  at the scheduled time, and never catch up. A home PC that is off overnight would have
  refreshed exactly never, while still looking installed.
* Nothing in an unattended run can tell Jeff it did not happen. The status banner is
  written *by* the refresh, so "I never ran" is the one state it cannot report.
* Whether Windows accepts our `schtasks` invocation could not be verified from macOS, on
  a machine we have no access to, by a user who cannot read a log.

Running on demand deletes all three problems rather than mitigating them, and it is what
was actually asked for: one-click refresh. The person clicking is present to see what
happened, which is worth more than any amount of self-reporting machinery.

The Windows-specific work is confined to `_shortcut_command` and `_run`, both unit-tested
with a fake runner — this file is written on macOS and cannot be executed here, so the
logic is kept testable even though the platform is not.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .config import WORKBOOK_NAME, app_dir, desktop_dir

log = logging.getLogger(__name__)

EXE_NAME = "ajz-refresh.exe"
SHORTCUT_NAME = "AJZ Dashboard.lnk"
LAUNCHER_NAME = "AJZ Dashboard.bat"


class InstallError(RuntimeError):
    """Setup could not complete. Message is written for Dave, not for Jeff."""


@dataclass(frozen=True)
class InstallReport:
    install_dir: Path
    exe_path: Path
    workbook_path: Path
    shortcut_path: Path
    shortcut_created: bool
    first_refresh_ok: bool

    def summary(self) -> str:
        lines = [
            "AJZ Dashboard installed.",
            f"  program   {self.exe_path}",
            f"  dashboard {self.workbook_path}",
            f"  desktop   {self.shortcut_path}"
            + ("" if self.shortcut_created else "   (COULD NOT BE CREATED — see log)"),
        ]
        if not self.first_refresh_ok:
            lines.append("  note      first refresh did not complete; see the log")
        return "\n".join(lines)

    @property
    def launcher_is_a_bat(self) -> bool:
        """True when the .lnk could not be made and a .bat stood in for it."""
        return self.shortcut_path.suffix.lower() == ".bat"


def is_windows() -> bool:
    return sys.platform == "win32"


def _ps_quote(value: object) -> str:
    """Quote a value for a PowerShell single-quoted string."""
    return "'" + str(value).replace("'", "''") + "'"


def _shortcut_command(shortcut_path: Path, target: Path, working_dir: Path) -> list[str]:
    """The PowerShell that writes a .lnk. Split out so it can be asserted on off-Windows.

    A .lnk is a binary OLE structure, so it is created through the WScript.Shell COM
    object rather than written by hand. PowerShell is used because it is present on every
    supported Windows and needs no extra dependency — pywin32 would mean shipping a much
    larger binary for this one call.
    """
    script = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(shortcut_path)}); "
        f"$s.TargetPath = {_ps_quote(target)}; "
        f"$s.WorkingDirectory = {_ps_quote(working_dir)}; "
        f"$s.IconLocation = {_ps_quote(target)}; "
        "$s.Description = 'Refresh and open the AJZ Dashboard'; "
        "$s.Save()"
    )
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]


def _run(command: list[str], runner=subprocess.run) -> tuple[int, str]:
    try:
        result = runner(command, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return 127, f"{command[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    output = (getattr(result, "stdout", "") or "") + (getattr(result, "stderr", "") or "")
    return result.returncode, output.strip()


def write_launcher_bat(target: Path, shortcut_dir: Path | None = None) -> Path | None:
    """Write a .bat that runs the program. The fallback when a .lnk cannot be made.

    A .lnk is a binary OLE structure, so creating one needs PowerShell and a COM object
    — and both can be unavailable: constrained language mode, an execution policy, or a
    locked-down machine will refuse `New-Object -ComObject`. On the first real install,
    something in that chain said no.

    A .bat is a text file. Writing one needs nothing but permission to create a file in
    the folder, so it works where the shortcut cannot. It looks slightly less polished
    and shows a console window, which this program shows anyway.

    Never leave him with no way to launch it — that is the whole point.
    """
    directory = shortcut_dir or desktop_dir()
    path = directory / LAUNCHER_NAME
    try:
        directory.mkdir(parents=True, exist_ok=True)
        # CRLF and cp437: .bat is parsed by cmd.exe, not by a modern text stack.
        path.write_text(
            "@echo off\r\n"
            "rem Opens the AJZ Dashboard with the latest numbers.\r\n"
            f'"{target}"\r\n',
            encoding="cp437",
            newline="",
        )
    except (OSError, UnicodeEncodeError) as exc:
        log.error("could not write the .bat launcher either: %s", exc)
        return None
    return path


def create_shortcut(
    target: Path,
    *,
    shortcut_dir: Path | None = None,
    working_dir: Path | None = None,
    runner=subprocess.run,
) -> tuple[Path, bool]:
    """Put something clickable on the Desktop. Returns (path, created).

    Tries a proper .lnk first and falls back to a .bat, so a machine that refuses COM
    still ends up with a working icon rather than an apology.
    """
    directory = shortcut_dir or desktop_dir()
    shortcut_path = directory / SHORTCUT_NAME
    if not is_windows():
        log.warning("not Windows — skipping shortcut creation (%s)", sys.platform)
        return shortcut_path, False

    directory.mkdir(parents=True, exist_ok=True)
    code, output = _run(
        _shortcut_command(shortcut_path, target, working_dir or target.parent),
        runner=runner,
    )
    if code == 0 and shortcut_path.exists():
        return shortcut_path, True

    # PowerShell can exit 0 having quietly created nothing, so existence is the test.
    log.error("could not create the desktop shortcut (exit %s): %s", code, output)
    fallback = write_launcher_bat(target, directory)
    if fallback is None:
        return shortcut_path, False
    log.warning("wrote %s instead of a shortcut", fallback)
    return fallback, True


def remove_shortcut(shortcut_dir: Path | None = None) -> bool:
    """Delete whatever we put on the Desktop — .lnk, .bat, or both. Data is untouched."""
    directory = shortcut_dir or desktop_dir()
    ok = True
    for name in (SHORTCUT_NAME, LAUNCHER_NAME):
        try:
            (directory / name).unlink(missing_ok=True)
        except OSError as exc:
            log.error("could not remove %s: %s", name, exc)
            ok = False
    return ok


def write_config(api_key: str, target_dir: Path | None = None) -> Path:
    """Write config.json with the API key.

    Never the workbook. v5.1 kept the key in `Settings!B1`, which made the spreadsheet
    itself a secret — and it was then emailed around and handed to freelancers. Keeping
    the key here means the dashboard is safe to share with anyone.
    """
    target = (target_dir or app_dir())
    target.mkdir(parents=True, exist_ok=True)
    path = target / "config.json"
    path.write_text(json.dumps({"fmp_api_key": api_key}, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)  # best-effort; a no-op on some Windows filesystems
    except OSError:
        pass
    return path


def find_bundled_key(bundle_dir: Path | None = None) -> str | None:
    """Look for a config.json shipped alongside the installer.

    This is how the install stays zero-question: the key is supplied when packaging, so
    Jeff double-clicks and is done. If it is absent, `install()` will say what is needed
    rather than prompting — a prompt is a thing that can be got wrong.

    Two locations are searched, in this order:

    1. Beside the .exe — where a config.json sent separately will sit. This is the one
       that matters when the binary is downloaded from a public release, because the key
       cannot be published alongside it.
    2. `sys._MEIPASS` — the temp folder a --onefile build unpacks into, which only holds
       a config.json that was baked in at build time.

    The order is the whole point. Under --onefile `_MEIPASS` is *always* set, so checking
    it first meant a config.json sitting next to the exe was never found, and setup died
    with "no API key" while the file was right there.
    """
    if bundle_dir is not None:
        bases = [Path(bundle_dir)]
    else:
        exe = Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0])
        bases = [exe.parent]
        unpacked = getattr(sys, "_MEIPASS", None)
        if unpacked:
            bases.append(Path(unpacked))

    for base in bases:
        candidate = base / "config.json"
        if not candidate.exists():
            continue
        try:
            key = str(json.loads(candidate.read_text(encoding="utf-8")).get("fmp_api_key") or "") or None
        except (json.JSONDecodeError, OSError):
            continue
        if key:
            return key
    return None


def install(
    api_key: str | None = None,
    *,
    install_dir: Path | None = None,
    workbook_path: Path | None = None,
    shortcut_dir: Path | None = None,
    source_exe: Path | None = None,
    runner=subprocess.run,
    refresh_now=None,
) -> InstallReport:
    """Perform the one-time setup. Idempotent: safe to run again over an existing install."""
    install_dir = install_dir or app_dir()
    install_dir.mkdir(parents=True, exist_ok=True)
    workbook_path = workbook_path or (install_dir / WORKBOOK_NAME)

    api_key = api_key or find_bundled_key()
    if not api_key:
        raise InstallError(
            "No API key available. Place a config.json containing "
            '{"fmp_api_key": "..."} next to the installer, or pass --key.'
        )
    write_config(api_key, install_dir)

    # Copy ourselves into place so the shortcut points at a stable path rather than
    # wherever the installer happened to be run from (often Downloads, which Jeff may
    # later empty).
    source = source_exe or Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0])
    exe_path = install_dir / EXE_NAME
    if source.exists() and source.resolve() != exe_path.resolve():
        try:
            shutil.copy2(source, exe_path)
        except (OSError, shutil.SameFileError) as exc:
            # Windows refuses to overwrite a running image, so re-running setup while a
            # refresh is in flight lands here. An existing copy is good enough to keep
            # going with; without one there is nothing to point a shortcut at.
            if not exe_path.exists():
                raise InstallError(
                    f"Could not copy the program into {install_dir}: {exc}"
                ) from exc
            log.warning("kept the existing program; could not overwrite it (%s)", exc)
    elif not exe_path.exists():
        exe_path = source

    shortcut_path, shortcut_created = create_shortcut(
        exe_path, shortcut_dir=shortcut_dir, working_dir=install_dir, runner=runner
    )

    first_refresh_ok = False
    if refresh_now is not None:
        try:
            refresh_now()
            first_refresh_ok = True
        except Exception:  # noqa: BLE001 - a failed first run must not fail the install
            log.exception("first refresh failed; the shortcut is still in place")

    return InstallReport(
        install_dir=install_dir,
        exe_path=exe_path,
        workbook_path=workbook_path,
        shortcut_path=shortcut_path,
        shortcut_created=shortcut_created,
        first_refresh_ok=first_refresh_ok,
    )


def uninstall(shortcut_dir: Path | None = None) -> bool:
    """Remove the Desktop shortcut. Leaves data — history, backups, and the workbook stay.

    Deleting Jeff's conviction scores because he asked to stop using the dashboard would
    be a wildly disproportionate response to that request.
    """
    return remove_shortcut(shortcut_dir)


def status(install_dir: Path | None = None, shortcut_dir: Path | None = None) -> dict[str, object]:
    """What is actually installed. For Dave when debugging remotely."""
    base = install_dir or app_dir()
    exe_path = base / EXE_NAME
    config_path = base / "config.json"
    desktop = shortcut_dir or desktop_dir()
    lnk = desktop / SHORTCUT_NAME
    bat = desktop / LAUNCHER_NAME

    return {
        # First line on purpose: when Jeff reports something odd, the first thing to
        # establish is which build he is running.
        "version": __version__,
        "platform": sys.platform,
        "install_dir": str(base),
        "install_dir_exists": base.exists(),
        "exe_present": exe_path.exists(),
        "config_present": config_path.exists(),
        "workbook_present": (base / WORKBOOK_NAME).exists(),
        "history_present": (base / "history.sqlite").exists(),
        "backup_count": len(list((base / "backups").glob("*.xlsx"))) if (base / "backups").exists() else 0,
        "desktop_dir": str(desktop),
        "shortcut_present": lnk.exists(),
        "bat_launcher_present": bat.exists(),
        "can_launch_from_desktop": lnk.exists() or bat.exists(),
    }
