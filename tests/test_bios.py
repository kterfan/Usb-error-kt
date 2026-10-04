import json
import unittest
from datetime import date

from usb_fixer import bios, demo, net, snapshot

# Trimmed copy of a real answer from the ASUS support API (ProArt B550-CREATOR, checked on the live site).
PROART = {
    "Result": {"Obj": [
        {"Name": "BIOS", "Files": [
            {"Version": "3611", "ReleaseDate": "2023/03/10", "Description": "old", "DownloadUrl": {"Global": "https://dlcdnets.asus.com/old.zip"}},
            {"Version": "4304", "ReleaseDate": "2025/04/21", "Description": "\"1. Improve system stability<br/>2. Security fixes\"",
             "DownloadUrl": {"Global": "https://dlcdnets.asus.com/4304.zip"}, "sha256": "ab" * 32},
        ]},
        {"Name": "BIOS Utilities", "Files": [{"Version": "9999", "ReleaseDate": "2026/01/01"}]},
    ]},
    "Status": "SUCCESS",
}


def system(**kw):
    s, _ = snapshot.parse_inventory(dict(demo.DEMO_INVENTORY, **kw))
    return s


class ParseTests(unittest.TestCase):
    def test_latest_is_newest_bios_file_not_utilities(self):
        c = bios.parse_asus(PROART, "4304")
        self.assertEqual((c.status, c.latest, c.latest_date), ("current", "4304", date(2025, 4, 21)))
        self.assertEqual(c.notes, "1. Improve system stability\n2. Security fixes")
        self.assertEqual(c.sha256, "ab" * 32)

    def test_older_installed_means_update(self):
        c = bios.parse_asus(PROART, "3611")
        self.assertEqual(c.status, "update")
        self.assertEqual(c.download_url, "https://dlcdnets.asus.com/4304.zip")

    def test_versions_compare_as_numbers(self):
        self.assertTrue(bios._newer("10", "9"))
        self.assertFalse(bios._newer("0803", "803"))
        self.assertIsNone(bios._newer("F12", "F9b"))

    def test_uncomparable_version_is_unknown_not_a_false_alarm(self):
        c = bios.parse_asus(PROART, "ProArt-X")
        self.assertEqual(c.status, "unknown")
        self.assertTrue(c.reason)

    def test_empty_list(self):
        self.assertEqual(bios.parse_asus({"Result": {"Obj": []}}, "1").status, "unknown")


class CheckLatestTests(unittest.TestCase):
    def test_asks_asus_with_the_board_model(self):
        urls = []
        c = bios.check_latest(system(), lambda u: urls.append(u) or json.dumps(PROART))
        self.assertEqual(c.status, "update")  # demo board has 3202
        self.assertEqual(urls, ["https://www.asus.com/support/api/product.asmx/GetPDBIOS?website=global&model=ROG%20STRIX%20B450-F%20GAMING&pdid=&cpu="])

    def test_demo_fetch(self):
        c = bios.check_latest(system(), demo.fake_asus_fetch)
        self.assertEqual((c.status, c.latest), ("update", "5220"))

    def test_non_asus_board_is_not_guessed(self):
        calls = []
        c = bios.check_latest(system(board_manufacturer="Micro-Star International Co., Ltd."), lambda u: calls.append(u))
        self.assertEqual(c.status, "unknown")
        self.assertEqual(calls, [])

    def test_virtual_machine(self):
        c = bios.check_latest(system(system_manufacturer="VMware, Inc.", system_model="VMware Virtual Platform"), demo.fake_asus_fetch)
        self.assertEqual(c.status, "unknown")

    def test_network_error_and_fail_answer(self):
        def boom(url):
            raise net.NetError("timeout")

        self.assertIn("timeout", bios.check_latest(system(), boom).reason)
        self.assertEqual(bios.check_latest(system(), lambda u: '{"Status": "FAIL", "Result": null}').status, "unknown")
        self.assertEqual(bios.check_latest(system(), lambda u: "<html>").status, "unknown")
        self.assertEqual(bios.check_latest(system(), lambda u: None).status, "unknown")


class NetTests(unittest.TestCase):
    def test_only_https_and_allowed_hosts(self):
        for url in ("http://www.asus.com/x", "https://evil.example.com/x", "https://www.asus.com.evil.com/x", "file:///etc/passwd"):
            with self.assertRaises(net.NetError):
                net.fetch_text(url)

    def test_user_agent_names_the_project(self):
        self.assertIn("github.com/kterfan", net.USER_AGENT)


if __name__ == "__main__":
    unittest.main()
