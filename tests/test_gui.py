import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6 import QtCore
    from usb_fixer import gui
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
        for _ in range(200):
            self.app.processEvents()
            if win.result is not None:
                break
            QtCore.QThread.msleep(20)
        self.assertIsNotNone(win.result, "scan did not finish")
        return win

    def test_bundled_font_is_loaded(self):
        self.assertTrue(gui.FONT_DIR.joinpath("Vazirmatn-Regular.ttf").is_file())
        families = gui.QtGui.QFontDatabase.families()
        self.assertIn("Vazirmatn", families)
        self.assertEqual(self.app.font().family(), "Vazirmatn")

    def test_scan_fills_every_tab(self):
        win = self.make_window()
        self.assertEqual(win.tree.topLevelItemCount(), len(win.findings))
        self.assertEqual(win.dev_tree.topLevelItemCount(), 5)
        self.assertEqual(win.guide_tree.topLevelItemCount(), 3)
        self.assertIn("مورد پیدا شد", win.summary.text())

    def test_default_checks_match_fix_defaults(self):
        win = self.make_window()
        checked = {f.fix_id for f in win._checked_findings()}
        self.assertIn("disable_suspend", checked)
        self.assertNotIn("disable_fast_startup", checked)

    def test_detail_is_rich_text_with_rtl_paragraphs(self):
        win = self.make_window()
        html = win.detail.toHtml()
        self.assertIn("دستگاه‌های USB با کد خطا", win.detail.toPlainText())
        self.assertIn("rtl", html.lower())

    def test_guide_links_and_copy(self):
        win = self.make_window()
        win.guide_tree.setCurrentItem(win.guide_tree.topLevelItem(1))
        self.assertIn("catalog.update.microsoft.com", win.guide_detail.toHtml())
        win.on_copy_id()
        self.assertEqual(self.app.clipboard().text(), "PCI\\VEN_1B21&DEV_1142")

    def test_fix_runs_after_confirmation(self):
        win = self.make_window()
        runner = win.runner
        win._ask = lambda *a, **k: True
        import tempfile
        os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()
        win.on_fix()
        for _ in range(300):
            self.app.processEvents()
            if "ناموفق: ۰" in win.log_box.toPlainText():
                break
            QtCore.QThread.msleep(20)
        self.assertIn("ناموفق: ۰", win.log_box.toPlainText())
        self.assertIn(["pnputil", "/scan-devices"], runner.calls)

    def test_nothing_selected_does_not_run(self):
        win = self.make_window()
        for i in range(win.tree.topLevelItemCount()):
            item = win.tree.topLevelItem(i)
            if item.flags() & gui.Qt.ItemIsUserCheckable:
                item.setCheckState(0, gui.Qt.Unchecked)
        shown = []
        win._info = lambda text, warn=False: shown.append(text)
        win.on_fix()
        self.assertEqual(shown, [gui.UI["nothing_selected"]])


if __name__ == "__main__":
    unittest.main()
