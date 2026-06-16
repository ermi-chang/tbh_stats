"""所持金の数字テンプレOCRエンジン（自己校正・本体ホットパス用）。

考え方（実験 scripts/ocr_digit_bench.py で実証済み）:
  ゲームHUDの所持金は固定ビットマップフォント＋安定スケール。tesseract を“先生”に、
  全前処理閾値で同一値に一致した高信頼フレームだけを正解ラベルとして集め、
  0〜9 の数字グリフ・テンプレを自動生成する。以後はテンプレ照合で読む（tesseractの
  5前処理 ≈490ms/読 に対し ≈4ms と約127倍高速・同精度）。

安全方針:
  - テンプレは tesseract の「全閾値一致(consensus)」読みからのみ学習（誤読で汚さない）。
  - 高速パスは **0〜9すべてが成熟（各≥MIN_SAMPLES）した時だけ** 使う。
    未学習の数字を別の数字へ高信頼で誤マッチする事故を根絶する。
  - 各グリフの相関が MATCH_MIN 未満なら読取を破棄して tesseract にフォールバック。
  - 永続化は data/money_digit_templates.npz。QThreadPool から並行アクセスされるため Lock 保護。
"""
from __future__ import annotations

import threading
from typing import Dict, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from .runtime_env import DATA_DIR

# 分割グリフを揃える正規化サイズ（テンプレ照合の比較基準）。bench と同値。
GLYPH_W, GLYPH_H = 18, 28
# 1桁テンプレが「成熟」とみなされる最小累積サンプル数。
MIN_SAMPLES_PER_DIGIT = 12
# グリフ相関(TM_CCOEFF_NORMED)の最低許容値。これ未満は信頼せずフォールバック。
MATCH_MIN = 0.45
# 高速パス中に tesseract 検証＆再学習を挟む間隔（N回に1回）。ドリフト自己修復用。
VERIFY_EVERY = 10

_TEMPLATE_PATH = DATA_DIR / "money_digit_templates.npz"


# ----------------------------------------------------- 分割 / 正規化 ---

def _binarize_digits(crop: Image.Image) -> np.ndarray:
    """数字が前景(白=255)になる二値画像を返す。"""
    gray = cv2.cvtColor(np.array(crop.convert("RGB")), cv2.COLOR_RGB2GRAY)
    _, binimg = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    # 前景(白)が多数派なら反転して、細い数字側を白にする。
    if np.count_nonzero(binimg) > binimg.size * 0.5:
        binimg = 255 - binimg
    return binimg


