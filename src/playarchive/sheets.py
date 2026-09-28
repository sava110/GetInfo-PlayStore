from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from playarchive.config import Config

TOKYO = ZoneInfo("Asia/Tokyo")

# 1アプリあたり 日付・版・内容の3列。シート1の週次表は触らない。
COLUMNS: tuple[tuple[str, str], ...] = (
    ("YY文字起こし iOS", "com.yysystem.YYSimpleTranscript"),
    ("YY文字起こし Android", "yytranscript.yysystem.android"),
    ("YYProbe iOS", "com.yysystem.YYProbe-Lite"),
    ("YYProbe Android", "yyprobe.yysystem.android"),
    ("YYレセプション", "com.yysystem.YYReceptionWindow"),
    ("YYデスクトップ字幕", "yysystem.yydesktopcaption"),
)

HEADER_APPS = tuple(label for group in COLUMNS for label in (group[0], "", ""))
HEADER_FIELDS = tuple(field for _ in COLUMNS for field in ("アプデ日", "Ver.", "内容"))


class SheetsError(Exception):
    pass


def format_sheet_date(updated: int | None) -> str:
    if not isinstance(updated, int):
        return ""
    local = datetime.fromtimestamp(updated, timezone.utc).astimezone(TOKYO)
    return local.strftime("%y/%m/%d")


def cells_for_app(app: dict | None) -> list[str]:
    latest = (app or {}).get("latest") or {}
    version = latest.get("version")
    changes = latest.get("recentChanges")
    return [
        format_sheet_date(latest.get("updated")),
        "" if version is None else str(version),
        "" if changes is None else str(changes),
    ]


def build_values_row(document: dict) -> list[str]:
    apps = document.get("apps") if isinstance(document, dict) else {}
    if not isinstance(apps, dict):
        apps = {}
    row: list[str] = []
    for _label, app_id in COLUMNS:
        row.extend(cells_for_app(apps.get(app_id)))
    return row


def build_table(document: dict) -> list[list[str]]:
    return [list(HEADER_APPS), list(HEADER_FIELDS), build_values_row(document)]


def write_table(table: list[list[str]], config: Config, client=None) -> str:
    if not config.spreadsheet_id:
        raise SheetsError("spreadsheet_id が空です。config.toml を確認してください。")
    gspread_client = client or _gspread_client(config)
    try:
        spreadsheet = gspread_client.open_by_key(config.spreadsheet_id)
    except Exception as exc:
        raise SheetsError(f"スプレッドシートを開けません: {exc}") from exc
    worksheet = _worksheet(spreadsheet, config.worksheet)
    width = max(len(row) for row in table)
    end_column = _column_letter(width)
    try:
        worksheet.update(range_name=f"A1:{end_column}{len(table)}", values=table)
    except Exception as exc:
        raise SheetsError(f"シートへ書き込めません: {exc}") from exc
    return config.worksheet


def _worksheet(spreadsheet, name: str):
    try:
        return spreadsheet.worksheet(name)
    except Exception:
        columns = len(HEADER_APPS)
        return spreadsheet.add_worksheet(title=name, rows=10, cols=max(columns, 18))


def _gspread_client(config: Config):
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:
        raise SheetsError(
            "gspread がありません。`.venv/bin/pip install -e .` を実行してください。"
        ) from exc
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    info = _service_account_info(config)
    credentials = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(credentials)


def _service_account_info(config: Config) -> dict:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        try:
            info = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SheetsError("GOOGLE_SERVICE_ACCOUNT_JSON が JSON ではありません。") from exc
        if not isinstance(info, dict):
            raise SheetsError("GOOGLE_SERVICE_ACCOUNT_JSON の形式が不正です。")
        return info
    path = config.credentials_path
    if path is None:
        env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        path = Path(env_path) if env_path else Path("credentials.json")
    if not path.is_file():
        raise SheetsError(
            "Google のサービスアカウント鍵がありません。"
            " credentials.json を置くか、GOOGLE_SERVICE_ACCOUNT_JSON を設定してください。"
        )
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SheetsError(f"認証ファイルを読めません: {path} ({exc})") from exc
    if not isinstance(info, dict):
        raise SheetsError(f"認証ファイルの形式が不正です: {path}")
    return info


def _column_letter(index: int) -> str:
    letter = ""
    remaining = index
    while remaining:
        remaining, remainder = divmod(remaining - 1, 26)
        letter = chr(65 + remainder) + letter
    return letter or "A"
