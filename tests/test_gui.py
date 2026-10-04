import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["USB_FIXER_SETTINGS_PATH"] = os.path.join(tempfile.mkdtemp(), "settings.ini")

try:
    from PySide6 import QtCore
    from usb_fixer import gui
    from usb_fixer.ui import theme
except ImportError:  # PySide6 (or the system libs for it) not installed
    gui = None

from usb_fixer import demo


@unittest.skipIf(gui is None, "PySide6 not available")
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = gui.make_app([])

    def make_window(self):
        win = gui.MainWindow(demo.DemoRunner(), demo=True)
        self.wait(win)
        return win

    def wait(self, win, cond=None):
        cond = cond or (lambda: win.result is not None and not win.busy)
        for _ in range(300):
            self.app.processEvents()
            if cond():
                return
            QtCore.QThread.msleep(20)
        self.fail("timed out")

    def test_bundled_font_is_loaded(self):
        self.assertTrue(gui.FONT_DIR.joinpath("Vazirmatn-Regular.ttf").is_file())
        self.assertIn("Vazirmatn", gui.QtGui.QFontDatabase.families())
        self.assertEqual(self.app.font().family(), "Vazirmatn")

    def test_scan_fills_every_page(self):
        win = self.make_window()
        self.assertEqual(len(win.problem_cards), len(win.findings))
        self.assertEqual(win.device_tree.topLevelItemCount(), 5)
        self.assertEqual(len(win.driver_cards), 3)
        self.assertIn("مشکل مهم", win.headline.text())

    def test_hero_counts_selected_fixes(self):
        win = self.make_window()
        n = len(win._checked_findings())
        self.assertGreater(n, 0)
        self.assertIn("انتخاب‌شده", win.btn_fix.text())
        self.assertTrue(win.btn_fix.isEnabled())
        for c in win.problem_cards:
            c.check.setChecked(False)
        self.assertFalse(win.btn_fix.isEnabled())

    def test_default_checks_match_fix_defaults(self):
        win = self.make_window()
        checked = {f.fix_id for f in win._checked_findings()}
        self.assertIn("disable_suspend", checked)
        self.assertNotIn("disable_fast_startup", checked)

    def test_details_expand_and_collapse(self):
        win = self.make_window()
        card = win.problem_cards[0]
        self.assertTrue(card.details.isHidden())
        card.toggle_details()
        self.assertFalse(card.details.isHidden())
        self.assertTrue(card.summary.isHidden())
        self.assertIn("دستگاه", card.details.text())
        card.toggle_details()
        self.assertTrue(card.details.isHidden())

    def test_driver_card_copy(self):
        win = self.make_window()
        win.driver_cards[1].copied.emit(win.driver_cards[1].card.hardware_id)
        self.assertEqual(self.app.clipboard().text(), "PCI\\VEN_1B21&DEV_1142")

    def test_theme_switch_changes_palette_and_persists(self):
        win = self.make_window()
        win.mode = "light"
        win.apply_theme()
        self.assertEqual(theme.CURRENT["name"], "light")
        win.cycle_theme()  # light -> dark
        self.assertEqual(win.mode, "dark")
        self.assertEqual(theme.CURRENT["name"], "dark")
        self.assertEqual(win.settings.value("theme"), "dark")
        self.assertEqual(len(win.problem_cards), len(win.findings))  # re-rendered, nothing lost
        win.mode = "auto"
        win.apply_theme()

    def test_fix_runs_after_confirmation(self):
        win = self.make_window()
        runner = win.runner
        asked = []
        win._ask = lambda title, intro, lines: asked.append(lines) or True
        os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()
        win.on_fix()
        self.wait(win, lambda: "ناموفق" in win.notice and not win.busy)
        self.assertTrue(asked and any("powercfg" in l for l in asked[0]))
        self.assertIn("۰ ناموفق", win.notice)
        self.assertIn(["pnputil", "/scan-devices"], runner.calls)

    def test_nothing_selected_does_not_run(self):
        win = self.make_window()
        for c in win.problem_cards:
            c.check.setChecked(False)
        shown = []
        win._info = lambda text, warn=False: shown.append(text)
        win.on_fix()
        self.assertEqual(shown, [gui.UI["nothing_selected"]])

    def test_clean_machine_shows_ok(self):
        inv = dict(demo.DEMO_INVENTORY, board_product="PRIME Z790-P", cpu="Intel(R) Core(TM) i7", bios_date="2026-01-01")
        inv["devices"] = inv["devices"][:1]
        inv["controllers"] = [dict(c, driver_provider="Intel") for c in inv["controllers"]]
        state = {"services": {"PlugPlay": 4}, "usbstor_start": 3, "uaspstor_start": 3, "hub_power": [], "disks": [], "events": []}
        off = "Current AC Power Setting Index: 0x00000000\nCurrent DC Power Setting Index: 0x00000000\n"
        win = gui.MainWindow(demo.DemoRunner(inv, state, power=off), demo=True)
        self.wait(win)
        self.assertEqual(win.problem_cards, [])
        self.assertIn("مشکلی پیدا نشد", win.headline.text())
        self.assertEqual(win.hero.property("state"), "ok")


if __name__ == "__main__":
    unittest.main()
