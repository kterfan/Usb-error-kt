import copy
import unittest
from datetime import date

from usb_fixer import demo, knowledge, snapshot
from usb_fixer.diagnostics import analyze, scan
from usb_fixer.system import CmdResult, decode_powershell_cmd, powershell_cmd

TODAY = date(2026, 10, 4)


def keys(findings):
    return [f.key for f in findings]


class SystemTests(unittest.TestCase):
    def test_powershell_roundtrip(self):
        script = "Write-Output 'سلام \"x\" $y'"
        cmd = powershell_cmd(script)
        self.assertIn("-EncodedCommand", cmd)
        self.assertTrue(decode_powershell_cmd(cmd).endswith(script))


class ParseTests(unittest.TestCase):
    def test_powercfg_takes_last_two_values(self):
        self.assertEqual(snapshot.parse_powercfg(demo.POWERCFG_OUT), (1, 1))

    def test_powercfg_mixed_values(self):
        text = "x 0x00000000 y 0x00000001 AC 0x00000001 DC 0x00000000"
        self.assertEqual(snapshot.parse_powercfg(text), (1, 0))

    def test_powercfg_garbage(self):
        self.assertIsNone(snapshot.parse_powercfg("nothing here"))

    def test_single_object_instead_of_list(self):
        inv = copy.deepcopy(demo.DEMO_INVENTORY)
        inv["controllers"] = inv["controllers"][0]  # PowerShell collapses 1-item arrays sometimes
        inv["devices"] = inv["devices"][0]
        system, devices = snapshot.parse_inventory(inv)
        self.assertEqual(len(system.controllers), 1)
        self.assertEqual(len(devices), 1)

    def test_controller_vendor(self):
        system, _ = snapshot.parse_inventory(demo.DEMO_INVENTORY)
        self.assertEqual([c.vendor for c in system.controllers], ["AMD", "ASMedia"])

    def test_bad_inventory_raises_scan_error(self):
        class Bad:
            def __call__(self, cmd):
                return CmdResult(0, "not json")

        with self.assertRaises(snapshot.ScanError):
            snapshot.take_snapshot(Bad())

    def test_failed_state_script_is_only_a_warning(self):
        runner = demo.DemoRunner()
        orig = runner.__call__

        def flaky(cmd):
            script = decode_powershell_cmd(cmd)
            if script and "# SCRIPT:state" in script:
                return CmdResult(1, "", "boom")
            return orig(cmd)

        snap = snapshot.take_snapshot(flaky)
        self.assertEqual(len(snap.warnings), 1)
        self.assertEqual(snap.state.hub_power, [])


