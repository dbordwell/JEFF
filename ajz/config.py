"""Configuration and secret loading (spec §11).

The API key NEVER lives in the workbook. v5.1 shipped Jeff's live key in plaintext in
`Settings!B1`, readable without even opening Excel, and Copilot advised handing that
file plus the key to an Upwork freelancer.

Keeping the key out of the workbook has a concrete payoff: the dashboard becomes safe
to email to anyone.

Resolution order (first hit wins):
    1. AJZ_FMP_API_KEY environment variable
    2. the config file  — %LOCALAPPDATA%\\AJZ\\config.json on Windows,
                          ~/.config/ajz/config.json elsewhere
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ENV_VAR = "AJZ_FMP_API_KEY"


class MissingApiKeyError(RuntimeError):
    """No key configured. Actionable message, never a stack trace at the user."""


def app_dir() -> Path:
    """Per-user application directory. No admin rights needed on any platform."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / "AJZ"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ajz"


@dataclass(frozen=True)
class Config:
    api_key: str
    workbook_path: Path
    history_path: Path
    backup_dir: Path
    cache_dir: Path
    log_dir: Path

    @property
    def redacted_key(self) -> str:
        """For logs. Never print the key itself."""
        if len(self.api_key) <= 8:
            return "***"
        return f"{self.api_key[:4]}…{self.api_key[-4:]}"


def _desktop() -> Path:
    candidate = Path.home() / "Desktop"
    return candidate if candidate.exists() else Path.home()


def load_api_key(config_path: Path | None = None) -> str:
    from_env = os.environ.get(ENV_VAR, "").strip()
    if from_env:
        return from_env

    path = config_path or (app_dir() / "config.json")
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise MissingApiKeyError(
                f"{path} is not valid JSON ({exc}). Expected: "
                '{"fmp_api_key": "your-key-here"}'
            ) from exc
        key = str(data.get("fmp_api_key", "")).strip()
        if key:
            return key

    raise MissingApiKeyError(
        "No FMP API key found.\n"
        f"  Either set the {ENV_VAR} environment variable,\n"
        f"  or create {path} containing:\n"
        '      {"fmp_api_key": "your-key-here"}'
    )


def load(config_path: Path | None = None, workbook_path: Path | None = None) -> Config:
    base = app_dir()
    return Config(
        api_key=load_api_key(config_path),
        workbook_path=workbook_path or (_desktop() / "AJZ Dashboard.xlsx"),
        history_path=base / "history.sqlite",
        backup_dir=base / "backups",
        cache_dir=base / "cache",
        log_dir=base / "logs",
    )


def redact(text: str, api_key: str) -> str:
    """Strip the key out of anything that might be logged or shown.

    Applied to every URL and error message, because API keys travel in query strings
    here and a leaked log is a leaked key.
    """
    if not api_key:
        return text
    return text.replace(api_key, "***REDACTED***")
