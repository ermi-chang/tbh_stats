"""プレイ中（周回中＋クリア瞬間）の連続キャプチャ収集（M2.5 ゲージ/クリアエフェクト解析用）。

普段の配置のまま、TBHを**実際にプレイ（ステージ周回）させながら**実行する。
高頻度でゲーム窓を連続キャプチャし、_play_samples/ に保存する。
解析目的:
  - 進行ゲージの位置・見た目（紫が溜まる→青到達→リセット）を特定する。
  - クリア瞬間の全画面エフェクトが検出可能か（フレーム全体の急変）を確認する。
  - 常時表示の青ポータル(次ステージ宝石)など、ゲーム部の永続アンカー候補を確認する。

ポイント: 実行中に**最低2〜3回ステージをクリア**させてください（周回中とクリア瞬間の両方を含めるため）。
配置は普段使うものでOK（1配置で十分。複数でも可）。

使い方:
  .venv\\Scripts\\python.exe scripts\\capture_play.py
オプション環境変数:
  SECONDS (収集秒数, 既定90) / INTERVAL (間隔秒, 既定0.4)
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tbh_ocr_stats.window_capture import capture_game_window  # noqa: E402

TAG = os.environ.get("TAG", "play")
OUT = ROOT / "_play_samples" / TAG
SECONDS = float(os.environ.get("SECONDS", "200"))
INTERVAL = float(os.environ.get("INTERVAL", "0.4"))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for p in OUT.glob("*.png"):
        p.unlink()
    print("=" * 60)
    print(f"プレイ中キャプチャ開始 [TAG={TAG}]：約{SECONDS:.0f}秒 / {INTERVAL:.1f}秒間隔")
    print(f"保存先: {OUT}")
    if TAG == "fail":
        print("普段の配置のまま、この間に**ステージ失敗を最低1回**起こしてください。")
    else:
        print("普段の配置のまま、この間に**ステージクリアを最低2〜3回**起こしてください。")
    print("=" * 60)
    time.sleep(2.0)

    t0 = time.time()
    idx = 0
    saved = 0
    while time.time() - t0 < SECONDS:
        elapsed = time.time() - t0
        img = capture_game_window()
        if img is None:
            print(f"  [{elapsed:5.1f}s] 取得失敗（ゲーム窓なし）")
        else:
            img.save(OUT / f"play_{idx:04d}_{elapsed:06.1f}s.png")
            saved += 1
            if idx % 5 == 0:
                print(f"  [{elapsed:5.1f}s] {saved}枚 ({img.width}x{img.height})")
        idx += 1
        time.sleep(INTERVAL)

    print("\n" + "=" * 60)
    print(f"完了: {saved}枚保存 -> {OUT}")
    print("このフォルダを解析して、ゲージ位置とクリアエフェクト検出可否を確認します。")
    print("=" * 60)


if __name__ == "__main__":
    main()
