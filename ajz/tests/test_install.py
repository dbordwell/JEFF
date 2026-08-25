"""Tests for the one-time setup (spec §3.3).

This code cannot be executed on the machine it was written on — it targets Windows and
was authored on macOS. So the platform-specific work is confined to command *builders*
and a single injectable `runner`, and everything below asserts on the commands that
would be issued rather than on their effects.

That is a real limitation and worth naming: these tests prove we construct the right
PowerShell invocation, not that Windows accepts it. A smoke run on a Windows CI runner is
the check that closes that gap.
"""

from __future__ import annotations

import json
import sys

import pytest

from ajz.install import (
    EXE_NAME,
    SHORTCUT_NAME,
    InstallError,
    _run,
    _shortcut_command,
    create_shortcut,
    find_bundled_key,
    install,
    status,
    uninstall,
    write_config,
)


class FakeRunner:
    """Stands in for subprocess.run, recording what would have been executed."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.commands: list[list[str]] = []

    def __call__(self, command, capture_output=None, text=None, timeout=None):
        self.commands.append(command)
        return self


# --- There is deliberately no scheduled task -------------------------------------------


def test_setup_registers_no_scheduled_task_at_all(tmp_path, monkeypatch):
    """The load-bearing absence, asserted so it cannot creep back in unnoticed.

    A 06:00 schtasks job was the original design. It was removed because schtasks skips
    a run outright when the machine is off, asleep, or on battery and never catches up,
    because an unattended run cannot tell Jeff it did not happen, and because whether
    Windows accepts the invocation could not be verified from macOS. On-demand deletes
    all three problems instead of mitigating them.

    Asserted on what setup *executes* rather than on the source text, since the module
    docstring discusses schtasks at length precisely so this decision stays explained.
    """
    monkeypatch.setattr("ajz.install.is_windows", lambda: True)
    runner = FakeRunner()
    install(api_key="k", install_dir=tmp_path / "app", shortcut_dir=tmp_path / "Desktop",
            source_exe=tmp_path / "x.exe", runner=runner)

    issued = [" ".join(str(part) for part in command) for command in runner.commands]
    assert not any("schtasks" in command for command in issued)
    assert any("CreateShortcut" in command for command in issued)


# --- The shortcut command ---------------------------------------------------------------


def test_shortcut_command_targets_the_installed_exe(tmp_path):
    shortcut = tmp_path / SHORTCUT_NAME
    exe = tmp_path / "app" / EXE_NAME
    command = _shortcut_command(shortcut, exe, exe.parent)

    assert command[0] == "powershell"
    assert "-NoProfile" in command and "-NonInteractive" in command
    script = command[-1]
    assert "WScript.Shell" in script and "CreateShortcut" in script
    assert str(exe) in script
    assert str(shortcut) in script
    assert script.rstrip().endswith("$s.Save()")


def test_shortcut_command_escapes_a_quote_in_the_path(tmp_path):
    """A single quote in a Windows username would otherwise break out of the string.

    'C:\\Users\\O'Brien\\Desktop' is a legal path, and unescaped it would terminate the
    PowerShell literal early and turn the rest of the path into stray commands.
    """
    shortcut = tmp_path / "O'Brien" / SHORTCUT_NAME
    command = _shortcut_command(shortcut, tmp_path / EXE_NAME, tmp_path)
    assert "O''Brien" in command[-1]


def test_shortcut_is_not_attempted_off_windows(tmp_path):
    """Nothing to create, and it must report that rather than raising."""
    runner = FakeRunner()
    path, created = create_shortcut(tmp_path / EXE_NAME, shortcut_dir=tmp_path, runner=runner)
    assert path == tmp_path / SHORTCUT_NAME
    if sys.platform != "win32":
        assert created is False
        assert runner.commands == []


def test_a_failed_shortcut_is_reported_not_raised(tmp_path, monkeypatch):
    """Setup must still finish: the program is installed even if the icon is missing."""
    monkeypatch.setattr("ajz.install.is_windows", lambda: True)
    runner = FakeRunner(returncode=1, stderr="access denied")
    _, created = create_shortcut(tmp_path / EXE_NAME, shortcut_dir=tmp_path, runner=runner)
    assert created is False


# --- _run error handling --------------------------------------------------------------


def test_run_reports_a_missing_powershell_rather_than_raising():
    def missing(*args, **kwargs):
        raise FileNotFoundError()

    code, output = _run(["powershell"], runner=missing)
    assert code == 127 and "not found" in output


def test_run_reports_a_timeout_rather_than_hanging_the_install():
    import subprocess

    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="powershell", timeout=60)

    code, _ = _run(["powershell"], runner=slow)
    assert code == 124


# --- Config ---------------------------------------------------------------------------


def test_config_is_written_outside_the_workbook(tmp_path):
    """REGRESSION (v5.1): the key lived in Settings!B1, making the spreadsheet a secret.

    Keeping it here is what lets Jeff email the dashboard to anyone safely.
    """
    path = write_config("test-key-123", tmp_path)
    assert path.name == "config.json"
    assert json.loads(path.read_text())["fmp_api_key"] == "test-key-123"


def test_bundled_key_is_found_next_to_the_installer(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"fmp_api_key": "bundled"}))
    assert find_bundled_key(tmp_path) == "bundled"


def test_missing_bundled_key_is_none_not_a_crash(tmp_path):
    assert find_bundled_key(tmp_path) is None


def test_corrupt_bundled_config_is_none_not_a_crash(tmp_path):
    (tmp_path / "config.json").write_text("{not json")
    assert find_bundled_key(tmp_path) is None


# --- install() ------------------------------------------------------------------------


def test_install_writes_config_and_reports_paths(tmp_path):
    runner = FakeRunner()
    report = install(
        api_key="k", install_dir=tmp_path / "app",
        workbook_path=tmp_path / "Desktop" / "AJZ Dashboard.xlsx",
        source_exe=tmp_path / "nonexistent.exe", runner=runner,
    )
    assert (tmp_path / "app" / "config.json").exists()
    assert report.install_dir == tmp_path / "app"


def test_install_without_a_key_fails_with_an_actionable_message(tmp_path):
    with pytest.raises(InstallError, match="config.json"):
        install(api_key=None, install_dir=tmp_path, source_exe=tmp_path / "x.exe",
                runner=FakeRunner())


def test_install_runs_one_refresh_immediately(tmp_path):
    """Jeff's first open must show real numbers, not 'check back tomorrow'."""
    called = []
    install(api_key="k", install_dir=tmp_path, source_exe=tmp_path / "x.exe",
            runner=FakeRunner(), refresh_now=lambda: called.append(True))
    assert called == [True]


