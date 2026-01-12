# 🚀 実行手順 (How to Run)

## 1. 依存関係のインストール (Install Dependencies)

```bash
pip install -r requirements.txt
```

## 2. 環境変数の設定 (Environment Variables)

`.env`ファイルを作成し、以下の環境変数を設定してください：

```env
CAPTCHA_API_KEY=your_2captcha_api_key_here
```

### `.env`ファイルの作成方法

プロジェクトのルートディレクトリに`.env`ファイルを作成：

```bash
# Windows (PowerShell)
New-Item .env

# Windows (CMD)
type nul > .env

# Linux/Mac
touch .env
```

`.env`ファイルに以下を記述：
```
CAPTCHA_API_KEY=your_actual_api_key
```

## 3. Google Sheets API認証情報の確認

`groovy-electron-478008-k6-38538c9620a5.json`ファイルがプロジェクトルートに存在することを確認してください。

このファイルはGoogle Sheets APIのサービスアカウント認証情報です。

### Googleスプレッドシートの共有設定

1. Googleスプレッドシートを開く
2. 「共有」ボタンをクリック
3. サービスアカウントのメールアドレス（`pokemon-sheet@groovy-electron-478008-k6.iam.gserviceaccount.com`）を追加
4. 「編集者」権限を付与

## 4. スプレッドシートの準備

Googleスプレッドシートを以下の形式で準備してください：

| A列 (Email) | B列 (Password) | C列 (Status) | D列 (Details) | E列 (Timestamp) |
|------------|---------------|-------------|--------------|----------------|
| email1@example.com | password1 | | | |
| email2@example.com | password2 | | | |

- **A列**: メールアドレス（必須）
- **B列**: パスワード（オプション、.envからも読み込み可能）
- **C列**: 状態（自動入力: 成功/失敗）
- **D列**: 具体的な状態（自動入力）
- **E列**: 最終進行時間（自動入力）

## 5. アプリケーションの起動

### 方法1: 直接実行

```bash
python app.py
```

### 方法2: Flaskコマンドで実行

```bash
flask run
```

### 方法3: 開発モードで実行（自動リロード）

```bash
python -m flask run --reload
```

## 6. Webインターフェースにアクセス

ブラウザで以下のURLを開いてください：

```
http://localhost:5000
```

## 7. ボットの使用方法

1. **Google Spreadsheet IDまたはURLを入力**
   - スプレッドシートのURL: `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`
   - または直接IDを入力

2. **ワークシート名を入力**（オプション）
   - 最初のシートを使用する場合は空白のまま

3. **抽選数を設定**（1-5）
   - 処理する抽選の数を指定

4. **最大連続失敗数を設定**（1-20、デフォルト: 5）
   - この回数連続で失敗するとボットが停止

5. **自動再起動設定**
   - 分後に再起動: 指定した分数後に自動再起動
   - 特定の日時に再起動: 指定した日時に自動再起動

6. **「Start Bot」ボタンをクリック**

## トラブルシューティング

### エラー: "CAPTCHA API key is required"
- `.env`ファイルに`CAPTCHA_API_KEY`が設定されているか確認

### エラー: "Cannot access Google Spreadsheet"
- スプレッドシートがサービスアカウントと共有されているか確認
- スプレッドシートIDが正しいか確認

### エラー: "gspread not found"
```bash
pip install gspread==6.1.2
```

### エラー: "ChromeDriver not found"
- `webdriver-manager`が自動的にダウンロードします
- インターネット接続を確認してください

## ログの確認

ログファイルは`logs/`ディレクトリに保存されます：
- `logs/bot_YYYY-MM-DD.log` - 日別のログファイル

## 停止方法

- Webインターフェースの「Stop Bot」ボタンをクリック
- または、ターミナルで`Ctrl+C`を押す
