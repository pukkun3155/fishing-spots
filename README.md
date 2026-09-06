# My 釣りポイント帳

沼津周辺の釣行を記録・分析するための個人用シングルページアプリ（React on CDN、ビルド不要）。

公開URL: https://pukkun3155.github.io/fishing-spots/

## 最新釣果情報の更新方法

`latest_reports.json` はアプリ起動時にfetchされる静的データです。**アプリ本体（`index.html`）を変更せず、このJSONファイルを更新してpushするだけ**で「今おすすめの狙い」「最近の周辺釣果」の内容を更新できます。

情報収集は毎回、人間またはAIが実際にWeb上で確認したものだけを登録します。自動スクレイピング・定期巡回は行いません（`report_sources.json` はチェック先の一覧であり、自動収集対象ではありません）。

### 更新手順チェックリスト

1. `report_sources.json` に登録済みの情報源を確認する
2. 各情報源で最新記事・釣果日を実際に確認する（推測で書かない）
3. 岸釣り（`shore`）／船釣り（`boat`）を判定する（不明なら `unknown`）
4. 原文を転載せず、短く要約する（`catchSummary`）
5. `python3 tools/update_latest_reports.py add --file <新規report.json>` で追加する（対話入力でも可）
6. `python3 tools/update_latest_reports.py validate` で検証する
7. `git diff` で変更内容を確認する
8. `git add` / `git commit` / `git push` する
9. GitHub Pagesの再ビルドを待つ（Actionsタブ、または数十秒〜1分程度）
10. 公開アプリ（今日タブの「今おすすめの狙い」）で反映を確認する

### 便利なコマンド

```bash
python3 tools/update_latest_reports.py validate      # 構造・必須項目・重複候補を検証
python3 tools/update_latest_reports.py list           # 新しい順に一覧表示
python3 tools/update_latest_reports.py freshness      # 鮮度バケット別に集計
python3 tools/update_latest_reports.py stale          # 61日以上前の候補を表示（削除はしない）
python3 tools/update_latest_reports.py archive        # 61日以上前をlatest_reports_archive.jsonへ移動（確認あり）
python3 tools/update_latest_reports.py add            # 対話入力で1件追加
python3 tools/update_latest_reports.py update --id <id> --file <patch.json>   # 既存reportを更新
python3 -m unittest tools/test_update_latest_reports.py -v                    # 自動テスト
```

書き込みを伴う操作（`add`/`update`/`archive`）は、実行前に必ず

1. プレビュー表示
2. 重複候補の警告表示（自動統合はしない）
3. `backups/latest_reports_YYYYMMDD_HHMMSS.json` へのバックアップ作成
4. 確認プロンプト（`--yes`でスキップ可）

を経てから保存します。

### 情報の鮮度について

`reportedAt`（実際の釣果日）を基準に、0〜7日／8〜14日／15〜30日／31〜60日／61日以上で扱いが変わります。61日を超えるデータは削除ではなく `latest_reports_archive.json` への移動を推奨します（`archive` コマンド）。

`updatedAt`（JSONを最後に更新した時刻）とは別の概念です。アプリの「今おすすめの狙い」の鮮度判定には `reportedAt` を使い、「情報更新から何日」の表示には `updatedAt` を使います。

### GitHub Actions

`.github/workflows/validate-reports.yml` が `latest_reports.json` 変更時に `validate` と自動テストのみを実行します。外部釣果サイトへのアクセスは行いません（壊れたJSONを公開しないための最終チェックです）。
