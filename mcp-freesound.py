#!/usr/bin/env python3
"""mcp-freesound - pure-Python MCP server for Freesound.org.

Run straight from a clone, no installation and no third-party packages required:

    python mcp-freesound.py                         # stdio transport (default)
    python mcp-freesound.py serve --transport http  # HTTP transport with bearer token
    python mcp-freesound.py gui                     # configuration GUI
    python mcp-freesound.py --help

When installed with pip the same CLI is available as ``mcp-freesound``.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mcp_freesound.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