def test_a_failing_first_refresh_does_not_fail_the_install(tmp_path):
    """The shortcut must survive a bad first run — clicking it later may well succeed."""
    def boom():
        raise RuntimeError("network down")

    report = install(api_key="k", install_dir=tmp_path, source_exe=tmp_path / "x.exe",
                     runner=FakeRunner(), refresh_now=boom)
    assert report.first_refresh_ok is False


def test_install_copies_the_exe_out_of_wherever_it_was_run_from(tmp_path):
    """The shortcut must point at a stable path — Downloads gets emptied."""
    source = tmp_path / "Downloads" / "AJZ Setup.exe"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"fake exe")

    report = install(api_key="k", install_dir=tmp_path / "app",
                     source_exe=source, runner=FakeRunner())
    assert report.exe_path == tmp_path / "app" / EXE_NAME
    assert report.exe_path.read_bytes() == b"fake exe"


def test_install_is_idempotent(tmp_path):
    """Running setup twice must not fail or duplicate anything."""
    source = tmp_path / "AJZ Setup.exe"
    source.write_bytes(b"exe")
    for _ in range(2):
        report = install(api_key="k", install_dir=tmp_path / "app",
                         source_exe=source, runner=FakeRunner())
    assert report.exe_path.exists()


def test_install_keeps_the_existing_exe_when_it_cannot_be_overwritten(tmp_path, monkeypatch):
    """Windows will not overwrite a running image.

    Re-running setup while a refresh is in flight raises PermissionError on the copy. An
    already-installed copy is good enough to carry on with, so setup completes rather
    than dying with a traceback the user cannot read.
    """
    install_dir = tmp_path / "app"
    install_dir.mkdir()
    (install_dir / EXE_NAME).write_bytes(b"the running one")
    source = tmp_path / "AJZ Setup.exe"
    source.write_bytes(b"the new one")

    def refuse(*args, **kwargs):
        raise PermissionError("in use")

    monkeypatch.setattr("ajz.install.shutil.copy2", refuse)
    report = install(api_key="k", install_dir=install_dir, source_exe=source,
                     runner=FakeRunner())
    assert report.exe_path.read_bytes() == b"the running one"


