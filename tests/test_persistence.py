"""Fixes must survive restarts: state of applied fixes, "reverted" detection, the logon guard, and undo."""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from usb_fixer import backup, demo, fixes, guard, state
from usb_fixer.diagnostics import analyze, scan
from usb_fixer.system import CmdResult

TODAY = date(2026, 10, 4)


class StateTests(unittest.TestCase):
    def test_record_and_forget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "backups"
            self.assertEqual(state.applied_ids(root), set())
            state.record_applied(["disable_suspend", "disable_hub_power"], root)
            self.assertEqual(state.applied_ids(root), {"disable_suspend", "disable_hub_power"})
            self.assertTrue((Path(tmp) / state.FILE).is_file())  # next to the backups folder
            state.forget(["disable_suspend"], root)
            self.assertEqual(state.applied_ids(root), {"disable_hub_power"})

    def test_corrupt_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / state.FILE).write_text("{not json", encoding="utf-8")
            self.assertEqual(state.applied_ids(Path(tmp)), set())


class RevertedTests(unittest.TestCase):
    def test_fix_that_came_back_is_marked(self):
        snap = scan(demo.DemoRunner(), TODAY).snapshot
        found = analyze(snap, TODAY, applied={"disable_suspend", "remove_ghosts"})
        suspend = next(f for f in found if f.fix_id == "disable_suspend")
        ghosts = next(f for f in found if f.fix_id == "remove_ghosts")
        self.assertTrue(suspend.reverted)
        self.assertIn("دوباره برگشته", suspend.title)
        self.assertFalse(ghosts.reverted)  # new ghosts are normal, not a reverted setting

    def test_reverted_info_is_raised_to_warning(self):
        snap = scan(demo.DemoRunner(), TODAY).snapshot
        found = analyze(snap, TODAY, applied={"disable_fast_startup"})
        fast = next(f for f in found if f.fix_id == "disable_fast_startup")
        self.assertEqual(fast.severity, "warn")


