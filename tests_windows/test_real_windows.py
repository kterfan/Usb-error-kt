"""Real changes on a real Windows machine: fix -> check -> Windows "reverts" -> guard -> undo -> check.

These tests change power plans, the registry and scheduled tasks, so they only run when
USB_FIXER_REAL_TESTS=1 (the GitHub Windows runner sets it; never run them on your own PC).
Every test puts the machine back the way it found it.
"""

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ENABLED = sys.platform == "win32" and os.environ.get("USB_FIXER_REAL_TESTS") == "1"

if ENABLED:
    from usb_fixer import backup, bios, fixes, guard, live, snapshot, state
    from usb_fixer.diagnostics import Finding, analyze
    from usb_fixer.snapshot import USB_SELECTIVE_SUSPEND, USB_SUBGROUP, read_all_power, take_snapshot
    from usb_fixer.system import is_admin, powershell_cmd, run


def reg_dword(key, name):
    """Current DWORD value, or None if the value does not exist."""
    res = run(["reg", "query", key, "/v", name])
    if not res.ok:
        return None
    m = re.search(r"REG_DWORD\s+0x([0-9a-fA-F]+)", res.out)
    return int(m.group(1), 16) if m else None


def set_reg(key, name, value):
    if value is None:
        run(["reg", "delete", key, "/v", name, "/f"])
    else:
        run(["reg", "add", key, "/v", name, "/t", "REG_DWORD", "/d", str(value), "/f"])


def suspend_values():
    schemes, _ = read_all_power(run)
    return {g: v.get("selective_suspend") for g, v in schemes.items()}


def set_suspend(scheme, ac, dc):
    run(["powercfg", "/SETACVALUEINDEX", scheme, USB_SUBGROUP, USB_SELECTIVE_SUSPEND, str(ac)])
    run(["powercfg", "/SETDCVALUEINDEX", scheme, USB_SUBGROUP, USB_SELECTIVE_SUSPEND, str(dc)])
    run(["powercfg", "/SETACTIVE", "SCHEME_CURRENT"])


