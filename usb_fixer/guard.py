"""Optional guard: a Windows scheduled task that, at each logon, re-applies fixes that Windows (an update,
a vendor power tool, a policy) has turned back. Only fixes the user applied with this program are touched,
and only the persistent settings (power, registry), never device removal or resets.
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from . import backup, fixes, state
from .diagnostics import PERSISTENT_FIXES, analyze
from .snapshot import take_snapshot
from .system import Runner

TASK_NAME = "USB Fixer Guard"


def exe_path() -> str:
    return sys.executable if getattr(sys, "frozen", False) else ""


def location_problem(path: str) -> str:
    """Why this exe location is a bad place for a logon task ('' if fine)."""
    if not path:
        return "نگهبان فقط با نسخهٔ نصب‌شدهٔ برنامه (Setup) کار می‌کنه."
    low = path.lower()
    if any(x in low for x in ("\\downloads\\", "\\temp\\", "\\appdata\\local\\temp")):
        return "برنامه از پوشهٔ دانلود/موقت اجرا شده؛ اگه جابه‌جا یا پاک بشه، نگهبان کار نمی‌کنه. اول برنامه رو نصب کن."
    return ""


def install_cmd(exe: str) -> list:
    return ["schtasks", "/Create", "/TN", TASK_NAME, "/TR", f'"{exe}" --guard', "/SC", "ONLOGON", "/RL", "HIGHEST", "/F"]


def remove_cmd() -> list:
    return ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]


def query_cmd() -> list:
    return ["schtasks", "/Query", "/TN", TASK_NAME]


def is_installed(runner: Runner) -> bool:
    return runner(query_cmd()).ok


def log_path() -> Path:
    return backup.backup_root().parent / "guard.log"


def run_guard(runner: Runner, log=None, root=None) -> int:
    """Re-apply reverted persistent fixes. Returns how many fixes were re-applied."""
    lines = []

    def out(msg: str) -> None:
        lines.append(msg)
        if log:
            log(msg)

    applied = state.applied_ids(root) & PERSISTENT_FIXES
    if not applied:
        out("nothing to guard")
        return 0
    snap = take_snapshot(runner)
    reverted = [f for f in analyze(snap, applied=applied) if f.reverted and f.fix_id in applied]
    if reverted:
        steps = fixes.collect_steps(reverted)
        res = fixes.execute(steps, runner, out, root=root, restore_point=False)
        # The guard's own backup would only hold the "reverted" (bad) state; keep "undo" pointing at the user's run.
        shutil.rmtree(res.backup_dir, ignore_errors=True)
        out(f"re-applied: {', '.join(f.fix_id for f in reverted)} (ok={res.ok}, failed={res.failed})")
    else:
        out("all fixes still in place")
    try:
        path = log_path() if root is None else Path(root) / "guard.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.now().isoformat(timespec='seconds')}] " + " | ".join(lines) + os.linesep)
    except OSError:
        pass
    return len(reverted)
