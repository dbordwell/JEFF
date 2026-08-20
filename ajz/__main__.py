"""Frozen-binary entry point.

PyInstaller needs a real script to target, and `python -m ajz` should behave the same as
the installed `ajz-refresh` command. Both land here.

The import below is absolute, not relative: PyInstaller runs this file as the top-level
script, where there is no parent package and `from .cli` raises ImportError at startup.
"""

from __future__ import annotations

import sys

from ajz.cli import main

if __name__ == "__main__":
    sys.exit(main())
