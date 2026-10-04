"""Product identity: name, version, author and links (shown in the app, report, exe and installer)."""

from . import __version__

APP_NAME = "USB Fixer"
APP_NAME_FA = "عیب‌یاب و تعمیرکار USB"
VERSION = __version__
VERSION_LABEL = f"{VERSION} (بتا)"
AUTHOR_EN = "Erfan Esmailzadeh"
AUTHOR_FA = "عرفان اسمعیل زاده"
GITHUB_PROFILE = "https://github.com/kterfan"
GITHUB_REPO = "https://github.com/kterfan/Usb-error-kt"
COPYRIGHT = f"© 2026 {AUTHOR_EN}"
PRIVACY_FA = (
    "این برنامه هیچ اطلاعاتی از کامپیوتر تو جایی نمی‌فرسته. فقط وقتی خودت روی یک لینک بزنی، "
    "مرورگر اون صفحه رو باز می‌کنه."
)


def credit_line_fa() -> str:
    return f"ساخته‌شده توسط {AUTHOR_FA} ({AUTHOR_EN})"


def banner() -> str:
    """One line for the console/report header."""
    return f"{APP_NAME} {VERSION} - {AUTHOR_EN} ({AUTHOR_FA}) - {GITHUB_PROFILE}"
