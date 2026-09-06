#!/usr/bin/env python3
"""latest_reports.json の更新支援CLI（標準ライブラリのみ）。

このスクリプトは外部サイトへは一切アクセスしません。
Web上で人間またはAIが実際に確認した釣果情報を、安全にJSONへ反映するための
検証・重複チェック・バックアップ・アーカイブ機能のみを提供します。

使い方の例:
    python3 tools/update_latest_reports.py validate
    python3 tools/update_latest_reports.py list
    python3 tools/update_latest_reports.py freshness
    python3 tools/update_latest_reports.py stale
    python3 tools/update_latest_reports.py archive
    python3 tools/update_latest_reports.py add --file new_report.json
    python3 tools/update_latest_reports.py add
    python3 tools/update_latest_reports.py update --id rep-001 --file patch.json
"""
import argparse
import copy
import difflib
import json
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS_PATH = REPO_ROOT / "latest_reports.json"
DEFAULT_ARCHIVE_PATH = REPO_ROOT / "latest_reports_archive.json"
DEFAULT_BACKUP_DIR = REPO_ROOT / "backups"

REQUIRED_FIELDS = ["id", "reportedAt", "fishName", "area", "fishingType", "sourceName", "sourceUrl"]
VALID_FISHING_TYPES = {"shore", "boat", "unknown"}
OPTIONAL_FIELDS_DEFAULTS = {
    "spotName": "", "method": "", "baitOrLure": "", "catchSummary": "",
    "sourcePublishedAt": "", "note": "",
}

JST = timezone(timedelta(hours=9))


def now_jst():
    return datetime.now(JST)


def parse_date_loose(s):
    """'YYYY-MM-DD' または ISO8601 を受け付ける。失敗したら None。"""
    if not isinstance(s, str) or not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s[:19] if "T" in s else s, fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=JST)
            return d
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def days_ago(date_str, now=None):
    now = now or now_jst()
    d = parse_date_loose(date_str)
    if d is None:
        return None
    return (now.date() - d.date()).days


def freshness_bucket(days):
    if days is None:
        return "unknown"
    if days <= 7:
        return "0-7"
    if days <= 14:
        return "8-14"
    if days <= 30:
        return "15-30"
    if days <= 60:
        return "31-60"
    return "61+"


# ── I/O ──

def load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"{path} が見つかりません")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def make_backup(path, backup_dir=DEFAULT_BACKUP_DIR):
    if not path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_jst().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"{path.stem}_{stamp}.json"
    i = 1
    while dest.exists():
        dest = backup_dir / f"{path.stem}_{stamp}_{i}.json"
        i += 1
    shutil.copy2(path, dest)
    return dest


# ── 検証 ──

def validate_report(report, index=None):
    errors = []
    label = report.get("id") or f"index:{index}"
    for field in REQUIRED_FIELDS:
        if not report.get(field):
            errors.append(f"[{label}] 必須項目 '{field}' がありません")
    fishing_type = report.get("fishingType")
    if fishing_type is not None and fishing_type not in VALID_FISHING_TYPES:
        errors.append(f"[{label}] fishingType '{fishing_type}' は不正です（shore/boat/unknownのみ許可）")
    url = report.get("sourceUrl", "")
    if url and not (url.startswith("http://") or url.startswith("https://")):
        errors.append(f"[{label}] sourceUrl '{url}' はhttp(s)://で始まる必要があります")
    reported_at = report.get("reportedAt")
    if reported_at and parse_date_loose(reported_at) is None:
        errors.append(f"[{label}] reportedAt '{reported_at}' の日付形式が不正です")
    published_at = report.get("sourcePublishedAt")
    if published_at and parse_date_loose(published_at) is None:
        errors.append(f"[{label}] sourcePublishedAt '{published_at}' の日付形式が不正です")
    return errors


def validate_data(data):
    errors = []
    if not isinstance(data, dict):
        return ["トップレベルはオブジェクトである必要があります"]
    if "reports" not in data or not isinstance(data["reports"], list):
        errors.append("'reports' 配列がありません")
        return errors
    seen_ids = {}
    for i, report in enumerate(data["reports"]):
        errors.extend(validate_report(report, index=i))
        rid = report.get("id")
        if rid:
            if rid in seen_ids:
                errors.append(f"[{rid}] idが重複しています（index {seen_ids[rid]} と {i}）")
            else:
                seen_ids[rid] = i
    return errors


# ── 重複検出（警告のみ・自動統合しない） ──

