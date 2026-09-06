#!/usr/bin/env python3
"""update_latest_reports.py の自動テスト（標準ライブラリunittestのみ）。

すべて一時ディレクトリ上で実行し、リポジトリ内の実データ
（latest_reports.json / latest_reports_archive.json）には一切触れない。
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_latest_reports as ulr  # noqa: E402


def make_report(**overrides):
    base = {
        "id": "rep-x", "reportedAt": "2026-09-01", "fishName": "シロギス",
        "area": "沼津周辺", "spotName": "テスト", "fishingType": "shore",
        "method": "ちょい投げ", "baitOrLure": "イソメ", "catchSummary": "テスト",
        "sourceName": "テストソース", "sourceUrl": "https://example.com/a",
        "sourcePublishedAt": "2026-09-01", "note": "",
    }
    base.update(overrides)
    return base


class TempRepoTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "latest_reports.json"
        self.archive_path = self.root / "latest_reports_archive.json"
        self.backup_dir = self.root / "backups"

    def tearDown(self):
        self.tmp.cleanup()

    def write_reports(self, reports, updated_at="2026-09-06T09:00:00+09:00"):
        ulr.save_json(self.path, {"schemaVersion": 1, "updatedAt": updated_at,
                                   "area": "沼津周辺", "reports": reports})


class TestValidate(TempRepoTestCase):
    def test_valid_json_passes(self):
        self.write_reports([make_report()])
        data = ulr.load_json(self.path)
        errors = ulr.validate_data(data)
        self.assertEqual(errors, [])

    def test_missing_required_field(self):
        r = make_report()
        del r["fishName"]
        errors = ulr.validate_report(r)
        self.assertTrue(any("fishName" in e for e in errors))

    def test_invalid_fishing_type(self):
        r = make_report(fishingType="airplane")
        errors = ulr.validate_report(r)
        self.assertTrue(any("fishingType" in e for e in errors))

    def test_invalid_url(self):
        r = make_report(sourceUrl="ftp://example.com/x")
        errors = ulr.validate_report(r)
        self.assertTrue(any("sourceUrl" in e for e in errors))

    def test_invalid_date(self):
        r = make_report(reportedAt="2026-13-40")
        errors = ulr.validate_report(r)
        self.assertTrue(any("reportedAt" in e for e in errors))

    def test_duplicate_id_detected(self):
        data = {"reports": [make_report(id="dup"), make_report(id="dup")]}
        errors = ulr.validate_data(data)
        self.assertTrue(any("idが重複" in e for e in errors))


class TestDuplicateWarnings(unittest.TestCase):
    def test_strong_duplicate_same_url_fish_date(self):
        a = make_report(id="a")
        b = make_report(id="b")
        warnings = ulr.find_duplicate_warnings([a, b])
        self.assertTrue(any("強い重複候補" in w for w in warnings))

    def test_no_warning_for_same_url_different_date(self):
        a = make_report(id="a", reportedAt="2026-09-01")
        b = make_report(id="b", reportedAt="2026-08-01", fishName="アジ")
        warnings = ulr.find_duplicate_warnings([a, b])
        self.assertEqual(warnings, [])

    def test_same_fish_area_date_different_url(self):
        a = make_report(id="a", sourceUrl="https://siteA.example.com")
        b = make_report(id="b", sourceUrl="https://siteB.example.com")
        warnings = ulr.find_duplicate_warnings([a, b])
        self.assertTrue(any("魚種/エリア/日付一致" in w for w in warnings))


class TestFreshness(unittest.TestCase):
    def test_buckets(self):
        now = ulr.parse_date_loose("2026-09-06")
        self.assertEqual(ulr.freshness_bucket(ulr.days_ago("2026-09-06", now)), "0-7")
        self.assertEqual(ulr.freshness_bucket(ulr.days_ago("2026-08-28", now)), "8-14")
        self.assertEqual(ulr.freshness_bucket(ulr.days_ago("2026-08-15", now)), "15-30")
        self.assertEqual(ulr.freshness_bucket(ulr.days_ago("2026-07-20", now)), "31-60")
        self.assertEqual(ulr.freshness_bucket(ulr.days_ago("2026-01-01", now)), "61+")

    def test_stale_detection_61_days(self):
        now = ulr.parse_date_loose("2026-09-06")
        old = make_report(id="old", reportedAt="2026-01-01")
        recent = make_report(id="new", reportedAt="2026-09-01")
        d_old = ulr.days_ago(old["reportedAt"], now)
        d_new = ulr.days_ago(recent["reportedAt"], now)
        self.assertGreaterEqual(d_old, 61)
        self.assertLess(d_new, 61)


class TestBackup(TempRepoTestCase):
    def test_backup_created_and_not_overwritten(self):
        self.write_reports([make_report()])
        b1 = ulr.make_backup(self.path, self.backup_dir)
        b2 = ulr.make_backup(self.path, self.backup_dir)
        self.assertIsNotNone(b1)
        self.assertTrue(b1.exists())
        self.assertNotEqual(b1, b2)
        self.assertTrue(b2.exists())


class TestArchive(TempRepoTestCase):
    def test_archive_moves_old_reports_and_backs_up(self):
        old = make_report(id="old-1", reportedAt="2026-01-01")
        recent = make_report(id="new-1", reportedAt="2026-09-01")
        self.write_reports([old, recent])

        parser = ulr.build_parser()
        args = parser.parse_args([
            "--path", str(self.path), "--archive-path", str(self.archive_path),
            "--backup-dir", str(self.backup_dir), "--now", "2026-09-06",
            "archive", "--yes",
        ])
        code = ulr.cmd_archive(args)
        self.assertEqual(code, 0)

        remaining = ulr.load_json(self.path)
        archived = ulr.load_json(self.archive_path)
        self.assertEqual([r["id"] for r in remaining["reports"]], ["new-1"])
        self.assertEqual([r["id"] for r in archived["reports"]], ["old-1"])
        self.assertTrue(self.backup_dir.exists())
        self.assertEqual(len(list(self.backup_dir.glob("*.json"))), 1)

    def test_archive_noop_when_nothing_stale(self):
        recent = make_report(id="new-1", reportedAt="2026-09-01")
        self.write_reports([recent])
        parser = ulr.build_parser()
        args = parser.parse_args([
            "--path", str(self.path), "--archive-path", str(self.archive_path),
            "--backup-dir", str(self.backup_dir), "--now", "2026-09-06",
            "archive", "--yes",
        ])
        code = ulr.cmd_archive(args)
        self.assertEqual(code, 0)
        self.assertFalse(self.archive_path.exists())


class TestAddUpdate(TempRepoTestCase):
    def test_add_report_from_file(self):
        self.write_reports([make_report(id="existing")])
        new_report_path = self.root / "new.json"
        ulr.save_json(new_report_path, make_report(id="brand-new", sourceUrl="https://other.example.com"))

        parser = ulr.build_parser()
        args = parser.parse_args([
            "--path", str(self.path), "--backup-dir", str(self.backup_dir),
            "add", "--file", str(new_report_path), "--yes",
        ])
        code = ulr.cmd_add(args)
        self.assertEqual(code, 0)
        data = ulr.load_json(self.path)
        self.assertEqual(len(data["reports"]), 2)
        self.assertTrue(any(r["id"] == "brand-new" for r in data["reports"]))

    def test_add_rejects_duplicate_id(self):
        self.write_reports([make_report(id="existing")])
        new_report_path = self.root / "new.json"
        ulr.save_json(new_report_path, make_report(id="existing"))
        parser = ulr.build_parser()
        args = parser.parse_args([
            "--path", str(self.path), "--backup-dir", str(self.backup_dir),
            "add", "--file", str(new_report_path), "--yes",
        ])
        code = ulr.cmd_add(args)
        self.assertEqual(code, 1)
        data = ulr.load_json(self.path)
        self.assertEqual(len(data["reports"]), 1)

    def test_update_existing_report(self):
        self.write_reports([make_report(id="existing", fishName="アジ")])
        patch_path = self.root / "patch.json"
        ulr.save_json(patch_path, {"fishName": "シロギス"})
        parser = ulr.build_parser()
        args = parser.parse_args([
            "--path", str(self.path), "--backup-dir", str(self.backup_dir),
            "update", "--id", "existing", "--file", str(patch_path), "--yes",
        ])
        code = ulr.cmd_update(args)
        self.assertEqual(code, 0)
        data = ulr.load_json(self.path)
        self.assertEqual(data["reports"][0]["fishName"], "シロギス")


if __name__ == "__main__":
    unittest.main()