class AnalyzeTests(unittest.TestCase):
    def setUp(self):
        self.result = scan(demo.DemoRunner(), TODAY)
        self.keys = keys(self.result.findings)

    def test_demo_machine_findings(self):
        for expected in (
            "device_errors", "unknown_devices", "ghost_devices", "selective_suspend", "hub_power",
            "fast_startup", "write_protect", "usb_disk_no_letter", "event_errors", "bios_old",
            "ms_default_driver", "amd_usb_dropout",
        ):
            self.assertIn(expected, self.keys)
        self.assertNotIn("no_controller", self.keys)
        self.assertNotIn("pcie_aspm", self.keys)  # demo ASPM is off

    def test_sorted_by_severity(self):
        order = {"error": 0, "warn": 1, "info": 2}
        sev = [order[f.severity] for f in self.result.findings]
        self.assertEqual(sev, sorted(sev))

    def test_unknown_device_not_double_counted_as_error(self):
        errs = next(f for f in self.result.findings if f.key == "device_errors")
        self.assertEqual([t[0] for t in errs.targets], ["USB\\VID_046D&PID_C52B\\5&2F1A&0&1"])

    def test_ghosts(self):
        g = next(f for f in self.result.findings if f.key == "ghost_devices")
        self.assertEqual(len(g.targets), 2)

    def test_every_finding_renders(self):
        for f in self.result.findings:
            self.assertTrue(f.title)
            self.assertTrue(f.detail)
            for m in f.manual:
                self.assertTrue(f.manual_texts)

    def test_support_link_added_for_bios_advice(self):
        f = next(f for f in self.result.findings if f.key == "bios_old")
        self.assertTrue(f.links and f.links[0][1].startswith("https://"))

    def test_clean_machine_has_no_findings(self):
        inv = copy.deepcopy(demo.DEMO_INVENTORY)
        inv["board_product"] = "PRIME Z790-P"
        inv["cpu"] = "Intel(R) Core(TM) i7-13700K"
        inv["bios_date"] = "2026-01-01"
        inv["devices"] = inv["devices"][:1]
        for c in inv["controllers"]:
            c["driver_provider"] = "Intel"
        state = {"services": {"PlugPlay": 4}, "usbstor_start": 3, "uaspstor_start": 3, "hub_power": [], "disks": [], "events": []}
        runner = demo.DemoRunner(inv, state, power="Current AC Power Setting Index: 0x00000000\nCurrent DC Power Setting Index: 0x00000000\n")
        self.assertEqual(scan(runner, TODAY).findings, [])

    def test_no_controller(self):
        inv = copy.deepcopy(demo.DEMO_INVENTORY)
        inv["controllers"] = []
        findings = scan(demo.DemoRunner(inv), TODAY).findings
        self.assertIn("no_controller", keys(findings))

    def test_virtual_machine_is_not_an_error(self):
        inv = copy.deepcopy(demo.DEMO_INVENTORY)
        inv["controllers"] = []
        inv["system_model"] = "Virtual Machine"
        inv["board_product"] = "Virtual Machine"
        findings = scan(demo.DemoRunner(inv), TODAY).findings
        self.assertIn("virtual_machine", keys(findings))
        self.assertNotIn("no_controller", keys(findings))

    def test_usbstor_disabled_and_offline_disk(self):
        state = copy.deepcopy(demo.DEMO_STATE)
        state["usbstor_start"] = 4
        state["deny_all"] = 1
        state["disks"][0]["offline"] = True
        findings = scan(demo.DemoRunner(state=state), TODAY).findings
        for k in ("usbstor_disabled", "storage_policy", "usb_disk_offline"):
            self.assertIn(k, keys(findings))
        # offline disks must not also ask for a drive letter
        self.assertNotIn("usb_disk_no_letter", keys(findings))


class KnowledgeTests(unittest.TestCase):
    def sysinfo(self, **kw):
        base = dict(board_manufacturer="MSI", board_product="MAG B550 TOMAHAWK", cpu="AMD Ryzen 7 5800X 8-Core Processor")
        base.update(kw)
        return snapshot.SystemInfo(**base)

    def rule(self, rid):
        return next(r for r in knowledge.load_rules() if r["id"] == rid)

    def test_amd_rule_matches_b550_ryzen_5000_with_old_bios(self):
        when = self.rule("amd_usb_dropout")["when"]
        self.assertTrue(knowledge.matches(when, self.sysinfo(bios_date=date(2020, 11, 1)), TODAY))

    def test_amd_rule_silent_with_fixed_or_unknown_bios(self):
        when = self.rule("amd_usb_dropout")["when"]
        self.assertFalse(knowledge.matches(when, self.sysinfo(bios_date=date(2021, 5, 1)), TODAY))
        self.assertFalse(knowledge.matches(when, self.sysinfo(bios_date=None), TODAY))

    def test_amd_rule_skips_intel_and_new_ryzen(self):
        when = self.rule("amd_usb_dropout")["when"]
        self.assertFalse(knowledge.matches(when, self.sysinfo(board_product="Z790-P", cpu="Intel Core i5"), TODAY))
        self.assertFalse(knowledge.matches(when, self.sysinfo(cpu="AMD Ryzen 7 7800X3D"), TODAY))
        self.assertFalse(knowledge.matches(when, self.sysinfo(board_product="X670E"), TODAY))

    def test_bios_age(self):
        when = self.rule("bios_old")["when"]
        self.assertFalse(knowledge.matches(when, self.sysinfo(bios_date=date(2025, 6, 1)), TODAY))
        self.assertTrue(knowledge.matches(when, self.sysinfo(bios_date=date(2020, 1, 1)), TODAY))
        self.assertFalse(knowledge.matches(when, self.sysinfo(bios_date=None), TODAY))


