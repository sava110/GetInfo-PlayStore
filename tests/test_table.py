import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from playarchive.table import render_markdown, write_markdown


class TableRenderTest(unittest.TestCase):
    def test_latest_and_history_use_readable_headers(self):
        document = {
            "apps": {
                "com.yysystem.YYSimpleTranscript": {
                    "latest": {
                        "version": "18.20.16",
                        "updated": int(
                            datetime(
                                2026, 9, 27, 22, 38, 45, tzinfo=timezone.utc
                            ).timestamp()
                        ),
                        "recentChanges": "一行目\n二行目",
                    },
                    "history": [
                        {
                            "version": "18.20.16",
                            "updated": int(
                                datetime(
                                    2026, 9, 27, 22, 38, 45, tzinfo=timezone.utc
                                ).timestamp()
                            ),
                            "recentChanges": "一行目\n二行目",
                            "fetchedAt": "2026-09-28T02:59:53Z",
                            "gapSuspected": False,
                        }
                    ],
                }
            }
        }
        text = render_markdown(document, generated_at="2026-09-28T03:00:00Z")
        self.assertIn("| アプリ | アプデ日 | Ver. | 内容 |", text)
        self.assertIn("| YY文字起こし iOS | 26/09/28 | 18.20.16 | 一行目<br>二行目 |", text)
        self.assertIn("## YY文字起こし iOS", text)
        self.assertIn("| 記録した日時 | アプデ日 | Ver. | 欠番 | 内容 |", text)
        self.assertIn("26/09/28 11:59", text)
        self.assertIn("まだ履歴がありません。", text)

    def test_write_creates_parent_directory(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "out" / "changelog.md"
            write_markdown({"apps": {}}, path, generated_at="2026-09-28T03:00:00Z")
            self.assertTrue(path.is_file())
            self.assertIn("# 更新履歴", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
