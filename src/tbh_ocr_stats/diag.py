"""軽量診断ロガー（M2.5 バグ④/⑤ Phase A 用）。

ステージ秒リセットが実機で効かない原因を「推測」ではなく「実測」で確証するための一時計測。
env `TBH_DIAG=1` のときだけ有効になり、毎ゲージpoll/毎OCR tickの検出器状態と、ステージ秒の
起点更新(reset)/区切り(finish)イベントを JSONL に追記する。無効時は全関数が即returnするので
本番性能に影響しない（呼び出し側でのガード不要）。

出力:
  _play_samples/diag/diag_<TAG>_<run_id>.jsonl   … 1行1イベント（ts で gauge/tick を時系列突合）
  _play_samples/diag/gauge/g_<ts>.png            … ゲージcropの実ピクセル（TBH_DIAG_FRAMES=1のみ）

環境変数:
  TBH_DIAG        … 非空で有効化
  TBH_DIAG_TAG    … ファイル名タグ（既定: TAG or "session"）
  TBH_DIAG_FRAMES … 非空でゲージcropのPNGも保存

解析後に _play_samples/ ごと破棄する（コミット対象外）。
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

_ENABLED = bool(os.environ.get("TBH_DIAG"))
_FRAMES = bool(os.environ.get("TBH_DIAG_FRAMES"))
_TAG = os.environ.get("TBH_DIAG_TAG") or os.environ.get("TAG") or "session"
_RUN_ID = time.strftime("%Y%m%d_%H%M%S")

_lock = threading.Lock()
_dir: Optional[Path] = None
_log_path: Optional[Path] = None


def enabled() -> bool:
    return _ENABLED


def _ensure() -> Optional[Path]:
    global _dir, _log_path
    if _dir is None:
        try:
            base = Path(__file__).resolve().parents[2] / "_play_samples" / "diag"
            base.mkdir(parents=True, exist_ok=True)
            _dir = base
            _log_path = base / f"diag_{_TAG}_{_RUN_ID}.jsonl"
        except Exception:
            return None
    return _dir


def log(src: str, **fields: Any) -> None:
    """1行を JSONL に追記。env無効なら即return。スレッドセーフ。"""
    if not _ENABLED:
        return
    if _ensure() is None or _log_path is None:
        return
    try:
        rec = {"t": round(time.time(), 3), "src": src}
        for k, v in fields.items():
            rec[k] = round(v, 4) if isinstance(v, float) else v
        line = json.dumps(rec, ensure_ascii=False, default=str)
        with _lock:
            with open(_log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        pass


def save_gauge_crop(ts: float, crop: Any) -> None:
    """ゲージcrop(PIL.Image)のPNGを保存（TBH_DIAG_FRAMES=1のときのみ）。"""
    if not (_ENABLED and _FRAMES):
        return
    d = _ensure()
    if d is None:
        return
    try:
        gdir = d / "gauge"
        gdir.mkdir(parents=True, exist_ok=True)
        crop.save(str(gdir / f"g_{ts:.3f}.png"))
    except Exception:
        pass


def save_gauge_context(ts: float, img: Any, roi: Any) -> None:
    """ゲージROI周辺の文脈画像を、ROI枠(赤)を描いて保存（TBH_DIAG_FRAMES=1のときのみ）。

    ゲージROIが実ゲージからズレているかを目視確認・再校正するための診断。ROIを中心に左右±広めに
    切り出し、現ROIの位置を赤枠で重ねる。これで「赤枠が実ゲージにどれだけズレているか」が一目で分かる。
    """
    if not (_ENABLED and _FRAMES):
        return
    d = _ensure()
    if d is None:
        return
    try:
        from PIL import ImageDraw  # 遅延import（無効時は触れない）
        x, y, w, h = (int(v) for v in roi)
        mx0, mx1 = 220, 260   # ROI左右の余白（実ゲージが右寄り/左寄りどちらでも入るよう広め）
        my = 90               # 上下の余白
        cx0, cy0 = max(0, x - mx0), max(0, y - my)
        cx1, cy1 = min(img.width, x + w + mx1), min(img.height, y + h + my)
        ctx = img.crop((cx0, cy0, cx1, cy1)).convert("RGB")
        draw = ImageDraw.Draw(ctx)
        # 現ROIの位置（文脈crop内の相対座標）を赤枠で描く
        draw.rectangle([x - cx0, y - cy0, x - cx0 + w, y - cy0 + h], outline=(255, 0, 0), width=2)
        gdir = d / "context"
        gdir.mkdir(parents=True, exist_ok=True)
        ctx.save(str(gdir / f"ctx_{ts:.3f}.png"))
    except Exception:
        pass
