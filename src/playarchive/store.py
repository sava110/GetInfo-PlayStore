from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


class HistoryError(Exception):
    def __init__(self, message: str, backup: Path | None = None):
        super().__init__(message)
        self.backup = backup


def empty_document() -> dict:
    return {"schemaVersion": 1, "apps": {}}


def load_history(path: Path) -> dict:
    if not path.exists():
        return empty_document()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HistoryError(f"履歴ファイルを読めません: {path} ({exc})") from exc
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        backup = _backup_corrupt(path)
        raise HistoryError(
            f"履歴ファイルを読めません: {path}\n壊れた内容の写し: {backup}\n直してから再度実行してください。",
            backup=backup,
        ) from exc
    if not isinstance(document, dict) or not isinstance(document.get("apps"), dict):
        backup = _backup_corrupt(path)
        raise HistoryError(
            f"履歴ファイルの形式が不正です: {path}\n壊れた内容の写し: {backup}",
            backup=backup,
        )
    version = document.get("schemaVersion", 1)
    if version != 1:
        raise HistoryError(f"未対応の履歴形式です (schemaVersion={version}): {path}")
    document["schemaVersion"] = 1
    return document


def save_history(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, ensure_ascii=False, indent=4) + "\n"
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def _backup_corrupt(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.corrupt-{stamp}")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.corrupt-{stamp}-{counter}")
        counter += 1
    backup.write_bytes(path.read_bytes())
    return backup
