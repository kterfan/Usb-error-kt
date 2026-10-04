"""Launcher used by PyInstaller (a script inside a package can't use relative imports)."""

import sys

from usb_fixer.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
