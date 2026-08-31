"""AJZ Dashboard.

The version lives here and nowhere else. `pyproject.toml` reads it from this module, so
the number in the package metadata, the number printed by `--status`, and the number
written into the workbook can never disagree with each other.

That mattered on the last release: `pyproject.toml` said 0.1.0 while the shipped asset
was tagged v1.1.0, and the running program reported no version at all. When Jeff says
something looks wrong, the first question is what he is actually running, and there was
no way for him to answer it.
"""

__version__ = "3.0.1"
