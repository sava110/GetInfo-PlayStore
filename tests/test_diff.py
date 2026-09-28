import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from playarchive.diff import (
    Snapshot,
    apply_snapshot,
    assess_gap,
    changelog_hash,
    is_immediate_next,
    normalize_changelog,
    parse_version,
)


def snap(version: str, changes: str = "note", updated: int | None = 100) -> Snapshot:
    return Snapshot(
        package_id="com.example.app",
        title="例",
        version=version,
        updated=updated,
        recent_changes=changes,
        url="https://example.test/app",
        developer="Dev",
    )


class DiffTest(unittest.TestCase):
    def test_html_and_newlines_normalize_to_the_same_text(self):
        self.assertEqual(
            normalize_changelog("修正<br>しました\r\n"),
            normalize_changelog("修正\nしました"),
        )
        self.assertEqual(
            changelog_hash("修正<br>しました"),
            changelog_hash("修正\nしました"),
        )

    def test_version_pairs(self):
        immediate = [
            ("1.0.0", "1.0.1"),
            ("1.9", "1.10"),
            ("1.9", "2.0"),
            ("1.2.3", "1.3.0"),
            ("1.2", "1.2.0"),
            ("1.2", "1.2.1"),
        ]
        gaps = [
            ("1.0", "1.4"),
            ("1.2.3", "1.4.0"),
            ("1.2", "1.2.2"),
        ]
        for previous, current in immediate:
            gap, compare = assess_gap(previous, current)
            self.assertFalse(gap, f"{previous} -> {current}")
            self.assertEqual(compare, "parsed")
            self.assertTrue(
                is_immediate_next(parse_version(previous), parse_version(current))
            )
        for previous, current in gaps:
            gap, compare = assess_gap(previous, current)
            self.assertTrue(gap, f"{previous} -> {current}")
            self.assertEqual(compare, "parsed")

    def test_unparsed_versions_do_not_guess_a_gap(self):
        gap, compare = assess_gap("Varies with device", "1.4")
        self.assertFalse(gap)
        self.assertEqual(compare, "unparsed")
        gap, compare = assess_gap("1.2-beta", "1.3")
        self.assertFalse(gap)
        self.assertEqual(compare, "unparsed")

    def test_same_version_changelog_edit_is_not_a_gap(self):
        first = apply_snapshot(None, snap("1.2.0", "old"), "2026-09-28T00:00:00Z")
        second = apply_snapshot(
            first.app, snap("1.2.0", "new"), "2026-09-28T01:00:00Z"
        )
        self.assertEqual(second.status, "ok")
        self.assertFalse(second.gap)
        self.assertEqual(len(second.app["history"]), 2)

    def test_identical_snapshot_does_not_append(self):
        first = apply_snapshot(None, snap("1.2.0"), "2026-09-28T00:00:00Z")
        second = apply_snapshot(first.app, snap("1.2.0"), "2026-09-28T01:00:00Z")
        self.assertEqual(second.status, "unchanged")
        self.assertEqual(len(second.app["history"]), 1)
        self.assertEqual(second.app["lastCheckedAt"], "2026-09-28T01:00:00Z")
        self.assertEqual(second.app["latest"]["fetchedAt"], "2026-09-28T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
