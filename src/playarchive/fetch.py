from __future__ import annotations

import json

from playarchive.diff import Snapshot, normalize_changelog

_RECENT_CHANGES_PATH = (144, 1, 1)
_RECENT_CHANGES_FALLBACK = (-1, "145", 1, 1)


class FetchError(Exception):
    pass


class PlayFetcher:
    def fetch(self, package_id: str, lang: str, country: str) -> Snapshot:
        dataset, url = _load_dataset(package_id, lang, country)
        title = _field(dataset, "title")
        if not isinstance(title, str) or not title.strip():
            raise FetchError("title missing")
        version = _field(dataset, "version", fallback="Varies with device")
        if not isinstance(version, str):
            version = "Varies with device"
        updated = _field(dataset, "updated")
        if isinstance(updated, bool) or not isinstance(updated, int):
            updated = None
        developer = _field(dataset, "developer")
        if not isinstance(developer, str):
            developer = ""
        return Snapshot(
            package_id=package_id,
            title=title.strip(),
            version=version,
            updated=updated,
            recent_changes=normalize_changelog(extract_recent_changes(dataset)),
            url=url,
            developer=developer,
        )


def extract_recent_changes(dataset: dict) -> str:
    try:
        node = dataset["ds:5"][1][2]
    except (KeyError, IndexError, TypeError):
        return ""
    text = _dig(node, _RECENT_CHANGES_PATH)
    if isinstance(text, str) and text.strip():
        return text
    if isinstance(node, list) and node and isinstance(node[-1], dict):
        text = _dig(node, _RECENT_CHANGES_FALLBACK)
        if isinstance(text, str):
            return text
    return ""


def _field(dataset: dict, name: str, fallback: str | None = None):
    from google_play_scraper.constants.element import ElementSpecs

    content = ElementSpecs.Detail[name].extract_content(dataset)
    if content is None:
        return fallback
    return content


def _load_dataset(package_id: str, lang: str, country: str) -> tuple[dict, str]:
    from google_play_scraper.constants.regex import Regex
    from google_play_scraper.constants.request import Formats
    from google_play_scraper.exceptions import ExtraHTTPError, NotFoundError
    from google_play_scraper.utils.request import get

    url = Formats.Detail.build(app_id=package_id, lang=lang, country=country)
    try:
        dom = get(url)
    except NotFoundError:
        url = Formats.Detail.fallback_build(app_id=package_id, lang=lang)
        try:
            dom = get(url)
        except NotFoundError as exc:
            raise FetchError("not found") from exc
        except ExtraHTTPError as exc:
            raise FetchError(str(exc)) from exc
    except ExtraHTTPError as exc:
        raise FetchError(str(exc)) from exc
    except OSError as exc:
        raise FetchError(str(exc) or exc.__class__.__name__) from exc

    dataset: dict = {}
    for match in Regex.SCRIPT.findall(dom):
        key_match = Regex.KEY.findall(match)
        value_match = Regex.VALUE.findall(match)
        if not key_match or not value_match:
            continue
        try:
            dataset[key_match[0]] = json.loads(value_match[0])
        except json.JSONDecodeError as exc:
            raise FetchError("play page parse failed") from exc
    if "ds:5" not in dataset:
        raise FetchError("play page parse failed")
    return dataset, url


def _dig(node, path: tuple):
    current = node
    for key in path:
        if isinstance(current, list):
            if not isinstance(key, int):
                return None
            if key < 0:
                if not current:
                    return None
                current = current[key]
            elif key >= len(current):
                return None
            else:
                current = current[key]
        elif isinstance(current, dict):
            current = current.get(str(key) if not isinstance(key, str) else key)
        else:
            return None
        if current is None:
            return None
    return current
