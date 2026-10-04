"""Entry point: `python -m usb_fixer` (GUI), `--scan` (console report), `--demo` (fake machine)."""

from __future__ import annotations

import argparse
import sys

from . import report, strings
from .diagnostics import scan
from .snapshot import ScanError
from .system import is_windows, run


def _utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass


def main(argv=None) -> int:
    _utf8_stdout()
    parser = argparse.ArgumentParser(prog="usb_fixer", description="Diagnose and fix USB problems on Windows.")
    parser.add_argument("--scan", action="store_true", help="print a text report instead of opening the window")
    parser.add_argument("--demo", action="store_true", help="use a fake machine (works on any OS)")
    args = parser.parse_args(argv)

    if args.demo:
        from .demo import DemoRunner

        runner = DemoRunner()
    elif not is_windows():
        print(strings.UI["windows_only"], file=sys.stderr)
        return 1
    else:
        runner = run

    if args.scan:
        try:
            print(report.build_report(scan(runner)))
        except ScanError as exc:
            print(f"{strings.UI['scan_failed']} {exc}", file=sys.stderr)
            return 2
        return 0

    from .gui import run_gui

    run_gui(runner, demo=args.demo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
