"""Platform and Python version compatibility support."""

from __future__ import annotations

import sys

WIN: bool = sys.platform in ("win32", "cygwin")
