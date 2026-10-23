import json
import unittest

from usb_fixer import demo, live
from usb_fixer.system import CmdResult, decode_powershell_cmd

UNKNOWN = {"id": "USB\\VID_0000&PID_0002\\5&1", "name": "Unknown USB Device (Device Descriptor Request Failed)", "error_code": 43}
TRANSCEND_UAS = {"id": "USB\\VID_8564&PID_1000\\A1B2", "name": "USB Attached SCSI (UAS) Mass Storage Device",
                 "cls": "SCSIAdapter", "error_code": 0}
ENUM_EVENT = {"provider": "Microsoft-Windows-USB-USBHUB3", "id": 43, "message": "Enumeration of device on port 4 failed."}


class InterpretTests(unittest.TestCase):
    def test_nothing_at_all_is_hardware(self):
        r = live.interpret([], [], [])
        self.assertEqual((r.kind, r.side), ("nothing", "hardware"))
        self.assertTrue(any("کابل" in s for s in r.steps))

    def test_enumeration_failure_without_device_is_hardware(self):
        r = live.interpret([], [ENUM_EVENT], [])
        self.assertEqual((r.kind, r.side), ("enum_failed", "hardware"))
        self.assertEqual(r.events, [ENUM_EVENT])

    def test_unrelated_event_is_ignored(self):
        r = live.interpret([], [{"provider": "Kernel-PnP", "id": 1, "message": "configured"}], [])
        self.assertEqual(r.kind, "nothing")

    def test_unknown_device_offers_a_reset(self):
        r = live.interpret([UNKNOWN], [ENUM_EVENT], [])
        self.assertEqual((r.kind, r.side), ("error", "hardware"))
        self.assertEqual(r.fixes[0].fix_id, "restart_errors")
        self.assertEqual(r.fixes[0].targets, [(UNKNOWN["id"], 43)])
        self.assertIn("ناشناس", r.added[0])

    def test_missing_driver_is_software(self):
        node = {"id": "USB\\VID_1234&PID_0001\\1", "name": "Gadget", "error_code": 28}
        r = live.interpret([node], [], [])
        self.assertEqual((r.kind, r.side), ("error", "software"))
        self.assertIn("28", r.explanation)

    def test_healthy_device_with_drive_letter(self):
        nodes = [{"id": "USB\\VID_0781&PID_5581\\X", "name": "USB Mass Storage Device", "error_code": 0},
                 {"id": "USBSTOR\\DISK&VEN_SANDISK\\X&0", "name": "SanDisk Ultra USB Device", "error_code": 0}]
        disk = {"number": 3, "offline": False, "partitions": [{"number": 1, "letter": "E", "type": "Basic", "size": 10, "fs": "FAT32"}]}
        r = live.interpret(nodes, [], [disk])
        self.assertEqual((r.kind, r.side), ("ok", "none"))
        self.assertEqual(r.added, ["SanDisk Ultra USB Device"])
        self.assertIn("E:", r.explanation)

    def test_storage_problems(self):
        node = [{"id": "USB\\VID_0781&PID_5581\\X", "name": "x", "error_code": 0}]
        offline = {"number": 3, "offline": True, "partitions": []}
        self.assertEqual(live.interpret(node, [], [offline]).fixes[0].fix_id, "disk_online")
        raw = {"number": 3, "partitions": {"number": 1, "letter": "F", "type": "Basic", "size": 10, "fs": "RAW"}}
        r = live.interpret(node, [], [raw])
        self.assertEqual(r.kind, "storage_issue")
        self.assertEqual(r.fixes, [])  # never offer to format
        self.assertTrue(any("ریکاوری" in s or "بازیابی" in s for s in r.steps))
        noletter = {"number": 3, "partitions": [{"number": 1, "letter": "", "type": "Basic", "size": 10, "fs": "NTFS"}]}
        r = live.interpret(node, [], [noletter])
        self.assertEqual(r.fixes[0].fix_id, "assign_letter")
        self.assertEqual(r.fixes[0].targets, [(3, 1)])

    def test_storage_without_a_disk_is_not_healthy(self):
        # the reported bug: a Transcend UASP drive arrived, no disk came of it, and the result said "healthy"
        r = live.interpret([TRANSCEND_UAS], [], [])
        self.assertEqual((r.kind, r.side), ("storage_issue", "hardware"))
        self.assertIn("This PC", r.explanation)
        self.assertEqual(r.added, ["دستگاه USB Transcend"])
        bot = {"id": "USB\\VID_8564&PID_1000\\X", "name": "USB Mass Storage Device", "cls": "USB", "error_code": 0}
        self.assertEqual(live.interpret([bot], [], []).kind, "storage_issue")

    def test_disk_without_any_letter_is_not_healthy(self):
        disk = {"number": 3, "size": 10, "partitions": [{"number": 1, "letter": "", "type": "Unknown", "size": 10, "fs": ""}]}
        self.assertNotEqual(live.interpret([TRANSCEND_UAS], [], [disk]).kind, "ok")

    def test_uninitialized_and_empty_disks(self):
        new = {"number": 3, "size": 10**12, "style": "RAW", "partitions": []}
        r = live.interpret([TRANSCEND_UAS], [], [new])
        self.assertEqual(r.kind, "storage_issue")
        self.assertIn("Not Initialized", r.title)
        self.assertEqual(r.fixes, [])  # never initializes on its own
        self.assertTrue(any("Initialize" in s for s in r.steps))
        msr_only = {"number": 3, "size": 10**12, "style": "GPT",
                    "partitions": [{"number": 1, "letter": "", "type": "Reserved", "size": 16, "fs": ""}]}
        r = live.interpret([TRANSCEND_UAS], [], [msr_only])
        self.assertEqual((r.kind, r.fixes), ("storage_issue", []))
        self.assertNotIn("Initialize", " ".join(r.steps))

    def test_fat32_partition_without_letter_gets_one(self):
        disk = {"number": 4, "size": 10, "partitions": [
            {"number": 1, "letter": "", "type": "FAT32 XINT13", "size": 10, "fs": "FAT32"}]}
        r = live.interpret([TRANSCEND_UAS], [], [disk])
        self.assertEqual(r.fixes[0].fix_id, "assign_letter")

    def test_empty_card_reader(self):
        nodes = [{"id": "USB\\VID_05E3&PID_0749\\1", "name": "USB Mass Storage Device", "cls": "USB", "error_code": 0},
                 {"id": "USBSTOR\\DISK&VEN_GENERIC-&PROD_SD/MMC\\1&0", "name": "Generic- SD/MMC USB Device",
                  "cls": "DiskDrive", "error_code": 0}]
        r = live.interpret(nodes, [], [{"number": 5, "size": 0, "partitions": []}])
        self.assertEqual(r.kind, "storage_issue")
        self.assertIn("کارت", r.title)

    def test_non_storage_device_needs_no_drive(self):
        mouse = {"id": "USB\\VID_046D&PID_C077\\1", "name": "HID-compliant mouse", "cls": "Mouse", "error_code": 0}
        self.assertEqual(live.interpret([mouse], [], []).kind, "ok")

    def test_nul_drive_letter_from_powershell_is_no_letter(self):
        out = json.dumps({"number": 3, "size": 10, "partitions": {"number": 1, "letter": "\u0000", "type": "Basic",
                                                                  "size": 10, "fs": "NTFS"}})
        disks = live.poll_disks(lambda c: CmdResult(0, out))
        self.assertEqual(disks[3]["partitions"][0]["letter"], "")
        self.assertEqual(live.interpret([TRANSCEND_UAS], [], list(disks.values())).fixes[0].fix_id, "assign_letter")


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


