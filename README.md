# My 釣りポイント帳

沼津周辺の釣行を記録・分析するための個人用シングルページアプリ（React on CDN、ビルド不要）。

公開URL: https://pukkun3155.github.io/fishing-spots/

## 天気・風・波の自動取得について

「今日の条件」の天気・気温・風向・風速・波は、[Open-Meteo](https://open-meteo.com/)（Forecast API / Marine Weather API）から手動ボタン操作で取得できます。APIキーは使用していません。取得はボタン押下時のみで、ページ読み込み時の自動取得は行いません。

取得した値は空欄のみを自動的に埋め、既に入力済みの値を無断で上書きすることはありません（異なる場合は比較表示のうえ、個別に「自動値を反映」を選んだ場合のみ反映されます）。潮回り・潮の動き・濁りは自動取得の対象外で、引き続き手入力です。

Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0)

## 潮汐（満潮・干潮）の自動取得について

登録済みポイントに気象庁の観測地点（駿河湾・伊豆エリアの公式候補のみ、GPSからの自動推定はなし）を設定すると、釣行前ブリーフィングから[気象庁 潮位表](https://www.data.jma.go.jp/kaiyou/db/tide/suisan/index.php)のテキストデータ版（公共データ利用規約 第1.0版）を取得できます。天文潮位（予測値）であり、実測潮位とは異なります。

大潮・中潮などの潮回りは気象庁のデータに明示されないため自動化せず、引き続き手入力です。満潮・干潮の時刻のみから機械的に「上げ／下げ」を判定して表示しますが、実際の潮流・海況を保証するものではありません。取得は手動ボタン操作のみで、同一地点・同一日は24時間キャッシュします。手入力済みの値は無断で上書きしません。

出典：気象庁ホームページ（潮汐データ：気象庁 天文潮位）

## 候補日時の比較について

「🎣 今日」タブの「📅 候補日時を比較」から、最大3件の釣行候補（日付・時刻・釣行時間・ポイント・狙い魚）を並べて比較できます。風・波・雨・潮汐・最近の岸釣り情報・本人実績・タックル適合をもとに「釣行しやすさ」を◎○△⚠？で判断材料として示すもので、「釣れる確率」や釣果を予測するものではありません。風速7m/s以上・波高1.0m以上・突風10m/s以上・雷の可能性のいずれかがある候補は、他条件に関わらず「⚠ 条件注意」として扱います（候補は削除しません）。

候補を「✅ この候補を採用」すると、今日の条件（日付・開始時刻・釣行時間）に反映されます。天気・波・潮の動きなどの予報値は、「予報値も反映する」を明示的に選んだ場合のみ、Open-Meteo/気象庁と同じ手入力優先ルールで反映されます（手入力済みの値を無断上書きしません）。Open-Meteoの予報取得可能期間（Weather最大16日・Marine最大8日）の都合上、実質的な比較対象は概ね8日先までです。

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
