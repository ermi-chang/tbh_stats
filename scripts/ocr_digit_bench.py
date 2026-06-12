"""所持金OCRの実測比較ハーネス（実験用・アプリ本体は無改変）。

目的:
  現行の tesseract OCR と、OpenCVによる数字テンプレート照合（自己校正）の
  「精度・速度・数字分割成功率」を実測で比較し、本実装に進むか数字で判断する。

考え方（自己教師あり）:
  ゲームHUDの所持金は固定ビットマップフォント＋安定スケール。
  tesseract を“先生”にして、全前処理閾値で同一値に一致した高信頼フレームだけを
  正解ラベル付きサンプルとして集める（誤読でテンプレを汚さない）。
  そのクロップを数字グリフに分割→0〜9のテンプレを自動生成し、テンプレ照合で読み直す。

使い方:
  # 1) ゲームでファーミングしながら（金額が変動して数字の種類が増える状態で）収集
  .venv\\Scripts\\python.exe scripts\\ocr_digit_bench.py collect --seconds 120 --interval 1.0
  # 2) 集めたクロップで実測比較
  .venv\\Scripts\\python.exe scripts\\ocr_digit_bench.py bench

出力物:
  scripts/_ocr_bench/crops/<value>_<ts>.png   収集した高信頼クロップ
  scripts/_ocr_bench/templates/<d>.png        自動生成した0〜9テンプレ（確認用）
  scripts/_ocr_bench/mismatches/...           テンプレ照合がラベルと食い違ったクロップ
  標準出力に精度/速度/分割成功率のレポート
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import time
from collections import Counter, defaultdict
from glob import glob

import numpy as np
from PIL import Image

# src/ をimport可能に
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "src"))

import cv2  # noqa: E402

from tbh_ocr_stats.app import (  # noqa: E402
    apply_anchor_rois,
    capture_monitor,
    crop_roi,
    load_config,
    ocr_money_from_crop,
    parse_money,
    preprocess_simple,
    resolve_tesseract,
)
import pytesseract  # noqa: E402

OUT_DIR = os.path.join(_HERE, "_ocr_bench")
CROP_DIR = os.path.join(OUT_DIR, "crops")
TPL_DIR = os.path.join(OUT_DIR, "templates")
MISS_DIR = os.path.join(OUT_DIR, "mismatches")

# 分割グリフを揃える正規化サイズ（テンプレ照合の比較基準）
GLYPH_W, GLYPH_H = 18, 28
# tesseractの「全閾値一致」とみなす前処理閾値（ocr_money_from_crop と同じ並び）
CONSENSUS_THRESHOLDS = [150, 135, 100, 69]


# ---------------------------------------------------------------- 収集 ---

def _consensus_money(crop: Image.Image, cfg: dict):
    """全前処理閾値で同一値に一致したら高信頼ラベルとして返す。違えば None。"""
    whitelist = "0123456789,."
    config = "--psm 7 --oem 3 -c tessedit_char_whitelist=" + whitelist
    values = []
    for th in CONSENSUS_THRESHOLDS:
        img = preprocess_simple(crop, threshold=th, invert=bool(cfg.get("money_invert", True)))
        money = parse_money(pytesseract.image_to_string(img, config=config).strip())
        if money is None:
            return None
        values.append(money)
    if len(set(values)) == 1:
        return values[0]
    return None


def cmd_collect(args):
    cfg = load_config()
    resolve_tesseract(cfg)
    monitor_index = int(cfg.get("monitor_index", 1))
    os.makedirs(CROP_DIR, exist_ok=True)
    end = time.time() + args.seconds
    saved = skipped = 0
    print(f"[collect] monitor={monitor_index} {args.seconds}s @ {args.interval}s間隔 → {CROP_DIR}")
    while time.time() < end:
        loop_start = time.time()
        img = capture_monitor(monitor_index)
        runtime = apply_anchor_rois(img, cfg)
        roi = runtime.get("money_roi")
        if roi:
            crop = crop_roi(img, tuple(roi))
            value = _consensus_money(crop, cfg)
            if value is not None:
                ts = int(time.time() * 1000)
                crop.save(os.path.join(CROP_DIR, f"{value}_{ts}.png"))
                saved += 1
            else:
                skipped += 1
        else:
            skipped += 1
        print(f"\r  saved={saved} skipped(低信頼/未検出)={skipped}", end="", flush=True)
        sleep = args.interval - (time.time() - loop_start)
        if sleep > 0:
            time.sleep(sleep)
    print(f"\n[collect] 完了: 保存{saved}枚 / スキップ{skipped}。次は `bench` を実行。")


# ------------------------------------------------------ 分割 / テンプレ ---

def _binarize_digits(crop: Image.Image) -> np.ndarray:
    """数字が前景(白=255)になる二値画像を返す。"""
    gray = cv2.cvtColor(np.array(crop.convert("RGB")), cv2.COLOR_RGB2GRAY)
    _, binimg = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    # 前景(白)が多数派なら反転して、細い数字側を白にする
    if np.count_nonzero(binimg) > binimg.size * 0.5:
        binimg = 255 - binimg
    return binimg


def _segment_glyphs(crop: Image.Image):
    """所持金クロップを数字グリフbboxへ分割。(x順のbboxリスト, 二値画像) を返す。

    連結成分のうち「高さがクロップ高の0.30〜0.85倍」のものだけを数字とみなす。
    これで 金額枠の枠線(高さ比≈1.0) と カンマ/小数点(高さ比≈0.13) を同時に除外できる。
    数字が連結した極端に広い成分が出たら分割失敗としてサンプルを捨てる(None)。
    """
    binimg = _binarize_digits(crop)
    h = binimg.shape[0]
    n, _labels, stats, _cent = cv2.connectedComponentsWithStats(binimg, connectivity=8)
    boxes = []
    for i in range(1, n):
        x, y, w, hh, area = stats[i]
        hfrac = hh / h
        if hfrac < 0.30 or hfrac > 0.85:   # 枠線(全高) と カンマ/点(低い) を除外
            continue
        if w < 2 or area < 8:
            continue
        boxes.append((int(x), int(y), int(w), int(hh)))
    if not boxes:
        return None, binimg
    boxes.sort(key=lambda b: b[0])
    widths = sorted(b[2] for b in boxes)
    median_w = widths[len(widths) // 2]
    if any(b[2] > median_w * 1.8 for b in boxes):   # 連結した数字＝分割失敗
        return None, binimg
    return boxes, binimg


def _norm_glyph(binimg: np.ndarray, box) -> np.ndarray:
    x, y, w, h = box
    g = binimg[y:y + h, x:x + w]
    return cv2.resize(g, (GLYPH_W, GLYPH_H), interpolation=cv2.INTER_AREA)


def _labeled_glyphs(crop: Image.Image, label_value: int):
    """クロップを分割し、ラベル桁数と一致したら (数字, 正規化グリフ) のリストを返す。"""
    label_digits = str(label_value)
    boxes, binimg = _segment_glyphs(crop)
    if boxes is None or len(boxes) != len(label_digits):
        return None  # 分割失敗（桁数不一致）
    out = []
    for d_char, box in zip(label_digits, boxes):
        out.append((int(d_char), _norm_glyph(binimg, box)))
    return out


def _build_templates(samples):
    """サンプル(crop, value)群から 0〜9 の平均テンプレを生成。"""
    acc = defaultdict(list)
    seg_ok = seg_fail = 0
    for crop, value in samples:
        glyphs = _labeled_glyphs(crop, value)
        if glyphs is None:
            seg_fail += 1
            continue
        seg_ok += 1
        for d, g in glyphs:
            acc[d].append(g.astype(np.float32))
    templates = {}
    for d, arrs in acc.items():
        templates[d] = np.mean(arrs, axis=0).astype(np.uint8)
    return templates, seg_ok, seg_fail, {d: len(v) for d, v in acc.items()}


def _match_digit(glyph: np.ndarray, templates) -> int:
    """正規化相関で最も近い数字を返す。"""
    best_d, best_s = -1, -2.0
    for d, tpl in templates.items():
        res = cv2.matchTemplate(glyph, tpl, cv2.TM_CCOEFF_NORMED)
        s = float(res[0, 0])
        if s > best_s:
            best_s, best_d = s, d
    return best_d


def _read_by_templates(crop: Image.Image, templates):
    """テンプレ照合でクロップを読む。分割失敗なら None。"""
    boxes, binimg = _segment_glyphs(crop)
    if boxes is None or not boxes:
        return None
    digits = [_match_digit(_norm_glyph(binimg, b), templates) for b in boxes]
    try:
        return int("".join(str(d) for d in digits))
    except ValueError:
        return None


# ---------------------------------------------------------------- bench --

def cmd_bench(args):
    cfg = load_config()
    resolve_tesseract(cfg)
    paths = sorted(glob(os.path.join(CROP_DIR, "*.png")))
    if not paths:
        print(f"[bench] クロップがありません。先に `collect` を実行してください: {CROP_DIR}")
        return
    samples = []
    for p in paths:
        name = os.path.basename(p)
        try:
            value = int(name.split("_")[0])
        except ValueError:
            continue
        samples.append((Image.open(p).convert("RGB"), value))
    random.seed(0)
    random.shuffle(samples)
    split = max(1, int(len(samples) * 0.7))
    train, test = samples[:split], samples[split:]
    if not test:
        test = train  # サンプルが少ない時は全件で評価
    print(f"[bench] 総{len(samples)}枚 (train={len(train)} / test={len(test)})")

    templates, seg_ok, seg_fail, per_digit = _build_templates(train)
    os.makedirs(TPL_DIR, exist_ok=True)
    for d, tpl in sorted(templates.items()):
        cv2.imwrite(os.path.join(TPL_DIR, f"{d}.png"), tpl)
    coverage = sorted(per_digit.items())
    missing = [d for d in range(10) if d not in templates]
    print(f"[bench] 分割成功率(train): {seg_ok}/{seg_ok + seg_fail} "
          f"({100 * seg_ok / max(1, seg_ok + seg_fail):.1f}%)")
    print(f"[bench] テンプレ枚数/桁: {coverage}")
    if missing:
        print(f"[bench][警告] テンプレ未生成の数字: {missing}（収集に出現せず）")

    # ---- 精度: テンプレ照合 vs ラベル ----
    os.makedirs(MISS_DIR, exist_ok=True)
    tpl_correct = tpl_segfail = tpl_wrong = 0
    for crop, value in test:
        pred = _read_by_templates(crop, templates)
        if pred is None:
            tpl_segfail += 1
        elif pred == value:
            tpl_correct += 1
        else:
            tpl_wrong += 1
            crop.save(os.path.join(MISS_DIR, f"label{value}_pred{pred}_{int(time.time()*1000)}.png"))
    n_test = len(test)
    print("\n=== 精度 (test, ラベル=tesseract全閾値一致の高信頼値) ===")
    print(f"  テンプレ照合 正解: {tpl_correct}/{n_test} ({100*tpl_correct/max(1,n_test):.1f}%) "
          f"/ 誤り {tpl_wrong} / 分割失敗 {tpl_segfail}")

    # ---- 速度: 現行tesseractパイプライン vs テンプレ照合 ----
    timed = test[: min(len(test), args.speed_n)]
    t0 = time.perf_counter()
    for crop, _ in timed:
        ocr_money_from_crop(crop, cfg, None)
    tess_ms = 1000 * (time.perf_counter() - t0) / max(1, len(timed))
    t0 = time.perf_counter()
    for crop, _ in timed:
        _read_by_templates(crop, templates)
    tpl_ms = 1000 * (time.perf_counter() - t0) / max(1, len(timed))
    print("\n=== 速度 (1読取あたり, n=%d) ===" % len(timed))
    print(f"  現行tesseract(5前処理): {tess_ms:.2f} ms")
    print(f"  テンプレ照合          : {tpl_ms:.2f} ms  （約 {tess_ms / max(0.001, tpl_ms):.1f}x 高速）")
    print(f"\n出力: テンプレ→{TPL_DIR} / 不一致→{MISS_DIR}")


def main():
    ap = argparse.ArgumentParser(description="所持金OCR 実測比較ハーネス")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="稼働画面から高信頼クロップを収集")
    c.add_argument("--seconds", type=float, default=120.0)
    c.add_argument("--interval", type=float, default=1.0)
    c.set_defaults(func=cmd_collect)
    b = sub.add_parser("bench", help="収集済みクロップで精度/速度を実測")
    b.add_argument("--speed-n", type=int, default=100, help="速度計測に使う枚数")
    b.set_defaults(func=cmd_bench)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
