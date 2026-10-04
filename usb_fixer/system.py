"""Running external commands, PowerShell helpers and admin handling.

Everything that touches the operating system goes through a ``Runner`` so the
rest of the code can be tested with a fake one.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass
class CmdResult:
    rc: int
    out: str = ""
    err: str = ""

    @property
    def ok(self) -> bool:
        return self.rc == 0


Runner = Callable[[Sequence[str]], CmdResult]

PS_PREFIX = (
    "$ProgressPreference='SilentlyContinue';"
    "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;\n"
)


def is_windows() -> bool:
    return os.name == "nt"


def _decode(data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("oem" if is_windows() else "latin-1", errors="replace")
    return text.lstrip("﻿")


def run(cmd: Sequence[str], timeout: int = 120) -> CmdResult:
    kwargs = {}
    if is_windows():
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.run(list(cmd), capture_output=True, timeout=timeout, **kwargs)
    except FileNotFoundError:
        return CmdResult(127, "", f"command not found: {cmd[0]}")
    except subprocess.TimeoutExpired:
        return CmdResult(124, "", "timed out")
    return CmdResult(proc.returncode, _decode(proc.stdout), _decode(proc.stderr))


def powershell_cmd(script: str) -> list[str]:
    """Build a command line that runs ``script`` in PowerShell.

    -EncodedCommand avoids every quoting problem of passing a script as an argument.
    """
    encoded = base64.b64encode((PS_PREFIX + script).encode("utf-16-le")).decode("ascii")
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        encoded,
    ]


def decode_powershell_cmd(cmd: Sequence[str]) -> str | None:
    """Inverse of powershell_cmd (used by tests and the demo runner)."""
    if "-EncodedCommand" not in cmd:
        return None
    encoded = cmd[list(cmd).index("-EncodedCommand") + 1]
    return base64.b64decode(encoded).decode("utf-16-le")


def is_admin() -> bool:
    if not is_windows():
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """Ask Windows (UAC) to start this program again with admin rights."""
    if not is_windows():
        return False
    import ctypes

    args = sys.argv[1:]
    if not getattr(sys, "frozen", False):
        args = ["-m", "usb_fixer"] + args
    result = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
        None, "runas", sys.executable, subprocess.list2cmdline(args), os.getcwd(), 1
    )
    return result > 32
