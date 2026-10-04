import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["USB_FIXER_SETTINGS_PATH"] = os.path.join(tempfile.mkdtemp(), "settings.ini")
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()  # backups/state of these tests never touch the real profile

try:
    from PySide6 import QtCore, QtWidgets
    from usb_fixer import gui
    from usb_fixer.ui import theme
except ImportError:  # PySide6 (or the system libs for it) not installed
    gui = None

from usb_fixer import about, demo, state, strings


def texts(widget):
    """All visible text in a widget tree (labels and buttons)."""
    out = [w.text() for w in widget.findChildren(QtWidgets.QLabel)]
    out += [w.text() for w in widget.findChildren(QtWidgets.QAbstractButton)]
    return "\n".join(out)


@unittest.skipIf(gui is None, "PySide6 not available")
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = gui.make_app([])

    def setUp(self):
        state.save({})

    def make_window(self, runner=None):
        win = gui.MainWindow(runner or demo.DemoRunner(), demo=True)
        win.resize(1100, 800)
        self.addCleanup(self.close, win)
        self.wait(lambda: win.result is not None and not win.busy and win.bios is not None and not win.bios_checking)
        return win

    def close(self, win):
        self.wait(lambda: not win.busy and not win.live_running and not win.bios_checking)
        win.close()
        win.deleteLater()
        self.app.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)

    def wait(self, cond, steps=500):
        for _ in range(steps):
            self.app.processEvents()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)  # old cards really go away
            if cond():
                return
            QtCore.QThread.msleep(10)
        self.fail("timed out")

    # ---------- identity ----------
    def test_bundled_font_is_loaded(self):
        self.assertTrue(gui.FONT_DIR.joinpath("Vazirmatn-Regular.ttf").is_file())
        self.assertIn("Vazirmatn", gui.QtGui.QFontDatabase.families())
        self.assertEqual(self.app.font().family(), "Vazirmatn")

    def test_author_and_version_are_shown(self):
        win = self.make_window()
        self.assertIn(about.VERSION, win.windowTitle())
        footer = win.credit.text()
        for part in (about.AUTHOR_FA, about.AUTHOR_EN, about.GITHUB_PROFILE, about.VERSION):
            self.assertIn(part, footer)
        self.assertEqual(self.app.applicationVersion(), about.VERSION)

    def test_about_dialog(self):
        win = self.make_window()
        dlg = gui.AboutDialog(win)
        t = texts(dlg)
        for part in (about.AUTHOR_FA, about.AUTHOR_EN, about.VERSION, "github.com/kterfan", about.PRIVACY_FA[:20]):
            self.assertIn(part, t)

    # ---------- pages ----------
    def test_scan_fills_every_page(self):
        win = self.make_window()
        self.assertEqual(len(win.problem_cards), len(win.findings) + 1)  # + optional "reset all USB" tool
        self.assertEqual(len(win.device_rows), 7)
        self.assertEqual(len(win.controller_cards), 2)
        self.assertIn("مشکل مهم", win.headline.text())
        self.assertEqual(gui.PAGES, ("problems", "live", "devices", "drivers", "system"))
        for name in gui.PAGES:
            win.go(name)
            self.assertEqual(win.stack.currentIndex(), gui.PAGES.index(name))

    def test_every_problem_card_shows_a_suggestion(self):
        win = self.make_window()
        for card in win.problem_cards:
            self.assertTrue(card.finding.recommendation)
            self.assertIn(card.finding.recommendation[:20], texts(card))

    def test_online_bios_answer_reaches_the_drivers_page(self):
        win = self.make_window()
        self.assertEqual(win.bios.latest, "5220")
        self.assertIn("5220", win.driver_report.bios_title)
        keys = [f.key for f in win.findings]
        self.assertIn("bios_update", keys)
        self.assertNotIn("bios_old", keys)

    def test_devices_page_uses_real_names(self):
        win = self.make_window()
        names = [r.device.name for r in win.device_rows]
        self.assertIn("Logitech USB Receiver", names)
        self.assertNotIn("USB Composite Device", names)

    def test_tech_copy(self):
        win = self.make_window()
        win.controller_cards[1].copied.emit(win.controller_cards[1].card.hardware_id)
        self.assertEqual(self.app.clipboard().text(), "PCI\\VEN_1B21&DEV_1142")

    # ---------- selection & confirm ----------
    def test_hero_counts_selected_fixes(self):
        win = self.make_window()
        self.assertGreater(len(win._checked_findings()), 0)
        self.assertIn("انتخاب‌شده", win.btn_fix.text())
        self.assertTrue(win.btn_fix.isEnabled())
        for c in win.problem_cards:
            c.check.setChecked(False)
        self.assertFalse(win.btn_fix.isEnabled())

    def test_default_checks(self):
        win = self.make_window()
        checked = {f.fix_id for f in win._checked_findings()}
        self.assertIn("disable_suspend", checked)
        self.assertNotIn("disable_fast_startup", checked)
        self.assertNotIn("reset_usb_stack", checked)

    def test_details_expand_and_collapse(self):
        win = self.make_window()
        card = win.problem_cards[0]
        self.assertTrue(card.details.isHidden())
        card.toggle_details()
        self.assertFalse(card.details.isHidden())
        card.toggle_details()
        self.assertTrue(card.details.isHidden())

    def test_confirm_dialog_explains_each_fix(self):
        win = self.make_window()
        dlg = win.make_confirm_dialog()
        chosen = []
        for f in win._checked_findings():
            if f.fix_id not in chosen:
                chosen.append(f.fix_id)
        self.assertEqual(dlg.blocks, chosen)
        t = texts(dlg)
        for fid in chosen:
            self.assertIn(strings.FIX_INFO[fid]["plain"][:25], t)
            self.assertIn(strings.FIX_INFO[fid]["reco"][:25], t)
        self.assertIn("نقطهٔ بازیابی", t)
        self.assertIn("بی‌خطر", t)
        self.assertTrue(dlg.tech.isHidden())  # raw commands only on request
        dlg._toggle_tech()
        self.assertFalse(dlg.tech.isHidden())
        self.assertIn("powercfg", dlg.tech.toPlainText())

    def test_risky_fix_is_labelled(self):
        win = self.make_window()
        fast = next(f for f in win.findings if f.fix_id == "disable_fast_startup")
        self.assertIn(strings.RISK_LABEL[strings.FIX_INFO["disable_fast_startup"]["risk"]], texts(win.make_confirm_dialog([fast])))

    def test_fix_runs_after_confirmation_and_is_remembered(self):
        win = self.make_window()
        asked = []
        win._ask_fix = lambda findings, steps: asked.append(steps) or True
        win.on_fix()
        self.wait(lambda: "ناموفق" in win.notice and not win.busy)
        self.assertTrue(asked and any("powercfg" in s.shown for s in asked[0]))
        self.assertIn("۰ ناموفق", win.notice)
        self.assertIn(["pnputil", "/scan-devices"], win.runner.calls)
        self.assertIn("disable_suspend", state.applied_ids())

    def test_cancel_does_nothing(self):
        win = self.make_window()
        before = len(win.runner.calls)
        win._ask_fix = lambda findings, steps: False
        win.on_fix()
        self.assertEqual(len(win.runner.calls), before)

    def test_nothing_selected_does_not_run(self):
        win = self.make_window()
        for c in win.problem_cards:
            c.check.setChecked(False)
        shown = []
        win._info = lambda text, warn=False: shown.append(text)
        win.on_fix()
        self.assertEqual(shown, [gui.UI["nothing_selected"]])

    # ---------- live test ----------
    def test_live_test_gives_a_verdict_and_a_fix(self):
        win = self.make_window()
        win.live_duration, win.live_interval = 10, 0.02
        win.start_live()
        self.assertTrue(win.live_running)
        self.wait(lambda: not win.live_running)
        r = win.live_result
        self.assertEqual((r.kind, r.side), ("error", "hardware"))
        self.assertIsNotNone(win.live_result_card)
        self.assertIn(r.title, texts(win.live_result_card))
        self.assertIn("سخت‌افزار", texts(win.live_result_card))
        fixes = win._live_fixes(r)
        self.assertEqual([f.fix_id for f in fixes], ["restart_errors", "disable_suspend"])
        self.assertTrue(fixes[1].targets)  # uses the scan's real power-plan values

    # ---------- persistence ----------
    def test_guard_toggle(self):
        win = self.make_window()
        self.assertFalse(win.guard_installed)
        win.on_guard_toggle()
        self.wait(lambda: win.guard_installed)
        self.assertIn("روشن", win.notice)
        self.assertTrue(any(c[:2] == ["schtasks", "/Create"] for c in win.runner.calls))
        win.on_guard_toggle()
        self.wait(lambda: win.guard_installed is False)

    def test_reverted_fix_is_flagged_after_restart(self):
        state.record_applied(["disable_suspend"])
        win = self.make_window()
        card = next(c for c in win.problem_cards if c.finding.fix_id == "disable_suspend")
        self.assertTrue(card.finding.reverted)
        self.assertIn("دوباره برگشته", texts(card))

    # ---------- theme / clean machine ----------
    def test_theme_switch_changes_palette_and_persists(self):
        win = self.make_window()
        win.mode = "light"
        win.apply_theme()
        self.assertEqual(theme.CURRENT["name"], "light")
        win.cycle_theme()
        self.assertEqual(win.mode, "dark")
        self.assertEqual(theme.CURRENT["name"], "dark")
        self.assertEqual(win.settings.value("theme"), "dark")
        self.assertEqual(self.app.palette().color(gui.QtGui.QPalette.Link).name(), theme.DARK["link"])
        self.assertEqual(len(win.problem_cards), len(win.findings) + 1)
        win.mode = "auto"
        win.apply_theme()

    def test_clean_machine_shows_ok(self):
        inv = dict(demo.DEMO_INVENTORY, board_product="PRIME Z790-P", cpu="Intel(R) Core(TM) i7", bios_date="2026-01-01",
                   bios_version="5220")
        inv["devices"] = inv["devices"][:1]
        inv["nodes"] = inv["nodes"][:1]
        inv["controllers"] = [dict(c, driver_provider="Intel") for c in inv["controllers"]]
        st = {"services": {"PlugPlay": 4}, "usbstor_start": 3, "uaspstor_start": 3, "hub_power": [], "disks": [], "events": []}
        off = "Current AC Power Setting Index: 0x00000000\nCurrent DC Power Setting Index: 0x00000000\n"
        win = self.make_window(demo.DemoRunner(inv, st, power=off))
        self.assertEqual([c.finding.key for c in win.problem_cards], ["reset_usb_stack"])
        self.assertIn("مشکلی پیدا نشد", win.headline.text())
        self.assertEqual(win.hero.property("state"), "ok")


if __name__ == "__main__":
    unittest.main()
