# USB Fixer (Usb-error-kt)

عیب‌یاب و تعمیرکار درگاه‌های USB برای **ویندوز**، با رابط گرافیکی فارسی.
A Windows tool that finds USB problems, identifies your motherboard/chipset, and fixes what it can **only after you confirm**.

## چه کار می‌کنه؟

۱. **اسکن** (فقط می‌خونه، چیزی رو تغییر نمی‌ده)
۲. **نمایش مشکلات** با توضیح فارسی، علت احتمالی و راه‌حل
۳. **تأیید شما** ← ساخت نقطهٔ بازیابی و پشتیبان ← اجرای رفع‌ها ← اسکن دوباره

### چیزهایی که شناسایی می‌شه
- **مادربرد و سیستم:** سازنده/مدل برد، نسخه و تاریخ BIOS، پردازنده، چیپست/سازندهٔ هر کنترلر USB (Intel، AMD، ASMedia، Renesas…) و درایورش
- **دستگاه‌ها:** کد خطا (10، 43، 28، 31، 39، 41، 19…)، «Unknown USB Device»، دستگاه‌های شبح
- **برق:** Selective Suspend، خاموش‌شدن خودکار هاب‌ها، Fast Startup، PCIe Link State
- **حافظهٔ USB:** درایور USBSTOR/UASP غیرفعال، سیاست‌های مسدودکننده، Write Protect، دیسک Offline/Read-only/بدون حرف درایو
- **لاگ ویندوز:** خطاهای USB هفتهٔ اخیر
- **دانش مادربرد** (`usb_fixer/data/knowledge.json`)، مثلاً مشکل شناخته‌شدهٔ قطع و وصل USB روی B450/X470/B550/X570 با Ryzen 3000/5000، و BIOS قدیمی. این فایل بدون تغییر کد قابل گسترشه.

### رفع خودکار (با تیک و تأیید شما)
ریست دستگاه‌های خطادار، حذف دستگاه‌های شبح، خاموش کردن Selective Suspend / صرفه‌جویی برق هاب‌ها / Fast Startup / ASPM، فعال کردن USBSTOR و UASP، برداشتن سیاست مسدودکننده و Write Protect، آنلاین کردن دیسک و دادن حرف درایو.

### چیزهایی که برنامه نمی‌تونه (فقط راهنمایی می‌ده)
آپدیت BIOS، روشن کردن «XHCI Hand-Off»، تغییر PCIe Gen یا C-State تو BIOS، نصب درایور چیپست، خرابی کابل/پورت/سخت‌افزار. برنامه هیچ فایلی از اینترنت دانلود نمی‌کنه.

## ایمنی
- اسکن چیزی رو تغییر نمی‌ده. هر رفع فقط با تیک و تأیید شما اجرا می‌شه و قبل از تأیید، دقیقاً فرمان‌ها نشون داده می‌شن.
- قبل از رفع‌ها: نقطهٔ بازیابی ویندوز + پشتیبان کلیدهای رجیستری و تنظیمات برق (`%LOCALAPPDATA%\UsbFixer\backups`).
- دکمهٔ «برگرداندن آخرین تغییرات» تنظیمات برق، رجیستری و هاب‌ها رو برمی‌گردونه. (ریست دستگاه و حذف دستگاه شبح برگشت‌پذیر نیست، ولی بی‌خطره: ویندوز دستگاه رو دوباره می‌سازه.)
- برای رفع مشکلات باید برنامه با دسترسی ادمین اجرا بشه.

## اجرا
نیاز: ویندوز ۱۰/۱۱ و پایتون ۳٫۹ به بالا. یک پکیج لازمه (رابط Qt): `pip install -r requirements.txt`.

```
python -m usb_fixer            # رابط گرافیکی
python -m usb_fixer --scan     # فقط گزارش متنی در کنسول
python -m usb_fixer --demo     # ماشین ساختگی؛ روی هر سیستم‌عاملی برای دیدن برنامه
```

## ساخت فایل exe
```
build.bat
```
خروجی: `dist\USB-Fixer.exe` (با درخواست دسترسی ادمین).

## تست
```
python -m unittest discover -s tests -t .
```
تست‌ها با خروجی ساختگی ویندوز اجرا می‌شن (`usb_fixer/demo.py`)، پس روی هر سیستم‌عاملی کار می‌کنن.

## وضعیت
نسخهٔ اول. منطق برنامه با ویندوز ساختگی تست شده؛ اجرای واقعی روی ویندوز (خروجی PowerShell/`pnputil` روی سخت‌افزارهای مختلف) هنوز باید امتحان بشه. اگه چیزی عجیب بود، گزارش بده (Issue)، ترجیحاً با خروجی `--scan`.

---

## English summary
`python -m usb_fixer` opens a GUI (Persian UI). It scans USB devices, motherboard/BIOS/CPU, USB controller vendors and drivers, power settings, storage policies and recent USB event-log errors; lists problems with explanations; and applies fixes only after explicit confirmation, creating a restore point and an undo file first. Things only the BIOS can change (XHCI hand-off, PCIe gen, C-states) are shown as manual steps. Standard library only; `build.bat` makes a single `.exe` with PyInstaller.

## فونت
برنامه فونت **Vazirmatn** (مجوز SIL OFL 1.1، پروژهٔ [rastikerdar/vazirmatn](https://github.com/rastikerdar/vazirmatn)) رو داخل خودش داره تا فارسی و انگلیسی روی هر ویندوزی یکسان و خوانا نشون داده بشه. متن مجوز: `usb_fixer/data/fonts/OFL.txt`.
