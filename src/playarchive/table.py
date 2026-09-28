from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from playarchive.sheets import COLUMNS, format_sheet_date

_GAP = "番号が飛んで見えます（間の版の文面は取れていません）"


def render_markdown(document: dict, *, generated_at: str | None = None) -> str:
    apps = document.get("apps") if isinstance(document, dict) else {}
    if not isinstance(apps, dict):
        apps = {}
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# 更新履歴",
        "",
        f"生成: {stamp}（日本時間の日付）",
        "",
        "GitHub 上でこのファイルを開くと表として表示されます。",
        "",
        "## いまの最新",
        "",
        "| アプリ | アプデ日 | Ver. | 内容 |",
        "| --- | --- | --- | --- |",
    ]
    for label, app_id in COLUMNS:
        app = apps.get(app_id) or {}
        latest = app.get("latest") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(label),
                    _cell(format_sheet_date(latest.get("updated"))),
                    _cell(latest.get("version")),
                    _cell(latest.get("recentChanges")),
                ]
            )
            + " |"
        )
    lines.extend(["", "---", ""])
    for label, app_id in COLUMNS:
        app = apps.get(app_id) or {}
        history = list(app.get("history") or [])
        lines.append(f"## {label}")
        lines.append("")
        lines.append(f"`{app_id}`")
        lines.append("")
        if not history:
            lines.append("まだ履歴がありません。")
            lines.append("")
            continue
        lines.extend(
            [
                "| 記録した日時 | アプデ日 | Ver. | 欠番 | 内容 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for entry in reversed(history):
            gap = _GAP if entry.get("gapSuspected") else ""
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(_iso_to_tokyo(entry.get("fetchedAt"))),
                        _cell(format_sheet_date(entry.get("updated"))),
                        _cell(entry.get("version")),
                        _cell(gap),
                        _cell(entry.get("recentChanges")),
                    ]
                )
                + " |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_markdown(document: dict, path: Path, *, generated_at: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(document, generated_at=generated_at), encoding="utf-8")


def _iso_to_tokyo(value) -> str:
    if not isinstance(value, str) or not value:
        return ""
    text = value.strip().replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%y/%m/%d %H:%M")


def _cell(value) -> str:
    if value is None:
        text = ""
    else:
        text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
    text = text.replace("|", "\\|")
    return text
