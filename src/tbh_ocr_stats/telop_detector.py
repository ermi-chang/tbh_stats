"""ゲーム部（テロップ/ゲージ/ステージ）の全画面アンカー検出（M2.5 レイアウト堅牢化の中核）。

実機データで確定した設計：
  クリア/失敗テロップは先頭が必ず「ステージ」で**常時表示**・配置非依存・テンプレ照合 score≈1.0。これを
  ゲーム部全体のアンカーにする。ゲーム部内の相対位置は固定なので、アンカーからの固定オフセット(×scale)で
  ゲージROI・ステージ番号・秒数・種別判定の各領域が一意に決まる。パネルとゲーム部の相対位置(6配置×窓構成)
  に一切依存しない。

アンカー（「ステージ」）の全画面探索は重いのでセッション開始(プローブ)時に1回だけ行い位置を凍結する。
以後の毎tickは凍結アンカー周辺の小領域だけを読むので軽い。

テンプレ素材: assets/telop_steji.png / telop_clear.png / telop_fail.png（実機キャプチャから生成・同梱）。

公開 API:
  locate_steji_anchor(img) -> Optional[(x,y,w,h,score,scale)]   # 全画面・プローブ時
  steji_score_at(img, anchor) -> float                          # 凍結位置の再確認（layout変化検知）
  gauge_roi_from_anchor(anchor, scale, img_h) -> (x,y,w,h)   # 配置(上/下)でdyミラー
  read_telop_at(img, anchor, scale) -> TelopRead(kind, stage, seconds, raw)
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from .runtime_env import BUNDLED_ASSET_DIR
from .stage_ocr_templates import read_stage_from_crop, read_digits_from_crop

# ---- テンプレ（グレースケール）読み込み ----
def _load_gray(name: str) -> Optional[np.ndarray]:
    p = BUNDLED_ASSET_DIR / name
    if not p.exists():
        return None
    img = cv2.imread(str(p))
    return None if img is None else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

_STEJI = _load_gray("telop_steji.png")    # 「ステージ」
_CLEAR = _load_gray("telop_clear.png")    # 「をクリアしました」
_FAIL = _load_gray("telop_fail.png")      # 「失敗しました」

# 多スケール探索の倍率。ゲーム倍率に追従する。
# テロップ素材(telop_*.png)は ゲーム倍率 TELOP_TEMPLATE_GAME_SCALE(=1.5x) で撮影。画面上のテロップは
# (現ゲーム倍率 / 1.5) 倍で写るので、対応倍率(1.0/1.25/1.5x; 2x/3xは現行版で廃止)の比を中心に多スケール照合する。
#   1.0x → 0.667 / 1.25x → 0.833 / 1.5x → 1.000
# 旧実装は固定 [0.7..1.3] で下限0.7のため 1x(0.667) を取りこぼし、テロップ未検出→ゲージROIが出ず
# クリア未記録・ステージ秒遅延になっていた。各倍率の前後にマージンを持たせる。
TELOP_TEMPLATE_GAME_SCALE = 1.5
_SUPPORTED_GAME_SCALES = [1.0, 1.25, 1.5]


def _telop_scale_candidates() -> List[float]:
    base = sorted({gs / TELOP_TEMPLATE_GAME_SCALE for gs in _SUPPORTED_GAME_SCALES})
    out: List[float] = []
    for v in base:
        out.extend([round(v * 0.95, 3), round(v, 3), round(v * 1.05, 3)])
    return sorted({x for x in out if 0.5 <= x <= 1.6})


_SCALES = _telop_scale_candidates()
# 「ステージ」検出の最低スコア。
STEJI_MIN_SCORE = 0.62
# 種別判定の最低スコア。
TYPE_MIN_SCORE = 0.70

# アンカー(「ステージ」左上)基準・scale=1.0 でのゲージROIオフセット。
# ゲーム部は配置で上下完全ミラー（上配置=帯がテロップの下 / 下配置=帯がテロップの上）。
# dx は上下で共通(+396)、dy のみ反転する。実測キャリブレーション:
#   上配置(telopが画面下半分): dy=+176（上play 424枚で purple継続→blue到達を確認）
#   下配置(telopが画面上半分): dy=-140（下layout 全枚数で purple一致＝上のリセット後purpleと同挙動）
# ※ dx=+184 には別要素(クリア/ポータル表示・常時blue)があり進行ゲージではない。混同しないこと。
GAUGE_DX, GAUGE_W, GAUGE_H = 396, 86, 16
GAUGE_DY_UP = 176
GAUGE_DY_DOWN = -140
# ステージ番号は「ステージ 」直後（右隣）。アンカー右端からの探索幅(文字高さ基準)。
STAGE_GAP_K = 0.15   # 「ステージ」と番号の隙間(高さ比)
STAGE_W_K = 5.2      # 番号領域の幅(高さ比, "X-YZ"を余裕で覆う)


@dataclass
class TelopRead:
    kind: Optional[str]      # "clear" / "fail" / None(種別不明)
    stage: Optional[str]     # "W-S"
    seconds: Optional[int]   # クリア秒数（clearのみ）
    raw: str = ""


def _match_multi(gray: np.ndarray, tpl: Optional[np.ndarray]) -> Tuple[float, Optional[Tuple[int, int, int, int]], float]:
    """多スケールテンプレ照合。(best_score, (x,y,w,h), scale) を返す。"""
    if tpl is None:
        return -1.0, None, 1.0
    th0, tw0 = tpl.shape
    best = (-1.0, None, 1.0)
    for sc in _SCALES:
        tw, th = int(tw0 * sc), int(th0 * sc)
        if tw < 8 or th < 6 or tw >= gray.shape[1] or th >= gray.shape[0]:
            continue
        t = cv2.resize(tpl, (tw, th), interpolation=cv2.INTER_AREA if sc < 1 else cv2.INTER_CUBIC)
        res = cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED)
        _mn, mx, _ml, ml = cv2.minMaxLoc(res)
        if mx > best[0]:
            best = (float(mx), (int(ml[0]), int(ml[1]), tw, th), float(sc))
    return best


def _to_gray(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)


def locate_steji_anchor(img: Image.Image) -> Optional[Tuple[int, int, int, int, float, float]]:
    """ゲーム窓全体から「ステージ」を多スケール探索（プローブ時）。(x,y,w,h,score,scale) or None。"""
    if _STEJI is None:
        return None
    score, loc, scale = _match_multi(_to_gray(img), _STEJI)
    if loc is None or score < STEJI_MIN_SCORE:
        return None
    x, y, w, h = loc
    return (x, y, w, h, score, scale)


def steji_score_at(img: Image.Image, anchor: Tuple[int, int, int, int]) -> float:
    """凍結アンカー位置で「ステージ」がまだ一致するかのスコア（layout変化検知用）。"""
    if _STEJI is None:
        return -1.0
    x, y, w, h = anchor[:4]
    gray = _to_gray(img)
    tpl = cv2.resize(_STEJI, (max(8, w), max(6, h)))
    pad = max(6, h // 2)
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(gray.shape[1], x + w + pad), min(gray.shape[0], y + h + pad)
    region = gray[y0:y1, x0:x1]
    if region.shape[0] < tpl.shape[0] or region.shape[1] < tpl.shape[1]:
        return -1.0
    return float(cv2.matchTemplate(region, tpl, cv2.TM_CCOEFF_NORMED).max())


# ----- アンカー・キャッシュ（2ワーカーで共有・毎tick全画面探索を避ける）-----
_cache_lock = threading.Lock()
_cached_anchor: Optional[Tuple[int, int, int, int, float]] = None  # (x,y,w,h,scale)


def get_telop_anchor(img: Image.Image) -> Optional[Tuple[int, int, int, int, float]]:
    """テロップアンカー(x,y,w,h,scale)を返す。直近位置が安価な再確認で有効ならそれを使い、
    無効/未取得のときだけ全画面探索する（layout変化に自動追従）。スレッド共有。"""
    global _cached_anchor
    with _cache_lock:
        cached = _cached_anchor
    if cached is not None and steji_score_at(img, cached[:4]) >= STEJI_MIN_SCORE:
        return cached
    res = locate_steji_anchor(img)
    new = (res[0], res[1], res[2], res[3], res[5]) if res else None
    with _cache_lock:
        _cached_anchor = new
    return new


def gauge_roi_from_anchor(anchor: Tuple[int, int, int, int], scale: float, img_h: Optional[int] = None) -> Tuple[int, int, int, int]:
    """「ステージ」アンカーからゲージROIを算出（既存 detect_gauge_state にそのまま渡せる窓相対ROI）。

    配置(上/下)で帯とテロップの上下関係がミラーするため、telop_y がゲーム窓の上半分にあれば「下配置」
    (帯はテロップの上=dy負)、下半分なら「上配置」(帯はテロップの下=dy正)として dy を選ぶ。img_h 未指定時は
    後方互換で上配置扱い。
    """
    x, y = anchor[0], anchor[1]
    sc = float(scale or 1.0)
    is_down = img_h is not None and y < img_h * 0.5
    dy = GAUGE_DY_DOWN if is_down else GAUGE_DY_UP
    return (int(x + GAUGE_DX * sc), int(y + dy * sc), int(GAUGE_W * sc), int(GAUGE_H * sc))


def _crop(img: Image.Image, x0: int, y0: int, x1: int, y1: int) -> Image.Image:
    x0 = max(0, min(x0, img.width - 1)); x1 = max(x0 + 1, min(x1, img.width))
    y0 = max(0, min(y0, img.height - 1)); y1 = max(y0 + 1, min(y1, img.height))
    return img.crop((x0, y0, x1, y1))


def read_telop_at(img: Image.Image, anchor: Tuple[int, int, int, int], scale: float) -> TelopRead:
    """凍結アンカー周辺の小領域だけでテロップを読む（毎tick・軽量）。種別/ステージ/秒数を返す。"""
    x, y, w, h = anchor[:4]
    sc = float(scale or 1.0)
    gray = _to_gray(img)

    # --- 種別判定: アンカー右側の帯で clear/fail テンプレ照合 ---
    band_y0 = max(0, y - h)
    band_y1 = min(gray.shape[0], y + 2 * h)
    band_x0 = x
    band_x1 = min(gray.shape[1], x + int(34 * h))  # テロップ全長を十分覆う
    band = gray[band_y0:band_y1, band_x0:band_x1]
    def band_score(tpl):
        if tpl is None or band.size == 0:
            return -1.0
        th0, tw0 = tpl.shape
        best = -1.0
        for s in (sc * 0.92, sc, sc * 1.08):
            tw, th = int(tw0 * s), int(th0 * s)
            if tw < 8 or th < 6 or tw >= band.shape[1] or th >= band.shape[0]:
                continue
            t = cv2.resize(tpl, (tw, th))
            best = max(best, float(cv2.matchTemplate(band, t, cv2.TM_CCOEFF_NORMED).max()))
        return best
    # clear/fail を位置つきで照合（位置でステージ番号/秒数領域を厳密に切り出す）。
    cs, cloc, _ = _match_multi(band, _CLEAR)
    fs, floc, _ = _match_multi(band, _FAIL)
    kind: Optional[str] = None
    if max(cs, fs) >= TYPE_MIN_SCORE:
        kind = "clear" if cs >= fs else "fail"

    pad = int(h * 0.15)
    stage: Optional[str] = None
    seconds: Optional[int] = None
    if kind == "clear" and cloc is not None:
        # ステージ番号 = 「ステージ」右端 〜 「をクリアしました」左端（検証済み2アンカー・カタカナ除外）。
        clear_abs_x = band_x0 + cloc[0]
        stage = read_stage_from_crop(_crop(img, x + w, y - pad, clear_abs_x, y + h + pad))
        # 秒数 = 「をクリアしました」右端 の "(Z秒)"。
        sec_x = clear_abs_x + cloc[2]
        seconds = read_digits_from_crop(_crop(img, sec_x, y - pad, sec_x + int(h * 3.6), y + h + pad))
    elif kind == "fail":
        # 失敗時のステージは "ステージ X-Y の挑戦に…" の "の" 手前。失敗はクリアとして記録しないため
        # 番号は best-effort（狭めの固定幅で読めれば読む）。
        stage = read_stage_from_crop(_crop(img, x + w, y - pad, x + w + int(h * 3.0), y + h + pad))

    raw = f"[telop kind={kind} cs={cs:.2f} fs={fs:.2f} stage={stage} sec={seconds}]"
    return TelopRead(kind, stage, seconds, raw)
