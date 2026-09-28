from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from playarchive.diff import Snapshot, normalize_changelog
from playarchive.fetch import FetchError

APP_ID = "yysystem.yydesktopcaption"
PAGE_URL = "https://yysystem.com/releasenotes/yydesktopcaption"
TITLE = "YYデスクトップ字幕"

_HEADING = re.compile(
    r"<h2\b[^>]*>\s*Ver\.(\d+(?:\.\d+)*)\s+(\d{4})\.(\d{1,2})\.(\d{1,2})\s*</h2>",
    re.IGNORECASE,
)
_PARAGRAPH = re.compile(r"<p\b[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)


def parse_latest_release(html: str) -> Snapshot:
    """Read the first release heading on the page and the notes under it."""
    match = _HEADING.search(html or "")
    if match is None:
        raise FetchError("release heading not found")
    version, year, month, day = match.group(1), *map(int, match.groups()[1:])
    try:
        released_on = datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError as exc:
        raise FetchError("release date is invalid") from exc
    block = html[match.end() :]
    next_heading = _HEADING.search(block)
    if next_heading is not None:
        block = block[: next_heading.start()]
    notes = _notes_from_block(block)
    if not notes:
        raise FetchError("release notes not found")
    return Snapshot(
        package_id=APP_ID,
        title=TITLE,
        version=version,
        updated=int(released_on.timestamp()),
        recent_changes=notes,
        url=PAGE_URL,
        developer="YYSYSTEM",
    )


def fetch_latest_release() -> Snapshot:
    request = Request(PAGE_URL, headers={"User-Agent": "playarchive"})
    try:
        with urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8")
    except HTTPError as exc:
        raise FetchError(f"release page status {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise FetchError(str(exc) or exc.__class__.__name__) from exc
    return parse_latest_release(html)


def _notes_from_block(block: str) -> str:
    paragraphs = []
    for raw in _PARAGRAPH.findall(block):
        text = normalize_changelog(raw)
        if not text or "ダウンロードはこちら" in text:
            continue
        paragraphs.append(text)
    return "\n".join(paragraphs)
