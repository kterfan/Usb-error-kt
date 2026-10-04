"""Plain-text report of a scan (for the console and the Save report button)."""

from __future__ import annotations

from . import strings
from .diagnostics import ScanResult


def system_lines(snap) -> list:
    s = snap.system
    bios_date = s.bios_date.isoformat() if s.bios_date else "?"
    lines = [
        f"{strings.UI['sys_board']}: {s.board_manufacturer} {s.board_product} {s.board_version}".rstrip(),
        f"{strings.UI['sys_bios']}: {s.bios_vendor} {s.bios_version} ({bios_date})",
        f"{strings.UI['sys_model']}: {s.system_manufacturer} {s.system_model}"
        + (" (لپ‌تاپ)" if s.is_laptop else ""),
        f"{strings.UI['sys_cpu']}: {s.cpu}",
        f"{strings.UI['sys_os']}: {s.os_caption} (build {s.os_build})",
        f"{strings.UI['sys_controllers']}:",
    ]
    if not s.controllers:
        lines.append("  —")
    for c in s.controllers:
        lines.append(
            f"  • {c.name} [{c.vendor}] درایور: {c.driver_provider or '?'} {c.driver_version} {c.driver_date}".rstrip()
        )
    return lines


def finding_text(f) -> str:
    parts = [f"[{strings.SEVERITY.get(f.severity, f.severity)}] {f.title}", f.detail]
    if f.fix_id:
        title, desc = strings.FIXES[f.fix_id]
        parts.append(f"{strings.UI['fix_header']} {title}؛ {desc}")
    if f.manual:
        parts.append(strings.UI["manual_header"])
        parts.extend(f"  - {m}" for m in f.manual_texts)
    for label, url in f.links:
        parts.append(f"{label}: {url}")
    return "\n".join(parts)


def build_report(result: ScanResult) -> str:
    out = ["USB Fixer", "=" * 40, ""]
    out += system_lines(result.snapshot)
    out += ["", "=" * 40, ""]
    if not result.findings:
        out.append(strings.UI["no_findings"])
    for f in result.findings:
        out += [finding_text(f), "", "-" * 40, ""]
    for w in result.snapshot.warnings:
        out.append(f"⚠ {w}")
    return "\n".join(out)
