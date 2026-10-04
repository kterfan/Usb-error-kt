"""Safety net around fixes: restore point, registry export, and an undo file."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .system import Runner, powershell_cmd

Log = Callable[[str], None]

UNDO_FILE = "undo.json"


def backup_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "UsbFixer" / "backups"


def new_backup_dir(root: Optional[Path] = None) -> Path:
    root = root or backup_root()
    path = root / datetime.now().strftime("%Y%m%d-%H%M%S")
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_restore_point(runner: Runner, log: Log) -> bool:
    res = runner(
        powershell_cmd(
            "Checkpoint-Computer -Description 'USB Fixer' -RestorePointType MODIFY_SETTINGS -ErrorAction Stop"
        )
    )
    if res.ok:
        log("نقطهٔ بازیابی ویندوز ساخته شد.")
        return True
    log("نقطهٔ بازیابی ساخته نشد (شاید System Restore خاموشه یا کمتر از ۲۴ ساعت از قبلی گذشته). پشتیبان تنظیمات ساخته می‌شه.")
    return False


def export_registry(keys: list, directory: Path, runner: Runner, log: Log) -> tuple:
    """Export each key to a .reg file. Returns (files, keys that could not be exported, i.e. do not exist yet)."""
    files, missing = [], []
    for i, key in enumerate(keys):
        target = directory / f"reg{i}.reg"
        res = runner(["reg", "export", key, str(target), "/y"])
        if res.ok:
            files.append(str(target))
        else:
            missing.append(key)
            log(f"این کلید هنوز وجود نداشت؛ موقع برگرداندن، مقدار جدید پاک می‌شه: {key}")
    return files, missing


def reg_value_exists(runner: Runner, key: str, name: str) -> bool:
    return runner(["reg", "query", key, "/v", name]).ok


def write_undo(directory: Path, data: dict) -> None:
    data = dict(data, created=datetime.now().isoformat(timespec="seconds"))
    (directory / UNDO_FILE).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def latest_undo_dir(root: Optional[Path] = None) -> Optional[Path]:
    root = root or backup_root()
    if not root.is_dir():
        return None
    for d in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        if (d / UNDO_FILE).is_file():
            return d
    return None


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def hub_power_script(names: list, enable: bool) -> str:
    arr = ",".join(_ps_quote(n) for n in names)
    return (
        f"$names = @({arr}); "
        "Get-CimInstance -Namespace root/wmi -ClassName MSPower_DeviceEnable | "
        "Where-Object { $names -contains $_.InstanceName } | "
        f"ForEach-Object {{ $_.Enable = ${str(enable).lower()}; Set-CimInstance -InputObject $_ }}"
    )


def undo(directory: Path, runner: Runner, log: Log) -> int:
    """Revert what the last run changed. Returns the number of failed steps."""
    data = json.loads((directory / UNDO_FILE).read_text(encoding="utf-8"))
    failed = 0

    def step(label: str, cmd: list) -> None:
        nonlocal failed
        res = runner(cmd)
        log(("✔ " if res.ok else "✘ ") + label)
        if not res.ok:
            failed += 1

    for f in data.get("reg_files", []):
        step(f"reg import {f}", ["reg", "import", f])
    for key, name in data.get("reg_delete", []):
        step(f"reg delete {key} /v {name}", ["reg", "delete", key, "/v", name, "/f"])
    for p in data.get("powercfg", []):
        sub, setting, scheme = p["subgroup"], p["setting"], p.get("scheme", "SCHEME_CURRENT")
        step(f"powercfg AC {scheme}", ["powercfg", "/SETACVALUEINDEX", scheme, sub, setting, str(p["ac"])])
        step(f"powercfg DC {scheme}", ["powercfg", "/SETDCVALUEINDEX", scheme, sub, setting, str(p["dc"])])
    if data.get("powercfg"):
        step("powercfg /SETACTIVE", ["powercfg", "/SETACTIVE", "SCHEME_CURRENT"])
    if data.get("hub_power"):
        step("hub power management", powershell_cmd(hub_power_script(data["hub_power"], True)))
    if data.get("fix_ids"):
        from . import state  # local import: state imports backup

        state.forget(data["fix_ids"], directory.parent)
    return failed
