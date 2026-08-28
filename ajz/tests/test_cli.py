"""Tests for what Jeff actually experiences when he clicks the shortcut.

The launcher is the human-facing surface now that there is no scheduled task, so these
assert on behaviour a person would notice: that the dashboard opens, that it still opens
when the refresh failed, and that nothing shouts jargon at him.
"""

from __future__ import annotations

import sys

import pytest
from pathlib import Path

from ajz import cli


class Args:
    """Stands in for the parsed argparse namespace."""

    def __init__(self, no_open=False, dry_run=False):
        self.no_open = no_open
        self.dry_run = dry_run


def test_a_missing_workbook_is_reported_not_crashed_on(tmp_path):
    assert cli.open_workbook(tmp_path / "nothing-here.xlsx") is False


def test_open_workbook_reports_failure_rather_than_raising(tmp_path, monkeypatch):
    workbook = tmp_path / "AJZ Dashboard.xlsx"
    workbook.write_bytes(b"xlsx")

    def refuse(*args, **kwargs):
        raise OSError("no handler")

    monkeypatch.setattr(cli.subprocess, "run", refuse)
    if sys.platform == "win32":
        monkeypatch.setattr(cli.os, "startfile", refuse, raising=False)

    assert cli.open_workbook(workbook) is False


def test_no_open_suppresses_opening(tmp_path, monkeypatch):
    opened: list[Path] = []
    monkeypatch.setattr(cli, "open_workbook", lambda path: opened.append(path) or True)

    cli._maybe_open(tmp_path / "AJZ Dashboard.xlsx", Args(no_open=True))
    assert opened == []


def test_a_dry_run_does_not_open_a_workbook_it_did_not_write(tmp_path, monkeypatch):
    opened: list[Path] = []
    monkeypatch.setattr(cli, "open_workbook", lambda path: opened.append(path) or True)

    cli._maybe_open(tmp_path / "AJZ Dashboard.xlsx", Args(dry_run=True))
    assert opened == []


def test_the_normal_path_opens_the_dashboard(tmp_path, monkeypatch):
    opened: list[Path] = []
    monkeypatch.setattr(cli, "open_workbook", lambda path: opened.append(path) or True)

    workbook = tmp_path / "AJZ Dashboard.xlsx"
    cli._maybe_open(workbook, Args())
    assert opened == [workbook]


def test_the_file_location_is_printed_when_it_cannot_be_opened(tmp_path, capsys):
    """Never leave him with nothing. If Excel will not launch, tell him where to look."""
    workbook = tmp_path / "AJZ Dashboard.xlsx"
    cli._maybe_open(workbook, Args())  # the file does not exist, so opening fails
    assert str(workbook) in capsys.readouterr().out


def test_an_unconfigured_copy_says_so_in_plain_english(monkeypatch, capsys):
    """Exit code 2 is for Dave; Jeff gets a sentence telling him what to do."""
    def unconfigured(**kwargs):
        raise cli.MissingApiKeyError("no key")

    monkeypatch.setattr(cli, "load", unconfigured)

    class FullArgs(Args):
        out = None
        verbose = False

    assert cli._do_refresh(FullArgs()) == 2
    output = capsys.readouterr().out
    assert "set up" in output.lower()
    for jargon in ("Traceback", "MissingApiKeyError", "fmp_api_key"):
        assert jargon not in output


# --- The double-click path ---------------------------------------------------------------


def test_double_clicking_before_setup_installs_rather_than_failing(tmp_path, monkeypatch):
    """The gesture every instruction we wrote depends on.

    A double-click passes no arguments. Installing used to require --install, so
    double-clicking the downloaded setup file ran a *refresh*, which failed with "not set
    up yet" and vanished — and could never succeed, because refresh only looks for the key
    in %LOCALAPPDATA%, never beside the exe where the user was told to put it.

    This is the bug that broke the first real install, and it survived a Windows CI test
    of the installer because that test typed --install explicitly.
    """
    monkeypatch.setattr(cli, "_is_set_up", lambda: False)
    chosen = []
    monkeypatch.setattr(cli, "_do_install", lambda args: chosen.append("install") or 0)
    monkeypatch.setattr(cli, "_do_refresh", lambda args: chosen.append("refresh") or 0)

    cli._main([])
    assert chosen == ["install"]


