from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

from playarchive.appstore import AppStoreFetcher
from playarchive.config import Config, ConfigError, load_config, load_watchlist
from playarchive.diff import apply_failure, apply_snapshot
from playarchive.fetch import FetchError, PlayFetcher
from playarchive.releasenotes import APP_ID as DESKTOP_CAPTION_ID
from playarchive.releasenotes import fetch_latest_release
from playarchive.sheets import SheetsError, build_table, write_table
from playarchive.store import HistoryError, load_history, save_history

_GAP_NOTE = (
    "番号が飛んで見えます。飛んだあいだの文面はこの取得では入手していません。"
    "意図して版を飛ばした可能性と、監視のあいだに消えた可能性は区別できません。"
)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="playarchive")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="監視リストを巡回して履歴を更新する")
    sub.add_parser("list", help="監視中アプリの概要を表示する")
    show = sub.add_parser("show", help="保存済みの履歴を表示する")
    show.add_argument("package")
    peek = sub.add_parser("peek", help="ストアの現在値を表示する")
    peek.add_argument("package")
    sub.add_parser("sheets", help="history.json の最新値をスプレッドシートへ書く")
    args = parser.parse_args(argv)

    try:
        config = load_config()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.command == "check":
        return run_check(config, PlayFetcher(), AppStoreFetcher())
    if args.command == "list":
        return run_list(config)
    if args.command == "show":
        return run_show(config, args.package)
    if args.command == "sheets":
        return run_sheets(config)
    return run_peek_any(config, args.package)


def run_check(
    config: Config,
    fetcher,
    appstore_fetcher=None,
    *,
    now: str | None = None,
    sleep=time.sleep,
    release_fetcher=fetch_latest_release,
) -> int:
    try:
        entries = load_watchlist(config.watchlist_path)
        document = load_history(config.history_path)
    except (ConfigError, HistoryError) as exc:
        print(exc, file=sys.stderr)
        return 2

    failures = 0
    fetched = False
    store = appstore_fetcher or AppStoreFetcher()
    if not entries:
        print("監視対象がありません")
    for source, identifier in entries:
        stamp = now or _utc_now()
        if source == "invalid":
            print(_status_line("failed", identifier, message="invalid package name"))
            failures += 1
            continue
        if fetched and config.request_interval_seconds:
            sleep(config.request_interval_seconds)
        fetched = True
        if source == "ios":
            fetch_fn = lambda ident=identifier: store.fetch(ident, config.country)
        else:
            fetch_fn = lambda ident=identifier: fetcher.fetch(
                ident, config.lang, config.country
            )
        failures += _record_fetch(config, document, identifier, fetch_fn, stamp)
    if fetched and config.request_interval_seconds:
        sleep(config.request_interval_seconds)
    failures += _record_release(config, document, release_fetcher, now or _utc_now())
    return 1 if failures else 0


def run_list(config: Config) -> int:
    try:
        entries = load_watchlist(config.watchlist_path)
        document = load_history(config.history_path)
    except (ConfigError, HistoryError) as exc:
        print(exc, file=sys.stderr)
        return 2
    invalid = 0
    if not entries:
        print("監視対象がありません")
    else:
        for source, identifier in entries:
            if source == "invalid":
                print(f"不正なパッケージ名  {identifier}")
                invalid += 1
                continue
            print(_list_line(identifier, document["apps"].get(identifier)))
    print(_list_line(DESKTOP_CAPTION_ID, document["apps"].get(DESKTOP_CAPTION_ID)))
    return 1 if invalid else 0


def run_show(config: Config, package_id: str) -> int:
    try:
        document = load_history(config.history_path)
    except HistoryError as exc:
        print(exc, file=sys.stderr)
        return 2
    app = document["apps"].get(package_id)
    if not app or not app.get("history"):
        print(f"履歴がありません: {package_id}", file=sys.stderr)
        return 1
    print(_render_show(package_id, app), end="")
    return 0


def run_sheets(config: Config, client=None) -> int:
    try:
        document = load_history(config.history_path)
        worksheet = write_table(build_table(document), config, client=client)
    except HistoryError as exc:
        print(exc, file=sys.stderr)
        return 2
    except SheetsError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"wrote {config.spreadsheet_id} / {worksheet}")
    return 0


def run_peek_any(config: Config, package_id: str) -> int:
    source = _peek_source(config, package_id)
    if source == "notes":
        return run_peek_release()
    if source == "ios":
        return run_peek_appstore(config, AppStoreFetcher(), package_id)
    return run_peek(config, PlayFetcher(), package_id)


def run_peek_appstore(config: Config, fetcher, identifier: str) -> int:
    try:
        snapshot = fetcher.fetch(identifier, config.country)
    except FetchError as exc:
        print(_one_line(str(exc) or "fetch failed"), file=sys.stderr)
        return 1
    _print_snapshot(snapshot, "ストア更新")
    return 0


def run_peek(config: Config, fetcher, package_id: str) -> int:
    try:
        snapshot = fetcher.fetch(package_id, config.lang, config.country)
    except FetchError as exc:
        print(_one_line(str(exc) or "fetch failed"), file=sys.stderr)
        return 1
    _print_snapshot(snapshot, "ストア更新")
    return 0


