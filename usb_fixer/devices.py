"""Turn raw device nodes into a list a person understands: what each device is, who made it, is it OK.

Windows lists a single webcam as several nodes ("USB Composite Device", its camera interface, its
microphone...). Here they are grouped back into one device by VID/PID, given a type in plain Persian,
a maker name from the vendor ID, and the best available real name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import strings

# USB vendor IDs of common makers (from the public USB ID list). Unknown IDs just show the hex value.
USB_VENDORS = {
    "045E": "Microsoft", "046D": "Logitech", "05AC": "Apple", "04E8": "Samsung", "054C": "Sony",
    "0781": "SanDisk", "0951": "Kingston", "1058": "Western Digital", "0BC2": "Seagate", "0930": "Toshiba",
    "8564": "Transcend", "125F": "ADATA", "05DC": "Lexar", "18A5": "Verbatim", "154B": "PNY",
    "090C": "Silicon Motion", "058F": "Alcor Micro", "152D": "JMicron", "174C": "ASMedia", "0BDA": "Realtek",
    "05E3": "Genesys Logic", "2109": "VIA Labs", "1A40": "Terminus", "0424": "Microchip (SMSC)", "04D8": "Microchip",
    "1B1C": "Corsair", "1532": "Razer", "1038": "SteelSeries", "3842": "EVGA", "0B05": "ASUS",
    "1462": "MSI", "26CE": "ASRock", "413C": "Dell", "03F0": "HP", "17EF": "Lenovo",
    "04F2": "Chicony", "5986": "Acer", "0C45": "Microdia", "1BCF": "Sunplus", "04D9": "Holtek",
    "8087": "Intel", "8086": "Intel", "1022": "AMD", "0CF3": "Qualcomm Atheros", "0A5C": "Broadcom",
    "0E8D": "MediaTek", "0A12": "Cambridge Silicon Radio", "2357": "TP-Link", "0B95": "ASIX",
    "0403": "FTDI", "067B": "Prolific", "1A86": "QinHeng (CH340)", "10C4": "Silicon Labs",
    "04A9": "Canon", "04B8": "Epson", "04F9": "Brother", "0FD9": "Elgato", "057E": "Nintendo",
    "28DE": "Valve", "0D8C": "C-Media", "1395": "Sennheiser", "0FCE": "Sony Ericsson", "22B8": "Motorola",
    "18D1": "Google", "2717": "Xiaomi", "12D1": "Huawei", "2A70": "OnePlus", "05C6": "Qualcomm",
    "0489": "Foxconn", "13D3": "IMC Networks (AzureWave)", "8644": "Intenso", "13FE": "Kingston",
    "0DD8": "Netac", "1F75": "Innostor", "3538": "Power Quotient", "1005": "Apacer", "0718": "Imation",
}

# Windows device class -> (type key, Persian label). Earlier entries win when a device has several.
TYPE_BY_CLASS = [
    ("Camera", "camera"), ("Image", "camera"),
    ("DiskDrive", "storage"), ("WPD", "storage"), ("CDROM", "storage"),
    ("Keyboard", "keyboard"), ("Mouse", "mouse"),
    ("Bluetooth", "bluetooth"), ("Net", "network"),
    ("AudioEndpoint", "audio"), ("MEDIA", "audio"),
    ("Printer", "printer"), ("Ports", "serial"), ("SmartCardReader", "card"),
    ("Biometric", "biometric"), ("HIDClass", "input"),
]

TYPE_LABEL = {
    "camera": "وب‌کم / دوربین", "storage": "حافظه (فلش یا هارد)", "keyboard": "کیبورد", "mouse": "ماوس",
    "bluetooth": "بلوتوث", "network": "کارت شبکه / وای‌فای", "audio": "صدا (هدست/میکروفون/کارت صدا)",
    "printer": "پرینتر", "serial": "دستگاه سریال (COM)", "card": "کارت‌خوان هوشمند", "biometric": "اثرانگشت",
    "input": "دستگاه ورودی (کیبورد/ماوس/دسته بازی)", "hub": "هاب USB", "root_hub": "هاب اصلی USB (سیستمی)",
    "controller": "کنترلر USB (روی مادربرد)", "unknown": "دستگاه ناشناس", "keyboard_mouse": "کیبورد و ماوس (دانگل بی‌سیم)", "other": "دستگاه USB",
}

GENERIC_NAMES = re.compile(
    r"^(usb composite device|usb input device|usb mass storage device|generic usb hub|usb root hub.*|"
    r"hid-compliant .*|hid keyboard device|usb attached scsi.*|usb video device|usb audio device|"
    r"unknown usb device.*|generic superspeed usb hub|usb2\.0 hub|usb 2\.0 hub)$",
    re.IGNORECASE,
)

VIDPID_RE = re.compile(r"VID_([0-9A-Fa-f]{4})&PID_([0-9A-Fa-f]{4})")


@dataclass
class FriendlyDevice:
    key: str  # VID_PID (or instance id when there is none)
    type: str
    name: str
    vendor: str
    status: str  # ok / error / absent
    error_code: int = 0
    group: str = "yours"  # yours / system / past
    count: int = 1
    ids: list = field(default_factory=list)

    @property
    def type_label(self) -> str:
        return TYPE_LABEL.get(self.type, TYPE_LABEL["other"])

    @property
    def status_text(self) -> str:
        if self.status == "error":
            reason = strings.ERROR_CODES.get(self.error_code, "خطای نامشخص")
            return f"مشکل داره (کد {self.error_code}: {reason})"
        if self.status == "absent":
            return "الان وصل نیست (فقط ردش تو ویندوز مونده)"
        return "سالم و وصل"


def vid_pid(instance_id: str):
    m = VIDPID_RE.search(instance_id)
    return (m.group(1).upper(), m.group(2).upper()) if m else (None, None)


def vendor_name(vid) -> str:
    if not vid:
        return ""
    return USB_VENDORS.get(vid.upper(), f"سازندهٔ ناشناس ({vid.upper()})")


def _is_generic(name: str) -> bool:
    return not name or bool(GENERIC_NAMES.match(name.strip()))


def _type_for(classes: set, names: list, instance_ids: list) -> str:
    upper_ids = " ".join(instance_ids).upper()
    if "ROOT_HUB" in upper_ids:
        return "root_hub"
    if "keyboard" in {c.lower() for c in classes} and "mouse" in {c.lower() for c in classes}:
        return "keyboard_mouse"
    for cls, kind in TYPE_BY_CLASS:
        if cls in classes:
            return kind
    if any("hub" in n.lower() for n in names):
        return "hub"
    if "USBSTOR" in upper_ids or any("mass storage" in n.lower() for n in names):
        return "storage"
    return "other"


def _display_name(real: str, vendor: str, kind: str) -> str:
    known_vendor = vendor and not vendor.startswith("سازندهٔ ناشناس")
    if real:
        if known_vendor and vendor.split()[0].lower() not in real.lower():
            return f"{vendor} {real}"
        return real
    label = TYPE_LABEL.get(kind, TYPE_LABEL["other"])
    return f"{label} {vendor}" if known_vendor else label


def build(snapshot) -> list:
    """Friendly devices: present ones from the node list (grouped), plus 'previously connected' ghosts."""
    nodes = list(getattr(snapshot, "nodes", []) or [])
    by_id = {n.instance_id.upper(): n for n in nodes}

    groups: dict = {}
    for n in nodes:
        vid, pid = vid_pid(n.instance_id)
        if vid is None and n.parent:  # e.g. USBSTOR\Disk... -> its USB parent
            vid, pid = vid_pid(n.parent)
            if vid is None and n.parent.upper() in by_id:
                vid, pid = vid_pid(by_id[n.parent.upper()].parent)
        key = f"{vid}_{pid}" if vid else n.instance_id.upper()
        groups.setdefault(key, []).append(n)

    out = []
    for key, members in groups.items():
        classes = {m.cls for m in members if m.cls}
        names = [m.name for m in members]
        ids = [m.instance_id for m in members]
        vid = key.split("_")[0] if "_" in key and len(key) == 9 else None
        kind = _type_for(classes, names, ids)

        # best real name: what the device reports about itself, then any non-generic node name
        candidates = [m.desc for m in members if m.desc] + names
        real = next((c for c in candidates if not _is_generic(c)), "")
        if vid == "0000":  # the device did not even send its descriptor
            kind, vendor = "unknown", ""
            name = "دستگاه ناشناس (ویندوز نتونست شناسایی‌اش کنه)"
        else:
            vendor = vendor_name(vid) if vid else ""
            name = _display_name(real, vendor, kind)

        bad = [m for m in members if m.error_code]
        roots = [m for m in members if "&MI_" not in m.instance_id.upper() and m.instance_id.upper().startswith("USB\\")]
        out.append(
            FriendlyDevice(
                key=key,
                type=kind,
                name=name,
                vendor=vendor,
                status="error" if bad else "ok",
                error_code=bad[0].error_code if bad else 0,
                group="system" if kind in ("root_hub", "hub") else "yours",
                count=max(1, len(roots)),
                ids=ids,
            )
        )

    present_keys = {d.key for d in out}
    for d in getattr(snapshot, "devices", []):
        if not d.is_ghost:
            continue
        vid, pid = vid_pid(d.instance_id)
        key = f"{vid}_{pid}" if vid else d.instance_id.upper()
        if key in present_keys:
            continue
        kind = "storage" if "mass storage" in d.name.lower() else _type_for(set(), [d.name], [d.instance_id])
        vendor = vendor_name(vid) if vid else ""
        name = _display_name("" if _is_generic(d.name) else d.name, vendor, kind)
        existing = next((x for x in out if x.key == key and x.group == "past"), None)
        if existing:
            existing.count += 1
            existing.ids.append(d.instance_id)
            continue
        out.append(FriendlyDevice(key, kind, name, vendor, "absent", group="past", ids=[d.instance_id]))

    order = {"yours": 0, "system": 1, "past": 2}
    out.sort(key=lambda d: (order[d.group], d.status != "error", d.name.lower()))
    return out
