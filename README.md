# ⚾ NPB Sabermetrics Data

baseballdata.jp から NPB の成績データを自動収集し、GitHub Pages で公開するリポジトリです。
毎日 **00:30 JST** に自動更新されます。

---

## 🚀 セットアップ手順（10分）

### Step 1 — リポジトリを作成

1. GitHub で [**New repository**](https://github.com/new) をクリック
2. Repository name: `npb-data`（任意）
3. **Public** を選択（GitHub Pages の無料利用に必要）
4. `Initialize with README` は **オフ**
5. **Create repository** をクリック

### Step 2 — ファイルをアップロード

以下のファイルをリポジトリのルートにアップロードします：

```
npb-data/
├── .github/
│   └── workflows/
│       └── scrape.yml    ← GitHub Actions ワークフロー
├── data/
│   └── npb_data.json     ← 初期プレースホルダー
├── npb_scraper.py        ← スクレイパー本体
└── requirements.txt      ← Python依存パッケージ
```

**アップロード方法：**
- GitHub リポジトリページで `Add file` → `Upload files`
- または `git clone` してファイルをコピーしてから `git push`

> **注意**: `.github/workflows/` ディレクトリは隠しフォルダです。  
> ターミナルで `git push` するか、ZIP を解凍して一括アップロードしてください。

### Step 3 — GitHub Pages を有効化

1. リポジトリの **Settings** タブを開く
2. 左メニューの **Pages** をクリック
3. Source: **Deploy from a branch**
4. Branch: **main** / **/ (root)** を選択
5. **Save** をクリック

✅ 数分後、以下の URL でデータが公開されます：
```
https://<あなたのユーザー名>.github.io/npb-data/data/npb_data.json
```

### Step 4 — 初回手動実行

1. リポジトリの **Actions** タブを開く
2. `📊 NPB データ自動更新` ワークフローをクリック
3. **Run workflow** → **Run workflow** で手動実行
4. 約2〜3分で完了。Actions ログで結果を確認

### Step 5 — ダッシュボードに URL を設定

1. NPB Sabermetrics ダッシュボード（Artifact）を開く
2. 右上の **設定** ボタンをクリック
3. 以下の URL を入力して保存：
   ```
   https://<ユーザー名>.github.io/npb-data/data/npb_data.json
   ```
4. **接続テスト** → **保存** で完了 🎉

---

## ⏰ 自動更新スケジュール

| スケジュール | 説明 |
|------------|------|
| 毎日 00:30 JST | GitHub Actions が自動実行 |
| 試合データなし | 変更がなければコミットなし（静か） |
| 手動実行 | Actions タブから任意のタイミングで実行可能 |

---

## 📊 データ構造

```json
{
  "2026": {
    "year": 2026,
    "fetched_at": "2026-06-04T15:30:00+00:00",
    "standings": {
      "central": [
        { "rank": 1, "team": "ヤクルト", "g": 53, "w": 31, "l": 21, "pct": 0.596, ... }
      ],
      "pacific": [ ... ]
    },
    "batters": [
      { "name": "佐藤 輝明", "team": "阪神", "league": "セ", "avg": 0.370, "NOI": 727.07, ... }
    ],
    "pitchers": [
      { "name": "青柳 晃洋", "team": "阪神", "league": "セ", "防御率": 2.68, "WHIP": 1.12, ... }
    ]
  },
  "2025": { ... }
}
```

---

## 🔧 手動実行オプション

Actions タブから手動実行する際、以下のオプションが使用可能：

| オプション | 説明 | 例 |
|-----------|------|----|
| year | 特定年度のみ取得 | `2025` |
| force | データ変化なしでも強制コミット | `true` |

---

## ⚠️ 注意事項

- **スクレイピングのルール**: サーバーに過負荷をかけないよう、リクエスト間に1.5秒の待機を設けています
- **データの権利**: baseballdata.jp のデータは個人利用目的で使用してください
- **GitHub Pages の制限**: リポジトリは Public が必要（Free プランの場合）

---

## 🛠️ ローカルでの実行

```bash
# 依存パッケージをインストール
pip install -r requirements.txt

# 現在のシーズンデータを取得
python3 npb_scraper.py

# 両年度を取得
python3 npb_scraper.py --both

# 特定年度を取得
python3 npb_scraper.py --year 2025
```
