"""Collect a read-only picture of the machine: board, USB devices, settings.

Nothing here changes the system. The PowerShell scripts only read.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from .system import Runner, powershell_cmd, run

# powercfg GUIDs
USB_SUBGROUP = "2a737441-1930-4402-8d77-b2bebba308a3"
USB_SELECTIVE_SUSPEND = "48e6b7a6-50f5-4782-a5d4-53bb8f07e226"
PCIE_SUBGROUP = "501a4d13-42af-4429-9fd1-a8218c268e20"
PCIE_ASPM = "ee12f906-d277-404b-b6da-e5fa1a576df5"

POWER_SETTINGS = {
    "selective_suspend": (USB_SUBGROUP, USB_SELECTIVE_SUSPEND),
    "pcie_aspm": (PCIE_SUBGROUP, PCIE_ASPM),
}

PCI_VENDORS = {
    "8086": "Intel",
    "1022": "AMD",
    "1B21": "ASMedia",
    "1033": "Renesas (NEC)",
    "1912": "Renesas",
    "1106": "VIA",
    "1B73": "Fresco Logic",
    "1B6F": "Etron",
}

INVENTORY_SCRIPT = r"""# SCRIPT:inventory
$ErrorActionPreference='SilentlyContinue'
$b = Get-CimInstance Win32_BaseBoard | Select-Object -First 1
$bi = Get-CimInstance Win32_BIOS | Select-Object -First 1
$cs = Get-CimInstance Win32_ComputerSystem | Select-Object -First 1
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$os = Get-CimInstance Win32_OperatingSystem | Select-Object -First 1
function Prop($id, $k) { (Get-PnpDeviceProperty -InstanceId $id -KeyName $k -ErrorAction SilentlyContinue).Data }
$all = @(Get-PnpDevice -Class USB)
$devices = @($all | ForEach-Object {
  $n = $_.FriendlyName; if (-not $n) { $n = $_.Name }
  [pscustomobject]@{ name="$n"; instance_id=$_.InstanceId; status="$($_.Status)"; present=[bool]$_.Present; error_code=[int]$_.ConfigManagerErrorCode; manufacturer="$($_.Manufacturer)" }
})
$controllers = @($all | Where-Object { $_.Present -and $_.InstanceId -like 'PCI\*' } | ForEach-Object {
  $dd = Prop $_.InstanceId 'DEVPKEY_Device_DriverDate'
  $ds = ''; if ($dd) { $ds = $dd.ToString('yyyy-MM-dd') }
  [pscustomobject]@{ name="$($_.FriendlyName)"; instance_id=$_.InstanceId; driver_provider="$(Prop $_.InstanceId 'DEVPKEY_Device_DriverProvider')"; driver_version="$(Prop $_.InstanceId 'DEVPKEY_Device_DriverVersion')"; driver_date=$ds }
})
$bd = ''; if ($bi.ReleaseDate) { $bd = $bi.ReleaseDate.ToString('yyyy-MM-dd') }
[pscustomobject]@{
  board_manufacturer="$($b.Manufacturer)"; board_product="$($b.Product)"; board_version="$($b.Version)"
  bios_vendor="$($bi.Manufacturer)"; bios_version="$($bi.SMBIOSBIOSVersion)"; bios_date=$bd
  system_manufacturer="$($cs.Manufacturer)"; system_model="$($cs.Model)"; pc_system_type=[int]$cs.PCSystemType
  cpu="$($cpu.Name)"; os_caption="$($os.Caption)"; os_build="$($os.BuildNumber)"
  devices=$devices; controllers=$controllers
} | ConvertTo-Json -Depth 5 -Compress
"""

STATE_SCRIPT = r"""# SCRIPT:state
$ErrorActionPreference='SilentlyContinue'
function RegVal($p, $n) { $v = Get-ItemProperty -Path $p -Name $n -ErrorAction SilentlyContinue; if ($null -ne $v) { $v.$n } else { $null } }
$svc = @{}
foreach ($n in 'PlugPlay') { $s = Get-Service -Name $n; if ($s) { $svc[$n] = [int]$s.Status } else { $svc[$n] = $null } }
$disks = @(Get-Disk | Where-Object { $_.BusType -eq 'USB' } | ForEach-Object {
  $d = $_
  $parts = @(Get-Partition -DiskNumber $d.Number | ForEach-Object { [pscustomobject]@{ number=[int]$_.PartitionNumber; letter="$($_.DriveLetter)".Trim(); type="$($_.Type)"; size=[int64]$_.Size } })
  [pscustomobject]@{ number=[int]$d.Number; name="$($d.FriendlyName)"; offline=[bool]$d.IsOffline; readonly=[bool]$d.IsReadOnly; size=[int64]$d.Size; partitions=$parts }
})
$hub = @(Get-CimInstance -Namespace root/wmi -ClassName MSPower_DeviceEnable | Where-Object { $_.InstanceName -like 'USB*' -and $_.Enable } | ForEach-Object { $_.InstanceName })
$since = (Get-Date).AddDays(-7)
$ev = @(Get-WinEvent -FilterHashtable @{LogName='System'; Level=2,3; StartTime=$since} | Where-Object { $_.ProviderName -match 'USB|Kernel-PnP' } | Group-Object ProviderName,Id | Sort-Object Count -Descending | Select-Object -First 10 | ForEach-Object {
  $m = ("$($_.Group[0].Message)" -replace '\s+', ' ')
  [pscustomobject]@{ provider="$($_.Group[0].ProviderName)"; id=[int]$_.Group[0].Id; count=[int]$_.Count; sample=$m.Substring(0, [Math]::Min(160, $m.Length)) }
})
[pscustomobject]@{
  services=$svc
  usbstor_start=(RegVal 'HKLM:\SYSTEM\CurrentControlSet\Services\USBSTOR' 'Start')
  uaspstor_start=(RegVal 'HKLM:\SYSTEM\CurrentControlSet\Services\UASPStor' 'Start')
  deny_all=(RegVal 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\RemovableStorageDevices' 'Deny_All')
  write_protect=(RegVal 'HKLM:\SYSTEM\CurrentControlSet\Control\StorageDevicePolicies' 'WriteProtect')
  fast_startup=(RegVal 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' 'HiberbootEnabled')
  hub_power=$hub; disks=$disks; events=$ev
} | ConvertTo-Json -Depth 6 -Compress
"""


class ScanError(Exception):
    """The machine could not be scanned (not Windows, PowerShell missing...)."""


@dataclass
class Controller:
    name: str
    instance_id: str
    vendor_id: str = ""
    device_id: str = ""
    driver_provider: str = ""
    driver_version: str = ""
    driver_date: str = ""

    @property
    def vendor(self) -> str:
        return PCI_VENDORS.get(self.vendor_id, self.vendor_id or "?")


@dataclass
class UsbDevice:
    name: str
    instance_id: str
    status: str = ""
    present: bool = True
    error_code: int = 0
    manufacturer: str = ""

    @property
    def has_error(self) -> bool:
        return self.present and self.error_code not in (0, None)

    @property
    def is_ghost(self) -> bool:
        return not self.present

    @property
    def is_unknown(self) -> bool:
        low = self.name.lower()
        return self.present and (
            low.startswith("unknown usb device")
            or self.instance_id.upper().startswith("USB\\VID_0000")
            or self.instance_id.upper().startswith("USB\\UNKNOWN")
        )


@dataclass
class SystemInfo:
    board_manufacturer: str = ""
    board_product: str = ""
    board_version: str = ""
    bios_vendor: str = ""
    bios_version: str = ""
    bios_date: Optional[date] = None
    system_manufacturer: str = ""
    system_model: str = ""
    is_laptop: bool = False
    cpu: str = ""
    os_caption: str = ""
    os_build: str = ""
    controllers: list = field(default_factory=list)


@dataclass
class DiskPartition:
    number: int
    letter: str = ""
    type: str = ""
    size: int = 0


@dataclass
class UsbDisk:
    number: int
    name: str = ""
    offline: bool = False
    readonly: bool = False
    size: int = 0
    partitions: list = field(default_factory=list)


@dataclass
class EventGroup:
    provider: str
    id: int
    count: int
    sample: str = ""


@dataclass
class State:
    plugplay_status: Optional[int] = None
    usbstor_start: Optional[int] = None
    uaspstor_start: Optional[int] = None
    deny_all: Optional[int] = None
    write_protect: Optional[int] = None
    fast_startup: Optional[int] = None
    hub_power: list = field(default_factory=list)
    disks: list = field(default_factory=list)
    events: list = field(default_factory=list)


@dataclass
class Snapshot:
    system: SystemInfo
    devices: list
    state: State
    power: dict  # name -> (ac, dc) or None
    warnings: list = field(default_factory=list)


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_date(text: str) -> Optional[date]:
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _load_json(text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("empty output")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("unexpected JSON")
    return data


def parse_inventory(data: dict) -> tuple[SystemInfo, list]:
    controllers = []
    for c in _as_list(data.get("controllers")):
        iid = c.get("instance_id", "")
        m = re.search(r"VEN_([0-9A-Fa-f]{4})&DEV_([0-9A-Fa-f]{4})", iid)
        controllers.append(
            Controller(
                name=c.get("name") or iid,
                instance_id=iid,
                vendor_id=m.group(1).upper() if m else "",
                device_id=m.group(2).upper() if m else "",
                driver_provider=c.get("driver_provider", ""),
                driver_version=c.get("driver_version", ""),
                driver_date=c.get("driver_date", ""),
            )
        )
    system = SystemInfo(
        board_manufacturer=data.get("board_manufacturer", ""),
        board_product=data.get("board_product", ""),
        board_version=data.get("board_version", ""),
        bios_vendor=data.get("bios_vendor", ""),
        bios_version=data.get("bios_version", ""),
        bios_date=_parse_date(data.get("bios_date", "")),
        system_manufacturer=data.get("system_manufacturer", ""),
        system_model=data.get("system_model", ""),
        is_laptop=_int(data.get("pc_system_type")) == 2,
        cpu=(data.get("cpu") or "").strip(),
        os_caption=data.get("os_caption", ""),
        os_build=data.get("os_build", ""),
        controllers=controllers,
    )
    devices = [
        UsbDevice(
            name=d.get("name") or d.get("instance_id", ""),
            instance_id=d.get("instance_id", ""),
            status=d.get("status", ""),
            present=bool(d.get("present", True)),
            error_code=_int(d.get("error_code")) or 0,
            manufacturer=d.get("manufacturer", ""),
        )
        for d in _as_list(data.get("devices"))
    ]
    return system, devices


def parse_state(data: dict) -> State:
    disks = []
    for d in _as_list(data.get("disks")):
        parts = [
            DiskPartition(
                number=_int(p.get("number")) or 0,
                letter=(p.get("letter") or "").strip(),
                type=p.get("type", ""),
                size=_int(p.get("size")) or 0,
            )
            for p in _as_list(d.get("partitions"))
        ]
        disks.append(
            UsbDisk(
                number=_int(d.get("number")) or 0,
                name=d.get("name", ""),
                offline=bool(d.get("offline")),
                readonly=bool(d.get("readonly")),
                size=_int(d.get("size")) or 0,
                partitions=parts,
            )
        )
    events = [
        EventGroup(e.get("provider", ""), _int(e.get("id")) or 0, _int(e.get("count")) or 0, e.get("sample", ""))
        for e in _as_list(data.get("events"))
    ]
    services = data.get("services") or {}
    return State(
        plugplay_status=_int(services.get("PlugPlay")),
        usbstor_start=_int(data.get("usbstor_start")),
        uaspstor_start=_int(data.get("uaspstor_start")),
        deny_all=_int(data.get("deny_all")),
        write_protect=_int(data.get("write_protect")),
        fast_startup=_int(data.get("fast_startup")),
        hub_power=[h for h in _as_list(data.get("hub_power")) if isinstance(h, str)],
        disks=disks,
        events=events,
    )


def parse_powercfg(text: str) -> Optional[tuple[int, int]]:
    """Return (ac, dc) from `powercfg /Q` output, independent of the Windows language."""
    values = re.findall(r"0x([0-9a-fA-F]{8})", text)
    if len(values) < 2:
        return None
    return int(values[-2], 16), int(values[-1], 16)


def read_power(runner: Runner) -> dict:
    result = {}
    for name, (sub, setting) in POWER_SETTINGS.items():
        res = runner(["powercfg", "/Q", "SCHEME_CURRENT", sub, setting])
        result[name] = parse_powercfg(res.out) if res.ok else None
    return result


def take_snapshot(runner: Runner = run) -> Snapshot:
    warnings: list[str] = []
    res = runner(powershell_cmd(INVENTORY_SCRIPT))
    try:
        if not res.ok:
            raise ValueError(res.err.strip() or f"exit code {res.rc}")
        system, devices = parse_inventory(_load_json(res.out))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ScanError(str(exc)) from exc

    state = State()
    res = runner(powershell_cmd(STATE_SCRIPT))
    try:
        if not res.ok:
            raise ValueError(res.err.strip() or f"exit code {res.rc}")
        state = parse_state(_load_json(res.out))
    except (ValueError, json.JSONDecodeError) as exc:
        warnings.append(f"state: {exc}")

    return Snapshot(system, devices, state, read_power(runner), warnings)
