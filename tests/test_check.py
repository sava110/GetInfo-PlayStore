import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from playarchive.cli import run_check, run_show
from playarchive.config import Config, ConfigError, load_config, load_watchlist
from playarchive.diff import Snapshot
from playarchive.fetch import FetchError
from playarchive.store import load_history


def snapshot(
    package_id: str,
    version: str,
    changes: str = "修正しました",
    updated: int = 1_700_000_000,
) -> Snapshot:
    return Snapshot(
        package_id=package_id,
        title="例のアプリ",
        version=version,
        updated=updated,
        recent_changes=changes,
        url=f"https://example.test/{package_id}",
        developer="Dev",
    )


class MapFetcher:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def fetch(self, package_id: str, lang: str = "", country: str = "") -> Snapshot:
        self.calls.append(package_id)
        value = self.mapping[package_id]
        if isinstance(value, Exception):
            raise value
        return value


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def config(self, lines: str, interval: float = 0) -> Config:
        watchlist = self.root / "watchlist.txt"
        watchlist.write_text(lines, encoding="utf-8")
        return Config(
            lang="ja",
            country="jp",
            history_path=self.root / "history.json",
            watchlist_path=watchlist,
            request_interval_seconds=interval,
            spreadsheet_id="test-sheet",
            worksheet="自動取得",
            credentials_path=None,
            table_path=self.root / "changelog.md",
        )

    def check(self, config: Config, fetcher) -> tuple[int, str]:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = run_check(
                config,
                fetcher,
                now="2026-09-28T02:00:00Z",
                sleep=lambda _seconds: None,
                release_fetcher=lambda: snapshot(
                    "yysystem.yydesktopcaption",
                    "4.0.7",
                    "画面表示の不具合を修正",
                    updated=1_754_438_400,
                ),
            )
        return code, stdout.getvalue()

    def test_baseline_then_second_check_does_not_append(self):
        config = self.config("com.example.app\n")
        fetcher = MapFetcher({"com.example.app": snapshot("com.example.app", "1.0.0")})
        code, output = self.check(config, fetcher)
        self.assertEqual(code, 0)
        self.assertIn("baseline  com.example.app  1.0.0", output)
        code, output = self.check(config, fetcher)
        self.assertEqual(code, 0)
        self.assertIn("unchanged com.example.app  1.0.0", output)
        history = load_history(config.history_path)["apps"]["com.example.app"]["history"]
        self.assertEqual(len(history), 1)
        self.assertIsNone(history[0]["previousVersion"])

    def test_version_jump_after_editing_the_saved_version_sets_gap(self):
        config = self.config("com.example.app\n")
        current = snapshot("com.example.app", "1.4.0", "新しい内容", updated=50)
        fetcher = MapFetcher({"com.example.app": current})
        self.check(config, fetcher)
        document = load_history(config.history_path)
        app = document["apps"]["com.example.app"]
        app["latest"]["version"] = "1.0"
        app["history"][0]["version"] = "1.0"
        config.history_path.write_text(
            json.dumps(document, ensure_ascii=False), encoding="utf-8"
        )
        code, output = self.check(config, fetcher)
        self.assertEqual(code, 0)
        self.assertIn("ok        com.example.app  1.0 -> 1.4.0  gap", output)
        history = load_history(config.history_path)["apps"]["com.example.app"]["history"]
        self.assertEqual(len(history), 2)
        self.assertTrue(history[-1]["gapSuspected"])
        self.assertEqual(history[-1]["previousVersion"], "1.0")

    def test_changelog_edit_appends_and_identical_rerun_does_not(self):
        config = self.config("com.example.app\n")
        fetcher = MapFetcher(
            {"com.example.app": snapshot("com.example.app", "1.2.0", "最初")}
        )
        self.check(config, fetcher)
        fetcher.mapping["com.example.app"] = snapshot(
            "com.example.app", "1.2.0", "書き換えた"
        )
        code, output = self.check(config, fetcher)
        self.assertEqual(code, 0)
        self.assertIn("ok        com.example.app  1.2.0 -> 1.2.0", output)
        self.assertNotIn("gap", output)
        history = load_history(config.history_path)["apps"]["com.example.app"]["history"]
        self.assertEqual(len(history), 2)
        self.assertFalse(history[-1]["gapSuspected"])
        code, output = self.check(config, fetcher)
        self.assertIn("unchanged", output)
        history = load_history(config.history_path)["apps"]["com.example.app"]["history"]
        self.assertEqual(len(history), 2)

    def test_later_failure_keeps_the_earlier_success(self):
        config = self.config("com.example.ok\ncom.example.missing\n")
        fetcher = MapFetcher(
            {
                "com.example.ok": snapshot("com.example.ok", "3.0.0"),
                "com.example.missing": FetchError("not found"),
            }
        )
        code, output = self.check(config, fetcher)
        self.assertEqual(code, 1)
        self.assertIn("baseline  com.example.ok  3.0.0", output)
        self.assertIn("failed    com.example.missing  not found", output)
        apps = load_history(config.history_path)["apps"]
        self.assertEqual(apps["com.example.ok"]["history"][0]["version"], "3.0.0")
        self.assertEqual(apps["com.example.missing"]["lastError"]["message"], "not found")
        self.assertEqual(apps["com.example.missing"]["history"], [])

    def test_invalid_package_is_rejected_before_fetch(self):
        config = self.config("# comment\n\nnot a package\ncom.example.app\ncom.example.app\n")
        fetcher = MapFetcher({"com.example.app": snapshot("com.example.app", "1.0")})
        code, output = self.check(config, fetcher)
        self.assertEqual(code, 1)
        self.assertIn("failed    not a package  invalid package name", output)
        self.assertEqual(fetcher.calls, ["com.example.app"])
        self.assertEqual(len(load_watchlist(config.watchlist_path)), 2)

    def test_ios_watch_line_uses_the_app_store_fetcher(self):
        config = self.config("ios com.yysystem.YYProbe-Lite\n")
        play = MapFetcher({})
        store = MapFetcher(
            {
                "com.yysystem.YYProbe-Lite": snapshot(
                    "com.yysystem.YYProbe-Lite",
                    "9.6.34",
                    "AiLENSの文字揃え",
                )
            }
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = run_check(
                config,
                play,
                store,
                now="2026-09-28T02:00:00Z",
                sleep=lambda _seconds: None,
                release_fetcher=lambda: snapshot(
                    "yysystem.yydesktopcaption", "4.0.7", "画面表示の不具合を修正"
                ),
            )
        self.assertEqual(code, 0)
        self.assertEqual(play.calls, [])
        self.assertEqual(store.calls, ["com.yysystem.YYProbe-Lite"])
        self.assertIn("baseline  com.yysystem.YYProbe-Lite  9.6.34", stdout.getvalue())
        history = load_history(config.history_path)["apps"][
            "com.yysystem.YYProbe-Lite"
        ]["history"]
        self.assertEqual(history[0]["version"], "9.6.34")

    def test_corrupt_history_stops_before_fetch(self):
        config = self.config("com.example.app\n")
        config.history_path.write_text("{", encoding="utf-8")
        fetcher = MapFetcher({"com.example.app": snapshot("com.example.app", "1.0")})
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code, _output = self.check(config, fetcher)
        self.assertEqual(code, 2)
        self.assertEqual(fetcher.calls, [])
        self.assertIn("壊れた内容の写し", stderr.getvalue())

    def test_show_mentions_a_gap_and_a_baseline(self):
        config = self.config("com.example.app\n")
        fetcher = MapFetcher(
            {"com.example.app": snapshot("com.example.app", "1.0", "最初の内容")}
        )
        self.check(config, fetcher)
        fetcher.mapping["com.example.app"] = snapshot(
            "com.example.app", "1.4", "飛んだあとの内容", updated=60
        )
        self.check(config, fetcher)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = run_show(config, "com.example.app")
        self.assertEqual(code, 0)
        text = stdout.getvalue()
        self.assertIn("監視開始時の記録です。", text)
        self.assertIn("番号が飛んで見えます。", text)
        self.assertIn("飛んだあとの内容", text)
        self.assertLess(text.index("飛んだあとの内容"), text.index("最初の内容"))

    def test_interval_below_zero_is_rejected(self):
        path = self.root / "config.toml"
        path.write_text("request_interval_seconds = 0\n", encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_config(path)


if __name__ == "__main__":
    unittest.main()
