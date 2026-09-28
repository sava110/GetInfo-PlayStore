import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from playarchive.fetch import FetchError
from playarchive.releasenotes import parse_latest_release

SAMPLE = """
<meta name="description" content="Ver.9.9.9 1999.1.1 ダウンロードはこちら" />
<h2 class="wp-block-heading">Ver.4.0.7　2026.8.6　</h2>
<p class="wp-block-paragraph"><strong>ダウンロードはこちら　<a href="https://example.test/a.msi">x64</a>　<a href="https://example.test/b.msi">x86</a></strong></p>
<p class="wp-block-paragraph">近日中にアップデートをお願いいたします<br>・セキュリティ対策<br>・画面表示の不具合を修正<br>・UI最適化</p>
<h2 class="wp-block-heading">Ver.4.0.6　2026.7.27</h2>
<p class="wp-block-paragraph">・古い更新内容</p>
"""


class ReleaseNoteParseTest(unittest.TestCase):
    def test_reads_only_the_top_release(self):
        snapshot = parse_latest_release(SAMPLE)
        self.assertEqual(snapshot.version, "4.0.7")
        self.assertEqual(snapshot.title, "YYデスクトップ字幕")
        self.assertEqual(
            snapshot.updated,
            int(datetime(2026, 8, 6, tzinfo=timezone.utc).timestamp()),
        )
        self.assertEqual(
            snapshot.recent_changes,
            "近日中にアップデートをお願いいたします\n・セキュリティ対策\n・画面表示の不具合を修正\n・UI最適化",
        )
        self.assertNotIn("ダウンロード", snapshot.recent_changes)
        self.assertNotIn("古い更新内容", snapshot.recent_changes)
        self.assertNotIn("9.9.9", snapshot.version)

    def test_missing_heading_is_an_error(self):
        with self.assertRaises(FetchError):
            parse_latest_release("<h2>更新履歴</h2><p>内容</p>")


if __name__ == "__main__":
    unittest.main()