class ExecuteRecordsTests(unittest.TestCase):
    def test_successful_persistent_fixes_are_recorded(self):
        findings = scan(demo.DemoRunner(), TODAY).findings
        chosen = [f for f in findings if f.fix_id in ("disable_suspend", "remove_ghosts")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "backups"
            res = fixes.execute(fixes.collect_steps(chosen), demo.DemoRunner(), lambda m: None, root=root)
            self.assertEqual(set(res.applied), {"disable_suspend", "remove_ghosts"})
            self.assertEqual(state.applied_ids(root), {"disable_suspend"})  # only settings that can revert

    def test_failed_fix_is_not_recorded(self):
        class Fail(demo.DemoRunner):
            def __call__(self, cmd):
                if cmd[:2] == ["reg", "add"]:
                    return CmdResult(1, "", "denied")
                return super().__call__(cmd)

        findings = scan(demo.DemoRunner(), TODAY).findings
        chosen = [f for f in findings if f.fix_id == "disable_suspend"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "backups"
            fixes.execute(fixes.collect_steps(chosen), Fail(), lambda m: None, root=root)
            self.assertEqual(state.applied_ids(root), set())

    def test_new_registry_value_is_deleted_on_undo(self):
        class NoValue(demo.DemoRunner):
            def __call__(self, cmd):
                if cmd[:2] == ["reg", "query"]:
                    return CmdResult(1, "", "ERROR: The system was unable to find the specified registry key or value.")
                return super().__call__(cmd)

        findings = scan(demo.DemoRunner(), TODAY).findings
        chosen = [f for f in findings if f.fix_id == "disable_suspend"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "backups"
            res = fixes.execute(fixes.collect_steps(chosen), NoValue(), lambda m: None, root=root)
            data = json.loads((Path(res.backup_dir) / backup.UNDO_FILE).read_text(encoding="utf-8"))
            self.assertEqual(data["reg_delete"], [[fixes.REG_USB_SERVICE, "DisableSelectiveSuspend"]])
            self.assertEqual(data["fix_ids"], ["disable_suspend"])
            runner = demo.DemoRunner()
            self.assertEqual(backup.undo(Path(res.backup_dir), runner, lambda m: None), 0)
            self.assertIn(["reg", "delete", fixes.REG_USB_SERVICE, "/v", "DisableSelectiveSuspend", "/f"], runner.calls)
            # per-plan values come back exactly
            self.assertIn(["powercfg", "/SETACVALUEINDEX", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
                           "2a737441-1930-4402-8d77-b2bebba308a3", "48e6b7a6-50f5-4782-a5d4-53bb8f07e226", "1"], runner.calls)
            self.assertEqual(state.applied_ids(root), set())  # undo also stops the guard from re-applying

    def test_existing_value_is_restored_by_import_not_deleted(self):
        findings = scan(demo.DemoRunner(), TODAY).findings
        chosen = [f for f in findings if f.fix_id == "disable_fast_startup"]
        with tempfile.TemporaryDirectory() as tmp:
            res = fixes.execute(fixes.collect_steps(chosen), demo.DemoRunner(), lambda m: None, root=Path(tmp))
            data = json.loads((Path(res.backup_dir) / backup.UNDO_FILE).read_text(encoding="utf-8"))
        self.assertEqual(data["reg_delete"], [])
        self.assertEqual(len(data["reg_files"]), 1)


class GuardTests(unittest.TestCase):
    def test_task_commands(self):
        cmd = guard.install_cmd("C:\\Program Files\\USB Fixer\\UsbFixer.exe")
        self.assertEqual(cmd[:4], ["schtasks", "/Create", "/TN", guard.TASK_NAME])
        self.assertIn('"C:\\Program Files\\USB Fixer\\UsbFixer.exe" --guard', cmd)
        self.assertIn("ONLOGON", cmd)
        self.assertIn("HIGHEST", cmd)
        self.assertEqual(guard.remove_cmd()[:2], ["schtasks", "/Delete"])

    def test_is_installed(self):
        runner = demo.DemoRunner()
        self.assertFalse(guard.is_installed(runner))
        runner(guard.install_cmd("x.exe"))
        self.assertTrue(guard.is_installed(runner))
        runner(guard.remove_cmd())
        self.assertFalse(guard.is_installed(runner))

    def test_location_problem(self):
        self.assertTrue(guard.location_problem(""))
        self.assertTrue(guard.location_problem("C:\\Users\\a\\Downloads\\UsbFixer.exe"))
        self.assertEqual(guard.location_problem("C:\\Program Files\\USB Fixer\\UsbFixer.exe"), "")

    def test_nothing_applied_does_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = demo.DemoRunner()
            self.assertEqual(guard.run_guard(runner, root=Path(tmp)), 0)
            self.assertEqual(runner.calls, [])

    def test_reapplies_only_reverted_persistent_fixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "backups"
            state.record_applied(["disable_suspend"], root)
            runner = demo.DemoRunner()  # demo power plan still has suspend ON -> it came back
            logs = []
            self.assertEqual(guard.run_guard(runner, logs.append, root=root), 1)
            changes = [c for c in runner.calls if c[:1] in (["powercfg"], ["reg"]) and c[1] in ("/SETACVALUEINDEX", "add")]
            self.assertTrue(changes)
            self.assertFalse(any(c[:2] == ["pnputil", "/remove-device"] for c in runner.calls))
            self.assertFalse(any("Checkpoint-Computer" in str(c) for c in runner.calls))  # no restore point at logon
            self.assertIn("re-applied: disable_suspend", logs[-1])
            self.assertTrue((root / "guard.log").is_file())
            self.assertIsNone(backup.latest_undo_dir(root))  # no undo point that would bring the bad state back

    def test_nothing_reverted(self):
        off = "Current AC Power Setting Index: 0x00000000\nCurrent DC Power Setting Index: 0x00000000\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state.record_applied(["disable_suspend"], root)
            logs = []
            self.assertEqual(guard.run_guard(demo.DemoRunner(power=off), logs.append, root=root), 0)
            self.assertIn("still in place", logs[-1])


if __name__ == "__main__":
    unittest.main()
