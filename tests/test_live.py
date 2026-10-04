import json
import unittest

from usb_fixer import demo, live
from usb_fixer.system import CmdResult, decode_powershell_cmd

UNKNOWN = {"id": "USB\\VID_0000&PID_0002\\5&1", "name": "Unknown USB Device (Device Descriptor Request Failed)", "error_code": 43}
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
