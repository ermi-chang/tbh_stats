"""ステージ番号("W-S")のテンプレOCR（所持金デジタルテンプレ engine を再利用・tesseract 非依存）。

経緯（実測で確定）:
  当初は別アプリ「青箱お知らせくん」の手書き 7px CHAR_TEMPLATES を移植したが、本体HUDの
  stage_num_roi フォントでは解像度不足で 9→4 等の誤読が出た。一方、本体が所持金で**実フォントから
  自己学習**した digit_ocr.py の 18×28 テンプレ（成熟済み）は、同じHUDフォントのステージ数字を
  高信頼で分類できる（実測: '1'=0.83 / '9'=0.79、左の矢印アイコンは 0.41 で明確に弾ける）。

方針:
  - 所持金エンジン(get_money_ocr_engine)のテンプレで各桁を分類する（= 実質ステージも自己校正済み）。
  - ハイフンはグリフ検出せず、構造（先頭=ワールド1〜3 / 残り=ステージ1〜10）から再構成する。
  - 先頭のアイコン等の非数字は「相関スコアが低い」「高さ比が小さい」で除外する。
  - テンプレ未成熟（所持金で 0〜9 が揃う前）の場合は None を返し、呼び出し側が tesseract に委ねる。

公開 API:
  read_stage_from_crop(crop: PIL.Image, engine=None) -> Optional[str]
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from .digit_ocr import _binarize_digits, _norm_glyph, get_money_ocr_engine

# 数字とみなす連結成分の最小・最大高さ比（クロップ高に対する割合）。
# 先頭アイコン(実測 hfrac≈0.4)やハイフン(≈0.08)を弾き、数字(≈0.6)だけを拾う。
DIGIT_MIN_HFRAC = 0.45
DIGIT_MAX_HFRAC = 0.95
# 数字と確定するための所持金テンプレ相関の下限。
# ステージ番号は低倍率(1x)だと数字が小さく(約10px)、1.5x学習テンプレへ正規化照合すると相関が下がる
# （実測 1x: 実数字"8"=0.54 / カタカナ"を"=0.31 / 矢印アイコン≈0.41）。0.55では実数字まで弾けて stage=None に
# なるため 0.45 に緩和（"を"/矢印は弾けたまま）。誤読は構造チェック(_STAGE_RE: world1-3/stage1-10)で除外。
# 1.25x/1.5x は数字相関が高い(0.78+)ので緩和の影響なし。
STAGE_MATCH_MIN = 0.45
# 秒数(クリア時間)読みは桁が大きめで誤混入を避けたいので従来どおり厳しめに保つ。
DIGITS_MATCH_MIN = 0.55

_STAGE_RE = re.compile(r"^([1-3])-(10|[1-9])$")


def _digit_boxes(binimg: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """二値画像(白=文字)から数字候補の連結成分bboxを x 昇順で返す。

    高さ比は**クロップ高ではなく文字高（最も背の高い成分）基準**で判定する。テロップのように上下に
    余白のあるクロップでも数字を取りこぼさず、ハイフン/カンマ等の低い成分だけを除外できる。
    枠線(クロップ高に迫る成分)は先に除外する。
    """
    H = binimg.shape[0]
    n, _labels, stats, _cent = cv2.connectedComponentsWithStats(binimg, connectivity=8)
    comps: List[Tuple[int, int, int, int]] = []
    for i in range(1, n):
        x, y, w, hh, area = stats[i]
        if w < 2 or area < 8:
            continue
        if hh > H * 0.9:  # 枠線など縦に張る成分は除外
            continue
        comps.append((int(x), int(y), int(w), int(hh)))
    if not comps:
        return []
    ref_h = max(c[3] for c in comps)  # 文字高（数字の高さ）
    boxes = [c for c in comps if c[3] >= 0.55 * ref_h]  # ハイフン/カンマ等の低成分を除外
    boxes.sort(key=lambda b: b[0])
    return boxes


def read_digits_from_crop(crop: Image.Image, engine=None, max_digits: int = 4) -> Optional[int]:
    """所持金テンプレを再利用して、クロップ内の数字列を整数で返す（"(96秒)"→96 等）。

    非数字（括弧・「秒」・スラッシュ等）はスコア閾値で自然に除外される。読めなければ None。
    """
    if crop is None:
        return None
    if engine is None:
        engine = get_money_ocr_engine()
    if not engine.is_complete():
        return None
    try:
        binimg = _binarize_digits(crop)
    except Exception:
        return None
    boxes = _digit_boxes(binimg)
    if not boxes:
        return None
    widths = sorted(b[2] for b in boxes)
    median_w = widths[len(widths) // 2]
    boxes = [b for b in boxes if b[2] <= median_w * 1.8]
    digits: List[int] = []
    for b in boxes:
        d, s = engine.match_glyph(_norm_glyph(binimg, b))
        if d < 0 or s < DIGITS_MATCH_MIN:
            continue
        digits.append(int(d))
    if not digits or len(digits) > max_digits:
        return None
    try:
        return int("".join(str(x) for x in digits))
    except ValueError:
        return None


def read_stage_from_crop(crop: Image.Image, engine=None) -> Optional[str]:
    """ステージ番号クロップを "W-S" に変換。読めない/テンプレ未成熟なら None。

    所持金テンプレで各数字グリフを分類し、ハイフンは構造から再構成する。
    """
    if crop is None:
        return None
    if engine is None:
        engine = get_money_ocr_engine()
    # 0〜9 が揃っていなければ高信頼分類はできない → 呼び出し側で tesseract フォールバック。
    if not engine.is_complete():
        return None
    try:
        binimg = _binarize_digits(crop)
    except Exception:
        return None
    boxes = _digit_boxes(binimg)
    if not boxes:
        return None
    # 連結した数字（極端に広い成分）が混じると分類が崩れるため、中央値の1.8倍超は破棄。
    widths = sorted(b[2] for b in boxes)
    median_w = widths[len(widths) // 2]
    boxes = [b for b in boxes if b[2] <= median_w * 1.8]

    digits: List[int] = []
    for b in boxes:
        d, s = engine.match_glyph(_norm_glyph(binimg, b))
        if d < 0 or s < STAGE_MATCH_MIN:
            continue  # アイコン等の非数字を除外
        digits.append(int(d))

    if not (2 <= len(digits) <= 3):
        return None
    # 構造再構成: 先頭=ワールド(1〜3) / 残り=ステージ(1〜10)。
    world = digits[0]
    sub = int("".join(str(x) for x in digits[1:]))
    stage = f"{world}-{sub}"
    return stage if _STAGE_RE.match(stage) else None