def find_duplicate_warnings(reports, new_report=None):
    """重複候補の警告を返す（自動統合はしない）。

    判定は3段階：
    1. sourceUrl + fishName + reportedAt がすべて一致 → 強い重複候補
       （同じ記事URLでも日付や魚種が違えば別記事として扱う。1つの情報源ページが
       複数日の記事を並べているケースを誤検出しないための条件）。
    2. fishName + area + reportedAt が一致（sourceUrlが違っても）→ 重複候補
       （別サイトが同じ釣果を紹介している可能性）。
    3. fishName + reportedAt が一致し、catchSummaryの類似度が高い → 類似の可能性。
    """
    warnings = []
    pool = list(reports)
    targets = [new_report] if new_report is not None else pool

    for target in targets:
        for other in pool:
            if other is target:
                continue
            if new_report is None and reports.index(other) <= reports.index(target):
                continue
            if target.get("id") == other.get("id"):
                continue

            same_url_key = (target.get("sourceUrl") and target.get("sourceUrl") == other.get("sourceUrl")
                             and target.get("fishName") == other.get("fishName")
                             and target.get("reportedAt") == other.get("reportedAt"))
            if same_url_key:
                warnings.append(
                    f"強い重複候補（同一URL・魚種・日付）: {target.get('id')} と {other.get('id')} "
                    f"（{target.get('sourceUrl')}）")
                continue

            same_key = (target.get("fishName") == other.get("fishName")
                        and target.get("area") == other.get("area")
                        and target.get("reportedAt") == other.get("reportedAt"))
            if same_key:
                warnings.append(
                    f"魚種/エリア/日付一致の重複候補: {target.get('id')} と {other.get('id')} "
                    f"（{target.get('fishName')} / {target.get('area')} / {target.get('reportedAt')}）")
                continue

            similar_key = (target.get("fishName") == other.get("fishName")
                           and target.get("reportedAt") == other.get("reportedAt"))
            if similar_key:
                ratio = difflib.SequenceMatcher(
                    None, target.get("catchSummary", ""), other.get("catchSummary", "")).ratio()
                if ratio > 0.8:
                    warnings.append(
                        f"類似の可能性（要約が近い）: {target.get('id')} と {other.get('id')} "
                        f"（類似度 {ratio:.2f}）")
    # de-dup warning strings while preserving order
    seen = set()
    unique = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return unique


# ── コマンド ──

def cmd_validate(args):
    data = load_json(args.path)
    errors = validate_data(data)
    dup_warnings = find_duplicate_warnings(data.get("reports", [])) if not errors else []
    if errors:
        print(f"❌ {len(errors)}件のエラーがあります：")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"✅ {len(data['reports'])}件のreportはすべて構造的に正常です。")
    if dup_warnings:
        print(f"\n⚠️ 重複候補が{len(dup_warnings)}件あります（自動修正はしません）：")
        for w in dup_warnings:
            print(f"  - {w}")
    return 0


def cmd_list(args):
    data = load_json(args.path)
    reports = sorted(data.get("reports", []), key=lambda r: r.get("reportedAt", ""), reverse=True)
    now = parse_date_loose(args.now) if args.now else now_jst()
    for r in reports:
        d = days_ago(r.get("reportedAt"), now)
        d_str = f"{d}日前" if d is not None else "日付不明"
        print(f"[{r.get('id')}] {r.get('reportedAt')}（{d_str}） {r.get('fishingType')}"
              f" {r.get('fishName')} @ {r.get('spotName') or r.get('area')} - {r.get('sourceName')}")
    print(f"\n合計 {len(reports)} 件")
    return 0


def cmd_freshness(args):
    data = load_json(args.path)
    now = parse_date_loose(args.now) if args.now else now_jst()
    buckets = {"0-7": [], "8-14": [], "15-30": [], "31-60": [], "61+": [], "unknown": []}
    for r in data.get("reports", []):
        d = days_ago(r.get("reportedAt"), now)
        buckets[freshness_bucket(d)].append(r)
    labels = {"0-7": "新しい情報(0-7日)", "8-14": "やや新しい(8-14日)", "15-30": "参考情報(15-30日)",
              "31-60": "古い情報(31-60日)", "61+": "非常に古い(61日以上)", "unknown": "日付不明"}
    for key in ["0-7", "8-14", "15-30", "31-60", "61+", "unknown"]:
        items = buckets[key]
        print(f"{labels[key]}: {len(items)}件")
        for r in items:
            print(f"  - [{r.get('id')}] {r.get('fishName')} ({r.get('reportedAt')}) {r.get('sourceName')}")
    return 0


