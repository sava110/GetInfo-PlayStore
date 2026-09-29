/**
 * GitHub 上の history.json を読み、どれか1アプリでも更新があれば1行追加する。
 *
 * セットアップ:
 * 1. 対象スプレッドシートで 拡張機能 → Apps Script を開き、このファイルの内容を貼る
 * 2. プロジェクトの設定 → タイムゾーン を「東京」にする（朝6時トリガーのため）
 * 3. 初回は syncFromGitHub を実行し、外部接続（raw.githubusercontent.com）を許可する
 * 4. createMorningTrigger を一度実行する（毎日 06:00 前後に syncFromGitHub）
 *
 * 書き込みタイミング:
 *   GitHub Actions が 03:00 JST 前後に history.json を更新し、このスクリプトは 06:00 JST 前後にそれを読む。
 *   対象アプリが1つも変わっていなければシートは触らない。変わっていれば末尾に1行足す。
 *   iOS / デスクトップは Ver の変化だけで記入。Android は Ver またはアプデ文面の変化で記入。
 *   変わっていないアプリの列は空白。反映済み・記事URLは常に空白（人が書く）。過去行は上書きしない。
 *
 * 既存の週次表（シート1 など）は触らない。無いときは「自動取得」シートを作る。
 */

var SHEET_NAME = "自動取得";
var GITHUB_OWNER = "sava110";
var GITHUB_REPO = "GetInfo-PlayStore";
var GITHUB_REF = "my-project";
var GITHUB_PATH = "data/history.json";

var COLS_PER_APP = 5;
var HEADER_ROWS = 2;
var DATA_ROW = 3;

var APPS = [
  { label: "YY文字起こし iOS", id: "com.yysystem.YYSimpleTranscript" },
  { label: "YY文字起こし Android", id: "yytranscript.yysystem.android", android: true },
  { label: "YYProbe iOS", id: "com.yysystem.YYProbe-Lite" },
  { label: "YYProbe Android", id: "yyprobe.yysystem.android", android: true },
  { label: "YYレセプション", id: "com.yysystem.YYReceptionWindow" },
  { label: "YYデスクトップ字幕", id: "yysystem.yydesktopcaption" },
];

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("更新履歴")
    .addItem("GitHub から取り込む", "syncFromGitHub")
    .addItem("毎日6時のトリガーを登録", "createMorningTrigger")
    .addToUi();
}

function createMorningTrigger() {
  var handlers = ["syncFromGitHub"];
  ScriptApp.getProjectTriggers().forEach(function (trigger) {
    if (handlers.indexOf(trigger.getHandlerFunction()) !== -1) {
      ScriptApp.deleteTrigger(trigger);
    }
  });
  ScriptApp.newTrigger("syncFromGitHub").timeBased().atHour(6).everyDays(1).create();
}

function createNoonTrigger() {
  createMorningTrigger();
}

function syncFromGitHub() {
  var document = fetchHistoryJson_();
  var sheet = getOrCreateSheet_();
  ensureHeaders_(sheet);
  appendRowIfUpdated_(sheet, document);
}

function fetchHistoryJson_() {
  // api.github.com は未認証だと IP あたり 60 回/時。Apps Script は Google の共有 IP なので
  // すぐ 403 (rate limit) になる。公開リポジトリは raw を使う。
  var url =
    "https://raw.githubusercontent.com/" +
    GITHUB_OWNER +
    "/" +
    GITHUB_REPO +
    "/" +
    GITHUB_REF +
    "/" +
    GITHUB_PATH;
  var response = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    headers: {
      "User-Agent": "GetInfo-PlayStore-sheets",
    },
  });
  var code = response.getResponseCode();
  if (code !== 200) {
    throw new Error("GitHub から history.json を読めません (" + code + "): " + response.getContentText());
  }
  return JSON.parse(response.getContentText());
}