def test_install_fails_loudly_if_there_is_no_exe_to_fall_back_on(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise PermissionError("in use")

    source = tmp_path / "AJZ Setup.exe"
    source.write_bytes(b"new")
    monkeypatch.setattr("ajz.install.shutil.copy2", refuse)
    with pytest.raises(InstallError, match="Could not copy"):
        install(api_key="k", install_dir=tmp_path / "app", source_exe=source,
                runner=FakeRunner())


def test_install_summary_is_plain_english(tmp_path):
    report = install(api_key="k", install_dir=tmp_path,
                     source_exe=tmp_path / "x.exe", runner=FakeRunner())
    summary = report.summary()
    assert "installed" in summary.lower()
    for jargon in ("schtasks", "powershell", "Traceback", "subprocess", "API"):
        assert jargon not in summary


# --- uninstall ------------------------------------------------------------------------


def test_uninstall_removes_the_shortcut_and_leaves_the_data(tmp_path):
    shortcut = tmp_path / SHORTCUT_NAME
    shortcut.write_bytes(b"lnk")
    workbook = tmp_path / "AJZ Dashboard.xlsx"
    workbook.write_bytes(b"his scores are in here")

    assert uninstall(shortcut_dir=tmp_path) is True
    assert not shortcut.exists()
    assert workbook.read_bytes() == b"his scores are in here"


def test_uninstall_on_a_machine_with_no_shortcut_is_not_an_error(tmp_path):
    """Idempotent: asking twice must not fail the second time."""
    assert uninstall(shortcut_dir=tmp_path) is True


def test_status_reports_what_is_present(tmp_path):
    (tmp_path / "config.json").write_text("{}")
    result = status(install_dir=tmp_path, shortcut_dir=tmp_path)
    assert result["config_present"] is True
    assert result["exe_present"] is False
    assert result["shortcut_present"] is False
    assert result["install_dir"] == str(tmp_path)


def test_bundled_key_is_found_next_to_the_exe_not_only_in_the_unpack_dir(tmp_path, monkeypatch):
    # Regression: under PyInstaller --onefile, sys._MEIPASS always exists and points at a
    # temp unpack folder. Checking it first meant a config.json handed over separately and
    # saved beside the exe was never seen, and setup failed with "no API key" while the
    # file sat right there. That is the only delivery route when the exe ships via a
    # public release, where the key cannot be published with it.
    exe_dir = tmp_path / "Downloads"
    exe_dir.mkdir()
    (exe_dir / "config.json").write_text(json.dumps({"fmp_api_key": "beside-the-exe"}))

    unpack = tmp_path / "_MEI12345"
    unpack.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "AJZ-Setup.exe"), raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(unpack), raising=False)

    assert find_bundled_key() == "beside-the-exe"


def test_bundled_key_falls_back_to_a_build_time_baked_config(tmp_path, monkeypatch):
    exe_dir = tmp_path / "Downloads"
    exe_dir.mkdir()
    unpack = tmp_path / "_MEI12345"
    unpack.mkdir()
    (unpack / "config.json").write_text(json.dumps({"fmp_api_key": "baked-in"}))

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "AJZ-Setup.exe"), raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(unpack), raising=False)

    assert find_bundled_key() == "baked-in"


# --- Where the shortcut lands -----------------------------------------------------------


