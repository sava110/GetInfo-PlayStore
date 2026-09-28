from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from playarchive.diff import Snapshot, normalize_changelog
from playarchive.fetch import FetchError

_LOOKUP = "https://itunes.apple.com/lookup"


def parse_lookup_payload(payload: dict, requested: str) -> Snapshot:
    if not isinstance(payload, dict):
        raise FetchError("app store parse failed")
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        raise FetchError("not found")
    app = results[0]
    if not isinstance(app, dict):
        raise FetchError("app store parse failed")
    bundle_id = app.get("bundleId")
    if not isinstance(bundle_id, str) or not bundle_id.strip():
        raise FetchError("bundleId missing")
    title = app.get("trackName")
    if not isinstance(title, str) or not title.strip():
        raise FetchError("title missing")
    version = app.get("version")
    if not isinstance(version, str):
        version = ""
    notes = app.get("releaseNotes")
    if not isinstance(notes, str):
        notes = ""
    developer = app.get("sellerName")
    if not isinstance(developer, str):
        developer = ""
    url = app.get("trackViewUrl")
    if not isinstance(url, str) or not url:
        url = f"https://apps.apple.com/app/id{app.get('trackId', requested)}"
    return Snapshot(
        package_id=bundle_id.strip(),
        title=title.strip(),
        version=version,
        updated=_parse_release_date(app.get("currentVersionReleaseDate")),
        recent_changes=normalize_changelog(notes),
        url=url,
        developer=developer,
    )


def _parse_release_date(value) -> int | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp())


class AppStoreFetcher:
    def fetch(self, identifier: str, country: str) -> Snapshot:
        query = {"country": country}
        if identifier.isdigit():
            query["id"] = identifier
        else:
            query["bundleId"] = identifier
        url = f"{_LOOKUP}?{urlencode(query)}"
        request = Request(url, headers={"User-Agent": "playarchive"})
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise FetchError(f"app store status {exc.code}") from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise FetchError(str(exc) or exc.__class__.__name__) from exc
        return parse_lookup_payload(payload, identifier)