def cmd_stale(args):
    data = load_json(args.path)
    now = parse_date_loose(args.now) if args.now else now_jst()
    stale = [r for r in data.get("reports", []) if (days_ago(r.get("reportedAt"), now) or 0) >= 61]
    if not stale:
        print("61日以上前のreportはありません。")
        return 0
    print(f"61日以上前のreportが{len(stale)}件あります（このコマンドは削除しません。archiveコマンドで移動できます）：")
    for r in stale:
        d = days_ago(r.get("reportedAt"), now)
        print(f"  - [{r.get('id')}] {r.get('fishName')} ({r.get('reportedAt')} / {d}日前) {r.get('sourceName')}")
    return 0


def cmd_archive(args):
    path = args.path
    archive_path = args.archive_path
    data = load_json(path)
    now = parse_date_loose(args.now) if args.now else now_jst()
    reports = data.get("reports", [])
    stale = [r for r in reports if (days_ago(r.get("reportedAt"), now) or 0) >= 61]

    if not stale:
        print("61日以上前のreportはありません。アーカイブ対象はありません。")
        return 0

    print(f"以下の{len(stale)}件を latest_reports_archive.json へ移動します：")
    for r in stale:
        d = days_ago(r.get("reportedAt"), now)
        print(f"  - [{r.get('id')}] {r.get('fishName')} ({r.get('reportedAt')} / {d}日前) {r.get('sourceName')}")

    if not args.yes:
        answer = input("\nこの内容でアーカイブへ移動しますか？ [y/N]: ").strip().lower()
        if answer != "y":
            print("キャンセルしました。何も変更していません。")
            return 1

    backup = make_backup(path, args.backup_dir)
    if backup:
        print(f"バックアップを作成しました: {backup}")

    stale_ids = {r["id"] for r in stale}
    remaining = [r for r in reports if r["id"] not in stale_ids]

    if archive_path.exists():
        archive_data = load_json(archive_path)
    else:
        archive_data = {"schemaVersion": 1, "reports": []}
    archive_backup = make_backup(archive_path, args.backup_dir) if archive_path.exists() else None
    if archive_backup:
        print(f"アーカイブ側のバックアップも作成しました: {archive_backup}")

    existing_archive_ids = {r["id"] for r in archive_data.get("reports", [])}
    to_append = [r for r in stale if r["id"] not in existing_archive_ids]
    archive_data["reports"] = archive_data.get("reports", []) + to_append
    archive_data["updatedAt"] = now.isoformat()

    data["reports"] = remaining
    data["updatedAt"] = now.isoformat()

    save_json(archive_path, archive_data)
    save_json(path, data)
    print(f"完了：{len(to_append)}件をアーカイブへ移動し、latest_reports.jsonを更新しました。")
    return 0


def _preview_and_confirm(action_label, preview_obj, warnings, yes):
    print(f"=== {action_label} プレビュー ===")
    print(json.dumps(preview_obj, ensure_ascii=False, indent=2))
    if warnings:
        print(f"\n⚠️ 重複候補が{len(warnings)}件あります（登録は可能ですが確認してください）：")
        for w in warnings:
            print(f"  - {w}")
    if yes:
        return True
    answer = input(f"\nこの内容で{action_label}を実行しますか？ [y/N]: ").strip().lower()
    return answer == "y"


def _prompt_report_interactively(existing=None):
    existing = existing or {}
    report = dict(existing)
    fields = REQUIRED_FIELDS + list(OPTIONAL_FIELDS_DEFAULTS.keys())
    print("各項目を入力してください（Enterで既存値/空のまま）。fishingTypeは shore/boat/unknown のいずれか。")
    for field in fields:
        current = report.get(field, OPTIONAL_FIELDS_DEFAULTS.get(field, ""))
        val = input(f"{field} [{current}]: ").strip()
        if val:
            report[field] = val
        elif field not in report:
            report[field] = OPTIONAL_FIELDS_DEFAULTS.get(field, "")
    return report


