from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

PACKAGE_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*(\.[a-zA-Z][a-zA-Z0-9_-]*)+$")
IOS_LINE = re.compile(r"^ios\s+(\S+)$", re.IGNORECASE)


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    lang: str
    country: str
    history_path: Path
    watchlist_path: Path
    request_interval_seconds: float
    spreadsheet_id: str
    worksheet: str
    credentials_path: Path | None


def load_config(path: Path | None = None) -> Config:
    config_path = path or Path("config.toml")
    data: dict = {}
    if config_path.exists():
        try:
            with config_path.open("rb") as handle:
                loaded = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"設定ファイルを読めません: {config_path} ({exc})") from exc
        if not isinstance(loaded, dict):
            raise ConfigError(f"設定ファイルの形式が不正です: {config_path}")
        data = loaded

    interval = data.get("request_interval_seconds", 1.0)
    if isinstance(interval, bool) or not isinstance(interval, (int, float)):
        raise ConfigError("request_interval_seconds は正の数にしてください。")
    if interval <= 0:
        raise ConfigError("request_interval_seconds は 0 より大きくしてください。")

    credentials_raw = data.get("credentials_path")
    credentials_path = Path(str(credentials_raw)) if credentials_raw else None
    return Config(
        lang=str(data.get("lang", "ja")),
        country=str(data.get("country", "jp")),
        history_path=Path(str(data.get("history_path", "data/history.json"))),
        watchlist_path=Path(str(data.get("watchlist_path", "watchlist.txt"))),
        request_interval_seconds=float(interval),
        spreadsheet_id=str(
            data.get(
                "spreadsheet_id",
                "1uy7g5RLMYqje0bHnnub83JbjEifC7rICD9C7BsLtEho",
            )
        ),
        worksheet=str(data.get("worksheet", "自動取得")),
        credentials_path=credentials_path,
    )


def load_watchlist(path: Path) -> list[tuple[str, str]]:
    """Return (source, identifier) in file order. source is play, ios, or invalid."""
    if not path.exists():
        raise ConfigError(f"監視リストがありません: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"監視リストを読めません: {path} ({exc})") from exc

    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        source, identifier = _parse_watch_line(line)
        key = f"{source}:{identifier}"
        if key in seen:
            continue
        seen.add(key)
        entries.append((source, identifier))
    return entries


def _parse_watch_line(line: str) -> tuple[str, str]:
    ios = IOS_LINE.fullmatch(line)
    if ios:
        identifier = ios.group(1)
        if identifier.isdigit() or PACKAGE_PATTERN.fullmatch(identifier):
            return "ios", identifier
        return "invalid", line
    if PACKAGE_PATTERN.fullmatch(line):
        return "play", line
    return "invalid", line
