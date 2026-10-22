"""core/stdio.py — keep the CLI from crashing on characters the console encoding lacks."""
from __future__ import annotations

import sys


def make_output_safe(streams=None) -> None:
    """Make stdout and stderr unable to raise ``UnicodeEncodeError``.

    Windows gives redirected output (a pipe, a file, a CI log) the legacy ANSI code page, cp1252, which has no
    "✓" or box-drawing characters, so every command that printed one died with a traceback. On Windows the
    streams become UTF-8; elsewhere the terminal's encoding is kept and anything it cannot show becomes "?".
    """
    for stream in (sys.stdout, sys.stderr) if streams is None else streams:
        reconfigure = getattr(stream, "reconfigure", None)  # absent when frozen without a console
        if reconfigure is None:
            continue
        try:
            if sys.platform == "win32":
                reconfigure(encoding="utf-8", errors="replace")
            else:
                reconfigure(errors="replace")
        except (OSError, ValueError):
            pass