class RunTests(unittest.TestCase):
    def test_demo_arrival_is_detected_and_stops_early(self):
        clock = FakeClock()
        progress = []
        r = live.run_test(demo.DemoRunner(), duration=30, interval=1, sleep=clock.sleep, clock=clock,
                          on_progress=lambda t, n: progress.append(n))
        self.assertEqual(r.kind, "error")
        self.assertEqual(r.events[0]["id"], 43)
        self.assertLess(clock.t, 10)  # stopped once the device settled, did not wait 30s
        self.assertEqual(progress[-1], 1)

    def test_nothing_plugged_waits_full_duration(self):
        class Quiet(demo.DemoRunner):
            def __call__(self, cmd):
                script = decode_powershell_cmd(list(cmd)) or ""
                if "live-nodes" in script or "live-disks" in script or "live-events" in script:
                    return CmdResult(0, "[]")
                return super().__call__(cmd)

        clock = FakeClock()
        r = live.run_test(Quiet(), duration=6, interval=1, sleep=clock.sleep, clock=clock)
        self.assertEqual(r.kind, "nothing")
        self.assertGreaterEqual(clock.t, 6)

    def storage_runner(self, letter_after: int):
        """A Transcend drive arrives on the 3rd poll; its disk gets a letter `letter_after` disk polls later."""
        class Drive(demo.DemoRunner):
            disk_polls = 0

            def __call__(self, cmd):
                script = decode_powershell_cmd(list(cmd)) or ""
                if "live-nodes" in script:
                    self.live_polls += 1
                    return CmdResult(0, json.dumps([TRANSCEND_UAS] if self.live_polls > 2 else []))
                if "live-disks" in script:
                    self.disk_polls += 1
                    disks = [{"number": 0, "size": 10, "partitions": [{"number": 1, "letter": "C", "type": "Basic", "size": 10}]}]
                    if self.live_polls > 2 and self.disk_polls > letter_after:
                        disks.append({"number": 7, "size": 10, "partitions": [
                            {"number": 1, "letter": "J", "type": "Basic", "size": 10, "fs": "NTFS"}]})
                    return CmdResult(0, json.dumps(disks))
                if "live-events" in script:
                    return CmdResult(0, "[]")
                return super().__call__(cmd)
        return Drive()

    def test_waits_for_the_drive_letter_before_judging(self):
        clock = FakeClock()
        r = live.run_test(self.storage_runner(letter_after=5), duration=30, interval=1, sleep=clock.sleep, clock=clock)
        self.assertEqual(r.kind, "ok")
        self.assertIn("J:", r.explanation)

    def test_drive_that_never_shows_up_is_reported(self):
        clock = FakeClock()
        r = live.run_test(self.storage_runner(letter_after=10**6), duration=30, interval=1, sleep=clock.sleep, clock=clock,
                          disk_wait=5)
        self.assertEqual(r.kind, "storage_issue")
        self.assertLess(clock.t, 15)  # gave up after the wait, not after the whole test

    def test_user_can_stop(self):
        clock = FakeClock()
        r = live.run_test(demo.DemoRunner(), duration=30, interval=1, sleep=clock.sleep, clock=clock, should_stop=lambda: True)
        self.assertEqual(r.kind, "nothing")
        self.assertEqual(clock.t, 0)

    def test_single_object_json_is_accepted(self):
        class One(demo.DemoRunner):
            def __call__(self, cmd):
                if "live-nodes" in (decode_powershell_cmd(list(cmd)) or ""):
                    return CmdResult(0, json.dumps(UNKNOWN))  # PowerShell returns an object, not a list, for one item
                return super().__call__(cmd)

        self.assertIn(UNKNOWN["id"], live.poll_nodes(One()))
        self.assertEqual(live.poll_nodes(lambda c: CmdResult(1, "", "x")), {})
        self.assertEqual(live.poll_nodes(lambda c: CmdResult(0, "garbage")), {})


if __name__ == "__main__":
    unittest.main()
