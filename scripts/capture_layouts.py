"""6配置×窓構成の実機キャプチャ収集（M2.5 レイアウト堅牢化の設計データ用）。

構造: 外側＝6配置（左上/中央上/右上・左下/中央下/右下）を1つずつ設定、
      内側＝その配置のまま窓を開閉操作（インベのみ→＋窓2→全開＋窓3）。
上下の往復を減らすため 上グループ→下グループ の順。各配置で窓2/窓3の内容を割り当て、
倉庫・ステータス・キューブ・ポータルを全体で網羅する。

画面のガイド表示に従って操作してください。スクリプトは各サブステップ中、ゲーム窓(hwnd)を
一定間隔で連続キャプチャし _layout_samples/ に保存する（ファイル名＝配置_窓状態_連番）。
ステージをクリアして「ステージ●●クリア」テロップが出ている瞬間を含められると理想（任意）。

使い方:
  .venv\\Scripts\\python.exe scripts\\capture_layouts.py
オプション環境変数:
  SEC_PER_STEP (各サブステップ秒数, 既定8) / SETUP_PAUSE (配置切替の猶予秒, 既定6)
  INTERVAL (キャプチャ間隔秒, 既定1.0)
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tbh_ocr_stats.window_capture import capture_game_window  # noqa: E402

OUT = ROOT / "_layout_samples"
SEC_PER_STEP = float(os.environ.get("SEC_PER_STEP", "8"))
SETUP_PAUSE = float(os.environ.get("SETUP_PAUSE", "6"))
INTERVAL = float(os.environ.get("INTERVAL", "1.0"))

# (ファイル名キー, 日本語名, グループ, 窓2の内容, 窓3の内容)
CONFIGS = [
    ("leftup", "左上", "上", "倉庫", "キューブ"),
    ("centerup", "中央上", "上", "ステータス", "ポータル"),
    ("rightup", "右上", "上", "倉庫", "ポータル"),
    ("leftdown", "左下", "下", "ステータス", "キューブ"),
    ("centerdown", "中央下", "下", "倉庫", "ポータル"),
    ("rightdown", "右下", "下", "ステータス", "キューブ"),
]


def _capture_phase(cfgkey: str, stepkey: str, label: str, seconds: float, seq_start: int) -> int:
    """seconds 間、INTERVAL ごとにキャプチャして保存。次の連番を返す。"""
    seq = seq_start
    t_end = time.time() + seconds
    while time.time() < t_end:
        remain = t_end - time.time()
        img = capture_game_window()
        if img is None:
            print(f"    [残り{remain:4.1f}s] 取得失敗（ゲーム窓なし）")
        else:
            fname = OUT / f"{cfgkey}_{stepkey}_{seq:03d}.png"
            img.save(fname)
            print(f"    [残り{remain:4.1f}s] 保存 {fname.name} ({img.width}x{img.height})")
            seq += 1
        time.sleep(INTERVAL)
    return seq


def _countdown(msg: str, seconds: float) -> None:
    print(f"\n>>> {msg}")
    end = time.time() + seconds
    while time.time() < end:
        r = end - time.time()
        print(f"    準備中… 残り{r:4.1f}s", end="\r")
        time.sleep(0.5)
    print(" " * 40, end="\r")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for p in OUT.glob("*.png"):
        p.unlink()

    steps_total = len(CONFIGS) * 3
    est = len(CONFIGS) * (SETUP_PAUSE + 3 * SEC_PER_STEP)
    print("=" * 64)
    print(f"レイアウト収集を開始します。全{steps_total}サブステップ / 所要 約{est:.0f}秒")
    print("画面の指示どおりに『配置の設定』→『窓の開閉』を操作してください。")
    print("（ステージをクリアしてテロップが出ている状態を含められると理想・任意）")
    print("=" * 64)
    time.sleep(2.0)

    seq = 0
    cur_group = None
    for cfgkey, jp, group, win2, win3 in CONFIGS:
        if group != cur_group:
            cur_group = group
            print("\n" + "#" * 64)
            print(f"#  【{group}グループ】 ここからゲーム部を「{group}」側にしてください")
            print("#" * 64)
        # 配置設定の猶予（全ウィンドウを閉じてインベのみの状態にしておく）
        _countdown(f"配置を【{jp}】に設定し、窓は『インベントリ(窓1)のみ』にしてください", SETUP_PAUSE)

        # ① インベのみ
        print(f"--- 配置[{jp}] ① 窓1(インベ)のみ ---")
        seq = _capture_phase(cfgkey, "inv", "inv", SEC_PER_STEP, seq)
        # ② ＋窓2
        print(f"--- 配置[{jp}] ② 窓2を『{win2}』で開いてください（インベ＋{win2}）---")
        time.sleep(2.0)
        seq = _capture_phase(cfgkey, "win2", win2, SEC_PER_STEP, seq)
        # ③ 全開＋窓3
        print(f"--- 配置[{jp}] ③ 窓3を『{win3}』も開いて全開（インベ＋{win2}＋{win3}）---")
        time.sleep(2.0)
        seq = _capture_phase(cfgkey, "full", win3, SEC_PER_STEP, seq)

    print("\n" + "=" * 64)
    print(f"完了: {seq}枚保存 -> {OUT}")
    print("このフォルダを解析して、ゲージ＝色／ステージ＝テロップの全画面検出器を設計します。")
    print("=" * 64)


if __name__ == "__main__":
    main()
