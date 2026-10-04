"""Is a newer BIOS published for this board? Checked online against the maker's official site.

Only ASUS offers a public, machine-readable list (verified). For other makers the answer is
"could not check automatically" plus the official support link; nothing is guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional
from urllib.parse import quote

from . import net
from .snapshot import SystemInfo

ASUS_API = "https://www.asus.com/support/api/product.asmx/GetPDBIOS?website=global&model={model}&pdid=&cpu="


@dataclass
class BiosCheck:
    status: str  # current / update / unknown
    installed: str = ""
    latest: str = ""
    latest_date: Optional[date] = None
    notes: str = ""
    download_url: str = ""
    sha256: str = ""
    source: str = ""
    reason: str = ""

    @property
    def is_current(self) -> bool:
        return self.status == "current"


def is_asus(system: SystemInfo) -> bool:
    return "asus" in system.board_manufacturer.lower()


def _date(text: str) -> Optional[date]:
    m = re.match(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _clean(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text or "", flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip().strip('"').strip()


def _newer(latest: str, installed: str) -> Optional[bool]:
    """True if latest > installed, None if the two cannot be compared reliably."""
    if latest.isdigit() and installed.isdigit():
        return int(latest) > int(installed)
    if latest.strip().lower() == installed.strip().lower():
        return False
    return None


def parse_asus(data: dict, installed: str) -> BiosCheck:
    result = (data or {}).get("Result") or {}
    groups = result.get("Obj") or []
    files = []
    for g in groups:
        if str(g.get("Name", "")).strip().upper() == "BIOS":
            files = g.get("Files") or []
            break
    files = [f for f in files if f.get("Version")]
    if not files:
        return BiosCheck("unknown", installed, source="ASUS", reason="ASUS برای این مدل فهرست BIOS برنگردوند.")
    files.sort(key=lambda f: (_date(f.get("ReleaseDate", "")) or date.min, f.get("Version", "")), reverse=True)
    top = files[0]
    latest = str(top.get("Version", "")).strip()
    check = BiosCheck(
        status="unknown",
        installed=installed,
        latest=latest,
        latest_date=_date(top.get("ReleaseDate", "")),
        notes=_clean(top.get("Description", "")),
        download_url=((top.get("DownloadUrl") or {}).get("Global") or ""),
        sha256=str(top.get("sha256") or ""),
        source="ASUS",
    )
    newer = _newer(latest, installed)
    if newer is None:
        check.reason = "شمارهٔ نسخهٔ نصب‌شده با فهرست سازنده قابل مقایسه نبود."
    else:
        check.status = "update" if newer else "current"
    return check


def check_latest(system: SystemInfo, fetch: Optional[net.Fetch] = None) -> BiosCheck:
    installed = system.bios_version.strip()
    if system.is_virtual:
        return BiosCheck("unknown", installed, reason="ماشین مجازی است.")
    if not is_asus(system) or not system.board_product:
        return BiosCheck(
            "unknown", installed,
            reason="سازندهٔ این مادربرد فهرست BIOS قابل‌خوندن برای برنامه‌ها نداره؛ از لینک رسمی چک کن.",
        )
    url = ASUS_API.format(model=quote(system.board_product.strip()))
    try:
        data = net.fetch_json(url, fetch)
    except net.NetError as exc:
        return BiosCheck("unknown", installed, source="ASUS", reason=f"اتصال به سایت ASUS نشد ({exc}).")
    if (data or {}).get("Status") == "FAIL" or not (data or {}).get("Result"):
        return BiosCheck("unknown", installed, source="ASUS", reason="ASUS این مدل رو تو فهرستش پیدا نکرد.")
    return parse_asus(data, installed)
