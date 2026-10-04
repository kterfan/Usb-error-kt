"""Drivers & BIOS page: a direct answer ("do I need to update anything?") instead of raw driver data.

Facts behind the verdict:
- On Windows 10/11 the built-in Microsoft driver (usbxhci) is the standard, recommended driver for
  USB 3.x controllers from Intel and AMD; vendors no longer ship separate USB 3 drivers for them.
- Older add-on chips (ASMedia, Renesas/NEC, VIA, Fresco Logic, Etron) sometimes work better with the
  board maker's driver, so that is suggested only if the user actually has problems.
- BIOS / chipset packages come from the board maker (and AMD/Intel for chipset).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from urllib.parse import quote_plus

from .snapshot import SystemInfo

VENDOR_PAGES = {
    "8086": ("Intel Chipset Device Software (صفحهٔ رسمی Intel)", "https://www.intel.com/content/www/us/en/download/19347/chipset-inf-utility.html"),
    "1022": ("درایور چیپست AMD (صفحهٔ رسمی AMD)", "https://www.amd.com/en/support"),
}

# What a controller drives, for the IDs we are sure about.
CONTROLLER_ROLES = {
    ("1022", "149C"): "پورت‌های USB متصل به پردازندهٔ Ryzen (یا چیپست X570)",
    ("1022", "43EE"): "پورت‌های USB چیپست سری 500 مادربرد (B550 / A520)",
    ("1022", "43D5"): "پورت‌های USB چیپست سری 400 مادربرد (B450 / X470)",
    ("8086", "1138"): "پورت‌های Thunderbolt 4 / USB4 مادربرد (کنترلر Intel)",
}
OLDER_ADDON_VENDORS = {"1B21", "1033", "1912", "1106", "1B73", "1B6F"}
OLD_DRIVER_DAYS = 3 * 365


@dataclass
class ControllerCard:
    title: str  # what it drives, in plain words
    name: str  # name Windows shows
    vendor: str
    hardware_id: str
    driver_text: str
    ok: bool
    advice: str = ""
    links: list = field(default_factory=list)
    tech: list = field(default_factory=list)  # (label, value) technical details, hidden by default


@dataclass
class DriverReport:
    verdict_ok: bool
    verdict_title: str
    verdict_text: str
    actions: list = field(default_factory=list)  # (text, link label, url)
    controllers: list = field(default_factory=list)
    bios_title: str = ""
    bios_text: str = ""
    bios_ok: Optional[bool] = None
    bios_links: list = field(default_factory=list)


def catalog_url(term: str) -> str:
    return "https://www.catalog.update.microsoft.com/Search.aspx?q=" + quote_plus(term)


def search_url(text: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(text)


def _date(text: str) -> Optional[date]:
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _subsystem(instance_id: str) -> str:
    for part in instance_id.split("&"):
        if part.upper().startswith("SUBSYS_"):
            return part[7:]
    return ""


def board_name(system: SystemInfo) -> str:
    if system.is_laptop and system.system_model:
        return f"{system.system_manufacturer} {system.system_model}".strip()
    return f"{system.board_manufacturer} {system.board_product}".strip()


def build_report(system: SystemInfo, bios=None, today: Optional[date] = None) -> DriverReport:
    today = today or date.today()
    cards, needs, maybe = [], [], []
    for c in system.controllers:
        short = f"VEN_{c.vendor_id}&DEV_{c.device_id}" if c.vendor_id else ""
        generic = c.driver_provider.lower().startswith("microsoft")
        when = _date(c.driver_date)
        role = CONTROLLER_ROLES.get((c.vendor_id, c.device_id), f"پورت‌های USB (کنترلر {c.vendor})")
        tech = [("Hardware ID", f"PCI\\{short}" + (f" (SUBSYS_{_subsystem(c.instance_id)})" if _subsystem(c.instance_id) else "")),
                ("نسخهٔ درایور", f"{c.driver_provider} {c.driver_version}".strip())]
        if generic and c.vendor_id in OLDER_ADDON_VENDORS:
            ok = True
            text = "درایور استاندارد ویندوز"
            advice = ("معمولاً کافیه. فقط اگه با پورت‌های همین کنترلر مشکل داری، درایور سازنده رو از صفحهٔ پشتیبانی "
                      "مادربرد امتحان کن.")
            maybe.append(c)
        elif generic:
            ok = True
            text = "درایور استاندارد ویندوز؛ برای USB 3 روی ویندوز ۱۰/۱۱ همین درایور توصیه‌شده است"
            advice = "نیازی به عوض کردن نیست."
        elif when and (today - when).days > OLD_DRIVER_DAYS:
            ok = False
            text = f"درایور سازنده، قدیمی (تاریخ {c.driver_date})"
            advice = "پیشنهاد: نسخهٔ جدیدترش رو از صفحهٔ پشتیبانی مادربرد یا سازندهٔ چیپ نصب کن."
            needs.append(c)
        else:
            ok = True
            text = f"درایور سازنده ({c.driver_provider} {c.driver_version})".strip()
            advice = "مشکلی نیست."
        links = []
        if not ok or c in maybe:
            links.append(("جست‌وجوی درایور در Microsoft Update Catalog", catalog_url(short)))
        cards.append(ControllerCard(role, c.name, c.vendor, f"PCI\\{short}", text, ok, advice, links, tech))

    actions = []
    if needs:
        verdict_ok = False
        title = f"{len(needs)} درایور USB قدیمیه و بهتره آپدیت بشه"
        text = "جزئیات هر کدوم پایین اومده."
    else:
        verdict_ok = True
        title = "درایورهای USB تو مشکلی ندارن؛ لازم نیست چیزی عوض کنی"
        text = ("کنترلرهای USB با درایور مناسب کار می‌کنن. اگه با USB مشکل داری، علتش احتمالاً درایور نیست؛ "
                "از «تست زنده» استفاده کن تا دقیق‌تر ببینیم.")
    vendors = {c.vendor_id for c in system.controllers}
    if "1022" in vendors:
        actions.append(("اختیاری: بستهٔ درایور چیپست AMD رو به‌روز نگه دار (برای پایداری کلی سیستم، نه فقط USB).",) + VENDOR_PAGES["1022"])
    if "8086" in vendors and not system.is_virtual:
        actions.append(("اختیاری: Intel Chipset Device Software فقط اسم دستگاه‌ها رو درست نشون می‌ده؛ برای USB ضروری نیست.",) + VENDOR_PAGES["8086"])
    if any((c.vendor_id, c.device_id) == ("8086", "1138") for c in system.controllers):
        actions.append(("اگه از Thunderbolt استفاده می‌کنی، درایور Thunderbolt رو از صفحهٔ پشتیبانی مادربرد نصب کن.",
                        "صفحهٔ پشتیبانی مادربرد (جست‌وجو)", search_url(f"{board_name(system)} Thunderbolt driver")))

    report = DriverReport(verdict_ok, title, text, actions, cards)
    _bios_section(report, system, bios)
    return report


def _bios_section(report: DriverReport, system: SystemInfo, bios) -> None:
    who = board_name(system)
    installed = system.bios_version or "?"
    when = system.bios_date.isoformat() if system.bios_date else "تاریخ نامعلوم"
    support = ("صفحهٔ پشتیبانی و BIOS مادربرد (جست‌وجو)", search_url(f"{who} support BIOS"))
    if bios is None:
        report.bios_title = f"BIOS نصب‌شده: {installed} ({when})"
        report.bios_text = "هنوز آنلاین چک نشده."
        report.bios_links = [support]
        return
    if bios.status == "current":
        report.bios_ok = True
        report.bios_title = f"BIOS تو به‌روزه ({installed})"
        latest_when = bios.latest_date.isoformat() if bios.latest_date else "?"
        report.bios_text = f"آخرین نسخه روی سایت رسمی {bios.source}: {bios.latest} (تاریخ {latest_when}). کاری لازم نیست."
        report.bios_links = [support]
    elif bios.status == "update":
        report.bios_ok = False
        latest_when = bios.latest_date.isoformat() if bios.latest_date else "?"
        report.bios_title = f"نسخهٔ جدید BIOS موجوده: {bios.latest} (نصب‌شده: {installed})"
        # each note line is isolated (FSI..PDI) so English lines keep their own direction inside the RTL card
        lines = "\n".join(f"• \u2068{line.strip()}\u2069" for line in bios.notes.splitlines() if line.strip())
        notes = f"\nتغییرات این نسخه (از سایت سازنده):\n{lines}" if lines else ""
        report.bios_text = (f"منتشرشده در {latest_when} روی سایت رسمی {bios.source}. آپدیت BIOS رو دقیقاً طبق "
                            f"راهنمای سازنده انجام بده و وسطش برق نباید قطع بشه.{notes}")
        report.bios_links = ([(f"دانلود BIOS {bios.latest} (فایل رسمی {bios.source})", bios.download_url)] if bios.download_url else []) + [support]
    else:
        report.bios_title = f"BIOS نصب‌شده: {installed} ({when})"
        report.bios_text = f"نتونستم خودکار چک کنم که نسخهٔ جدیدتری هست یا نه: {bios.reason}"
        report.bios_links = [support]
