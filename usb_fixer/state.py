"""What this program has changed before, so a later scan can tell whether a fix survived reboots/updates.

Stored next to the backups in %LOCALAPPDATA%\\UsbFixer\\applied.json.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import backup

FILE = "applied.json"


def _path(root: Optional[Path] = None) -> Path:
    base = Path(root) if root else backup.backup_root()
    return base.parent / FILE if base.name == "backups" else base / FILE


def load(root: Optional[Path] = None) -> dict:
    try:
        data = json.loads(_path(root).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data: dict, root: Optional[Path] = None) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def applied_ids(root: Optional[Path] = None) -> set:
    return set((load(root).get("fixes") or {}).keys())


def record_applied(fix_ids: list, root: Optional[Path] = None) -> None:
    if not fix_ids:
        return
    data = load(root)
    fixes = data.setdefault("fixes", {})
    now = datetime.now().isoformat(timespec="seconds")
    for f in fix_ids:
        fixes[f] = {"applied_at": now}
    save(data, root)


def forget(fix_ids: list, root: Optional[Path] = None) -> None:
    data = load(root)
    fixes = data.get("fixes") or {}
    for f in fix_ids:
        fixes.pop(f, None)
    data["fixes"] = fixes
    save(data, root)
