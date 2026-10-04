"""Turn a Snapshot into a list of findings (problems), each with a proposed fix."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from urllib.parse import quote_plus

from . import knowledge, strings
from .snapshot import Snapshot, SystemInfo, take_snapshot
from .system import Runner, run

SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}
SUPPORT_LINK_MANUAL = {"update_bios", "update_chipset", "install_driver"}


@dataclass
class Finding:
    key: str
    severity: str
    params: dict = field(default_factory=dict)
    fix_id: Optional[str] = None
    targets: list = field(default_factory=list)
    manual: list = field(default_factory=list)
    links: list = field(default_factory=list)  # (label, url)
    title_override: Optional[str] = None
    detail_override: Optional[str] = None

    @property
    def title(self) -> str:
        if self.title_override:
            return self.title_override
        return strings.FINDINGS[self.key][0]

    @property
    def detail(self) -> str:
        if self.detail_override:
            return self.detail_override
        return strings.FINDINGS[self.key][1].format(**self.params)

    @property
    def manual_texts(self) -> list:
        return [strings.MANUAL.get(m, m) for m in self.manual]


@dataclass
class ScanResult:
    snapshot: Snapshot
    findings: list


def _error_lines(devices) -> str:
    lines = []
    for d in devices:
        reason = strings.ERROR_CODES.get(d.error_code, "کد خطای نامشخص")
        lines.append(f"• {d.name} (کد {d.error_code}): {reason}")
    return "\n".join(lines)


def _plain_lines(items) -> str:
    return "\n".join(f"• {i}" for i in items)


def check_controllers(snap: Snapshot) -> list:
    if snap.system.controllers:
        return []
    if snap.system.is_virtual:
        return [Finding("virtual_machine", "info")]
    # A machine with no USB devices at all and no controller is the suspicious case.
    return [
        Finding(
            "no_controller",
            "error",
            manual=["update_chipset", "xhci_handoff", "check_hardware"],
        )
    ]


def check_devices(snap: Snapshot) -> list:
    out = []
    errors = [d for d in snap.devices if d.has_error and not d.is_unknown]
    if errors:
        manual = []
        codes = {d.error_code for d in errors}
        if codes & {28, 31, 39}:
            manual.append("install_driver")
        if codes & {10, 43, 41, 24}:
            manual.append("try_port_cable")
        out.append(
            Finding(
                "device_errors",
                "error",
                params={"lines": _error_lines(errors)},
                fix_id="restart_errors",
                targets=[(d.instance_id, d.error_code) for d in errors],
                manual=manual,
            )
        )
    unknown = [d for d in snap.devices if d.is_unknown]
    if unknown:
        out.append(
            Finding(
                "unknown_devices",
                "warn",
                params={"lines": _plain_lines(f"{d.name} ({d.instance_id})" for d in unknown)},
                fix_id="restart_errors",
                targets=[(d.instance_id, d.error_code) for d in unknown],
                manual=["try_port_cable", "xhci_handoff"],
            )
        )
    ghosts = [d for d in snap.devices if d.is_ghost and not d.instance_id.upper().startswith("ROOT\\")]
    if ghosts:
        out.append(
            Finding(
                "ghost_devices",
                "info",
                params={"count": len(ghosts)},
                fix_id="remove_ghosts",
                targets=[d.instance_id for d in ghosts],
            )
        )
    return out


def check_drivers(snap: Snapshot) -> list:
    generic = [
        c
        for c in snap.system.controllers
        if c.driver_provider.lower().startswith("microsoft") and c.vendor_id in {"1B21", "1033", "1912", "1B73", "1B6F", "1106"}
    ]
    if not generic:
        return []
    lines = _plain_lines(f"{c.name} ({c.vendor}) نسخهٔ {c.driver_version or '?'}" for c in generic)
    return [Finding("ms_default_driver", "info", params={"lines": lines}, manual=["update_chipset"])]


def check_power(snap: Snapshot) -> list:
    out = []
    ss = snap.power.get("selective_suspend")
    if ss and (ss[0] == 1 or ss[1] == 1):
        out.append(
            Finding(
                "selective_suspend",
                "warn",
                params={"ac": "روشن" if ss[0] == 1 else "خاموش", "dc": "روشن" if ss[1] == 1 else "خاموش"},
                fix_id="disable_suspend",
                targets=[ss],
            )
        )
    if snap.state.hub_power:
        out.append(
            Finding(
                "hub_power",
                "warn",
                params={"count": len(snap.state.hub_power)},
                fix_id="disable_hub_power",
                targets=list(snap.state.hub_power),
            )
        )
    if snap.state.fast_startup == 1:
        out.append(Finding("fast_startup", "info", fix_id="disable_fast_startup"))
    aspm = snap.power.get("pcie_aspm")
    if aspm and (aspm[0] != 0 or aspm[1] != 0):
        out.append(
            Finding(
                "pcie_aspm",
                "info",
                params={"ac": "روشن" if aspm[0] else "خاموش", "dc": "روشن" if aspm[1] else "خاموش"},
                fix_id="disable_aspm",
                targets=[aspm],
            )
        )
    return out


def check_storage(snap: Snapshot) -> list:
    out = []
    st = snap.state
    if st.usbstor_start == 4:
        out.append(Finding("usbstor_disabled", "error", fix_id="enable_usbstor"))
    if st.uaspstor_start == 4:
        out.append(Finding("uasp_disabled", "warn", fix_id="enable_uasp"))
    if st.deny_all == 1:
        out.append(Finding("storage_policy", "warn", fix_id="remove_storage_policy"))
    if st.write_protect == 1:
        out.append(Finding("write_protect", "warn", fix_id="remove_write_protect"))

    offline = [d for d in st.disks if d.offline]
    if offline:
        out.append(
            Finding(
                "usb_disk_offline",
                "warn",
                params={"lines": _plain_lines(f"دیسک {d.number}: {d.name}" for d in offline)},
                fix_id="disk_online",
                targets=[d.number for d in offline],
            )
        )
    readonly = [d for d in st.disks if d.readonly and not d.offline]
    if readonly:
        out.append(
            Finding(
                "usb_disk_readonly",
                "info",
                params={"lines": _plain_lines(f"دیسک {d.number}: {d.name}" for d in readonly)},
                fix_id="disk_writable",
                targets=[d.number for d in readonly],
            )
        )
    missing = []
    for d in st.disks:
        if d.offline:
            continue
        for p in d.partitions:
            if not p.letter and p.size > 0 and p.type.lower() in {"basic", "ifs", ""}:
                missing.append((d, p))
    if missing:
        out.append(
            Finding(
                "usb_disk_no_letter",
                "warn",
                params={"lines": _plain_lines(f"دیسک {d.number} ({d.name}) پارتیشن {p.number}" for d, p in missing)},
                fix_id="assign_letter",
                targets=[(d.number, p.number) for d, p in missing],
            )
        )
    return out


def check_events(snap: Snapshot) -> list:
    if not snap.state.events:
        return []
    lines = _plain_lines(f"{e.provider} (شناسه {e.id}) × {e.count}: {e.sample}" for e in snap.state.events)
    return [Finding("event_errors", "info", params={"lines": lines})]


def check_knowledge(snap: Snapshot, today: date, rules: list) -> list:
    out = []
    for rule in rules:
        if not knowledge.matches(rule.get("when", {}), snap.system, today):
            continue
        if rule.get("builtin") == "bios_old":
            age = knowledge.bios_age_days(snap.system, today) or 0
            out.append(
                Finding(
                    "bios_old",
                    rule.get("severity", "info"),
                    params={
                        "version": snap.system.bios_version or "?",
                        "date": snap.system.bios_date.isoformat() if snap.system.bios_date else "?",
                        "years": age // 365,
                    },
                    manual=list(rule.get("manual", [])),
                )
            )
        else:
            out.append(
                Finding(
                    rule["id"],
                    rule.get("severity", "info"),
                    manual=list(rule.get("manual", [])),
                    title_override=rule.get("title"),
                    detail_override=rule.get("detail"),
                )
            )
    return out


def support_url(system: SystemInfo) -> str:
    if system.is_laptop and system.system_model:
        who = f"{system.system_manufacturer} {system.system_model}"
    else:
        who = f"{system.board_manufacturer} {system.board_product}"
    return "https://www.google.com/search?q=" + quote_plus(f"{who} support drivers BIOS")


def analyze(snap: Snapshot, today: Optional[date] = None, rules: Optional[list] = None) -> list:
    today = today or date.today()
    if rules is None:
        rules = knowledge.load_rules()
    findings = (
        check_controllers(snap)
        + check_devices(snap)
        + check_drivers(snap)
        + check_power(snap)
        + check_storage(snap)
        + check_events(snap)
        + check_knowledge(snap, today, rules)
    )
    url = support_url(snap.system)
    for f in findings:
        if SUPPORT_LINK_MANUAL & set(f.manual):
            f.links.append(("صفحهٔ پشتیبانی و درایور سازنده (جست‌وجو)", url))
    findings.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 9))
    return findings


def scan(runner: Runner = run, today: Optional[date] = None) -> ScanResult:
    snap = take_snapshot(runner)
    return ScanResult(snap, analyze(snap, today))