def test_double_clicking_after_setup_refreshes(tmp_path, monkeypatch):
    """Once installed, the same gesture must mean "give me current numbers"."""
    monkeypatch.setattr(cli, "_is_set_up", lambda: True)
    monkeypatch.setattr(cli, "_is_the_installed_exe", lambda: True)
    chosen = []
    monkeypatch.setattr(cli, "_do_install", lambda args: chosen.append("install") or 0)
    monkeypatch.setattr(cli, "_do_refresh", lambda args: chosen.append("refresh") or 0)

    cli._main([])
    assert chosen == ["refresh"]


def test_double_clicking_a_downloaded_upgrade_installs_rather_than_just_refreshing(
        tmp_path, monkeypatch):
    """The upgrade gesture, and the same bug as the one above wearing a different hat.

    Jeff is already set up, so routing on "is it set up?" alone sends a freshly
    downloaded build straight to refresh. It produces a correct workbook once, never
    copies itself into %LOCALAPPDATA%, and leaves the desktop shortcut pointing at the
    OLD program — which then cannot read the new workbook at all.

    Routing on "am I the installed program?" instead covers install, upgrade and daily
    refresh with one rule and no version numbers.
    """
    monkeypatch.setattr(cli, "_is_set_up", lambda: True)
    monkeypatch.setattr(cli, "_is_the_installed_exe", lambda: False)
    chosen = []
    monkeypatch.setattr(cli, "_do_install", lambda args: chosen.append("install") or 0)
    monkeypatch.setattr(cli, "_do_refresh", lambda args: chosen.append("refresh") or 0)

    cli._main([])
    assert chosen == ["install"]


def test_running_from_source_is_never_treated_as_an_upgrade(monkeypatch):
    """`python -m ajz` is not a frozen exe and has no business copying itself anywhere."""
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    assert cli._is_the_installed_exe() is True


def test_the_installed_exe_recognises_itself(tmp_path, monkeypatch):
    exe = tmp_path / "ajz-refresh.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli.sys, "executable", str(exe), raising=False)
    monkeypatch.setattr("ajz.config.app_dir", lambda: tmp_path)
    assert cli._is_the_installed_exe() is True


def test_a_copy_in_downloads_knows_it_is_not_the_installed_exe(tmp_path, monkeypatch):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    downloaded = downloads / "AJZ-Setup.exe"
    downloaded.write_bytes(b"x")
    installed = tmp_path / "AJZ"
    installed.mkdir()
    (installed / "ajz-refresh.exe").write_bytes(b"x")

    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli.sys, "executable", str(downloaded), raising=False)
    monkeypatch.setattr("ajz.config.app_dir", lambda: installed)
    assert cli._is_the_installed_exe() is False


def test_set_up_is_judged_by_the_installed_key(tmp_path, monkeypatch):
    monkeypatch.delenv("AJZ_FMP_API_KEY", raising=False)
    monkeypatch.setattr("ajz.config.app_dir", lambda: tmp_path)
    assert cli._is_set_up() is False

    (tmp_path / "config.json").write_text('{"fmp_api_key": "k"}')
    assert cli._is_set_up() is True


def test_an_environment_key_counts_as_set_up(tmp_path, monkeypatch):
    monkeypatch.setenv("AJZ_FMP_API_KEY", "from-the-environment")
    monkeypatch.setattr("ajz.config.app_dir", lambda: tmp_path)
    assert cli._is_set_up() is True


# --- The window that vanished ------------------------------------------------------------


def test_a_failure_holds_the_window_open(monkeypatch):
    """"It flashes so quickly I think it says something about the key."

    Windows destroys the console the moment the process exits, so the one line telling
    him what went wrong was unreadable. An error nobody can read is not an error message.
    """
    monkeypatch.setattr(cli.sys, "stdin", _Tty())
    waited = []
    monkeypatch.setattr("builtins.input", lambda prompt="": waited.append(prompt))

    assert cli._hold_window_open(2) == 2
    assert waited, "a failing run must stay on screen"


def test_success_does_not_make_him_press_a_key(monkeypatch):
    """A good refresh opens Excel and gets out of the way."""
    monkeypatch.setattr(cli.sys, "stdin", _Tty())
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("should not pause"))

    assert cli._hold_window_open(0) == 0


def test_no_pause_when_there_is_no_console_to_hold(monkeypatch):
    """Scripts and CI must never block waiting for a keypress that will never come."""
    monkeypatch.setattr(cli.sys, "stdin", _NotATty())
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("should not pause"))

    assert cli._hold_window_open(2) == 2


class _Tty:
    def isatty(self):
        return True


class _NotATty:
    def isatty(self):
        return False