if __name__ == "__main__":
    unittest.main()


class NewChecksTests(unittest.TestCase):
    def state_with(self, **part):
        state = copy.deepcopy(demo.DEMO_STATE)
        state["disks"][0]["partitions"][0].update(part)
        return state

    def test_raw_partition_is_an_error_and_never_auto_fixed(self):
        found = scan(demo.DemoRunner(state=self.state_with(fs="RAW", letter="F")), TODAY).findings
        raw = next(f for f in found if f.key == "usb_disk_raw")
        self.assertEqual(raw.severity, "error")
        self.assertIsNone(raw.fix_id)  # formatting is never offered
        self.assertEqual(raw.manual, ["recover_data", "format_after_recovery"])
        self.assertIn("F:", raw.detail)

    def test_raw_without_letter_is_not_also_offered_a_letter(self):
        found = scan(demo.DemoRunner(state=self.state_with(fs="RAW")), TODAY).findings
        self.assertIn("usb_disk_raw", keys(found))
        self.assertNotIn("usb_disk_no_letter", keys(found))

    def test_every_finding_has_a_recommendation(self):
        for f in scan(demo.DemoRunner(), TODAY).findings:
            self.assertTrue(f.recommendation.strip(), f.key)

    def bios(self, status, latest="3202"):
        from usb_fixer import bios

        return bios.BiosCheck(status, "3202", latest, date(2026, 5, 14), download_url="https://dlcdnets.asus.com/x.zip", source="ASUS")

    def test_current_bios_silences_old_bios_warnings(self):
        # the user's case: an up-to-date BIOS must not be told it is old
        snap = scan(demo.DemoRunner(), TODAY).snapshot
        found = keys(analyze(snap, TODAY, bios=self.bios("current")))
        self.assertNotIn("amd_usb_dropout", found)
        self.assertNotIn("bios_old", found)
        self.assertNotIn("bios_update", found)

    def test_newer_bios_replaces_generic_old_bios_finding(self):
        snap = scan(demo.DemoRunner(), TODAY).snapshot
        found = analyze(snap, TODAY, bios=self.bios("update", "5220"))
        self.assertNotIn("bios_old", keys(found))
        upd = next(f for f in found if f.key == "bios_update")
        self.assertIn("5220", upd.detail)
        self.assertEqual(upd.links[0][1], "https://dlcdnets.asus.com/x.zip")

    def test_unknown_online_answer_keeps_offline_rules(self):
        snap = scan(demo.DemoRunner(), TODAY).snapshot
        found = keys(analyze(snap, TODAY, bios=self.bios("unknown")))
        self.assertIn("amd_usb_dropout", found)
        self.assertIn("bios_old", found)

    def test_online_scan_uses_fetch(self):
        result = scan(demo.DemoRunner(), TODAY, online=True, fetch=demo.fake_asus_fetch)
        self.assertEqual(result.bios.latest, "5220")
        self.assertIn("bios_update", keys(result.findings))


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        import contextlib
        import io

        from usb_fixer.__main__ import main

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                code = main(list(args))
            except SystemExit as exc:  # argparse --version
                code = exc.code
        return code, out.getvalue()

    def test_version_names_the_author(self):
        from usb_fixer import __version__, about

        code, text = self.run_cli("--version")
        self.assertEqual(code, 0)
        self.assertIn(__version__, text)
        self.assertIn("Erfan Esmailzadeh", text)
        self.assertIn("عرفان اسمعیل زاده", text)
        self.assertIn(about.GITHUB_PROFILE, text)

    def test_demo_scan_report(self):
        code, text = self.run_cli("--demo", "--scan")
        self.assertEqual(code, 0)
        self.assertTrue(text.startswith("USB Fixer"))
        self.assertIn("[خطا]", text)


class ReportFileTests(unittest.TestCase):
    def test_report_option_writes_utf8_file(self):
        import contextlib
        import io
        import os
        import tempfile

        from usb_fixer.__main__ import main

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "r.txt")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--demo", "--scan", "--report", path]), 0)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        self.assertIn("Erfan Esmailzadeh", text)
        self.assertIn("دستگاه", text)
