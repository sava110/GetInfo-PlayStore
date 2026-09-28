import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from playarchive.store import HistoryError, load_history, save_history


class StoreTest(unittest.TestCase):
    def test_round_trip_creates_parent_and_keeps_unicode(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "data" / "history.json"
            document = {
                "schemaVersion": 1,
                "apps": {"com.example.app": {"title": "例のアプリ"}},
            }
            save_history(path, document)
            self.assertEqual(load_history(path), document)
            self.assertIn("例のアプリ", path.read_text(encoding="utf-8"))

    def test_missing_file_is_an_empty_document(self):
        with TemporaryDirectory() as tmp:
            loaded = load_history(Path(tmp) / "missing.json")
            self.assertEqual(loaded["schemaVersion"], 1)
            self.assertEqual(loaded["apps"], {})

    def test_corrupt_json_is_copied_aside_and_left_in_place(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(HistoryError) as caught:
                load_history(path)
            self.assertTrue(caught.exception.backup.is_file())
            self.assertEqual(path.read_text(encoding="utf-8"), "{")
            self.assertIn("壊れた内容の写し", str(caught.exception))

    def test_unknown_schema_is_rejected_without_replacing_the_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            path.write_text(
                json.dumps({"schemaVersion": 2, "apps": {}}), encoding="utf-8"
            )
            with self.assertRaises(HistoryError) as caught:
                load_history(path)
            self.assertIsNone(caught.exception.backup)
            self.assertIn("schemaVersion=2", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
