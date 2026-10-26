"""Allow ``python -m mcp_freesound``."""

import sys

from mcp_freesound.cli import main

if __name__ == "__main__":
    sys.exit(main())
