import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from usb_fixer import backup, demo, fixes
from usb_fixer.diagnostics import Finding, scan
from usb_fixer.system import CmdResult, decode_powershell_cmd

TODAY = date(2026, 10, 4)


def by_fix(findings, fix_id):
    return next(f for f in findings if f.fix_id == fix_id)


class StepTests(unittest.TestCase):
    def setUp(self):
        self.findings = scan(demo.DemoRunner(), TODAY).findings

    def cmds(self, fix_id):
        return [s.cmd for s in fixes.build_steps(by_fix(self.findings, fix_id))]

    def test_restart_errors(self):
        self.assertIn(["pnputil", "/restart-device", "USB\\VID_046D&PID_C52B\\5&2F1A&0&1"], self.cmds("restart_errors"))

    def test_disabled_device_is_enabled_not_restarted(self):
        f = Finding("device_errors", "error", fix_id="restart_errors", targets=[("USB\\X", 22)])
        self.assertEqual(fixes.build_steps(f)[0].cmd, ["pnputil", "/enable-device", "USB\\X"])

    def test_remove_ghosts_only_ghosts(self):
        cmds = self.cmds("remove_ghosts")
        self.assertEqual(len(cmds), 2)
        self.assertTrue(all(c[:2] == ["pnputil", "/remove-device"] for c in cmds))
        self.assertEqual({c[2] for c in cmds}, {"USB\\VID_0781&PID_5581\\0123456789", "USB\\VID_090C&PID_1000\\ABCDEF"})

    def test_suspend_sets_ac_dc_and_activates(self):
        cmds = self.cmds("disable_suspend")
        self.assertEqual(cmds[0][:3], ["powercfg", "/SETACVALUEINDEX", "SCHEME_CURRENT"])
        self.assertEqual(cmds[0][-1], "0")
        self.assertEqual(cmds[1][1], "/SETDCVALUEINDEX")
        self.assertEqual(cmds[2], ["powercfg", "/SETACTIVE", "SCHEME_CURRENT"])

    def test_registry_fixes_backup_their_key(self):
        step = fixes.build_steps(by_fix(self.findings, "disable_fast_startup"))[0]
        self.assertEqual(step.backup_reg, [fixes.REG_POWER])
        self.assertEqual(step.cmd[:2], ["reg", "add"])

    def test_disk_letter(self):
        script = decode_powershell_cmd(self.cmds("assign_letter")[0])
        self.assertIn("Add-PartitionAccessPath -DiskNumber 2 -PartitionNumber 1 -AssignDriveLetter", script)

    def test_defaults_cover_every_fix(self):
        from usb_fixer import strings

        self.assertEqual(set(fixes.DEFAULT_CHECKED), set(strings.FIXES))

    def test_risky_fixes_not_checked_by_default(self):
        for fix_id in ("remove_storage_policy", "disable_fast_startup", "disk_writable"):
            self.assertFalse(fixes.DEFAULT_CHECKED[fix_id])

    def test_collect_steps_dedupes(self):
        f = by_fix(self.findings, "disable_suspend")
        self.assertEqual(len(fixes.collect_steps([f, f])), len(fixes.build_steps(f)))

    def test_steps_of_finding_without_fix(self):
        self.assertEqual(fixes.build_steps(Finding("bios_old", "info")), [])


class ExecuteTests(unittest.TestCase):
    def test_execute_backs_up_runs_and_rescans(self):
        findings = scan(demo.DemoRunner(), TODAY).findings
        chosen = [by_fix(findings, k) for k in ("disable_suspend", "disable_hub_power", "disable_fast_startup")]
        steps = fixes.collect_steps(chosen)
        runner = demo.DemoRunner()
        logs = []
        with tempfile.TemporaryDirectory() as tmp:
            result = fixes.execute(steps, runner, logs.append, root=Path(tmp))
            undo_file = Path(result.backup_dir) / backup.UNDO_FILE
            data = json.loads(undo_file.read_text(encoding="utf-8"))
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.ok, len(steps))
        self.assertEqual(data["powercfg"][0]["ac"], 1)
        self.assertEqual(data["hub_power"], ["USB\\ROOT_HUB30\\4&1B2C3D&0&0_0"])
        self.assertEqual(len(data["reg_files"]), 1)
        self.assertEqual(runner.calls[-1], ["pnputil", "/scan-devices"])
        # backup happens before the first change
        first_change = next(i for i, c in enumerate(runner.calls) if c[:2] == ["powercfg", "/SETACVALUEINDEX"])
        first_export = next(i for i, c in enumerate(runner.calls) if c[:2] == ["reg", "export"])
        self.assertLess(first_export, first_change)

    def test_failed_step_is_counted_and_logged(self):
        class Failing(demo.DemoRunner):
            def __call__(self, cmd):
                if cmd[:2] == ["pnputil", "/remove-device"]:
                    return CmdResult(1, "", "access denied")
                return super().__call__(cmd)

        step = fixes.Step("pnputil /remove-device X", ["pnputil", "/remove-device", "X"])
        logs = []
        with tempfile.TemporaryDirectory() as tmp:
            result = fixes.execute([step], Failing(), logs.append, root=Path(tmp))
        self.assertEqual((result.ok, result.failed), (0, 1))
        self.assertTrue(any("access denied" in line for line in logs))

    def test_undo_restores_power_hub_and_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            backup.write_undo(d, {
                "reg_files": ["C:\\x\\reg0.reg"],
                "powercfg": [{"subgroup": "SUB", "setting": "SET", "ac": 1, "dc": 0}],
                "hub_power": ["USB\\A"],
            })
            runner = demo.DemoRunner()
            failed = backup.undo(d, runner, lambda m: None)
        self.assertEqual(failed, 0)
        cmds = runner.calls
        self.assertIn(["reg", "import", "C:\\x\\reg0.reg"], cmds)
        self.assertIn(["powercfg", "/SETACVALUEINDEX", "SCHEME_CURRENT", "SUB", "SET", "1"], cmds)
        self.assertIn(["powercfg", "/SETDCVALUEINDEX", "SCHEME_CURRENT", "SUB", "SET", "0"], cmds)
        hub = [decode_powershell_cmd(c) for c in cmds if decode_powershell_cmd(c) and "MSPower_DeviceEnable" in decode_powershell_cmd(c)]
        self.assertIn("$_.Enable = $true", hub[0])

    def test_latest_undo_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(backup.latest_undo_dir(root))
            for name in ("20260101-000000", "20260202-000000"):
                (root / name).mkdir()
                backup.write_undo(root / name, {})
            (root / "20260303-000000").mkdir()  # newest but has no undo file
            self.assertEqual(backup.latest_undo_dir(root).name, "20260202-000000")

    def test_ps_quote(self):
        self.assertEqual(backup._ps_quote("it's"), "'it''s'")


if __name__ == "__main__":
    unittest.main()
