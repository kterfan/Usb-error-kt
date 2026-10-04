import unittest
from datetime import date

from usb_fixer import demo, guide, report, snapshot
from usb_fixer.diagnostics import scan

TODAY = date(2026, 10, 4)


class GuideTests(unittest.TestCase):
    def setUp(self):
        self.system, _ = snapshot.parse_inventory(demo.DEMO_INVENTORY)
        self.cards = guide.build_cards(self.system, TODAY)

    def test_one_card_per_controller_plus_board(self):
        self.assertEqual(len(self.cards), 3)
        self.assertTrue(self.cards[-1].name.startswith("مادربرد"))

    def test_hardware_id_and_subsystem(self):
        asmedia = self.cards[1]
        self.assertEqual(asmedia.hardware_id, "PCI\\VEN_1B21&DEV_1142")
        self.assertEqual(asmedia.short_id, "VEN_1B21&DEV_1142")
        self.assertEqual(asmedia.subsystem, "11421B21")

    def test_catalog_link_uses_hardware_id(self):
        urls = [u for _, u in self.cards[1].links]
        self.assertTrue(any(u.startswith("https://www.catalog.update.microsoft.com/Search.aspx?q=VEN_1B21%26DEV_1142") for u in urls))

    def test_vendor_pages(self):
        self.assertIn("intel.com", guide.VENDOR_PAGES["8086"][1])
        amd_urls = [u for _, u in self.cards[0].links]
        self.assertIn("https://www.amd.com/en/support", amd_urls)
        # no verified page for ASMedia: falls back to a search link
        self.assertTrue(any("google.com/search" in u for _, u in self.cards[1].links))

    def test_generic_driver_advice(self):
        self.assertTrue(self.cards[0].is_generic)
        self.assertIn("عمومی", self.cards[0].advice[0])

    def test_old_vendor_driver_is_flagged(self):
        self.system.controllers[0].driver_provider = "Advanced Micro Devices, Inc."
        self.system.controllers[0].driver_date = "2019-01-01"
        cards = guide.build_cards(self.system, TODAY)
        self.assertIn("قدیمیه", cards[0].advice[0])

    def test_laptop_gets_laptop_support_link(self):
        self.system.is_laptop = True
        self.system.system_manufacturer, self.system.system_model = "Dell Inc.", "Latitude 7420"
        board = guide.build_cards(self.system, TODAY)[-1]
        self.assertEqual(len(board.links), 2)

    def test_report_contains_guide(self):
        text = report.build_report(scan(demo.DemoRunner(), TODAY))
        self.assertIn(report.strings.UI["guide_header"], text)
        self.assertIn("PCI\\VEN_1B21&DEV_1142", text)


if __name__ == "__main__":
    unittest.main()
