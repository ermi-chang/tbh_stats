from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import mss
import numpy as np
import pytesseract
from PIL import Image


DURATION_MIN_SEC = 3
DURATION_MAX_SEC = 900


@dataclass
class MoneyOCRResult:
    money: Optional[int]
    raw_text: str


@dataclass
class StageOCRResult:
    stage: Optional[str]
    duration_sec: Optional[int]
    raw_text: str


def capture_monitor(monitor_index: int) -> Image.Image:
    with mss.mss() as sct:
        monitors = sct.monitors
        if monitor_index >= len(monitors):
            monitor_index = 1
        shot = sct.grab(monitors[monitor_index])
        return Image.frombytes("RGB", shot.size, shot.rgb)


def crop_roi(img: Image.Image, roi: Tuple[int, int, int, int]) -> Image.Image:
    x, y, w, h = map(int, roi)
    x = max(0, min(x, img.width - 1))
    y = max(0, min(y, img.height - 1))
    w = max(1, min(w, img.width - x))
    h = max(1, min(h, img.height - y))
    return img.crop((x, y, x + w, y + h))


def preprocess_simple(img: Image.Image, scale: float, threshold: int, invert: bool) -> Image.Image:
    arr = np.array(img.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    if scale and abs(scale - 1.0) > 0.01:
        gray = cv2.resize(gray, None, fx=float(scale), fy=float(scale), interpolation=cv2.INTER_CUBIC)
    if threshold > 0:
        _, gray = cv2.threshold(gray, int(threshold), 255, cv2.THRESH_BINARY)
    if invert:
        gray = 255 - gray
    return Image.fromarray(gray)


def gauge_mask_preview(crop: Image.Image) -> Image.Image:
    """Return a small visual mask for the progress gauge debug preview."""
    arr = np.array(crop.convert("RGB"))
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    h, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    blue = (h >= 85) & (h <= 115) & (sat > 45) & (val > 95)
    purple = (h >= 125) & (h <= 155) & (sat > 45) & (val > 95)
    out = np.zeros_like(arr)
    out[purple] = [180, 70, 220]
    out[blue] = [60, 190, 255]
    return Image.fromarray(out)


def detect_gauge_state(crop: Image.Image, cfg: dict) -> Tuple[str, float, float, float, str]:
    """Detect TBH stage progress gauge state from the right-bottom gauge ROI."""
    arr = np.array(crop.convert("RGB"))
    if arr.size == 0:
        return "unknown", 0.0, 0.0, 0.0, "empty"
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    h, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    blue = (h >= 85) & (h <= 115) & (sat > 45) & (val > 95)
    purple = (h >= 125) & (h <= 155) & (sat > 45) & (val > 95)

    def width_ratio(mask: np.ndarray) -> Tuple[float, int, int]:
        _, xs = np.where(mask)
        if len(xs) == 0:
            return 0.0, 0, 0
        width = int(xs.max() - xs.min() + 1)
        return width / max(1, crop.width), width, int(len(xs))

    blue_ratio, _, blue_count = width_ratio(blue)
    purple_ratio, _, purple_count = width_ratio(purple)
    fill_ratio = max(blue_ratio, purple_ratio)
    min_blue = float(cfg.get("gauge_blue_reached_ratio", 0.78))
    min_purple = float(cfg.get("gauge_purple_ratio", 0.08))
    min_px = int(cfg.get("gauge_min_pixels", 12))
    state = "unknown"
    if blue_ratio >= min_blue and blue_count >= min_px:
        state = "blue_reached"
    elif blue_count >= min_px:
        state = "blue"
    elif purple_ratio >= min_purple and purple_count >= min_px:
        state = "purple"
    raw = f"{state} fill={fill_ratio:.2f} blue={blue_ratio:.2f} purple={purple_ratio:.2f}"
    return state, fill_ratio, blue_ratio, purple_ratio, raw


def parse_money(text: str) -> Optional[int]:
    t = text.strip()
    t = t.translate(str.maketrans({
        "O": "0", "o": "0", "D": "0", "Q": "0",
        "I": "1", "l": "1", "|": "1", "!": "1",
        "S": "5", "s": "5", "B": "8",
    }))
    candidates = re.findall(r"[0-9][0-9,\. ]{0,24}", t)
    nums: List[int] = []
    for c in candidates:
        cleaned = re.sub(r"[^0-9]", "", c)
        if cleaned and len(cleaned) <= 12:
            try:
                nums.append(int(cleaned))
            except ValueError:
                pass
    if not nums:
        return None
    nums.sort(key=lambda x: (len(str(x)), x), reverse=True)
    return nums[0]


def normalize_ocr_text(text: str) -> str:
    return text.translate(str.maketrans({
        "O": "0", "o": "0", "D": "0", "Q": "0",
        "I": "1", "l": "1", "|": "1", "!": "1",
        "S": "5", "s": "5", "B": "8",
        "—": "-", "–": "-", "−": "-", "ー": "-", "―": "-",
        "（": "(", "）": ")",
    }))


def stage_to_index(stage: Optional[str]) -> Optional[int]:
    if not stage:
        return None
    m = re.match(r"^(\d{1,2})-(\d{1,2})$", str(stage).strip())
    if not m:
        return None
    world, num = int(m.group(1)), int(m.group(2))
    if not (1 <= world <= 3 and 1 <= num <= 10):
        return None
    return (world - 1) * 10 + (num - 1)


def index_to_stage(idx: Optional[int]) -> Optional[str]:
    if idx is None or not (0 <= int(idx) <= 29):
        return None
    idx = int(idx)
    return f"{idx // 10 + 1}-{idx % 10 + 1}"


def next_stage_after(stage: Optional[str]) -> Optional[str]:
    idx = stage_to_index(stage)
    if idx is None or idx >= 29:
        return None
    return index_to_stage(idx + 1)


def is_valid_stage(stage: Optional[str]) -> bool:
    return stage_to_index(stage) is not None


def choose_stage_candidate(candidates: List[str], cfg: dict) -> Optional[str]:
    uniq: List[str] = []
    for st in candidates:
        if st and is_valid_stage(st) and st not in uniq:
            uniq.append(st)
    if not uniq:
        return None

    expected: List[str] = []
    for st in cfg.get("_expected_stage_candidates", []) or []:
        if is_valid_stage(st) and st not in expected:
            expected.append(st)

    for st in expected:
        if st in uniq:
            return st

    for cand in uniq:
        m = re.match(r"^(\d+)-(\d+)$", cand)
        if not m:
            continue
        world, num = int(m.group(1)), int(m.group(2))
        if num == 7:
            corrected = f"{world}-1"
            if corrected in expected:
                return corrected

    if len(uniq) == 1 and expected:
        cand = uniq[0]
        ci = stage_to_index(cand)
        for exp in expected:
            ei = stage_to_index(exp)
            if ci is not None and ei is not None and cand.split("-")[0] == exp.split("-")[0]:
                if abs(ci - ei) >= 3:
                    return exp

    return uniq[0]


def parse_stage_result(text: str) -> Tuple[Optional[str], Optional[int]]:
    t = normalize_ocr_text(text)
    t = re.sub(r"\s+", " ", t)
    stage: Optional[str] = None
    duration: Optional[int] = None

    m = re.search(r"(\d{1,3})\s*[-]\s*(\d{1,3})", t)
    if m:
        stage = f"{int(m.group(1))}-{int(m.group(2))}"

    nums = []
    for d in re.findall(r"\d{1,5}", t):
        try:
            nums.append(int(d))
        except ValueError:
            pass

    if stage:
        stage_nums = [int(x) for x in stage.split("-")]
        for val in reversed(nums):
            if val not in stage_nums and DURATION_MIN_SEC <= val <= DURATION_MAX_SEC:
                duration = val
                break
    elif len(nums) >= 3:
        stage = f"{nums[0]}-{nums[1]}"
        duration = parse_duration_text(t)
    elif len(nums) >= 1:
        duration = parse_duration_text(t)

    if stage is not None and not is_valid_stage(stage):
        stage = None
    if duration is not None and not (DURATION_MIN_SEC <= duration <= DURATION_MAX_SEC):
        duration = None
    return stage, duration


def parse_stage_number_text(text: str) -> Optional[str]:
    t = normalize_ocr_text(text)
    t = re.sub(r"\s+", "", t)
    m = re.search(r"(\d{1,2})[-](\d{1,2})", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 1 <= a <= 3 and 1 <= b <= 10:
            return f"{a}-{b}"
    nums = [int(x) for x in re.findall(r"\d{1,2}", t)]
    if len(nums) >= 2 and 1 <= nums[0] <= 3 and 1 <= nums[1] <= 10:
        return f"{nums[0]}-{nums[1]}"
    return None


def parse_duration_text(text: str) -> Optional[int]:
    t = normalize_ocr_text(text)
    direct = re.search(r"(\d{1,3})\s*(?:遘竹sec|s)", t, flags=re.IGNORECASE)
    if direct:
        v = int(direct.group(1))
        if DURATION_MIN_SEC <= v <= DURATION_MAX_SEC:
            return v

    candidates: List[int] = []
    for x in re.findall(r"\d{1,8}", t):
        if 1 <= len(x) <= 3:
            v = int(x)
            if DURATION_MIN_SEC <= v <= DURATION_MAX_SEC:
                candidates.append(v)
            continue
        for n in (3, 2):
            if len(x) >= n:
                v = int(x[:n])
                if DURATION_MIN_SEC <= v <= DURATION_MAX_SEC:
                    candidates.append(v)
                    break
    if not candidates:
        return None
    return candidates[0]


def _ocr_text_from_crop(crop: Image.Image, cfg: dict, whitelist: str, psm_list: List[int]) -> List[str]:
    img = preprocess_simple(crop, cfg.get("stage_scale", 3.0), cfg.get("stage_threshold", 135), cfg.get("stage_invert", True))
    raws: List[str] = []
    for psm in psm_list:
        config = f"--psm {psm} --oem 3 -c tessedit_char_whitelist={whitelist}"
        try:
            raw = pytesseract.image_to_string(img, config=config).strip()
            if raw:
                raws.append(raw)
        except Exception as e:
            raws.append(f"ERR:{e}")
    return raws


def ocr_stage_split_from_image(img: Image.Image, cfg: dict) -> StageOCRResult:
    raw_parts: List[str] = []
    stage: Optional[str] = None
    duration: Optional[int] = None

    if cfg.get("stage_num_roi"):
        crop = crop_roi(img, tuple(cfg["stage_num_roi"]))
        raws = _ocr_text_from_crop(crop, cfg, "0123456789-繝ｼ窶・", [7, 8, 13])
        cand = []
        for r in raws:
            st = parse_stage_number_text(r)
            raw_parts.append(f"繧ｹ繝・・繧ｸ={st or '-'} raw:{r}")
            if st:
                cand.append(st)
        if cand:
            stage = choose_stage_candidate(cand, cfg)

    if cfg.get("stage_time_roi"):
        crop = crop_roi(img, tuple(cfg["stage_time_roi"]))
        raws = _ocr_text_from_crop(crop, cfg, "0123456789遘痴ec()・茨ｼ・.", [7, 8, 13])
        cand = []
        for r in raws:
            dur = parse_duration_text(r)
            raw_parts.append(f"遘・{dur if dur is not None else '-'} raw:{r}")
            if dur:
                cand.append(dur)
        if cand:
            duration = cand[0]

    if (stage is None or duration is None) and cfg.get("stage_roi"):
        full = ocr_stage_from_crop(crop_roi(img, tuple(cfg["stage_roi"])), cfg)
        raw_parts.append(f"蜈ｨ譁・{full.raw_text}")
        if stage is None:
            stage = full.stage
        if duration is None:
            duration = full.duration_sec

    return StageOCRResult(stage, duration, " / ".join(raw_parts))


def ocr_money_from_crop(crop: Image.Image, cfg: dict, last_money: Optional[int]) -> MoneyOCRResult:
    img = preprocess_simple(crop, cfg.get("money_scale", 3.0), cfg.get("money_threshold", 150), cfg.get("money_invert", True))
    configs = [
        "--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789,.",
    ]
    if not cfg.get("light_mode", True):
        configs += [
            "--psm 8 --oem 3 -c tessedit_char_whitelist=0123456789,.",
            "--psm 13 --oem 3 -c tessedit_char_whitelist=0123456789,.",
        ]
    results: List[Tuple[int, str]] = []
    raws: List[str] = []
    for config in configs:
        raw = pytesseract.image_to_string(img, config=config).strip()
        money = parse_money(raw)
        raws.append(f"{raw!r}->{money}")
        if money is not None:
            results.append((money, raw))
    if not results:
        return MoneyOCRResult(None, " / ".join(raws))
    if last_money:
        sane = [r for r in results if r[0] >= last_money * 0.5 and r[0] <= last_money * 20]
        if sane:
            results = sane
    results.sort(key=lambda r: (len(str(r[0])), -abs((r[0] - (last_money or r[0])))), reverse=True)
    return MoneyOCRResult(results[0][0], f"{results[0][1]!r} => {results[0][0]}")


def ocr_stage_from_crop(crop: Image.Image, cfg: dict) -> StageOCRResult:
    img = preprocess_simple(crop, cfg.get("stage_scale", 3.0), cfg.get("stage_threshold", 135), cfg.get("stage_invert", True))
    configs = [
        "--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789-繝ｼ窶千ｧ痴sec()・茨ｼ・.",
    ]
    if not cfg.get("light_mode", True):
        configs += [
            "--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789-繝ｼ窶千ｧ痴sec()・茨ｼ・.",
            "--psm 8 --oem 3 -c tessedit_char_whitelist=0123456789-繝ｼ窶千ｧ痴sec()・茨ｼ・.",
        ]
    raws: List[str] = []
    candidates: List[Tuple[str, Optional[str], Optional[int]]] = []
    for config in configs:
        raw = pytesseract.image_to_string(img, config=config).strip()
        stg, dur = parse_stage_result(raw)
        raws.append(f"{raw!r}->{stg},{dur}")
        if stg or dur:
            candidates.append((raw, stg, dur))
    if not candidates:
        return StageOCRResult(None, None, " / ".join(raws))
    candidates.sort(key=lambda x: (1 if x[1] else 0, 1 if x[2] else 0), reverse=True)
    raw, stg, dur = candidates[0]
    return StageOCRResult(stg, dur, f"{raw!r} => {stg},{dur}")
