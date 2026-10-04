"""Entry point: `python -m usb_fixer` (GUI), `--scan` (console report), `--demo` (fake machine)."""

from __future__ import annotations

import argparse
import sys

from . import about, report, strings
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
    parser.add_argument("--version", action="version", version=about.banner())
    parser.add_argument("--offline", action="store_true", help="do not check the board maker's site for a newer BIOS")
    parser.add_argument("--report", metavar="FILE", help="with --scan: also write the report to FILE (UTF-8)")
    parser.add_argument("--guard", action="store_true", help="re-apply fixes that Windows turned back (used by the logon task)")
    args = parser.parse_args(argv)

    if args.demo:
        from .demo import DemoRunner

        runner = DemoRunner()
    elif not is_windows():
        print(strings.UI["windows_only"], file=sys.stderr)
        return 1
    else:
        runner = run

    if args.guard:
        from .guard import run_guard

        run_guard(runner, print)
        return 0

    if args.scan:
        try:
            from . import state

            text = report.build_report(scan(runner, online=not (args.offline or args.demo), applied=state.applied_ids()))
            if args.report:
                with open(args.report, "w", encoding="utf-8") as fh:
                    fh.write(text)
            if sys.stdout is not None:  # the windowed exe has no console
                print(text)
        except ScanError as exc:
            print(f"{strings.UI['scan_failed']} {exc}", file=sys.stderr)
            return 2
        return 0

    from .gui import run_gui

    run_gui(runner, demo=args.demo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
