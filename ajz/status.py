"""Refresh status and the plain-English banner (spec §10).

The front sheet is the entire error-reporting surface. Jeff is never asked to read a
log, and never sees a code. Every message here is written to be read by someone who
does not know what an API is.

The governing rule: stale-but-labelled always beats blank or wrong. The workbook must
never show a number without showing how old it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class RefreshState(str, Enum):
    OK = "ok"
    PARTIAL = "partial"  # refreshed, but some tickers had no data
    STALE = "stale"  # provider unreachable; showing last good data
    QUOTA = "quota"  # hit the plan's request limit
    AUTH_ERROR = "auth_error"  # key rejected/expired — needs a human


@dataclass(frozen=True)
class RefreshStatus:
    state: RefreshState
    data_as_of: datetime | None = None
    missing_tickers: tuple[str, ...] = ()

    @property
    def headline(self) -> str:
        """The banner text. Plain English, no jargon, no error codes."""
        when = self._friendly_when()
        if self.state in (RefreshState.OK, RefreshState.PARTIAL):
            return f"Data current as of {when}"
        if self.state is RefreshState.STALE:
            return (
                "Could not reach the data provider this morning. "
                f"Showing the numbers from {when}."
            )
        if self.state is RefreshState.QUOTA:
            return f"Daily data limit reached. Showing the numbers from {when}."
        if self.state is RefreshState.AUTH_ERROR:
            return "The data subscription needs attention — please call Dave."
        return "Status unknown."

    @property
    def note(self) -> str | None:
        """Secondary line, only when there is genuinely something to add."""
        if not self.missing_tickers:
            return None
        listed = ", ".join(self.missing_tickers)
        count = len(self.missing_tickers)
        plural = "ticker" if count == 1 else "tickers"
        return f"{count} {plural} had no data today: {listed}"

    @property
    def is_healthy(self) -> bool:
        return self.state in (RefreshState.OK, RefreshState.PARTIAL)

    def _friendly_when(self) -> str:
        if self.data_as_of is None:
            return "an unknown date"
        # e.g. "Tue 19 Aug 2026, 6:05 AM" — unambiguous without being technical.
        stamp = self.data_as_of.strftime("%a %d %b %Y, %I:%M %p")
        return stamp.replace(" 0", " ").replace(", 0", ", ")