def cmd_add(args):
    data = load_json(args.path)
    reports = data.get("reports", [])

    if args.file:
        new_reports = load_json(args.file)
        if isinstance(new_reports, dict) and "reports" in new_reports:
            new_reports = new_reports["reports"]
        elif isinstance(new_reports, dict):
            new_reports = [new_reports]
    else:
        new_reports = [_prompt_report_interactively()]

    all_errors = []
    for i, r in enumerate(new_reports):
        all_errors.extend(validate_report(r, index=i))
    existing_ids = {r["id"] for r in reports}
    for r in new_reports:
        if r.get("id") in existing_ids:
            all_errors.append(f"[{r.get('id')}] は既に存在するidです（updateコマンドを使ってください）")

    if all_errors:
        print("❌ 追加できません。以下のエラーを解消してください：")
        for e in all_errors:
            print(f"  - {e}")
        return 1

    warnings = []
    for r in new_reports:
        warnings.extend(find_duplicate_warnings(reports, new_report=r))

    if not _preview_and_confirm("追加", new_reports, warnings, args.yes):
        print("キャンセルしました。何も変更していません。")
        return 1

    backup = make_backup(args.path, args.backup_dir)
    if backup:
        print(f"バックアップを作成しました: {backup}")

    data["reports"] = reports + new_reports
    data["updatedAt"] = (parse_date_loose(args.now) if args.now else now_jst()).isoformat()
    save_json(args.path, data)
    print(f"完了：{len(new_reports)}件を追加しました。")
    return 0


def cmd_update(args):
    if not args.id:
        print("❌ --id を指定してください")
        return 1
    data = load_json(args.path)
    reports = data.get("reports", [])
    target = next((r for r in reports if r.get("id") == args.id), None)
    if target is None:
        print(f"❌ id '{args.id}' のreportが見つかりません")
        return 1

    if args.file:
        patch = load_json(args.file)
    else:
        patch = _prompt_report_interactively(existing=target)

    updated = copy.deepcopy(target)
    updated.update(patch)
    errors = validate_report(updated)
    if errors:
        print("❌ 更新できません。以下のエラーを解消してください：")
        for e in errors:
            print(f"  - {e}")
        return 1

    others = [r for r in reports if r.get("id") != args.id]
    warnings = find_duplicate_warnings(others, new_report=updated)

    diff_preview = {"before": target, "after": updated}
    if not _preview_and_confirm("更新", diff_preview, warnings, args.yes):
        print("キャンセルしました。何も変更していません。")
        return 1

    backup = make_backup(args.path, args.backup_dir)
    if backup:
        print(f"バックアップを作成しました: {backup}")

    data["reports"] = [updated if r.get("id") == args.id else r for r in reports]
    data["updatedAt"] = (parse_date_loose(args.now) if args.now else now_jst()).isoformat()
    save_json(args.path, data)
    print(f"完了：id '{args.id}' を更新しました。")
    return 0


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--path", type=Path, default=DEFAULT_REPORTS_PATH, help="latest_reports.jsonのパス")
    p.add_argument("--archive-path", type=Path, default=DEFAULT_ARCHIVE_PATH, help="latest_reports_archive.jsonのパス")
    p.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR, help="バックアップ格納先")
    p.add_argument("--now", type=str, default=None, help="現在日時を固定する場合のISO日付（主にテスト用）")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="JSON構造・必須項目・重複候補を検証する")
    sub.add_parser("list", help="reportsを新しい順に一覧表示する")
    sub.add_parser("freshness", help="鮮度バケット別に件数・内訳を表示する")
    sub.add_parser("stale", help="61日以上前のreport候補を表示する（削除はしない）")

    p_archive = sub.add_parser("archive", help="61日以上前のreportをarchiveファイルへ移動する")
    p_archive.add_argument("--yes", "-y", action="store_true", help="確認プロンプトをスキップする")

    p_add = sub.add_parser("add", help="新しいreportを追加する")
    p_add.add_argument("--file", type=Path, default=None, help="追加するreport(1件またはreports配列)のJSONファイル")
    p_add.add_argument("--yes", "-y", action="store_true", help="確認プロンプトをスキップする")

    p_update = sub.add_parser("update", help="既存reportを更新する")
    p_update.add_argument("--id", type=str, required=True, help="更新対象のreport id")
    p_update.add_argument("--file", type=Path, default=None, help="更新内容(差分)のJSONファイル")
    p_update.add_argument("--yes", "-y", action="store_true", help="確認プロンプトをスキップする")

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "validate": cmd_validate,
        "list": cmd_list,
        "freshness": cmd_freshness,
        "stale": cmd_stale,
        "archive": cmd_archive,
        "add": cmd_add,
        "update": cmd_update,
    }
    try:
        return handlers[args.command](args)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ エラー: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
