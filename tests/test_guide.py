import unittest
from datetime import date

from usb_fixer import bios, demo, guide, report, snapshot
from usb_fixer.diagnostics import scan

TODAY = date(2026, 10, 4)


class DriverReportTests(unittest.TestCase):
    def setUp(self):
        self.system, _ = snapshot.parse_inventory(demo.DEMO_INVENTORY)

    def test_inbox_drivers_give_a_clear_no_action_verdict(self):
        rep = guide.build_report(self.system, today=TODAY)
        self.assertTrue(rep.verdict_ok)
        self.assertIn("لازم نیست", rep.verdict_title)
        self.assertEqual(len(rep.controllers), 2)
        self.assertTrue(all(c.ok for c in rep.controllers))

    def test_controller_role_is_explained_in_plain_words(self):
        rep = guide.build_report(self.system, today=TODAY)
        self.assertIn("سری 400", rep.controllers[0].title)  # AMD 43D5 = B450/X470 chipset ports
        self.assertIn("ASMedia", rep.controllers[1].title)

    def test_technical_ids_are_kept_but_hidden_in_tech(self):
        asmedia = guide.build_report(self.system, today=TODAY).controllers[1]
        self.assertEqual(asmedia.hardware_id, "PCI\\VEN_1B21&DEV_1142")
        self.assertIn("SUBSYS_11421B21", dict(asmedia.tech)["Hardware ID"])

    def test_addon_chip_gets_catalog_link_only_as_an_option(self):
        asmedia = guide.build_report(self.system, today=TODAY).controllers[1]
        self.assertTrue(asmedia.ok)
        urls = [u for _, u in asmedia.links]
        self.assertTrue(any(u.startswith("https://www.catalog.update.microsoft.com/Search.aspx?q=VEN_1B21%26DEV_1142") for u in urls))

    def test_old_vendor_driver_flips_the_verdict(self):
        self.system.controllers[0].driver_provider = "Advanced Micro Devices, Inc."
        self.system.controllers[0].driver_date = "2019-01-01"
        rep = guide.build_report(self.system, today=TODAY)
        self.assertFalse(rep.verdict_ok)
        self.assertFalse(rep.controllers[0].ok)
        self.assertIn("قدیمی", rep.verdict_title)

    def test_amd_chipset_action_is_optional(self):
        rep = guide.build_report(self.system, today=TODAY)
        self.assertTrue(any("amd.com" in a[2] and a[0].startswith("اختیاری") for a in rep.actions))

    def test_bios_section_states(self):
        rep = guide.build_report(self.system, None, TODAY)
        self.assertIsNone(rep.bios_ok)
        self.assertIn("آنلاین چک نشده", rep.bios_text)

        current = bios.BiosCheck("current", "3202", "3202", date(2020, 3, 10), source="ASUS")
        rep = guide.build_report(self.system, current, TODAY)
        self.assertTrue(rep.bios_ok)
        self.assertIn("به‌روزه", rep.bios_title)

        update = bios.BiosCheck("update", "3202", "5220", date(2026, 5, 14), "1. a\n2. b", "https://dlcdnets.asus.com/x.zip", source="ASUS")
        rep = guide.build_report(self.system, update, TODAY)
        self.assertFalse(rep.bios_ok)
        self.assertIn("5220", rep.bios_title)
        self.assertEqual(rep.bios_links[0][1], "https://dlcdnets.asus.com/x.zip")
        self.assertIn("• ⁨1. a⁩", rep.bios_text)

        unknown = bios.BiosCheck("unknown", "3202", reason="network")
        rep = guide.build_report(self.system, unknown, TODAY)
        self.assertIsNone(rep.bios_ok)
        self.assertIn("network", rep.bios_text)

    def test_laptop_uses_laptop_model_for_support_search(self):
        self.system.is_laptop = True
        self.system.system_manufacturer, self.system.system_model = "Dell Inc.", "Latitude 7420"
        self.assertEqual(guide.board_name(self.system), "Dell Inc. Latitude 7420")

    def test_report_contains_guide_and_author(self):
        text = report.build_report(scan(demo.DemoRunner(), TODAY))
        self.assertIn("درایورهای USB تو مشکلی ندارن", text)
        self.assertIn("PCI\\VEN_1B21&DEV_1142", text)
        self.assertIn("Erfan Esmailzadeh", text)
        self.assertIn("https://github.com/kterfan", text)


if __name__ == "__main__":
    unittest.main()