@unittest.skipUnless(ENABLED, "real Windows tests are opt-in (USB_FIXER_REAL_TESTS=1 on Windows)")
class RealWindowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not is_admin():
            raise unittest.SkipTest("needs an elevated (admin) session")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "backups"
        self.log = []

    def tearDown(self):
        self.tmp.cleanup()

    def test_selective_suspend_fix_survives_revert_and_undoes_cleanly(self):
        original = suspend_values()
        if not original or not all(original.values()):
            self.skipTest(f"this Windows has no readable USB selective suspend setting: {original}")
        reg_before = reg_dword(fixes.REG_USB_SERVICE, "DisableSelectiveSuspend")
        try:
            # 1) put the machine in the "problem" state: suspend ON in every plan
            for g in original:
                set_suspend(g, 1, 1)
            set_reg(fixes.REG_USB_SERVICE, "DisableSelectiveSuspend", None)
            snap = take_snapshot(run)
            finding = next((f for f in analyze(snap) if f.fix_id == "disable_suspend"), None)
            self.assertIsNotNone(finding, "scan did not see selective suspend turned on")
            self.assertEqual(set(finding.targets[0]), set(original))  # every power plan is targeted

            # 2) fix
            res = fixes.execute(fixes.collect_steps([finding]), run, self.log.append, root=self.root, restore_point=False)
            self.assertEqual(res.failed, 0, "\n".join(self.log))
            self.assertTrue(all(v == (0, 0) for v in suspend_values().values()), suspend_values())
            self.assertEqual(reg_dword(fixes.REG_USB_SERVICE, "DisableSelectiveSuspend"), 1)
            self.assertIn("disable_suspend", state.applied_ids(self.root))
            self.assertNotIn("disable_suspend", [f.fix_id for f in analyze(take_snapshot(run))])

            # 3) Windows (an update, a vendor tool) turns it back on in the active plan
            set_suspend("SCHEME_CURRENT", 1, 1)
            again = [f for f in analyze(take_snapshot(run), applied=state.applied_ids(self.root)) if f.fix_id == "disable_suspend"]
            self.assertTrue(again and again[0].reverted, "reverted fix not detected")

            # 4) the logon guard puts it right, without leaving its own undo point
            self.assertEqual(guard.run_guard(run, self.log.append, root=self.root), 1, "\n".join(self.log))
            self.assertTrue(all(v == (0, 0) for v in suspend_values().values()), suspend_values())
            self.assertTrue((self.root / "guard.log").is_file())

            # 5) undo returns exactly to the state before the fix
            directory = backup.latest_undo_dir(self.root)
            self.assertEqual(directory.name, Path(res.backup_dir).name)
            self.assertEqual(backup.undo(directory, run, self.log.append), 0, "\n".join(self.log))
            self.assertTrue(all(v == (1, 1) for v in suspend_values().values()), suspend_values())
            self.assertIsNone(reg_dword(fixes.REG_USB_SERVICE, "DisableSelectiveSuspend"))  # did not exist before
            self.assertNotIn("disable_suspend", state.applied_ids(self.root))
        finally:
            for g, (ac, dc) in original.items():
                set_suspend(g, ac, dc)
            set_reg(fixes.REG_USB_SERVICE, "DisableSelectiveSuspend", reg_before)
        self.assertEqual(suspend_values(), original)

    def test_fast_startup_registry_roundtrip(self):
        before = reg_dword(fixes.REG_POWER, "HiberbootEnabled")
        try:
            set_reg(fixes.REG_POWER, "HiberbootEnabled", 1)
            f = Finding("fast_startup", "info", fix_id="disable_fast_startup")
            res = fixes.execute(fixes.collect_steps([f]), run, self.log.append, root=self.root, restore_point=False)
            self.assertEqual(res.failed, 0, "\n".join(self.log))
            self.assertEqual(reg_dword(fixes.REG_POWER, "HiberbootEnabled"), 0)
            self.assertEqual(backup.undo(Path(res.backup_dir), run, self.log.append), 0, "\n".join(self.log))
            self.assertEqual(reg_dword(fixes.REG_POWER, "HiberbootEnabled"), 1)
        finally:
            set_reg(fixes.REG_POWER, "HiberbootEnabled", before)

    def test_guard_task_install_query_remove(self):
        self.assertFalse(guard.is_installed(run), "a USB Fixer Guard task already exists on this machine")
        exe = str(Path(self.tmp.name) / "USB-Fixer.exe")
        try:
            res = run(guard.install_cmd(exe))
            self.assertTrue(res.ok, res.err or res.out)
            self.assertTrue(guard.is_installed(run))
            xml = run(["schtasks", "/Query", "/TN", guard.TASK_NAME, "/XML"]).out
            self.assertIn("--guard", xml)
            self.assertIn("HighestAvailable", xml)
            self.assertIn("LogonTrigger", xml)
        finally:
            run(guard.remove_cmd())
        self.assertFalse(guard.is_installed(run))

    def test_live_test_scripts_run(self):
        for script in (live.NODES_SCRIPT, live.DISKS_SCRIPT, live.EVENTS_SCRIPT.replace("{seconds}", "60")):
            res = run(powershell_cmd(script))
            self.assertTrue(res.ok, f"{script.splitlines()[0]}: {res.err}")
        self.assertIsInstance(live.poll_nodes(run), dict)
        self.assertIsInstance(live.poll_disks(run), dict)
        result = live.run_test(run, duration=3, interval=1)
        self.assertEqual(result.kind, "nothing")  # nobody plugs anything into a CI machine

    def test_full_scan_has_power_plans_and_nodes_field(self):
        snap = take_snapshot(run)
        print("\nplans:", snap.power_schemes, "active:", snap.current_scheme, "nodes:", len(snap.nodes), "warnings:", snap.warnings)
        self.assertTrue(snap.power_schemes)
        self.assertIn(snap.current_scheme, snap.power_schemes)


@unittest.skipUnless(ENABLED, "real Windows tests are opt-in (USB_FIXER_REAL_TESTS=1 on Windows)")
class OnlineTests(unittest.TestCase):
    def test_asus_bios_list_for_a_real_board(self):
        system, _ = snapshot.parse_inventory({
            "board_manufacturer": "ASUSTeK COMPUTER INC.", "board_product": "ProArt B550-CREATOR",
            "bios_version": "4304", "system_manufacturer": "System manufacturer", "system_model": "System Product Name",
        })
        check = bios.check_latest(system)
        print("\nASUS:", check)
        if check.status == "unknown" and "اتصال" in check.reason:
            self.skipTest(f"no connection to ASUS: {check.reason}")
        self.assertIn(check.status, ("current", "update"))
        self.assertTrue(check.latest.isdigit())
        self.assertTrue(check.download_url.startswith("https://"))


if __name__ == "__main__":
    unittest.main()
