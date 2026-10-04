"""A fake Windows machine, so the program can be exercised (tests, --demo) on any OS."""

from __future__ import annotations

import json
from typing import Optional, Sequence

from .system import CmdResult, decode_powershell_cmd

DEMO_INVENTORY = {
    "board_manufacturer": "ASUSTeK COMPUTER INC.",
    "board_product": "ROG STRIX B450-F GAMING",
    "board_version": "Rev X.0x",
    "bios_vendor": "American Megatrends Inc.",
    "bios_version": "3202",
    "bios_date": "2020-03-10",
    "system_manufacturer": "System manufacturer",
    "system_model": "System Product Name",
    "pc_system_type": 1,
    "cpu": "AMD Ryzen 5 3600 6-Core Processor        ",
    "os_caption": "Microsoft Windows 11 Pro",
    "os_build": "22631",
    "controllers": [
        {
            "name": "AMD USB 3.10 eXtensible Host Controller - 1.10 (Microsoft)",
            "instance_id": "PCI\\VEN_1022&DEV_43D5&SUBSYS_11421B21&REV_01\\4&2A5C2F4D&0&0A08",
            "driver_provider": "Microsoft",
            "driver_version": "10.0.22621.1",
            "driver_date": "2006-06-21",
        },
        {
            "name": "ASMedia USB 3.1 eXtensible Host Controller",
            "instance_id": "PCI\\VEN_1B21&DEV_1142&SUBSYS_11421B21&REV_00\\4&1A2B3C4D&0&0B08",
            "driver_provider": "Microsoft",
            "driver_version": "10.0.22621.1",
            "driver_date": "2006-06-21",
        },
    ],
    "devices": [
        {"name": "USB Root Hub (USB 3.0)", "instance_id": "USB\\ROOT_HUB30\\4&1B2C3D&0&0", "status": "OK", "present": True, "error_code": 0, "manufacturer": "(Standard USB HUBs)"},
        {"name": "Unknown USB Device (Device Descriptor Request Failed)", "instance_id": "USB\\VID_0000&PID_0002\\5&2F1A&0&3", "status": "Error", "present": True, "error_code": 43, "manufacturer": "(Standard USB HUBs)"},
        {"name": "USB Composite Device", "instance_id": "USB\\VID_046D&PID_C52B\\5&2F1A&0&1", "status": "Error", "present": True, "error_code": 10, "manufacturer": "(Standard USB Host Controller)"},
        {"name": "USB Mass Storage Device", "instance_id": "USB\\VID_0781&PID_5581\\0123456789", "status": "Unknown", "present": False, "error_code": 0, "manufacturer": "Compatible USB storage device"},
        {"name": "USB Mass Storage Device", "instance_id": "USB\\VID_090C&PID_1000\\ABCDEF", "status": "Unknown", "present": False, "error_code": 0, "manufacturer": "Compatible USB storage device"},
    ],
}

DEMO_STATE = {
    "services": {"PlugPlay": 4},
    "usbstor_start": 3,
    "uaspstor_start": 3,
    "deny_all": None,
    "write_protect": 1,
    "fast_startup": 1,
    "hub_power": ["USB\\ROOT_HUB30\\4&1B2C3D&0&0_0"],
    "disks": [
        {"number": 2, "name": "SanDisk Ultra USB 3.0", "offline": False, "readonly": False, "size": 31457280000,
         "partitions": [{"number": 1, "letter": "", "type": "Basic", "size": 31455000000}]},
    ],
    "events": [
        {"provider": "Microsoft-Windows-USB-USBHUB3", "id": 43, "count": 6, "sample": "Enumeration of device on port 3 failed."},
    ],
}

POWERCFG_OUT = (
    "Power Setting GUID: 48e6b7a6-50f5-4782-a5d4-53bb8f07e226  (USB selective suspend setting)\n"
    "  Minimum Possible Setting: 0x00000000\n  Maximum Possible Setting: 0x00000001\n"
    "  Possible Settings increment: 0x00000001\n  Possible Settings units: \n"
    "Current AC Power Setting Index: 0x00000001\nCurrent DC Power Setting Index: 0x00000001\n"
)


ASPM_OFF_OUT = "Current AC Power Setting Index: 0x00000000\nCurrent DC Power Setting Index: 0x00000000\n"


class DemoRunner:
    """Answers like Windows would, and remembers every command it was asked to run."""

    def __init__(self, inventory: Optional[dict] = None, state: Optional[dict] = None, power: str = POWERCFG_OUT):
        self.inventory = DEMO_INVENTORY if inventory is None else inventory
        self.state = DEMO_STATE if state is None else state
        self.power = power
        self.calls: list = []

    def __call__(self, cmd: Sequence[str]) -> CmdResult:
        cmd = list(cmd)
        self.calls.append(cmd)
        script = decode_powershell_cmd(cmd)
        if script is not None:
            if "# SCRIPT:inventory" in script:
                return CmdResult(0, json.dumps(self.inventory))
            if "# SCRIPT:state" in script:
                return CmdResult(0, json.dumps(self.state))
            return CmdResult(0, "")
        if cmd[0] == "powercfg" and len(cmd) > 1 and cmd[1] == "/Q":
            if "ee12f906-d277-404b-b6da-e5fa1a576df5" in cmd:
                return CmdResult(0, ASPM_OFF_OUT)
            return CmdResult(0, self.power)
        return CmdResult(0, "")
