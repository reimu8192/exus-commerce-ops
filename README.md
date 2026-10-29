# NEXUS Commerce Operations — integrated prototype

Claude版 **Restock Dashboard** の FastAPI / SQLite / runner 構造を継承し、NEXUSスタイルのデスクトップ・モバイル画面へ統合した実装です。**実サイトの購入・自動決済・在庫照会アダプタは同梱していません**。開始停止等は実APIとSQLiteに接続していますが、在庫監視の動作確認はデモのみです。

## Windowsで起動

1. ZIPを展開します。
2. **`start-demo.bat`** をダブルクリックします。初回はPython 3.10以上とインターネット（依存ライブラリのインストール用）が必要です。
3. ブラウザで `http://127.0.0.1:8000` を開きます。停止はコンソールウィンドウで Ctrl+C。

`start-local.bat` はデモを切り、実アダプタ未接続の状態を確認できます。デモは `data-demo.db`、ローカル版は `data.db` とデータベースを分離しています。起動オプション `NEXUS_SEED_DEMO=1` は空のDBに6つのサンプルタスクを一度だけ登録します。

## PowerShellから手動起動

```powershell
cd restock-nexus
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DEMO_MODE="1"
$env:NEXUS_SEED_DEMO="1"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

ブラウザ: <http://127.0.0.1:8000>

## 実装済み

- NEXUSスタイルのレスポンシブなGUI：Overview / Tasks / Stores / Profiles / Activity log / Settings
- タスク登録・変更・削除、個別・複数・全件開始停止
- サイト別間隔設定・有効無効と実装アダプタの接続状況表示
- 同時チェックの上限（グローバル4、サイト別1）およびサイト全体の最短チェック間隔
- タスク詳細ドロワー、履歴、検索・フィルタ、選択操作
- プロファイルの登録・更新・削除（カード番号は取り扱わない）
- SQLite永続化、最大10,000件のログ保持、設定JSONの安全なエクスポート
- ライト/ダーク、モバイル、Ctrl+Kコマンドパレット
- 外部JS/CDNなし、同一オリジン書き込み制限、ローカルホストのみ許可
- デモモード、SQLite連動の統合テスト

## 未実装 / 制限

- Amazon、楽天、GEO等の実ストア監視アダプタは**未実装**。デモ時の在庫結果はランダムで、実在庫とは一切関係しません。
- 購入、カート追加、ログイン、支払いは行いません。
- 管理画面のログイン認証、個人情報の保存時暗号化は未実装。住所等はSQLiteに平文保存されます。**LAN/WAN、公開サーバーに出さないでください。**
- 同一オリジン保護は認証の代替になりません。
- ログ集計グラフは最新100件を使う簡易表示です。
- バックエンドは1プロセスで実行してください（`--workers 1`）。複数workerでの共有スケジューラは未対応。

## 監視モジュールの追加

`app/adapters.py` の `ADAPTERS` に async checker を追加します。

```python
async def your_store_check(task):
    # 利用規約やサイトの負荷を尊重した、許可された方法で在庫を取得
    return CheckResult(in_stock=False, detail="在庫なし")

ADAPTERS['geo'] = your_store_check
```

サイト別の **adapter-level** 出力は `CheckResult(in_stock, detail)` に統一します。購入処理や認証情報は含めません。監視間隔と同時実行制御は `runner.py` が担当します。

## 基本テスト

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

**比較対象**：最初に共有したNEXUS単体HTML版はUIデモでしたが、この版の画面はFastAPI/SQLiteの実データに接続されています。
