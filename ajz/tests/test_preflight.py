"""Fail fast when the dashboard is open in Excel (from Jeff's log, 2026-08-31).

His refresh.log shows the same shape three times in seven days:

    13:38:38  refreshing ...
    13:38:55  WARNING  workbook is open in Excel: Could not replace ...
    13:39:19  refreshing ...
    13:39:36  status=ok  written=True

Seventeen seconds of API calls, a backup, a history snapshot and a full workbook build
-- all of it discarded, because the very last step could not write. He then closes Excel
and does it again. The check costs microseconds and belongs at the front.

This is also the only part of the "Excel goes not responding" report we can act on with
evidence: whatever the cause turns out to be, refreshing onto a file he has open is the
state it happens in, and this removes the wait during which it can happen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ajz.store import WorkbookLockedError, assert_writable


def test_a_writable_workbook_passes(tmp_path):
    path = tmp_path / "AJZ Dashboard.xlsx"
    path.write_bytes(b"not really a workbook, but it is ours and it is writable")
    assert_writable(path)


def test_a_missing_workbook_passes(tmp_path):
    """First run. Nothing to be locked out of."""
    assert_writable(tmp_path / "AJZ Dashboard.xlsx")


def test_a_locked_workbook_raises_before_any_work_happens(tmp_path, monkeypatch):
    """Excel on Windows holds the file with a deny-write share, so opening it for
    writing raises PermissionError. macOS has no mandatory locking, so the condition
    has to be simulated -- what is under test is our reaction, not Windows' behaviour.
    """
    path = tmp_path / "AJZ Dashboard.xlsx"
    path.write_bytes(b"held open by Excel")

    real_open = Path.open

    def deny(self, *args, **kwargs):
        if self == path and "r+" in str(args[0] if args else kwargs.get("mode", "")):
            raise PermissionError(13, "Permission denied")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny)

    with pytest.raises(WorkbookLockedError) as caught:
        assert_writable(path)
    assert "excel" in str(caught.value).lower()


def test_the_refresh_checks_before_spending_a_single_api_call(tmp_path, monkeypatch):
    """The point of the whole exercise: no fetch, no backup, no snapshot."""
    from ajz import refresh as refresh_module

    path = tmp_path / "AJZ Dashboard.xlsx"
    path.write_bytes(b"held open by Excel")

    def boom(*args, **kwargs):
        raise AssertionError("work was done before checking the file could be written")

    monkeypatch.setattr(refresh_module, "read_existing", boom)
    monkeypatch.setattr(refresh_module, "backup_workbook", boom)

    def locked(_path):
        raise WorkbookLockedError("The dashboard is open in Excel.")

    monkeypatch.setattr(refresh_module, "assert_writable", locked)

    with pytest.raises(WorkbookLockedError):
        refresh_module.refresh(
            fetch=boom,
            workbook_path=path,
            history_path=tmp_path / "history.sqlite",
            backup_dir=tmp_path / "backups",
        )


# --- Warnings that only ever reached the log file ------------------------------------


def test_warnings_are_shown_to_jeff_not_just_logged(capsys):
    """From his log, 2026-08-27:

        WARNING  AMD: duplicate row in Universe sheet; kept the first

    He never saw it. Warnings went to refresh.log, which is a file he has no reason to
    open and did not know existed until we asked him for it. A duplicate ticker sat in
    his Universe for days, silently ignored, while the sheet looked fine.

    A warning nobody reads is not a warning.
    """
    from ajz.cli import _emit_warnings

    _emit_warnings(["AMD: duplicate row in Universe sheet; kept the first"], print)
    out = capsys.readouterr().out
    assert "AMD" in out
    assert "duplicate" in out


def test_no_warnings_means_no_noise(capsys):
    from ajz.cli import _emit_warnings

    _emit_warnings([], print)
    assert capsys.readouterr().out == ""