function getOrCreateSheet_() {
  var book = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = book.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = book.insertSheet(SHEET_NAME);
  }
  return sheet;
}

function ensureHeaders_(sheet) {
  var width = APPS.length * COLS_PER_APP;
  var names = [];
  var fields = [];
  APPS.forEach(function (app) {
    names.push(app.label, "", "", "", "");
    fields.push("情報取得日時", "アプリVer", "アプデ内容", "反映済み", "記事URL");
  });
  sheet.getRange(1, 1, 1, width).breakApart();
  sheet.getRange(1, 1, 1, width).setValues([names]);
  sheet.getRange(2, 1, 1, width).setValues([fields]);
  sheet.getRange(1, 1, HEADER_ROWS, width).setFontWeight("bold");
  for (var i = 0; i < APPS.length; i++) {
    sheet.getRange(1, i * COLS_PER_APP + 1, 1, COLS_PER_APP).merge();
  }
  sheet.setFrozenRows(HEADER_ROWS);
  var contentCols = [];
  for (var j = 0; j < APPS.length; j++) {
    contentCols.push(j * COLS_PER_APP + 3);
  }
  contentCols.forEach(function (column) {
    sheet.setColumnWidth(column, 280);
  });
}

function appendRowIfUpdated_(sheet, document) {
  var apps = document && document.apps && typeof document.apps === "object" ? document.apps : {};
  var width = APPS.length * COLS_PER_APP;
  var previous = lastWrittenState_(sheet);
  var next = [];
  var anyUpdated = false;

  APPS.forEach(function (app, index) {
    var latest = (apps[app.id] && apps[app.id].latest) || {};
    var version = latest.version == null ? "" : String(latest.version);
    var changes = latest.recentChanges == null ? "" : String(latest.recentChanges);
    var changed = appUpdated_(app, previous[index], version, changes);
    if (changed) {
      anyUpdated = true;
      next.push(
        formatFetchedAt_(latest.fetchedAt),
        version,
        changes,
        "",
        ""
      );
    } else {
      next.push("", "", "", "", "");
    }
  });

  if (!anyUpdated) {
    return;
  }

  var row = Math.max(sheet.getLastRow() + 1, DATA_ROW);
  sheet.getRange(row, 1, 1, width).setValues([next]);
  for (var j = 0; j < APPS.length; j++) {
    sheet.getRange(row, j * COLS_PER_APP + 3).setWrap(true);
  }
}

function appUpdated_(app, previous, version, changes) {
  if (app.android) {
    return (
      (version !== "" || changes !== "") &&
      (version !== previous.version || changes !== previous.changes)
    );
  }
  return version !== "" && version !== previous.version;
}

function lastWrittenState_(sheet) {
  var lastRow = sheet.getLastRow();
  var states = APPS.map(function () {
    return { version: "", changes: "" };
  });
  if (lastRow < DATA_ROW) {
    return states;
  }
  var width = APPS.length * COLS_PER_APP;
  var values = sheet.getRange(DATA_ROW, 1, lastRow - DATA_ROW + 1, width).getValues();
  for (var r = values.length - 1; r >= 0; r--) {
    for (var i = 0; i < APPS.length; i++) {
      if (states[i].version !== "" || states[i].changes !== "") {
        continue;
      }
      var writtenVersion = String(values[r][i * COLS_PER_APP + 1] || "");
      var writtenChanges = String(values[r][i * COLS_PER_APP + 2] || "");
      if (writtenVersion !== "" || writtenChanges !== "") {
        states[i] = { version: writtenVersion, changes: writtenChanges };
      }
    }
  }
  return states;
}

function formatFetchedAt_(value) {
  if (!value || typeof value !== "string") {
    return "";
  }
  var parsed = new Date(value);
  if (isNaN(parsed.getTime())) {
    return value;
  }
  return Utilities.formatDate(parsed, "Asia/Tokyo", "yyyy/MM/dd HH:mm");
}
