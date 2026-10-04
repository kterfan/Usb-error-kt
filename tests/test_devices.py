import unittest

from usb_fixer import demo, devices
from usb_fixer.diagnostics import scan


class DeviceListTests(unittest.TestCase):
    def setUp(self):
        self.items = devices.build(scan(demo.DemoRunner()).snapshot)
        self.by_name = {d.name: d for d in self.items}

    def test_children_are_merged_into_one_physical_device(self):
        receiver = self.by_name["Logitech USB Receiver"]
        self.assertEqual(receiver.type, "keyboard_mouse")
        self.assertEqual(receiver.status, "error")
        self.assertEqual(receiver.error_code, 10)
        self.assertGreaterEqual(len(receiver.ids), 3)  # composite + HID keyboard/mouse

    def test_generic_windows_names_are_replaced(self):
        names = set(self.by_name)
        self.assertNotIn("USB Composite Device", names)
        self.assertNotIn("USB Mass Storage Device", names)
        self.assertIn("Logitech BRIO 4K Stream Edition", names)
        self.assertIn("SanDisk Ultra", names)

    def test_groups_and_order(self):
        groups = [d.group for d in self.items]
        self.assertEqual(groups, sorted(groups, key=["yours", "system", "past"].index))
        yours = [d for d in self.items if d.group == "yours"]
        self.assertEqual(yours[0].status, "error")  # broken devices first
        self.assertTrue(any(d.group == "system" and d.type == "root_hub" for d in self.items))
        past = [d for d in self.items if d.group == "past"]
        self.assertTrue(past and all(d.status == "absent" for d in past))

    def test_unknown_device(self):
        unknown = next(d for d in self.items if d.type == "unknown")
        self.assertEqual(unknown.error_code, 43)
        self.assertIn("ناشناس", unknown.name)

    def test_status_text_is_plain_persian(self):
        self.assertIn("سالم", self.by_name["SanDisk Ultra"].status_text)
        self.assertIn("10", self.by_name["Logitech USB Receiver"].status_text)

    def test_vendor_lookup(self):
        self.assertEqual(devices.vendor_name("046D"), "Logitech")
        self.assertEqual(devices.vid_pid("USB\\VID_0781&PID_5581\\X"), ("0781", "5581"))
        self.assertEqual(devices.vid_pid("USB\\ROOT_HUB30\\X"), (None, None))

    def test_no_nodes(self):
        inv = dict(demo.DEMO_INVENTORY, nodes=[], devices=[])
        snap = scan(demo.DemoRunner(inventory=inv)).snapshot
        self.assertEqual(devices.build(snap), [])


if __name__ == "__main__":
    unittest.main()
