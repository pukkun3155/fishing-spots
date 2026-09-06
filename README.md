# My 釣りポイント帳

沼津周辺の釣行を記録・分析するための個人用シングルページアプリ（React on CDN、ビルド不要）。

公開URL: https://pukkun3155.github.io/fishing-spots/

## 最新釣果情報（`latest_reports.json`）の更新方法

`latest_reports.json` はアプリ起動時にfetchされる静的データです。**アプリ本体（`index.html`）を変更せず、このJSONファイルを更新してpushするだけ**で「今おすすめの狙い」「最近の周辺釣果」の内容を更新できます。

手順：

1. 沼津・内浦・沼津サーフ・静浦周辺の公開釣果情報（釣具店・遊漁船の公式釣果ページ等）を実際に確認する。推測で書かない。転載はせず、短い要約のみ記載する。
2. `reports` 配列に新しい報告を追加する（各項目に `sourceName`／`sourceUrl`／`reportedAt`（日付）／`fishingType`（`shore`/`boat`/`unknown`）を必ず入れる）。
3. `updatedAt` を更新する。
4. `latest_reports.json` をこのリポジトリの `main` ブランチ直下へ push する。
5. GitHub Pagesの再ビルドを待つ（数十秒〜1分程度）。

以上でアプリ側のコードは一切変更不要です。

情報が30日を超えて古い場合、アプリ側で自動的に「古い情報」として扱われ、おすすめ度への寄与も弱くなります。
