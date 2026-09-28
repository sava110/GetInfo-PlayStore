import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from playarchive.appstore import parse_lookup_payload
from playarchive.fetch import FetchError


def sample_payload(**overrides):
    app = {
        "trackId": 1493896577,
        "trackName": "YYProbe - 会話の可視化アプリ -",
        "bundleId": "com.yysystem.YYProbe-Lite",
        "version": "9.6.34",
        "currentVersionReleaseDate": "2026-09-27T22:46:54Z",
        "sellerName": "EQUOS RESEARCH CO.,LTD.",
        "releaseNotes": "本バージョンでは下記対応を行いました。<br>・AiLENSに表示するテキストを上揃えと下揃えを選択できるようにしました",
        "trackViewUrl": "https://apps.apple.com/jp/app/id1493896577",
    }
    app.update(overrides)
    return {"resultCount": 1, "results": [app]}


class AppStoreParseTest(unittest.TestCase):
    def test_reads_version_date_and_notes(self):
        snapshot = parse_lookup_payload(sample_payload(), "com.yysystem.YYProbe-Lite")
        self.assertEqual(snapshot.package_id, "com.yysystem.YYProbe-Lite")
        self.assertEqual(snapshot.version, "9.6.34")
        self.assertEqual(
            snapshot.updated,
            int(datetime(2026, 9, 27, 22, 46, 54, tzinfo=timezone.utc).timestamp()),
        )
        self.assertIn("上揃えと下揃え", snapshot.recent_changes)
        self.assertNotIn("<br>", snapshot.recent_changes)

    def test_empty_results_is_not_found(self):
        with self.assertRaises(FetchError) as caught:
            parse_lookup_payload({"resultCount": 0, "results": []}, "1493896577")
        self.assertEqual(str(caught.exception), "not found")

    def test_missing_release_notes_are_empty(self):
        snapshot = parse_lookup_payload(sample_payload(releaseNotes=None), "1493896577")
        self.assertEqual(snapshot.recent_changes, "")


if __name__ == "__main__":
    unittest.main()
