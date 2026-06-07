# TBH 効率ログ 1.0.0

TaskBarHero の周回効率を、画面 OCR と右下ゲージ検出で記録するローカル用ツールです。

## 概要

- Python / PySide6 ベースのデスクトップアプリ
- ゲーム通信や自動操作は行わず、画面 OCR と画像認識のみでローカル計測
- ステージ履歴、GPS、GPH、周回/h、ステージ別ハイスコアを確認可能
- 詳細仕様は `TBH_EFFICIENCY_LOG_SPEC.md` を参照

## 1.0.0 時点の主な内容

- ステージ OCR の誤読補正を搭載
- 所持金減少時の集計除外ロジックを追加
- UI 言語は日本語 / English / 中文に対応
- ゲーム表示言語は TaskBarHero 対応 16 言語に対応
- 可変ゲージ監視とボスアイコン誤検出の軽減ロジックを搭載
- オススメ表示はハイスコア行の周回/h基準に調整

## セットアップ

### 必要環境

- Windows
- Python 3
- Tesseract OCR

Tesseract の標準想定パスは `C:\Program Files\Tesseract-OCR\tesseract.exe` です。

### 起動方法

1. `run.bat` を実行
2. 初回起動時は `.venv` を作成し、`requirements.txt` の依存関係をインストール
3. `範囲・OCR` タブで UI 言語・ゲーム言語を選択
4. ゲーム画面を表示した状態で `自動設定`
5. `OCRテスト`
6. `計測` タブで開始

## 保存されるローカルデータ

以下は実行時に作成・更新されるため、GitHub には含めません。

- `config.json`
- `data/`
- `exports/`
- `logs/`

## 同梱ファイル

- `src/`
- `assets/`
- `requirements.txt`
- `run.bat`
- `check_tesseract.bat`
- `install_tesseract_winget.bat`
- `README.md`
- `TBH_EFFICIENCY_LOG_SPEC.md`
