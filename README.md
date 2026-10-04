# USB Fixer (Usb-error-kt) — نسخهٔ 0.9.0 (بتا)

عیب‌یاب و تعمیرکار درگاه‌های USB برای **ویندوز ۱۰/۱۱**، با رابط گرافیکی فارسی (روشن/تاریک).

**سازنده: عرفان اسمعیل زاده (Erfan Esmailzadeh)** · گیت‌هاب: [github.com/kterfan](https://github.com/kterfan) · کد: [kterfan/Usb-error-kt](https://github.com/kterfan/Usb-error-kt)

A Windows tool that finds USB problems, identifies your motherboard/chipset, tells you whether a problem is hardware or Windows, and fixes what it can **only after you confirm**. Made by **Erfan Esmailzadeh**.

## صفحه‌های برنامه

| صفحه | چی نشون می‌ده |
|---|---|
| **مشکلات** | هر مشکل با توضیح ساده، **پیشنهاد مستقیم** («اجرا کن / لازم نیست / احتیاط»)، میزان ریسک و برگشت‌پذیری |
| **تست زنده** | دستگاه رو وصل کن؛ برنامه می‌بینه ویندوز چه واکنشی نشون داد و می‌گه مشکل از **سخت‌افزاره** (کابل/پورت/برق/دستگاه) یا از **ویندوز**، و اگه قابل رفع باشه همون‌جا رفعش می‌کنه |
| **دستگاه‌ها** | دستگاه‌ها با اسم واقعی (مثلاً «Logitech USB Receiver» به‌جای «USB Composite Device»)، نوع، سازنده و وضعیت؛ جدا شده به «وصل‌شده‌های تو»، «بخش‌های سیستمی» و «قبلاً وصل بوده» |
| **درایورها و BIOS** | یک جواب مستقیم: «لازمه چیزی آپدیت کنی یا نه؟» + نقش هر کنترلر USB به زبان ساده + **چک آنلاین BIOS** از سایت رسمی سازنده |
| **سیستم و نگهبان** | مشخصات مادربرد/BIOS/پردازنده/ویندوز و «نگهبان ماندگاری» |

## چیزهایی که شناسایی می‌شه
- **مادربرد و سیستم:** سازنده/مدل برد، نسخه و تاریخ BIOS، پردازنده، چیپست و سازندهٔ هر کنترلر USB و درایورش
- **BIOS آنلاین:** برای مادربردهای **ASUS** آخرین نسخه مستقیم از سایت رسمی ASUS خونده می‌شه (نسخه، تاریخ، تغییرات، لینک دانلود رسمی). اگه BIOS به‌روز باشه، هشدارهای «BIOS قدیمی» دیگه نشون داده نمی‌شن. برای MSI/Gigabyte/ASRock و بقیه، چون سایتشون فهرست قابل‌خوندن برای برنامه نمی‌ده، فقط لینک رسمی نشون داده می‌شه (حدس زده نمی‌شه).
- **دستگاه‌ها:** کد خطا (10، 43، 28، 31، 39، 41، 19…)، «Unknown USB Device»، دستگاه‌های شبح
- **برق:** Selective Suspend (روی **همهٔ** پلن‌های برق)، خاموش‌شدن خودکار هاب‌ها، Fast Startup، PCIe Link State
- **حافظهٔ USB:** USBSTOR/UASP غیرفعال، سیاست‌های مسدودکننده، Write Protect، دیسک Offline/Read-only/بدون حرف درایو، و **پارتیشن RAW** (خراب/ناخوانا). برنامه هیچ‌وقت فرمت نمی‌کنه؛ اول راه نجات اطلاعات رو می‌گه.
- **لاگ ویندوز:** خطاهای USB هفتهٔ اخیر
- **دانش مادربرد** (`usb_fixer/data/knowledge.json`)، مثلاً قطع و وصل USB روی B450/X470/B550/X570 با Ryzen 3000/5000 که فقط برای BIOSهای قبل از AGESA 1.2.0.2 (آوریل ۲۰۲۱) هشدار داده می‌شه.

## رفع خودکار (فقط با تیک و تأیید تو)
ریست دستگاه‌های خطادار، **ریست کامل USB** (همهٔ کنترلرها)، حذف دستگاه‌های شبح، خاموش کردن Selective Suspend / صرفه‌جویی برق هاب‌ها / Fast Startup / ASPM، فعال کردن USBSTOR و UASP، برداشتن سیاست مسدودکننده و Write Protect، آنلاین کردن دیسک و دادن حرف درایو.

پنجرهٔ تأیید برای هر کار می‌گه: **دقیقاً چی کار می‌کنه** (به زبان ساده)، **ریسکش** (بی‌خطر / کم‌ریسک / احتیاط)، **برگشت‌پذیره یا نه**، و **پیشنهاد من** (انجامش بدی یا نه). فرمان‌های فنی فقط اگه بخوای نشون داده می‌شن.

## ماندگاری بعد از ری‌استارت
- تنظیم‌ها روی همهٔ پلن‌های برق و به‌صورت سراسری (رجیستری) اعمال می‌شن تا با عوض شدن پلن برنگردن.
- برنامه یادش می‌مونه چه چیزهایی رو درست کرده؛ اگه بعداً (مثلاً با آپدیت ویندوز یا ابزار سازنده) برگشته باشن، با برچسب **«دوباره برگشته»** نشونشون می‌ده.
- **نگهبان ماندگاری** (اختیاری، از صفحهٔ «سیستم و نگهبان»): یه Scheduled Task که موقع ورود به ویندوز فقط همون تنظیم‌هایی رو که با این برنامه درست کردی، اگه برگشته باشن، دوباره درست می‌کنه. با Uninstall برنامه خودش پاک می‌شه.

## ایمنی
- اسکن چیزی رو تغییر نمی‌ده.
- قبل از رفع‌ها: نقطهٔ بازیابی ویندوز + پشتیبان رجیستری و تنظیمات برق (`%LOCALAPPDATA%\UsbFixer\backups`).
- «برگرداندن تغییرات» تنظیمات برق (هر پلن جدا)، رجیستری (حتی مقدارهایی که قبلاً وجود نداشتن پاک می‌شن) و هاب‌ها رو دقیقاً به حالت قبل برمی‌گردونه.
- **حریم خصوصی:** هیچ اطلاعاتی از کامپیوترت فرستاده نمی‌شه. تنها درخواست اینترنتی، خوندن فهرست عمومی BIOS از `www.asus.com` با اسم مدل مادربرده (فقط HTTPS و فقط همین دامنه). با `--offline` اونم خاموش می‌شه.

## نصب و اجرا
- **نسخهٔ نصبی:** `USB-Fixer-Setup-<نسخه>.exe` (پیشنهادی؛ نگهبان فقط با نسخهٔ نصب‌شده کار می‌کنه)
- **نسخهٔ تک‌فایلی:** `USB-Fixer.exe`

از سورس (پایتون ۳٫۹+): `pip install -r requirements.txt`

```
python -m usb_fixer                       # رابط گرافیکی
python -m usb_fixer --scan                # گزارش متنی
python -m usb_fixer --scan --report r.txt # گزارش در فایل
python -m usb_fixer --demo                # ماشین ساختگی؛ روی هر سیستم‌عاملی
python -m usb_fixer --version             # نسخه و سازنده
```

## لوگو
لوگو با `tools/make_icon.py` ساخته می‌شه (`usb_fixer/data/icon.png` و `icon.ico`).

## ساخت
`build.bat` ← `dist\USB-Fixer.exe` (با اطلاعات نسخه و سازنده در Properties › Details) و اگه Inno Setup 6 نصب باشه، `dist\USB-Fixer-Setup-<نسخه>.exe`.

## تست‌ها
```
python -m unittest discover -s tests -t .
```
- **تست‌های منطق و رابط گرافیکی** (بیش از ۱۲۰ تست) با ویندوز ساختگی (`usb_fixer/demo.py`) روی هر سیستم‌عاملی اجرا می‌شن.
- **تست‌های واقعی ویندوز** (`tests_windows/`) روی ماشین ویندوز گیت‌هاب: رفع واقعی ← برگشتن تنظیم ← نگهبان ← برگرداندن، Scheduled Task، اسکریپت‌های تست زنده و API واقعی ASUS. این‌ها تنظیمات سیستم رو عوض می‌کنن، پس فقط با `USB_FIXER_REAL_TESTS=1` اجرا می‌شن؛ روی کامپیوتر خودت اجراشون نکن.
- CI همچنین exe، اطلاعات نسخه، و نصب/حذف بی‌صدای Setup رو تست می‌کنه.

## محدودیت‌ها
- exe امضای دیجیتال نداره، پس ویندوز (SmartScreen) ممکنه هشدار بده: «More info › Run anyway».
- چک آنلاین BIOS فعلاً فقط برای ASUS خودکاره.
- سرعت هر پورت (USB 2/3) و درخت کامل پورت‌ها هنوز نشون داده نمی‌شه.

---

## English summary
GUI (Persian, light/dark) with five pages: problems (each with a direct recommendation, risk and reversibility), a live plug-in test that tells hardware from software problems, devices with real names, a driver/BIOS page with a direct verdict and an online BIOS check (ASUS official API), and system/guard. Fixes run only after a plain-language confirmation, with a restore point and an exact undo (per power plan; registry values that did not exist are removed). Fixes are applied to all power plans plus machine-wide, remembered, flagged when Windows reverts them, and optionally re-applied at logon by a guard task. Tests: 120+ unit/GUI tests on a fake Windows, plus real fix→revert→guard→undo tests on the GitHub Windows runner, exe version info and installer install/uninstall checks.

© 2026 Erfan Esmailzadeh — https://github.com/kterfan

## فونت
فونت **Vazirmatn** (مجوز SIL OFL 1.1، [rastikerdar/vazirmatn](https://github.com/rastikerdar/vazirmatn)) داخل برنامه است. متن مجوز: `usb_fixer/data/fonts/OFL.txt`.