def run_peek_release(release_fetcher=fetch_latest_release) -> int:
    try:
        snapshot = release_fetcher()
    except FetchError as exc:
        print(_one_line(str(exc) or "fetch failed"), file=sys.stderr)
        return 1
    _print_snapshot(snapshot, "リリース日")
    return 0


def _record_fetch(config: Config, document: dict, identifier: str, fetch_fn, stamp: str) -> int:
    try:
        snapshot = fetch_fn()
    except FetchError as exc:
        message = _one_line(str(exc) or "fetch failed")
        document["apps"][identifier] = apply_failure(
            document["apps"].get(identifier), message, stamp
        )
        _save(config, document)
        print(_status_line("failed", identifier, message=message))
        return 1
    history_id = snapshot.package_id or identifier
    result = apply_snapshot(document["apps"].get(history_id), snapshot, stamp)
    document["apps"][history_id] = result.app
    _save(config, document)
    print(
        _status_line(
            result.status,
            history_id,
            version=result.version,
            previous=result.previous_version,
            gap=result.gap,
        )
    )
    return 0


def _peek_source(config: Config, package_id: str) -> str:
    if package_id == DESKTOP_CAPTION_ID:
        return "notes"
    try:
        entries = load_watchlist(config.watchlist_path)
    except ConfigError:
        entries = []
    for source, identifier in entries:
        if identifier == package_id:
            return source
    if package_id.isdigit():
        return "ios"
    try:
        document = load_history(config.history_path)
    except HistoryError:
        return "play"
    url = (document.get("apps") or {}).get(package_id, {}).get("url") or ""
    if "apps.apple.com" in url or "itunes.apple.com" in url:
        return "ios"
    return "play"


def _record_release(config: Config, document: dict, release_fetcher, stamp: str) -> int:
    try:
        snapshot = release_fetcher()
    except FetchError as exc:
        message = _one_line(str(exc) or "fetch failed")
        document["apps"][DESKTOP_CAPTION_ID] = apply_failure(
            document["apps"].get(DESKTOP_CAPTION_ID), message, stamp
        )
        _save(config, document)
        print(_status_line("failed", DESKTOP_CAPTION_ID, message=message))
        return 1
    result = apply_snapshot(document["apps"].get(DESKTOP_CAPTION_ID), snapshot, stamp)
    document["apps"][DESKTOP_CAPTION_ID] = result.app
    _save(config, document)
    print(
        _status_line(
            result.status,
            DESKTOP_CAPTION_ID,
            version=result.version,
            previous=result.previous_version,
            gap=result.gap,
        )
    )
    return 0


def _print_snapshot(snapshot, when_label: str) -> None:
    print(snapshot.title)
    print(f"パッケージ: {snapshot.package_id}")
    print(f"版: {snapshot.version or 'Varies with device'}")
    print(f"{when_label}: {_format_updated(snapshot.updated)}")
    print(f"開発者: {snapshot.developer or '-'}")
    print("新機能:")
    print(_changes_or_empty(snapshot.recent_changes))


def _save(config: Config, document: dict) -> None:
    try:
        save_history(config.history_path, document)
    except OSError as exc:
        print(f"履歴を保存できません: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def _status_line(
    kind: str,
    package_id: str,
    *,
    version: str = "",
    previous: str | None = None,
    gap: bool = False,
    message: str = "",
) -> str:
    label = f"{kind:<9}"
    if kind == "ok":
        suffix = "  gap" if gap else ""
        return f"{label} {package_id}  {previous or '-'} -> {version}{suffix}"
    if kind in {"unchanged", "baseline"}:
        return f"{label} {package_id}  {version}"
    return f"{label} {package_id}  {message}"


def _list_line(package_id: str, app: dict | None) -> str:
    if not app or not app.get("latest"):
        return f"（未取得）  {package_id}"
    title = app.get("title") or package_id
    latest = app["latest"]
    count = len(app.get("history") or [])
    checked = app.get("lastCheckedAt") or "-"
    return (
        f"{title}  {package_id}  版 {latest.get('version') or '-'}  "
        f"最終確認 {checked}  履歴 {count}"
    )


def _render_show(package_id: str, app: dict) -> str:
    history = list(app.get("history") or [])
    title = app.get("title") or package_id
    lines = [f"{title} ({package_id})", f"履歴 {len(history)} 件", ""]
    for entry in reversed(history):
        version = entry.get("version") or "-"
        when_label = "リリース日" if _is_release_note(app) else "ストア更新"
        lines.append(
            f"{entry.get('fetchedAt') or '-'}  版 {version}  "
            f"{when_label} {_format_updated(entry.get('updated'))}"
        )
        if entry.get("gapSuspected"):
            lines.append(_GAP_NOTE)
        elif entry.get("previousVersion") is None:
            lines.append("監視開始時の記録です。")
        elif entry.get("versionCompare") == "unparsed":
            lines.append("版番号を数値として比べられませんでした。")
        lines.append(_changes_or_empty(entry.get("recentChanges") or ""))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _is_release_note(app: dict) -> bool:
    return "releasenotes/" in (app.get("url") or "")


def _changes_or_empty(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return "ストアに新機能の記載なし"
    return cleaned


def _format_updated(value) -> str:
    if not isinstance(value, int):
        return "-"
    return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _one_line(message: str) -> str:
    compact = " ".join(message.split())
    if len(compact) > 200:
        return compact[:197] + "..."
    return compact
