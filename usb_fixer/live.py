"""Live test: watch what Windows does while the user plugs a device in, then explain it.

This is what tells "the port/cable/device is the problem" apart from "Windows is the problem":
- Windows saw nothing at all            -> hardware side (cable, port, power, the device)
- Windows saw it but could not talk to it -> usually power/cable/device; sometimes driver
- Windows set it up but it shows an error -> driver/settings (software side), fixable here
- storage arrived but no drive / RAW      -> volume problem, fixable or recoverable
- storage arrived but no disk came of it  -> never "healthy": nothing shows up in This PC
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import devices, strings
from .diagnostics import Finding
from .snapshot import drive_letter, is_data_partition
from .system import Runner, powershell_cmd

NODES_SCRIPT = r"""# SCRIPT:live-nodes
$ErrorActionPreference='SilentlyContinue'
$n = @(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB\*' -or $_.InstanceId -like 'USBSTOR\*' } | ForEach-Object {
  $f = $_.FriendlyName; if (-not $f) { $f = $_.Name }
  [pscustomobject]@{ id=$_.InstanceId; name="$f"; cls="$($_.Class)"; error_code=[int]$_.ConfigManagerErrorCode }
})
ConvertTo-Json -InputObject $n -Depth 3 -Compress
"""

# Every disk, not only BusType USB: a UASP drive can report another bus type. Only disks that were not
# there before the test count, so the internal ones never get in the way.
DISKS_SCRIPT = r"""# SCRIPT:live-disks
$ErrorActionPreference='SilentlyContinue'
$d = @(Get-Disk | ForEach-Object {
  $k = $_
  $p = @(Get-Partition -DiskNumber $k.Number | ForEach-Object { $v = $_ | Get-Volume -ErrorAction SilentlyContinue; [pscustomobject]@{ number=[int]$_.PartitionNumber; letter=("$($_.DriveLetter)" -replace '[^A-Za-z]', ''); type="$($_.Type)"; size=[int64]$_.Size; fs="$($v.FileSystemType)" } })
  [pscustomobject]@{ number=[int]$k.Number; name="$($k.FriendlyName)"; bus="$($k.BusType)"; style="$($k.PartitionStyle)"; size=[int64]$k.Size; offline=[bool]$k.IsOffline; partitions=$p }
})
ConvertTo-Json -InputObject $d -Depth 4 -Compress
"""

EVENTS_SCRIPT = r"""# SCRIPT:live-events
$ErrorActionPreference='SilentlyContinue'
$since = (Get-Date).AddSeconds(-{seconds})
$e = @(Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=$since} | Where-Object { $_.ProviderName -match 'USB|Kernel-PnP' -and $_.Level -le 3 } | Select-Object -First 20 | ForEach-Object {
  $m = ("$($_.Message)" -replace '\s+', ' ')
  [pscustomobject]@{ provider="$($_.ProviderName)"; id=[int]$_.Id; message=$m.Substring(0, [Math]::Min(200, $m.Length)) }
})
ConvertTo-Json -InputObject $e -Depth 3 -Compress
"""

ENUM_FAIL = re.compile(r"enumerat|descriptor|reset|failed|could not|power surge|over.?current", re.IGNORECASE)
STORAGE_CLASSES = {"diskdrive", "scsiadapter", "cdrom"}  # SCSIAdapter: the UASP side of a USB 3 drive
STORAGE_NAME = re.compile(r"mass storage|attached scsi|\buas\b", re.IGNORECASE)
CARD_READER = re.compile(r"sd/mmc|micro ?sd|compact ?flash|\bcf\b|\bxd\b|\bms\b|memory ?stick|card|reader", re.IGNORECASE)


@dataclass
class LiveResult:
    kind: str  # nothing / enum_failed / error / storage_issue / ok
    side: str  # hardware / software / none
    title: str
    explanation: str
    steps: list = field(default_factory=list)
    fixes: list = field(default_factory=list)  # Finding objects the user can run from the result
    added: list = field(default_factory=list)  # friendly names
    events: list = field(default_factory=list)


def _json_list(text: str) -> list:
    try:
        data = json.loads(text.strip() or "[]")
    except ValueError:
        return []
    if isinstance(data, dict):
        return [data]
    return data if isinstance(data, list) else []


def poll_nodes(runner: Runner) -> dict:
    res = runner(powershell_cmd(NODES_SCRIPT))
    return {n["id"]: n for n in _json_list(res.out) if isinstance(n, dict) and n.get("id")} if res.ok else {}


def _partitions(disk: dict) -> list:
    parts = disk.get("partitions") or []
    if isinstance(parts, dict):  # PowerShell returns an object, not a list, for one partition
        parts = [parts]
    return [p for p in parts if isinstance(p, dict)]


def poll_disks(runner: Runner) -> dict:
    res = runner(powershell_cmd(DISKS_SCRIPT))
    if not res.ok:
        return {}
    out = {}
    for d in _json_list(res.out):
        if isinstance(d, dict) and "number" in d:
            parts = _partitions(d)
            for p in parts:
                p["letter"] = drive_letter(p.get("letter"))
            out[d["number"]] = dict(d, partitions=parts)
    return out


def _letters(disks: list) -> list:
    return [x for d in disks for p in _partitions(d) if (x := drive_letter(p.get("letter")))]


def recent_events(runner: Runner, seconds: int) -> list:
    res = runner(powershell_cmd(EVENTS_SCRIPT.replace("{seconds}", str(int(seconds)))))
    return _json_list(res.out) if res.ok else []


def _friendly(nodes: list) -> list:
    """Group added nodes by VID/PID and pick the best name for each physical device."""
    groups: dict = {}
    by_serial = {}  # USB\VID_x&PID_y\SERIAL -> group key, so USBSTOR\...\SERIAL&0 joins its USB parent
    for n in nodes:
        vid, pid = devices.vid_pid(n.get("id", ""))
        if vid:
            by_serial[n.get("id", "").rsplit("\\", 1)[-1].upper()] = f"{vid}_{pid}"
    for n in nodes:
        iid = n.get("id", "")
        vid, pid = devices.vid_pid(iid)
        serial = iid.rsplit("\\", 1)[-1].split("&")[0].upper()
        key = f"{vid}_{pid}" if vid else by_serial.get(serial, iid)
        groups.setdefault(key, []).append(n)
    out = []
    for key, members in groups.items():
        vid = key.split("_")[0] if len(key) == 9 else None
        names = [m.get("name", "") for m in members]
        real = next((x for x in names if x and not devices._is_generic(x)), "")
        vendor = devices.vendor_name(vid) if vid and vid != "0000" else ""
        name = real or (f"دستگاه USB {vendor}".strip() if vendor else "دستگاه USB")
        code = max((m.get("error_code") or 0 for m in members), default=0)
        unknown = vid == "0000" or any("unknown usb device" in x.lower() for x in names)
        if unknown and not real:
            name = "دستگاه ناشناس USB (خودش رو معرفی نکرد)"
        storage = any(str(m.get("cls", "")).lower() in STORAGE_CLASSES or str(m.get("id", "")).upper().startswith("USBSTOR\\")
                      or STORAGE_NAME.search(m.get("name", "") or "") for m in members)
        out.append({"key": key, "name": name, "error_code": code, "ids": [m.get("id") for m in members],
                    "unknown": unknown, "storage": storage,
                    "card_reader": storage and any(CARD_READER.search(x or "") for x in names)})
    return out


def _no_drive(storage: list, enum_events: list, names: list) -> LiveResult:
    """A storage device arrived on USB, but no drive came out of it: nothing to see in This PC."""
    if storage and all(a["card_reader"] for a in storage):
        return LiveResult(
            "storage_issue", "hardware", "کارت‌خوان وصل شد ولی کارتی توش دیده نشد",
            "خود کارت‌خوان سالم وصل شده، ولی ویندوز هیچ کارت حافظه‌ای توش ندید؛ برای همین تو This PC درایوی اضافه نشد.",
            [
                "کارت رو کامل جا بزن و دوباره تست کن (تست رو شروع کن، بعد کارت رو بذار).",
                "اگه کارت توش بوده: کارت رو روی یه گوشی یا کارت‌خوان دیگه امتحان کن؛ ممکنه خود کارت خراب باشه.",
            ],
            added=names, events=enum_events,
        )
    return LiveResult(
        "storage_issue", "hardware", "حافظه به USB وصل شد ولی ویندوز خودِ دیسک رو ندید",
        "بخش USB دستگاه (برد داخل قاب هارد یا فلش) جواب داد، ولی دیسک داخلش بالا نیومد؛ برای همین تو This PC "
        "چیزی نمی‌بینی. تو هاردهای اکسترنال معمولاً یعنی برق کافی برای چرخیدن هارد نمی‌رسه، کابل ایراد داره یا خود "
        "هارد مشکل پیدا کرده؛ گاهی هم درایور حافظه (USBSTOR یا UASP) تو ویندوز خاموشه.",
        [
            "دستگاه رو مستقیم به پورت پشت کیس بزن، بدون هاب و کابل رابط، با یه کابل کوتاه و سالم.",
            "اگه هارد اکسترناله، گوش کن: اگه نمی‌چرخه یا تیک‌تیک می‌کنه، برق کم داره یا خود هارد خرابه. "
            "کابل دوشاخه (Y) یا هاب برق‌دار رو امتحان کن.",
            "یه «اسکن» کامل بگیر: اگه درایور حافظه یا سیاستی جلوی دیسک رو گرفته باشه، همون‌جا نشون داده و رفع می‌شه.",
            "تو Disk Management (کلیک راست روی Start) ببین دیسک اونجا هست یا نه.",
            "روی یه کامپیوتر دیگه امتحان کن: اگه اونجا هم دیده نشد، خود هارد یا قابش خرابه. "
            "اگه اطلاعات مهمی روشه، قبل از هر کاری به یه متخصص بازیابی اطلاعات بسپارش.",
        ],
        added=names, events=enum_events,
    )


def interpret(added_nodes: list, events: list, new_disks: list) -> LiveResult:
    """Pure decision logic (tested without Windows)."""
    added = _friendly(added_nodes)
    names = [a["name"] for a in added]
    enum_events = [e for e in events if ENUM_FAIL.search(f"{e.get('message', '')}")]

    if not added:
        if enum_events:
            return LiveResult(
                "enum_failed", "hardware",
                "دستگاه به پورت رسید، ولی ویندوز نتونست باهاش ارتباط بگیره",
                "ویندوز متوجه شد چیزی وصل شده ولی دستگاه درست جواب نداد. این تقریباً همیشه یعنی برق ناکافی، "
                "کابل خراب/بلند، هاب، یا خود دستگاه؛ نه تنظیمات ویندوز.",
                [
                    "دستگاه رو مستقیم به پورت پشت کیس (روی خود مادربرد) بزن، بدون هاب و کابل رابط.",
                    "یه کابل دیگه و کوتاه امتحان کن.",
                    "اگه هارد اکسترنال بدون آداپتوره، برق یک پورت کافی نیست؛ از هاب برق‌دار یا آداپتورش استفاده کن.",
                    "روی یه کامپیوتر دیگه امتحان کن: اگه اونجا هم کار نکرد، خود دستگاه خرابه.",
                ],
                events=enum_events,
            )
        return LiveResult(
            "nothing", "hardware",
            "ویندوز اصلاً متوجه وصل شدن دستگاه نشد",
            "هیچ اتفاقی تو ویندوز نیفتاد؛ نه دستگاهی اضافه شد و نه خطایی ثبت شد. یعنی سیگنالی به ویندوز نرسیده: "
            "معمولاً کابل (مثلاً کابل «فقط شارژ» که سیم دیتا نداره)، پورت خراب یا خاموش، یا خود دستگاه.",
            [
                "یه دستگاه سالم دیگه (مثلاً یه فلش) رو به همین پورت بزن: اگه اونم دیده نشد، پورت مشکل داره.",
                "کابل دیگه‌ای امتحان کن؛ بعضی کابل‌ها فقط شارژ می‌کنن و دیتا رد نمی‌کنن.",
                "اگه هیچ پورتی کار نمی‌کنه، تو BIOS ببین USB یا «XHCI Hand-Off» خاموش نباشه.",
                "دستگاه رو روی یه کامپیوتر دیگه امتحان کن.",
            ],
        )

    bad = [a for a in added if a["error_code"] or a["unknown"]]
    if bad:
        first = bad[0]
        code = first["error_code"]
        if first["unknown"] or code == 43:
            side = "hardware"
            title = "ویندوز دستگاه رو دید ولی دستگاه درست معرفی نشد"
            explanation = ("دستگاه وصل شد ولی اطلاعات خودش رو درست نفرستاد (Device Descriptor / کد 43). معمولاً برق "
                           "ناکافی، کابل، پورت یا خود دستگاهه؛ گاهی هم با ریست درست می‌شه.")
        elif code in (28, 31, 39):
            side = "software"
            title = "دستگاه وصل شد ولی درایورش نصب نیست یا خرابه"
            explanation = f"کد {code}: {strings.ERROR_CODES.get(code, '')}. این مشکل نرم‌افزاریه و با نصب درایور درست حل می‌شه."
        else:
            side = "software"
            title = "دستگاه وصل شد ولی ویندوز نتونست راه‌اندازیش کنه"
            explanation = f"کد {code}: {strings.ERROR_CODES.get(code, 'خطای نامشخص')}."
        fixes = [
            Finding("device_errors", "error", params={"lines": f"• {first['name']}"}, fix_id="restart_errors",
                    targets=[(i, code) for i in first["ids"][:1]]),
            Finding("selective_suspend", "warn", params={"ac": "?", "dc": "?"}, fix_id="disable_suspend", targets=[]),
        ]
        steps = ["اول «رفع پیشنهادی» رو بزن (ریست دستگاه + خاموش کردن Selective Suspend) و دوباره تست کن."]
        if side == "hardware":
            steps += ["اگه درست نشد: پورت پشت کیس، کابل دیگه، و بدون هاب امتحان کن.",
                      "روی کامپیوتر دیگه هم امتحان کن تا معلوم بشه دستگاه سالمه یا نه."]
        else:
            steps += ["از صفحهٔ «درایورها» درایور سازندهٔ دستگاه رو نصب کن، یا Windows Update رو اجرا کن."]
        return LiveResult("error", side, title, explanation, steps, fixes, names, enum_events)

    storage = [a for a in added if a["storage"]]
    for d in new_disks:
        parts = _partitions(d)
        if d.get("offline"):
            f = Finding("usb_disk_offline", "warn", params={"lines": f"• دیسک {d['number']}"}, fix_id="disk_online",
                        targets=[d["number"]])
            return LiveResult("storage_issue", "software", "حافظه وصل شد ولی ویندوز Offline نگهش داشته",
                              "ویندوز دیسک رو می‌بینه ولی فعالش نکرده. با یه کلیک درست می‌شه و به اطلاعات دست نمی‌زنه.",
                              ["«رفع پیشنهادی» رو بزن."], [f], names)
        if not (d.get("size") or 0) and not parts:
            continue  # a card-reader slot with no card in it: not a disk yet
        data = [p for p in parts if (p.get("size") or 0) > 0 and is_data_partition(p.get("type", ""))]
        if not data:
            steps = [strings.MANUAL["recover_data"],
                     "فقط اگه هارد نوئه یا اطلاعاتی روش نیست: تو Disk Management روی دیسک کلیک راست کن، "
                     + ("Initialize Disk و بعد " if str(d.get("style", "")).upper() == "RAW" else "")
                     + "New Simple Volume رو بزن."]
            if str(d.get("style", "")).upper() == "RAW":
                return LiveResult("storage_issue", "software", "حافظه وصل شد ولی مقداردهی نشده (Not Initialized)",
                                  "ویندوز دیسک رو کامل می‌بینه ولی هیچ جدول پارتیشنی روش نیست؛ برای همین تو This PC دیده نمی‌شه. "
                                  "یا هارد نوئه و هنوز آماده نشده، یا اطلاعات پارتیشن‌بندیش از بین رفته. اگه قبلاً روش "
                                  "اطلاعات داشتی، Initialize نکن.", steps, [], names, enum_events)
            return LiveResult("storage_issue", "software", "حافظه وصل شد ولی هیچ پارتیشنی نداره",
                              "ویندوز دیسک رو می‌بینه ولی فضاش پارتیشن‌بندی نشده (Unallocated)؛ برای همین تو This PC "
                              "دیده نمی‌شه. اگه قبلاً روش اطلاعات داشتی، پارتیشن جدید نساز.", steps, [], names, enum_events)
        raw = [p for p in data if str(p.get("fs", "")).upper() in ("RAW", "UNKNOWN")]
        if raw:
            return LiveResult("storage_issue", "hardware" if len(raw) == len(data) else "software",
                              "حافظه وصل شد ولی ویندوز نمی‌تونه محتواش رو بخونه (RAW)",
                              "فایل‌سیستم این حافظه خراب یا ناشناخته‌ست. ویندوز ممکنه پیشنهاد فرمت بده؛ این کار اطلاعات رو پاک می‌کنه.",
                              [strings.MANUAL["recover_data"], strings.MANUAL["format_after_recovery"]], [], names)
        no_letter = [p for p in data if not p.get("letter")]
        if no_letter and not any(p.get("letter") for p in parts):
            f = Finding("usb_disk_no_letter", "warn", params={"lines": f"• دیسک {d['number']}"}, fix_id="assign_letter",
                        targets=[(d["number"], p.get("number")) for p in no_letter])
            return LiveResult("storage_issue", "software", "حافظه وصل شد ولی حرف درایو نگرفت",
                              "برای همین تو This PC دیده نمی‌شه. با دادن حرف درایو درست می‌شه و به اطلاعات دست نمی‌زنه.",
                              ["«رفع پیشنهادی» رو بزن."], [f], names)

    letters = _letters(new_disks)
    if (storage or new_disks) and not letters:
        return _no_drive(storage, enum_events, names)
    extra = f" تو This PC با حرف {', '.join(l + ':' for l in letters)} دیده می‌شه." if letters else ""
    return LiveResult(
        "ok", "none", "دستگاه سالم وصل شد و ویندوز درست راه‌اندازیش کرد",
        f"وصل شد: {'، '.join(names)}.{extra} از نظر ویندوز و USB مشکلی نیست. اگه هنوز تو یه برنامهٔ خاص کار نمی‌کنه، "
        "مشکل از تنظیمات همون برنامه‌ست (مثلاً انتخاب دوربین/میکروفون درست تو تنظیماتش).",
        [], [], names, enum_events,
    )


def run_test(
    runner: Runner,
    duration: float = 30,
    interval: float = 1.5,
    on_progress: Optional[Callable[[float, int], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    disk_wait: float = 12,
) -> LiveResult:
    """Wait up to `duration` seconds for something to be plugged in, let it settle, then interpret."""
    start = clock()
    before = poll_nodes(runner)
    disks_before = poll_disks(runner)
    added: dict = {}
    quiet_polls = 0
    while clock() - start < duration:
        if should_stop and should_stop():
            break
        sleep(interval)
        now = poll_nodes(runner)
        new = {k: v for k, v in now.items() if k not in before}
        if new:
            grew = len(new) > len(added)
            added.update(new)
            for k in added:  # keep the latest error code of each node
                if k in now:
                    added[k] = now[k]
            quiet_polls = 0 if grew else quiet_polls + 1
            if quiet_polls >= 2:  # nothing new for two polls: Windows has finished setting it up
                break
        if on_progress:
            on_progress(clock() - start, len(added))
    new_disks = _new_disks(runner, disks_before) if added else []
    if added and any(a["storage"] for a in _friendly(list(added.values()))):
        # the disk and its drive letter come a few seconds after the USB part: give them time before judging
        waited = clock()
        while not _letters(new_disks) and clock() - waited < disk_wait:
            if should_stop and should_stop():
                break
            sleep(interval)
            new_disks = _new_disks(runner, disks_before)
            if on_progress:
                on_progress(clock() - start, len(added))
    events = recent_events(runner, clock() - start + 5)
    return interpret(list(added.values()), events, new_disks)


def _new_disks(runner: Runner, before: dict) -> list:
    return [d for n, d in poll_disks(runner).items() if n not in before]
