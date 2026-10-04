"""Fixes. Each fix turns a Finding into concrete commands (Steps) that are shown to the
user first and only run after they confirm."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import backup
from .diagnostics import Finding
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
}

REG_POWER = r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power"
REG_USBSTOR = r"HKLM\SYSTEM\CurrentControlSet\Services\USBSTOR"
REG_UASP = r"HKLM\SYSTEM\CurrentControlSet\Services\UASPStor"
REG_POLICY = r"HKLM\SOFTWARE\Policies\Microsoft\Windows\RemovableStorageDevices"
REG_STORAGE_POLICY = r"HKLM\SYSTEM\CurrentControlSet\Control\StorageDevicePolicies"


@dataclass
class Step:
    shown: str
    cmd: list
    backup_reg: list = field(default_factory=list)
    undo: Optional[dict] = None


def _ps_step(script: str, **kw) -> Step:
    return Step(shown=script, cmd=powershell_cmd(script), **kw)


def _powercfg_steps(sub: str, setting: str, original) -> list:
    undo = {"type": "powercfg", "subgroup": sub, "setting": setting, "ac": original[0], "dc": original[1]}
    return [
        Step(f"powercfg /SETACVALUEINDEX SCHEME_CURRENT {sub} {setting} 0",
             ["powercfg", "/SETACVALUEINDEX", "SCHEME_CURRENT", sub, setting, "0"], undo=undo),
        Step(f"powercfg /SETDCVALUEINDEX SCHEME_CURRENT {sub} {setting} 0",
             ["powercfg", "/SETDCVALUEINDEX", "SCHEME_CURRENT", sub, setting, "0"]),
        Step("powercfg /SETACTIVE SCHEME_CURRENT", ["powercfg", "/SETACTIVE", "SCHEME_CURRENT"]),
    ]


def _reg_add(key: str, name: str, value: int) -> Step:
    return Step(
        f'reg add "{key}" /v {name} /t REG_DWORD /d {value} /f',
        ["reg", "add", key, "/v", name, "/t", "REG_DWORD", "/d", str(value), "/f"],
        backup_reg=[key],
    )


def _reg_delete(key: str, name: str) -> Step:
    return Step(
        f'reg delete "{key}" /v {name} /f',
        ["reg", "delete", key, "/v", name, "/f"],
        backup_reg=[key],
    )


def build_steps(finding: Finding) -> list:
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
        return _powercfg_steps(USB_SUBGROUP, USB_SELECTIVE_SUSPEND, t[0])
    if fix == "disable_aspm":
        return _powercfg_steps(PCIE_SUBGROUP, PCIE_ASPM, t[0])
    if fix == "disable_hub_power":
        script = (
            "Get-CimInstance -Namespace root/wmi -ClassName MSPower_DeviceEnable | "
            "Where-Object { $_.InstanceName -like 'USB*' -and $_.Enable } | "
            "ForEach-Object { $_.Enable = $false; Set-CimInstance -InputObject $_ }"
        )
        return [_ps_step(script, undo={"type": "hub_power", "names": list(t)})]
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
    return []


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


def execute(steps: list, runner: Runner, log, root=None) -> ExecResult:
    result = ExecResult()
    directory = backup.new_backup_dir(root)
    result.backup_dir = str(directory)
    result.restore_point = backup.create_restore_point(runner, log)

    keys = sorted({k for s in steps for k in s.backup_reg})
    reg_files = backup.export_registry(keys, directory, runner, log)
    undo = {"reg_files": reg_files, "powercfg": [], "hub_power": []}
    for s in steps:
        if not s.undo:
            continue
        if s.undo["type"] == "powercfg":
            undo["powercfg"].append({k: v for k, v in s.undo.items() if k != "type"})
        elif s.undo["type"] == "hub_power":
            undo["hub_power"].extend(s.undo["names"])
    backup.write_undo(directory, undo)

    for s in steps:
        res = runner(s.cmd)
        if res.ok:
            result.ok += 1
            log(f"✔ {s.shown}")
        else:
            result.failed += 1
            log(f"✘ {s.shown}\n   {(res.err or res.out).strip()[:300]}")
    runner(["pnputil", "/scan-devices"])
    return result
