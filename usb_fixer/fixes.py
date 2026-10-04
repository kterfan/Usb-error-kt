"""Fixes. Each fix turns a Finding into concrete commands (Steps) that are shown to the
user first and only run after they confirm."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import backup, state
from .diagnostics import PERSISTENT_FIXES, Finding
from .snapshot import PCIE_ASPM, PCIE_SUBGROUP, USB_SELECTIVE_SUSPEND, USB_SUBGROUP
from .system import Runner, powershell_cmd

# Fixes that start ticked in the UI. The rest are optional or carry some risk.
DEFAULT_CHECKED = {
    "restart_errors": True,
    "remove_ghosts": True,
    "disable_suspend": True,
    "disable_hub_power": True,
    "enable_usbstor": True,
    "enable_uasp": True,
    "disk_online": True,
    "assign_letter": True,
    "disable_fast_startup": False,
    "disable_aspm": False,
    "remove_storage_policy": False,
    "remove_write_protect": False,
    "disk_writable": False,
    "reset_usb_stack": False,
}

REG_POWER = r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power"
REG_USBSTOR = r"HKLM\SYSTEM\CurrentControlSet\Services\USBSTOR"
REG_UASP = r"HKLM\SYSTEM\CurrentControlSet\Services\UASPStor"
REG_POLICY = r"HKLM\SOFTWARE\Policies\Microsoft\Windows\RemovableStorageDevices"
REG_STORAGE_POLICY = r"HKLM\SYSTEM\CurrentControlSet\Control\StorageDevicePolicies"
# Machine-wide switch of the USB hub driver; also covers devices plugged in later (documented by Microsoft).
REG_USB_SERVICE = r"HKLM\SYSTEM\CurrentControlSet\Services\USB"

HUB_POWER_OFF = (
    "Get-CimInstance -Namespace root/wmi -ClassName MSPower_DeviceEnable | "
    "Where-Object { $_.InstanceName -like 'USB*' -and $_.Enable } | "
    "ForEach-Object { $_.Enable = $false; Set-CimInstance -InputObject $_ }"
)


@dataclass
class Step:
    shown: str
    cmd: list
    backup_reg: list = field(default_factory=list)
    undo: Optional[dict] = None
    fix_id: str = ""
    reg_value: Optional[tuple] = None  # (key, name) written by this step, deleted on undo if it did not exist


def _ps_step(script: str, **kw) -> Step:
    return Step(shown=script, cmd=powershell_cmd(script), **kw)


def _schemes(target) -> dict:
    """Targets of the power fixes: {scheme guid: (ac, dc)}; older form (ac, dc) means the active plan only."""
    if isinstance(target, dict) and target:
        return target
    return {"SCHEME_CURRENT": tuple(target) if target else (1, 1)}


def _powercfg_steps(sub: str, setting: str, target) -> list:
    steps = []
    for scheme, original in _schemes(target).items():
        undo = {"type": "powercfg", "scheme": scheme, "subgroup": sub, "setting": setting,
                "ac": original[0], "dc": original[1]}
        steps.append(Step(f"powercfg /SETACVALUEINDEX {scheme} {sub} {setting} 0",
                          ["powercfg", "/SETACVALUEINDEX", scheme, sub, setting, "0"], undo=undo))
        steps.append(Step(f"powercfg /SETDCVALUEINDEX {scheme} {sub} {setting} 0",
                          ["powercfg", "/SETDCVALUEINDEX", scheme, sub, setting, "0"]))
    steps.append(Step("powercfg /SETACTIVE SCHEME_CURRENT", ["powercfg", "/SETACTIVE", "SCHEME_CURRENT"]))
    return steps


def _reg_add(key: str, name: str, value: int) -> Step:
    return Step(
        f'reg add "{key}" /v {name} /t REG_DWORD /d {value} /f',
        ["reg", "add", key, "/v", name, "/t", "REG_DWORD", "/d", str(value), "/f"],
        backup_reg=[key],
        reg_value=(key, name),
    )


def _reg_delete(key: str, name: str) -> Step:
    return Step(
        f'reg delete "{key}" /v {name} /f',
        ["reg", "delete", key, "/v", name, "/f"],
        backup_reg=[key],
    )


def build_steps(finding: Finding) -> list:
    steps = _build(finding)
    for s in steps:
        s.fix_id = finding.fix_id or ""
    return steps


def _build(finding: Finding) -> list:
    fix = finding.fix_id
    t = finding.targets
    if fix == "restart_errors":
        steps = []
        for iid, code in t:
            verb = "/enable-device" if code == 22 else "/restart-device"
            steps.append(Step(f"pnputil {verb} {iid}", ["pnputil", verb, iid]))
        return steps
    if fix == "remove_ghosts":
        return [Step(f"pnputil /remove-device {iid}", ["pnputil", "/remove-device", iid]) for iid in t]
    if fix == "disable_suspend":
        return _powercfg_steps(USB_SUBGROUP, USB_SELECTIVE_SUSPEND, t[0] if t else None) + [
            _reg_add(REG_USB_SERVICE, "DisableSelectiveSuspend", 1)
        ]
    if fix == "disable_aspm":
        return _powercfg_steps(PCIE_SUBGROUP, PCIE_ASPM, t[0] if t else None)
    if fix == "disable_hub_power":
        return [_ps_step(HUB_POWER_OFF, undo={"type": "hub_power", "names": list(t)})]
    if fix == "disable_fast_startup":
        return [_reg_add(REG_POWER, "HiberbootEnabled", 0)]
    if fix == "enable_usbstor":
        return [_reg_add(REG_USBSTOR, "Start", 3)]
    if fix == "enable_uasp":
        return [_reg_add(REG_UASP, "Start", 3)]
    if fix == "remove_storage_policy":
        return [_reg_delete(REG_POLICY, "Deny_All")]
    if fix == "remove_write_protect":
        return [_reg_add(REG_STORAGE_POLICY, "WriteProtect", 0)]
    if fix == "disk_online":
        return [_ps_step(f"Set-Disk -Number {n} -IsOffline $false") for n in t]
    if fix == "disk_writable":
        return [_ps_step(f"Set-Disk -Number {n} -IsReadOnly $false") for n in t]
    if fix == "assign_letter":
        return [
            _ps_step(f"Add-PartitionAccessPath -DiskNumber {d} -PartitionNumber {p} -AssignDriveLetter")
            for d, p in t
        ]
    if fix == "reset_usb_stack":
        return [Step(f"pnputil /restart-device {iid}", ["pnputil", "/restart-device", iid]) for iid in t]
    return []


def reset_stack_finding(snapshot) -> Optional[Finding]:
    """Not a problem by itself: an optional 'reset all USB controllers' action offered on the page."""
    ids = [c.instance_id for c in snapshot.system.controllers]
    if not ids:
        return None
    return Finding("reset_usb_stack", "info", fix_id="reset_usb_stack", targets=ids,
                   title_override="ریست کامل USB (همهٔ کنترلرها)",
                   detail_override="همهٔ کنترلرهای USB یک بار ریست می‌شن. وقتی مفیده که چند دستگاه با هم مشکل دارن یا بعد از Sleep هیچ USBای کار نمی‌کنه.")


def collect_steps(findings: list) -> list:
    """Steps for all selected findings, without duplicates, order preserved."""
    seen = set()
    steps = []
    for f in findings:
        for s in build_steps(f):
            key = tuple(s.cmd)
            if key not in seen:
                seen.add(key)
                steps.append(s)
    return steps


@dataclass
class ExecResult:
    ok: int = 0
    failed: int = 0
    restore_point: bool = False
    backup_dir: Optional[str] = None
    applied: list = field(default_factory=list)  # fix ids whose steps all succeeded


def execute(steps: list, runner: Runner, log, root=None, restore_point: bool = True) -> ExecResult:
    result = ExecResult()
    directory = backup.new_backup_dir(root)
    result.backup_dir = str(directory)
    if restore_point:
        result.restore_point = backup.create_restore_point(runner, log)

    keys = sorted({k for s in steps for k in s.backup_reg})
    reg_files, _missing = backup.export_registry(keys, directory, runner, log)
    undo = {"reg_files": reg_files, "powercfg": [], "hub_power": [], "reg_delete": [], "fix_ids": []}
    for s in steps:
        # "reg import" only restores values that existed; a value we create must be deleted on undo
        if s.reg_value and list(s.reg_value) not in undo["reg_delete"] and not backup.reg_value_exists(runner, *s.reg_value):
            undo["reg_delete"].append(list(s.reg_value))
        if not s.undo:
            continue
        if s.undo["type"] == "powercfg":
            undo["powercfg"].append({k: v for k, v in s.undo.items() if k != "type"})
        elif s.undo["type"] == "hub_power":
            undo["hub_power"].extend(s.undo["names"])

    failed_fixes = set()
    for s in steps:
        res = runner(s.cmd)
        if res.ok:
            result.ok += 1
            log(f"✔ {s.shown}")
        else:
            result.failed += 1
            failed_fixes.add(s.fix_id)
            log(f"✘ {s.shown}\n   {(res.err or res.out).strip()[:300]}")
    runner(["pnputil", "/scan-devices"])

    done = []
    for s in steps:
        if s.fix_id and s.fix_id not in failed_fixes and s.fix_id not in done:
            done.append(s.fix_id)
    result.applied = done
    undo["fix_ids"] = [f for f in done if f in PERSISTENT_FIXES]
    backup.write_undo(directory, undo)
    state.record_applied(undo["fix_ids"], root)
    return result
