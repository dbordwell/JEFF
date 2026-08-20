"""One-time setup on Jeff's PC (spec §3.3).

    AJZ Setup.exe            install: copy, configure, schedule, run once
    ajz-refresh --uninstall  remove the scheduled task
    ajz-refresh --status     report what is installed, for Dave

Design constraints, all downstream of "assume no access to the machine and no admin
rights":

* Installs to %LOCALAPPDATA%\\AJZ — a per-user directory, so no elevation prompt.
* Registers a USER-level scheduled task via schtasks — again no elevation.
* Runs one refresh immediately, so Jeff's first open already shows real numbers rather
  than an empty file that "will fill in tomorrow".
* Prints one line and exits. Every question it could ask has been answered in advance.

The Windows-specific work is confined to `_task_command` and `_run`, both of which are
unit-tested with a fake runner — this file is written on macOS and cannot be executed
here, so the logic is kept testable even though the platform is not.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import app_dir

log = logging.getLogger(__name__)

TASK_NAME = "AJZ Dashboard Refresh"
DEFAULT_TIME = "06:00"  # after the US close the prior day, before he'd look
EXE_NAME = "ajz-refresh.exe"


class InstallError(RuntimeError):
    """Setup could not complete. Message is written for Dave, not for Jeff."""


@dataclass(frozen=True)
class InstallReport:
    install_dir: Path
    exe_path: Path
    workbook_path: Path
    task_name: str
    scheduled_time: str
    task_registered: bool
    first_refresh_ok: bool

    def summary(self) -> str:
        lines = [
            "AJZ Dashboard installed.",
            f"  program   {self.exe_path}",
            f"  dashboard {self.workbook_path}",
            f"  schedule  daily at {self.scheduled_time}"
            + ("" if self.task_registered else "   (NOT registered — see log)"),
        ]
        if not self.first_refresh_ok:
            lines.append("  note      first refresh did not complete; see the log")
        return "\n".join(lines)


def is_windows() -> bool:
    return sys.platform == "win32"


def desktop_dir() -> Path:
    candidate = Path.home() / "Desktop"
    return candidate if candidate.exists() else Path.home()


def _task_command(exe_path: Path, when: str, task_name: str = TASK_NAME) -> list[str]:
    """The schtasks invocation. Split out so it can be asserted on without Windows.

    Deliberately omits /RU and /RL: defaulting to the current user at normal integrity
    is what keeps this installable without an admin prompt. Adding /RU SYSTEM would
    require elevation and would also run when Jeff is not logged in, which we do not
    want — the task must be able to write to his Desktop.
    """
    return [
        "schtasks", "/Create",
        "/TN", task_name,
        "/TR", f'"{exe_path}"',
        "/SC", "DAILY",
        "/ST", when,
        "/F",  # overwrite an existing task rather than failing on reinstall
    ]


def _delete_task_command(task_name: str = TASK_NAME) -> list[str]:
    return ["schtasks", "/Delete", "/TN", task_name, "/F"]


def _query_task_command(task_name: str = TASK_NAME) -> list[str]:
    return ["schtasks", "/Query", "/TN", task_name]


def _run(command: list[str], runner=subprocess.run) -> tuple[int, str]:
    try:
        result = runner(command, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return 127, f"{command[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    output = (getattr(result, "stdout", "") or "") + (getattr(result, "stderr", "") or "")
    return result.returncode, output.strip()


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
    when: str = DEFAULT_TIME,
    install_dir: Path | None = None,
    workbook_path: Path | None = None,
    source_exe: Path | None = None,
    runner=subprocess.run,
    refresh_now=None,
) -> InstallReport:
    """Perform the one-time setup. Idempotent: safe to run again over an existing install."""
    install_dir = install_dir or app_dir()
    install_dir.mkdir(parents=True, exist_ok=True)
    workbook_path = workbook_path or (desktop_dir() / "AJZ Dashboard.xlsx")

    api_key = api_key or find_bundled_key()
    if not api_key:
        raise InstallError(
            "No API key available. Place a config.json containing "
            '{"fmp_api_key": "..."} next to the installer, or pass --key.'
        )
    write_config(api_key, install_dir)

    # Copy ourselves into place so the scheduled task points at a stable path rather
    # than wherever the installer happened to be run from (often Downloads, which Jeff
    # may later empty).
    source = source_exe or Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0])
    exe_path = install_dir / EXE_NAME
    if source.exists() and source.resolve() != exe_path.resolve():
        shutil.copy2(source, exe_path)
    elif not exe_path.exists():
        exe_path = source

    task_registered = False
    if is_windows():
        code, output = _run(_task_command(exe_path, when), runner=runner)
        task_registered = code == 0
        if not task_registered:
            log.error("could not register the scheduled task: %s", output)
    else:
        log.warning("not Windows — skipping scheduled task registration (%s)", sys.platform)

    first_refresh_ok = False
    if refresh_now is not None:
        try:
            refresh_now()
            first_refresh_ok = True
        except Exception:  # noqa: BLE001 - a failed first run must not fail the install
            log.exception("first refresh failed; the schedule is still in place")

    return InstallReport(
        install_dir=install_dir,
        exe_path=exe_path,
        workbook_path=workbook_path,
        task_name=TASK_NAME,
        scheduled_time=when,
        task_registered=task_registered,
        first_refresh_ok=first_refresh_ok,
    )


def uninstall(runner=subprocess.run) -> bool:
    """Remove the scheduled task. Leaves data — history, backups, and the workbook stay.

    Deleting Jeff's conviction scores because he asked to stop the daily refresh would be
    a wildly disproportionate response to that request.
    """
    if not is_windows():
        log.warning("not Windows — nothing to unschedule")
        return False
    code, output = _run(_delete_task_command(), runner=runner)
    if code != 0:
        log.error("could not remove the scheduled task: %s", output)
    return code == 0


def status(runner=subprocess.run, install_dir: Path | None = None) -> dict[str, object]:
    """What is actually installed. For Dave when debugging remotely."""
    base = install_dir or app_dir()
    exe_path = base / EXE_NAME
    config_path = base / "config.json"

    scheduled = None
    if is_windows():
        code, _ = _run(_query_task_command(), runner=runner)
        scheduled = code == 0

    return {
        "platform": sys.platform,
        "install_dir": str(base),
        "install_dir_exists": base.exists(),
        "exe_present": exe_path.exists(),
        "config_present": config_path.exists(),
        "history_present": (base / "history.sqlite").exists(),
        "backup_count": len(list((base / "backups").glob("*.xlsx"))) if (base / "backups").exists() else 0,
        "task_scheduled": scheduled,
    }
