from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_BR_TAG = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_HTML_TAG = re.compile(r"<[^>]+>")
_VERSION = re.compile(r"\d+(?:[.\s]\d+)*\Z")


@dataclass(frozen=True)
class Snapshot:
    package_id: str
    title: str
    version: str
    updated: int | None
    recent_changes: str
    url: str
    developer: str


@dataclass(frozen=True)
class ApplyResult:
    app: dict
    status: str
    gap: bool
    previous_version: str | None
    version: str


def normalize_changelog(text: str) -> str:
    cleaned = text or ""
    cleaned = _BR_TAG.sub("\n", cleaned)
    cleaned = _HTML_TAG.sub("", cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    return cleaned.strip()


def changelog_hash(text: str) -> str:
    digest = hashlib.sha256(normalize_changelog(text).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def parse_version(value: str) -> tuple[int, ...] | None:
    text = (value or "").strip()
    if not text or _VERSION.fullmatch(text) is None:
        return None
    return tuple(int(part) for part in re.split(r"[.\s]", text))


def is_immediate_next(previous: tuple[int, ...], current: tuple[int, ...]) -> bool:
    width = max(len(previous), len(current))
    prev_n = previous + (0,) * (width - len(previous))
    curr_n = current + (0,) * (width - len(current))
    if prev_n == curr_n:
        return True
    for index, (old, new) in enumerate(zip(prev_n, curr_n)):
        if old == new:
            continue
        return new == old + 1 and all(part == 0 for part in curr_n[index + 1 :])
    return False


def assess_gap(previous_version: str, current_version: str) -> tuple[bool, str]:
    if previous_version == current_version:
        parsed = parse_version(previous_version) is not None
        return False, "parsed" if parsed else "unparsed"
    previous = parse_version(previous_version)
    current = parse_version(current_version)
    if previous is None or current is None:
        return False, "unparsed"
    return (not is_immediate_next(previous, current)), "parsed"


def apply_snapshot(app: dict | None, snapshot: Snapshot, now: str) -> ApplyResult:
    version = snapshot.version or ""
    updated = snapshot.updated
    changes = normalize_changelog(snapshot.recent_changes)
    digest = changelog_hash(changes)
    latest = {
        "version": version,
        "updated": updated,
        "recentChanges": changes,
        "changelogHash": digest,
        "fetchedAt": now,
    }
    if app is None or not app.get("latest"):
        entry = _entry(
            version=version,
            previous_version=None,
            updated=updated,
            changes=changes,
            digest=digest,
            now=now,
            gap=False,
            version_compare="parsed" if parse_version(version) else "unparsed",
        )
        return ApplyResult(
            app=_app_record(app, snapshot, latest, now, [entry]),
            status="baseline",
            gap=False,
            previous_version=None,
            version=version,
        )

    previous = app["latest"]
    history = list(app.get("history") or [])
    if _same_release(previous, version, updated, digest) or _tail_matches(
        history, version, updated, digest
    ):
        kept = dict(app)
        kept["title"] = snapshot.title
        kept["url"] = snapshot.url
        kept["developer"] = snapshot.developer
        kept["lastCheckedAt"] = now
        kept["lastError"] = None
        return ApplyResult(
            app=kept,
            status="unchanged",
            gap=False,
            previous_version=previous.get("version"),
            version=version,
        )

    previous_version = previous.get("version") or ""
    gap, version_compare = assess_gap(previous_version, version)
    history.append(
        _entry(
            version=version,
            previous_version=previous_version or None,
            updated=updated,
            changes=changes,
            digest=digest,
            now=now,
            gap=gap,
            version_compare=version_compare,
        )
    )
    return ApplyResult(
        app=_app_record(app, snapshot, latest, now, history),
        status="ok",
        gap=gap,
        previous_version=previous_version or None,
        version=version,
    )


def apply_failure(app: dict | None, message: str, now: str) -> dict:
    error = {"at": now, "message": message}
    if app is None:
        return {
            "title": "",
            "url": "",
            "developer": "",
            "latest": None,
            "lastCheckedAt": now,
            "lastError": error,
            "history": [],
        }
    kept = dict(app)
    kept["lastCheckedAt"] = now
    kept["lastError"] = error
    kept["history"] = list(app.get("history") or [])
    return kept


def _same_release(latest: dict, version: str, updated: int | None, digest: str) -> bool:
    return (
        latest.get("version") == version
        and latest.get("updated") == updated
        and latest.get("changelogHash") == digest
    )


def _tail_matches(
    history: list[dict], version: str, updated: int | None, digest: str
) -> bool:
    if not history:
        return False
    tail = history[-1]
    return (
        tail.get("version") == version
        and tail.get("updated") == updated
        and tail.get("changelogHash") == digest
    )


def _entry(
    *,
    version: str,
    previous_version: str | None,
    updated: int | None,
    changes: str,
    digest: str,
    now: str,
    gap: bool,
    version_compare: str,
) -> dict:
    return {
        "version": version,
        "previousVersion": previous_version,
        "updated": updated,
        "recentChanges": changes,
        "changelogHash": digest,
        "fetchedAt": now,
        "gapSuspected": gap,
        "versionCompare": version_compare,
    }


def _app_record(
    app: dict | None,
    snapshot: Snapshot,
    latest: dict,
    now: str,
    history: list[dict],
) -> dict:
    return {
        "title": snapshot.title,
        "url": snapshot.url,
        "developer": snapshot.developer,
        "latest": latest,
        "lastCheckedAt": now,
        "lastError": None,
        "history": history,
    }
