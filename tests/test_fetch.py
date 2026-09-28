import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from playarchive.fetch import extract_recent_changes


def _dataset(node) -> dict:
    # 実ページは ds:5[1][2] にアプリ本体の配列がある。
    return {"ds:5": [None, [None, None, node]]}


def _node_with_changes(text: str) -> dict:
    node = [None] * 145
    node[144] = [None, [None, text]]
    return _dataset(node)


class FetchParseTest(unittest.TestCase):
    def test_reads_recent_changes_path(self):
        dataset = _node_with_changes("• バグを修正しました<br>• 表示を調整しました")
        self.assertEqual(
            extract_recent_changes(dataset),
            "• バグを修正しました<br>• 表示を調整しました",
        )

    def test_missing_path_is_empty(self):
        self.assertEqual(extract_recent_changes(_dataset([None])), "")

    def test_object_form_fallback(self):
        node = [{"145": [None, [None, "フォールバックの更新内容"]]}]
        dataset = _dataset(node)
        self.assertEqual(extract_recent_changes(dataset), "フォールバックの更新内容")


if __name__ == "__main__":
    unittest.main()
