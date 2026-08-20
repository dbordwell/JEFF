"""Tests for the one-time setup (spec §3.3).

This code cannot be executed on the machine it was written on — it targets Windows and
was authored on macOS. So the platform-specific work is confined to command *builders*
and a single injectable `runner`, and everything below asserts on the commands that
would be issued rather than on their effects.

That is a real limitation and worth naming: these tests prove we construct the right
schtasks invocation, not that Windows accepts it. A smoke run on a Windows CI runner is
the check that closes that gap.
"""

from __future__ import annotations

import json
import sys

import pytest

from ajz.install import (
    DEFAULT_TIME,
    EXE_NAME,
    TASK_NAME,
    InstallError,
    _delete_task_command,
    _run,
    _task_command,
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


# --- The scheduled task command -------------------------------------------------------


def test_task_command_creates_a_daily_user_level_task(tmp_path):
    exe = tmp_path / EXE_NAME
    command = _task_command(exe, "06:00")

    assert command[:2] == ["schtasks", "/Create"]
    assert "/SC" in command and command[command.index("/SC") + 1] == "DAILY"
    assert "/ST" in command and command[command.index("/ST") + 1] == "06:00"
    assert command[command.index("/TN") + 1] == TASK_NAME


def test_task_command_requests_no_elevation(tmp_path):
    """/RU and /RL would force an admin prompt.

    The install has to work with no access to Jeff's PC and no admin rights, and the task
    must run as him so it can write to his Desktop.
    """
    command = _task_command(tmp_path / EXE_NAME, "06:00")
    assert "/RU" not in command
    assert "/RL" not in command
    assert "SYSTEM" not in " ".join(command)


def test_task_command_overwrites_on_reinstall(tmp_path):
    """/F makes reinstalling idempotent instead of failing on an existing task."""
    assert "/F" in _task_command(tmp_path / EXE_NAME, "06:00")


def test_task_command_quotes_a_path_containing_spaces(tmp_path):
    """%LOCALAPPDATA% sits under 'C:\\Users\\...', and Jeff's name may contain a space."""
    exe = tmp_path / "Program Files" / EXE_NAME
    command = _task_command(exe, "06:00")
    target = command[command.index("/TR") + 1]
    assert target.startswith('"') and target.endswith('"')


def test_delete_command_is_forced_so_it_never_prompts():
    assert "/F" in _delete_task_command()


# --- _run error handling --------------------------------------------------------------


def test_run_reports_a_missing_schtasks_rather_than_raising():
    def missing(*args, **kwargs):
        raise FileNotFoundError()

    code, output = _run(["schtasks"], runner=missing)
    assert code == 127 and "not found" in output


def test_run_reports_a_timeout_rather_than_hanging_the_install():
    import subprocess

    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="schtasks", timeout=60)

    code, _ = _run(["schtasks"], runner=slow)
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
    assert report.scheduled_time == DEFAULT_TIME


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
    """The schedule must survive a bad morning — tomorrow's run may well succeed."""
    def boom():
        raise RuntimeError("network down")

    report = install(api_key="k", install_dir=tmp_path, source_exe=tmp_path / "x.exe",
                     runner=FakeRunner(), refresh_now=boom)
    assert report.first_refresh_ok is False


def test_install_copies_the_exe_out_of_wherever_it_was_run_from(tmp_path):
    """The task must point at a stable path — Downloads gets emptied."""
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


def test_custom_time_is_honoured(tmp_path):
    report = install(api_key="k", when="07:30", install_dir=tmp_path,
                     source_exe=tmp_path / "x.exe", runner=FakeRunner())
    assert report.scheduled_time == "07:30"


def test_install_summary_is_plain_english(tmp_path):
    report = install(api_key="k", install_dir=tmp_path,
                     source_exe=tmp_path / "x.exe", runner=FakeRunner())
    summary = report.summary()
    assert "installed" in summary.lower()
    for jargon in ("schtasks", "Traceback", "subprocess", "API"):
        assert jargon not in summary


# --- uninstall ------------------------------------------------------------------------


def test_uninstall_reports_platform_appropriate_result_rather_than_crashing():
    # On Windows there is a scheduled task and registry state to tear down, so uninstall
    # does real work and reports True. Everywhere else there is nothing to remove: it must
    # report False rather than raise, so the CI smoke run on windows-latest stays green.
    expected = sys.platform == "win32"
    assert uninstall(runner=FakeRunner()) is expected


def test_status_reports_what_is_present(tmp_path):
    (tmp_path / "config.json").write_text("{}")
    result = status(runner=FakeRunner(), install_dir=tmp_path)
    assert result["config_present"] is True
    assert result["exe_present"] is False
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