def test_desktop_prefers_the_registry_over_guessing(tmp_path, monkeypatch):
    """OneDrive Desktop backup moves the real Desktop, and ~/Desktop may still exist.

    Guessing would put the shortcut in the stale folder, so setup would look like it had
    silently done nothing. The registry follows the redirection; the guess does not.
    """
    from ajz.config import desktop_dir

    redirected = tmp_path / "OneDrive" / "Desktop"
    redirected.mkdir(parents=True)
    (tmp_path / "Desktop").mkdir()  # the decoy the old code would have picked

    monkeypatch.setattr("ajz.config.sys.platform", "win32")
    monkeypatch.setattr("ajz.config._desktop_from_registry", lambda: redirected)
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path))

    assert desktop_dir() == redirected


def test_desktop_falls_back_when_the_registry_cannot_answer(tmp_path, monkeypatch):
    """Off Windows there is no winreg at all, and a bad read must not be fatal."""
    from ajz.config import _desktop_from_registry, desktop_dir

    if sys.platform != "win32":
        assert _desktop_from_registry() is None

    monkeypatch.setattr("ajz.config._desktop_from_registry", lambda: None)
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path))

    assert desktop_dir() == tmp_path  # no ~/Desktop exists, so home is the fallback
    (tmp_path / "Desktop").mkdir()
    assert desktop_dir() == tmp_path / "Desktop"


def test_the_workbook_lives_beside_the_program_not_on_the_desktop(tmp_path):
    """One clickable thing. A second copy on the Desktop is a stale copy waiting to be
    opened by mistake, and it would show yesterday's numbers with a confident banner."""
    report = install(api_key="k", install_dir=tmp_path / "app",
                     shortcut_dir=tmp_path / "Desktop",
                     source_exe=tmp_path / "x.exe", runner=FakeRunner())
    assert report.workbook_path.parent == report.install_dir
    assert report.shortcut_path.parent != report.workbook_path.parent


# --- Reinstalling over an existing install -----------------------------------------------


def test_reinstalling_preserves_everything_he_has_typed(tmp_path):
    """Upgrading is just running the new setup over the old one.

    Nothing versioned is written, so there is no second copy to conflict with: the exe is
    overwritten in place, config.json is rewritten with the same key, and the shortcut has
    a fixed name so it replaces rather than duplicates.

    What must survive is everything that is *his*: the workbook holding hand-entered
    conviction scores, the history series, and the backups. Setup never deletes; the
    refresh it triggers reads the existing workbook as the system of record.
    """
    install_dir = tmp_path / "app"
    install_dir.mkdir()
    workbook = install_dir / "AJZ Dashboard.xlsx"
    workbook.write_bytes(b"his conviction scores live here")
    history = install_dir / "history.sqlite"
    history.write_bytes(b"the whole series")
    backups = install_dir / "backups"
    backups.mkdir()
    (backups / "2026-08-24.xlsx").write_bytes(b"yesterday")

    source = tmp_path / "AJZ Setup.exe"
    source.write_bytes(b"v1.1.1")

    for _ in range(2):  # twice: upgrading must be as safe as installing
        install(api_key="k", install_dir=install_dir, shortcut_dir=tmp_path / "Desktop",
                source_exe=source, runner=FakeRunner())

    assert workbook.read_bytes() == b"his conviction scores live here"
    assert history.read_bytes() == b"the whole series"
    assert (backups / "2026-08-24.xlsx").read_bytes() == b"yesterday"
    assert (install_dir / EXE_NAME).read_bytes() == b"v1.1.1"


def test_reinstalling_creates_one_shortcut_not_two(tmp_path):
    """The shortcut name is fixed, so a second setup replaces it in place."""
    desktop = tmp_path / "Desktop"
    source = tmp_path / "AJZ Setup.exe"
    source.write_bytes(b"exe")

    runner = FakeRunner()
    for _ in range(3):
        install(api_key="k", install_dir=tmp_path / "app", shortcut_dir=desktop,
                source_exe=source, runner=runner)

    targets = {
        command[-1].split("CreateShortcut(")[1].split(")")[0]
        for command in runner.commands
        if "CreateShortcut" in command[-1]
    }
    assert len(targets) <= 1, f"more than one shortcut path was written: {targets}"
