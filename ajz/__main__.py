"""Frozen-binary entry point.

PyInstaller needs a real script to target, and `python -m ajz` should behave the same as
the installed `ajz-refresh` command. Both land here.
"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
