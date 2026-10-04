"""Manual driver-update guide: exact names and IDs of what is installed, plus official links.

No network access here. It only builds the information and links the user needs to
check for a newer driver by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from urllib.parse import quote_plus

from .snapshot import SystemInfo

# Official pages we are confident about. Everything else falls back to a search link.
VENDOR_PAGES = {
    "8086": ("Intel Chipset INF Utility (صفحهٔ رسمی)", "https://www.intel.com/content/www/us/en/download/19347/chipset-inf-utility.html"),
    "1022": ("درایور چیپست AMD (صفحهٔ رسمی پشتیبانی)", "https://www.amd.com/en/support"),
}

GENERIC_DRIVER_DATES = {"2006-06-21"}  # date Microsoft stamps on its inbox drivers
OLD_DRIVER_DAYS = 3 * 365


@dataclass
class DriverCard:
    name: str
    vendor: str
    hardware_id: str  # e.g. PCI\VEN_1B21&DEV_1142
    short_id: str  # e.g. VEN_1B21&DEV_1142
    subsystem: str = ""
    provider: str = ""
    version: str = ""
    driver_date: str = ""
    advice: list = field(default_factory=list)
    links: list = field(default_factory=list)  # (label, url)

    @property
    def is_generic(self) -> bool:
        return self.provider.lower().startswith("microsoft")


def catalog_url(term: str) -> str:
    return "https://www.catalog.update.microsoft.com/Search.aspx?q=" + quote_plus(term)


def search_url(text: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(text)


def _parse_date(text: str) -> Optional[date]:
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _subsystem(instance_id: str) -> str:
    for part in instance_id.split("&"):
        if part.upper().startswith("SUBSYS_"):
            return part[7:]
    return ""


def build_cards(system: SystemInfo, today: Optional[date] = None) -> list:
    today = today or date.today()
    cards = []
    for c in system.controllers:
        short = f"VEN_{c.vendor_id}&DEV_{c.device_id}" if c.vendor_id else ""
        card = DriverCard(
            name=c.name,
            vendor=c.vendor,
            hardware_id=f"PCI\\{short}" if short else c.instance_id,
            short_id=short,
            subsystem=_subsystem(c.instance_id),
            provider=c.driver_provider,
            version=c.driver_version,
            driver_date=c.driver_date,
        )
        if c.vendor_id in VENDOR_PAGES:
            card.links.append(VENDOR_PAGES[c.vendor_id])
        else:
            card.links.append((f"جست‌وجوی درایور {c.vendor} (گوگل)", search_url(f"{c.vendor} {c.name} driver Windows")))
        if short:
            card.links.append(("جست‌وجو تو Microsoft Update Catalog (رسمی)", catalog_url(short)))

        when = _parse_date(c.driver_date)
        if card.is_generic:
            card.advice.append(
                "این کنترلر با درایور عمومی مایکروسافت کار می‌کنه. معمولاً مشکلی نیست؛ اگه USB قطع و وصل می‌شه "
                "یا کند است، درایور سازنده رو امتحان کن."
            )
        elif when and (today - when).days > OLD_DRIVER_DAYS:
            card.advice.append(f"درایور نصب‌شده قدیمیه (تاریخ {c.driver_date}). نسخهٔ جدیدتر رو از لینک‌های زیر چک کن.")
        else:
            card.advice.append("درایور سازنده نصبه. برای اطمینان، نسخه و تاریخش رو با صفحهٔ رسمی مقایسه کن.")
        card.advice.append(
            "ترتیب پیشنهادی: ۱) سایت رسمی سازنده، ۲) سایت پشتیبانی مادربرد، ۳) Microsoft Update Catalog. "
            "فقط فایل‌های امضادار از منبع رسمی نصب کن، و قبلش نقطهٔ بازیابی بساز."
        )
        cards.append(card)

    # The board itself: BIOS and chipset drivers come from the board maker.
    if system.board_manufacturer or system.board_product:
        who = f"{system.board_manufacturer} {system.board_product}".strip()
        board = DriverCard(
            name=f"مادربرد: {who}",
            vendor=system.board_manufacturer,
            hardware_id="",
            short_id="",
            provider=system.bios_vendor,
            version=f"BIOS {system.bios_version}".strip(),
            driver_date=system.bios_date.isoformat() if system.bios_date else "",
        )
        board.links.append(("صفحهٔ پشتیبانی/BIOS/چیپست مادربرد (جست‌وجو)", search_url(f"{who} support BIOS chipset drivers")))
        if system.is_laptop and system.system_model:
            laptop = f"{system.system_manufacturer} {system.system_model}"
            board.links.append(("صفحهٔ پشتیبانی لپ‌تاپ (جست‌وجو)", search_url(f"{laptop} support drivers")))
        board.advice.append("آپدیت BIOS و درایور چیپست فقط از صفحهٔ سازندهٔ مادربرد (یا لپ‌تاپ) انجام بشه.")
        cards.append(board)
    return cards
