import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from playarchive.cli import run_sheets
from playarchive.config import Config
from playarchive.sheets import (
    COLUMNS,
    HEADER_APPS,
    HEADER_FIELDS,
    build_table,
    cells_for_app,
    format_sheet_date,
    write_table,
)


def sample_document():
    return {
        "schemaVersion": 1,
        "apps": {
            "com.yysystem.YYSimpleTranscript": {
                "latest": {
                    "version": "18.20.16",
                    "updated": int(
                        datetime(2026, 9, 27, 22, 38, 45, tzinfo=timezone.utc).timestamp()
                    ),
                    "recentChanges": "LLM音声認識の言語判別を改善しました",
                }
            },
            "yytranscript.yysystem.android": {
                "latest": {
                    "version": "2.8.2",
                    "updated": int(
                        datetime(2026, 9, 22, 3, 1, 47, tzinfo=timezone.utc).timestamp()
                    ),
                    "recentChanges": "韓国語のローカライズ対応",
                }
            },
            "com.yysystem.YYProbe-Lite": {
                "latest": {
                    "version": "9.6.34",
                    "updated": int(
                        datetime(2026, 9, 27, 22, 46, 54, tzinfo=timezone.utc).timestamp()
                    ),
                    "recentChanges": "AiLENSの文字揃え",
                }
            },
            "yyprobe.yysystem.android": {
                "latest": {
                    "version": "Varies with device",
                    "updated": int(
                        datetime(2026, 9, 25, 10, 42, 29, tzinfo=timezone.utc).timestamp()
                    ),
                    "recentChanges": "高精度認識モードの対応言語を見直し",
                }
            },
            "com.yysystem.YYReceptionWindow": {
                "latest": {
                    "version": "6.3.29",
                    "updated": int(
                        datetime(2026, 9, 27, 22, 36, 9, tzinfo=timezone.utc).timestamp()
                    ),
                    "recentChanges": "高精度認識モードの言語判別を改善しました",
                }
            },
            "yysystem.yydesktopcaption": {
                "latest": {
                    "version": "4.0.7",
                    "updated": int(
                        datetime(2026, 8, 6, 0, 0, tzinfo=timezone.utc).timestamp()
                    ),
                    "recentChanges": "画面表示の不具合を修正",
                }
            },
        },
    }


class FakeWorksheet:
    def __init__(self):
        self.updated = None

    def update(self, range_name, values):
        self.updated = (range_name, values)


class FakeSpreadsheet:
    def __init__(self, names):
        self.names = names
        self.added = None
        self.worksheets = {name: FakeWorksheet() for name in names}

    def worksheet(self, name):
        if name not in self.worksheets:
            raise KeyError(name)
        return self.worksheets[name]

    def add_worksheet(self, title, rows, cols):
        sheet = FakeWorksheet()
        self.added = (title, rows, cols)
        self.worksheets[title] = sheet
        return sheet


class FakeClient:
    def __init__(self, spreadsheet):
        self.spreadsheet = spreadsheet
        self.opened = None

    def open_by_key(self, key):
        self.opened = key
        return self.spreadsheet


class SheetsLayoutTest(unittest.TestCase):
    def test_three_columns_per_app_in_the_requested_order(self):
        self.assertEqual(
            [label for label, _app_id in COLUMNS],
            [
                "YY文字起こし iOS",
                "YY文字起こし Android",
                "YYProbe iOS",
                "YYProbe Android",
                "YYレセプション",
                "YYデスクトップ字幕",
            ],
        )
        table = build_table(sample_document())
        self.assertEqual(table[0][0], "YY文字起こし iOS")
        self.assertEqual(table[0][3], "YY文字起こし Android")
        self.assertEqual(table[1][:3], ["アプデ日", "Ver.", "内容"])
        self.assertEqual(table[2][:3], ["26/09/28", "18.20.16", "LLM音声認識の言語判別を改善しました"])
        self.assertEqual(table[2][3:6], ["26/09/22", "2.8.2", "韓国語のローカライズ対応"])
        self.assertEqual(table[2][10], "Varies with device")
        self.assertEqual(table[2][15:18], ["26/08/06", "4.0.7", "画面表示の不具合を修正"])
        self.assertEqual(len(table[2]), 18)
        self.assertEqual(len(HEADER_APPS), 18)
        self.assertEqual(len(HEADER_FIELDS), 18)

    def test_missing_app_leaves_three_empty_cells(self):
        self.assertEqual(cells_for_app(None), ["", "", ""])
        table = build_table({"schemaVersion": 1, "apps": {}})
        self.assertEqual(table[2], [""] * 18)

    def test_tokyo_date_from_utc_timestamp(self):
        stamp = int(datetime(2026, 9, 27, 22, 38, 45, tzinfo=timezone.utc).timestamp())
        self.assertEqual(format_sheet_date(stamp), "26/09/28")

    def test_write_creates_the_auto_sheet_and_does_not_touch_sheet1(self):
        spreadsheet = FakeSpreadsheet(["シート1"])
        client = FakeClient(spreadsheet)
        config = Config(
            lang="ja",
            country="jp",
            history_path=Path("data/history.json"),
            watchlist_path=Path("watchlist.txt"),
            request_interval_seconds=1.0,
            spreadsheet_id="sheet-id",
            worksheet="自動取得",
            credentials_path=None,
        )
        name = write_table(build_table(sample_document()), config, client=client)
        self.assertEqual(name, "自動取得")
        self.assertEqual(client.opened, "sheet-id")
        self.assertEqual(spreadsheet.added[0], "自動取得")
        written = spreadsheet.worksheets["自動取得"].updated
        self.assertEqual(written[0], "A1:R3")
        self.assertEqual(written[1][0][0], "YY文字起こし iOS")
        self.assertNotIn("シート1", spreadsheet.added)

    def test_sheets_command_writes_from_history_file(self):
        with TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.json"
            history.write_text(
                json.dumps(sample_document(), ensure_ascii=False), encoding="utf-8"
            )
            config = Config(
                lang="ja",
                country="jp",
                history_path=history,
                watchlist_path=Path(tmp) / "watchlist.txt",
                request_interval_seconds=1.0,
                spreadsheet_id="sheet-id",
                worksheet="自動取得",
                credentials_path=None,
            )
            spreadsheet = FakeSpreadsheet(["自動取得"])
            code = run_sheets(config, client=FakeClient(spreadsheet))
            self.assertEqual(code, 0)
            values = spreadsheet.worksheets["自動取得"].updated[1]
            self.assertEqual(values[2][1], "18.20.16")


if __name__ == "__main__":
    unittest.main()