def _segment_glyphs(crop: Image.Image):
    """所持金クロップを数字グリフbboxへ分割。(x順bboxリスト, 二値画像) または (None, 二値)。

    高さがクロップ高の0.30〜0.85倍の連結成分のみを数字とみなし、金額枠の枠線(高さ比≈1.0)と
    カンマ/小数点(高さ比≈0.13)を同時に除外する。連結した極端に広い成分が出たら分割失敗(None)。
    """
    binimg = _binarize_digits(crop)
    h = binimg.shape[0]
    n, _labels, stats, _cent = cv2.connectedComponentsWithStats(binimg, connectivity=8)
    boxes = []
    for i in range(1, n):
        x, y, w, hh, area = stats[i]
        hfrac = hh / h
        if hfrac < 0.30 or hfrac > 0.85:
            continue
        if w < 2 or area < 8:
            continue
        boxes.append((int(x), int(y), int(w), int(hh)))
    if not boxes:
        return None, binimg
    boxes.sort(key=lambda b: b[0])
    widths = sorted(b[2] for b in boxes)
    median_w = widths[len(widths) // 2]
    if any(b[2] > median_w * 1.8 for b in boxes):  # 連結した数字＝分割失敗
        return None, binimg
    return boxes, binimg


def _norm_glyph(binimg: np.ndarray, box) -> np.ndarray:
    x, y, w, h = box
    g = binimg[y:y + h, x:x + w]
    return cv2.resize(g, (GLYPH_W, GLYPH_H), interpolation=cv2.INTER_AREA)


# ----------------------------------------------------------- エンジン ---

class DigitTemplateOCR:
    """0〜9 の平均グリフ・テンプレを蓄積し、テンプレ照合で所持金を読むエンジン。"""

    def __init__(self, path=_TEMPLATE_PATH):
        self.path = path
        self._lock = threading.Lock()
        # 数字 -> 累積和(float64, GLYPH_H×GLYPH_W) と サンプル数。平均はこの場で算出。
        self._sums: Dict[int, np.ndarray] = {}
        self._counts: Dict[int, int] = {}
        self._templates: Dict[int, np.ndarray] = {}  # キャッシュ済み平均テンプレ(uint8)
        self._dirty_since_save = 0
        self._verify_counter = 0
        self._load()

    # ---- 永続化 ----
    def _load(self) -> None:
        try:
            if not self.path.exists():
                return
            data = np.load(self.path, allow_pickle=False)
            for d in range(10):
                sk, ck = f"sum_{d}", f"cnt_{d}"
                if sk in data and ck in data:
                    cnt = int(data[ck])
                    if cnt > 0:
                        self._sums[d] = data[sk].astype(np.float64)
                        self._counts[d] = cnt
            self._rebuild_templates()
        except Exception:
            # テンプレ破損時は学習し直せばよいだけなので握りつぶす。
            self._sums.clear()
            self._counts.clear()
            self._templates.clear()

    def _save_locked(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            arrays = {}
            for d in range(10):
                if d in self._sums:
                    arrays[f"sum_{d}"] = self._sums[d]
                    arrays[f"cnt_{d}"] = np.int64(self._counts[d])
            np.savez(self.path, **arrays)
            self._dirty_since_save = 0
        except Exception:
            pass

    def _rebuild_templates(self) -> None:
        self._templates = {
            d: (self._sums[d] / self._counts[d]).astype(np.uint8)
            for d in self._sums
        }

    # ---- 状態 ----
    def is_complete(self) -> bool:
        """0〜9 すべてが成熟(各≥MIN_SAMPLES)していれば高速パス使用可。"""
        return all(self._counts.get(d, 0) >= MIN_SAMPLES_PER_DIGIT for d in range(10))

    def coverage(self) -> Dict[int, int]:
        return dict(self._counts)

    def tick_should_verify(self) -> bool:
        """高速パス中に tesseract 検証を挟むべきタイミングか（N回に1回 True）。"""
        with self._lock:
            self._verify_counter = (self._verify_counter + 1) % VERIFY_EVERY
            return self._verify_counter == 0

    # ---- 学習 ----
    def learn(self, crop: Image.Image, value: int) -> bool:
        """高信頼ラベル value のクロップからテンプレを更新。分割が桁数と一致した時のみ採用。"""
        if value is None or value < 0:
            return False
        digits = str(int(value))
        boxes, binimg = _segment_glyphs(crop)
        if boxes is None or len(boxes) != len(digits):
            return False
        with self._lock:
            for d_char, box in zip(digits, boxes):
                d = int(d_char)
                g = _norm_glyph(binimg, box).astype(np.float64)
                if d in self._sums:
                    self._sums[d] += g
                    self._counts[d] += 1
                else:
                    self._sums[d] = g
                    self._counts[d] = 1
            self._rebuild_templates()
            self._dirty_since_save += 1
            if self._dirty_since_save >= 20:
                self._save_locked()
        return True

    def flush(self) -> None:
        with self._lock:
            self._save_locked()

    # ---- 照合 ----
    def _match_digit(self, glyph: np.ndarray) -> Tuple[int, float]:
        best_d, best_s = -1, -2.0
        for d, tpl in self._templates.items():
            s = float(cv2.matchTemplate(glyph, tpl, cv2.TM_CCOEFF_NORMED)[0, 0])
            if s > best_s:
                best_s, best_d = s, d
        return best_d, best_s

    def match_glyph(self, glyph: np.ndarray) -> Tuple[int, float]:
        """正規化済み(GLYPH_H×GLYPH_W)グリフを 0〜9 テンプレと照合し (数字, 相関) を返す。

        所持金以外（ステージ番号など同一HUDフォント）の桁分類に再利用するための公開API。
        テンプレ未生成なら (-1, -2.0)。学習との競合を避けるためロック保護する。
        """
        with self._lock:
            if not self._templates:
                return -1, -2.0
            return self._match_digit(glyph)

    def read(self, crop: Image.Image) -> Tuple[Optional[int], float]:
        """テンプレ照合で所持金を読む。(値, 最小グリフ相関) を返す。

        高速パスとして信頼できない場合は (None, score)。呼び出し側は tesseract にフォールバックする。
        全数字が成熟していない／分割失敗／いずれかのグリフ相関が MATCH_MIN 未満、のいずれかで None。
        """
        with self._lock:
            if not self.is_complete():
                return None, 0.0
            templates_ready = bool(self._templates)
        if not templates_ready:
            return None, 0.0
        boxes, binimg = _segment_glyphs(crop)
        if boxes is None or not boxes:
            return None, 0.0
        digits = []
        min_score = 2.0
        for b in boxes:
            d, s = self._match_digit(_norm_glyph(binimg, b))
            if s < MATCH_MIN:
                return None, s
            digits.append(d)
            min_score = min(min_score, s)
        try:
            return int("".join(str(d) for d in digits)), min_score
        except ValueError:
            return None, min_score


# ----------------------------------------------- モジュール・シングルトン ---

_engine: Optional[DigitTemplateOCR] = None
_engine_lock = threading.Lock()


def get_money_ocr_engine() -> DigitTemplateOCR:
    """プロセス内で共有する所持金テンプレOCRエンジンを返す（遅延生成）。"""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = DigitTemplateOCR()
    return _engine
