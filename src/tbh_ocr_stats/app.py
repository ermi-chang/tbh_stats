from __future__ import annotations

from collections import deque
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import mss
import numpy as np
import pytesseract
from PIL import Image
from PySide6.QtCore import QObject, QPoint, QRect, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QDialog,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .digit_ocr import MIN_SAMPLES_PER_DIGIT, get_money_ocr_engine
from .runtime_env import (
    DEFAULT_ANCHOR_TEMPLATE,
    DEFAULT_BOSS_TEMPLATE,
    USER_ASSET_DIR,
    configure_tesseract,
    db_connect,
    init_db as runtime_init_db,
    load_config as runtime_load_config,
    find_tesseract as runtime_find_tesseract,
    save_config as runtime_save_config,
    session_export_paths,
    user_anchor_template_path,
)


APP_VERSION = "1.0.0"
DISPLAY_VERSION = f"v{APP_VERSION}"
ASSET_DIR = USER_ASSET_DIR
APP_CREATOR_NAME = "ermi-chang"
APP_CREATOR_GITHUB = "https://github.com/ermi-chang"
APP_CREATOR_BMAC = "https://buymeacoffee.com/ermichanglv"

UI_LANGUAGES = {
    "ja": "日本語",
    "en": "English",
    "zh": "中文",
}

GAME_LANGUAGES = [
    ("ja", "日本語"),
    ("en", "English"),
    ("de", "Deutsch"),
    ("es", "Español"),
    ("fr", "Français"),
    ("pl", "Polski"),
    ("pt-BR", "Português-Brasil"),
    ("ru", "Русский"),
    ("tr", "Türkçe"),
    ("uk", "Українська"),
    ("zh-Hans", "简体中文"),
    ("zh-Hant", "繁體中文"),
    ("ko", "한국어"),
    ("th", "ภาษาไทย"),
    ("vi", "Tiếng Việt"),
    ("id", "Bahasa Indonesia"),
]

# UI translation is independent from the in-game OCR language.
# OCR itself stays number-first: stage = digits + hyphen, seconds = digits.
I18N = {
    "ja": {},
    "en": {
        "TBH 効率ログ": "TBH Efficiency Log",
        "待機": "Idle",
        "計測中": "Running",
        "停止": "Stopped",
        "▶ 開始": "▶ Start",
        "■ 停止": "■ Stop",
        "計測": "Measure",
        "効率表": "Best",
        "所持金": "Gold",
        "増加G": "Gold +",
        "経過": "Elapsed",
        "直近5分GPS": "GPS 5m",
        "平均GPH": "Avg GPH",
        "今ステージ周回/h": "Runs/h",
        "オススメ": "Best stage",
        "ステージ履歴（1クリア=1行）": "Stage log (1 clear = 1 row)",
        "CSV": "CSV",
        "リセット": "Reset",
        "ステージ": "Stage",
        "秒": "Sec",
        "GPS": "GPS",
        "GPH": "GPH",
        "周回/h": "Runs/h",
        "対象画面": "Screen",
        "UI言語": "UI",
        "ゲーム言語": "Game",
        "秒数": "Seconds",
        "ゲージ": "Gauge",
        "自動追従": "Auto track",
        "自動設定": "Auto setup",
        "OCRテスト": "OCR test",
        "元画像": "Original",
        "OCR処理後": "Processed",
        "OCR": "OCR",
        "参照": "Browse",
        "所持金 拡大": "Gold scale",
        "所持金 しきい値": "Gold threshold",
        "所持金反転": "Gold invert",
        "通知系 拡大": "Notice scale",
        "通知系 しきい値": "Notice threshold",
        "通知反転": "Notice invert",
        "所持金更新": "Gold refresh",
        "軽量モード": "Light mode",
        "OCRテスト結果": "OCR result",
        "ステージ別ハイスコア（1-1〜3-10）": "Stage best scores (1-1 to 3-10)",
        "選択ステージリセット": "Reset selected",
        "全リセット": "Reset all",
        "各ステージの最高効率を保存します。3件以上あるステージは外れ値を除外してハイスコアを判定します。": "Stores the best score per stage. After 3+ logs, outliers are ignored before picking the best score.",
        "最高GPS": "Best GPS",
        "最高GPH": "Best GPH",
        "採用/全件": "Used/All",
        "範囲なし": "No ROI",
        "範囲未設定": "No ROI",
    },
    "zh": {
        "TBH 効率ログ": "TBH 效率日志",
        "待機": "待机",
        "計測中": "记录中",
        "停止": "已停止",
        "▶ 開始": "▶ 开始",
        "■ 停止": "■ 停止",
        "計測": "记录",
        "効率表": "效率表",
        "所持金": "金币",
        "増加G": "增加G",
        "経過": "经过",
        "直近5分GPS": "近5分GPS",
        "平均GPH": "平均GPH",
        "今ステージ周回/h": "当前周回/h",
        "オススメ": "推荐",
        "ステージ履歴（1クリア=1行）": "关卡记录（1次通关=1行）",
        "CSV": "CSV",
        "リセット": "重置",
        "ステージ": "关卡",
        "秒": "秒",
        "GPS": "GPS",
        "GPH": "GPH",
        "周回/h": "周回/h",
        "対象画面": "目标屏幕",
        "UI言語": "界面",
        "ゲーム言語": "游戏语言",
        "秒数": "秒数",
        "ゲージ": "进度条",
        "自動追従": "自动追踪",
        "自動設定": "自动设置",
        "OCRテスト": "OCR测试",
        "元画像": "原图",
        "OCR処理後": "处理后",
        "OCR": "OCR",
        "参照": "浏览",
        "所持金 拡大": "金币放大",
        "所持金 しきい値": "金币阈值",
        "所持金反転": "金币反转",
        "通知系 拡大": "通知放大",
        "通知系 しきい値": "通知阈值",
        "通知反転": "通知反转",
        "所持金更新": "金币刷新",
        "軽量モード": "轻量模式",
        "OCRテスト結果": "OCR结果",
        "ステージ別ハイスコア（1-1〜3-10）": "关卡最高效率（1-1〜3-10）",
        "選択ステージリセット": "重置所选",
        "全リセット": "全部重置",
        "各ステージの最高効率を保存します。3件以上あるステージは外れ値を除外してハイスコアを判定します。": "保存每个关卡的最高效率。记录达到3件后，会排除异常值再判断最高值。",
        "最高GPS": "最高GPS",
        "最高GPH": "最高GPH",
        "採用/全件": "采用/全部",
        "範囲なし": "无范围",
        "範囲未設定": "未设置范围",
    },
}

def ui_text(key: str, lang: str) -> str:
    if lang == "ja":
        return key
    return I18N.get(lang, {}).get(key, key)

def source_key_from_text(text: str) -> str:
    # Keep dynamic values untouched. Reverse lookup maps translated labels back to Japanese keys.
    for lang, table in I18N.items():
        for k, v in table.items():
            if text == v:
                return k
    return text

# 添付してもらった default_anchor_gold.png はゲーム内スケール x1.5 の状態で切り出したもの。
# ゲーム側の設定は x1 / x1.25 / x1.5 / x2 / x3 の5段階なので、
# テンプレート照合では「現在スケール ÷ 1.5」を候補にする。
ANCHOR_TEMPLATE_GAME_SCALE = 1.5
SUPPORTED_GAME_SCALES = [1.0, 1.25, 1.5, 2.0, 3.0]

def template_scale_candidates() -> List[float]:
    base = [gs / ANCHOR_TEMPLATE_GAME_SCALE for gs in SUPPORTED_GAME_SCALES]
    # 端数丸めやDPI差の保険として、各候補の前後も薄く探索する。
    extra = []
    for v in base:
        extra.extend([v * 0.96, v, v * 1.04])
    return sorted(set(round(x, 4) for x in extra if 0.45 <= x <= 2.25))

def nearest_supported_game_scale(relative_template_scale: float) -> float:
    game_scale = float(relative_template_scale) * ANCHOR_TEMPLATE_GAME_SCALE
    return min(SUPPORTED_GAME_SCALES, key=lambda x: abs(x - game_scale))

ROI_LABELS = {
    "anchor": "基準アイコン",
    "money": "所持金",
    "stage_num": "ステージ",
    "stage_time": "秒数",
    "gauge": "進捗ゲージ",
    "stage": "旧通知ROI",
}
ROI_COLORS = {
    "anchor": "#ffcc58",
    "money": "#d88934",
    "stage_num": "#6aa6c9",
    "stage_time": "#b47a3c",
    "gauge": "#4ea3c9",
    "stage": "#7e8f7a",
}

# OCR duration sanity. TBH stage clear times are expected to be seconds, not 4-5 digit
# strings. If OCR reads "1488" or "14842", keep the most plausible prefix.
DURATION_MIN_SEC = 3
DURATION_MAX_SEC = 900
OCR_PREPROCESS_SCALE = 3.0

# 左上ゴールドアイコンを基準にした自動ROI。
# 基準テンプレートは assets/default_anchor_gold.png（34x28）で、
# offsets はそのテンプレートサイズでの相対座標。検出スケールに応じて拡大縮小する。
AUTO_ROI_LAYOUT = {
    # x/y/w/h are relative to detected left-top gold icon at scale=1.0 (template x1.5基準).
    "money": [36, -1, 112, 31],
    "stage": [4, 713, 430, 34],
    "stage_num": [94, 717, 58, 25],
    "stage_time": [318, 717, 72, 25],
    # gauge は直接この矩形を使わず、まずこの周辺から右下ボスアイコンを探す。
    "gauge": [420, 840, 100, 60],
}

# Gold anchorから見た右下ボスアイコン探索範囲。広く見せるためではなく、
# ボスアイコン検出を安定させるための内部探索窓。
BOSS_SEARCH_LAYOUT = [375, 800, 180, 135]
# Boss icon top-leftから見た実ゲージ部分。添付のx1.5画像基準。
BOSS_TO_GAUGE_LAYOUT = [20, 14, 78, 16]

# ルーン画面検出用。ルーン枠の所持金は上部HUDと「同じ金コイン＋同じ並び」なので、
# 画面内に出現する2個目の金コインを探し、通常の金額オフセットで読む（手動ROI不要）。
# RUNE_MONEY_OFFSET は AUTO_ROI_LAYOUT["money"] と同義。ズレた時に独立調整できるよう別定数化。
RUNE_MONEY_OFFSET = [36, -1, 112, 31]
# HUDコイン中心からこの距離(px, x1基準テンプレ幅換算)以内のマッチは自分自身とみなし除外。
RUNE_COIN_MIN_SEP_FACTOR = 2.2  # 検出アンカー幅 × この係数



def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def find_tesseract() -> Optional[str]:
    return runtime_find_tesseract()


def resolve_tesseract(cfg: dict) -> Optional[str]:
    """Set pytesseract command if available and return the resolved path."""
    return configure_tesseract(cfg)


def load_config() -> dict:
    return runtime_load_config()


def save_config(cfg: dict) -> None:
    runtime_save_config(cfg)


def init_db() -> None:
    runtime_init_db()


@dataclass
class MoneyOCRResult:
    money: Optional[int]
    raw_text: str
    # 全前処理が同一値に一致した高信頼読みか（テンプレ自己学習の教師に使う）。
    consensus: bool = False


@dataclass
class StageOCRResult:
    stage: Optional[str]
    duration_sec: Optional[int]
    raw_text: str
    stage_candidates: List[str] = field(default_factory=list)
    duration_candidates: List[int] = field(default_factory=list)


@dataclass
class WorkerResult:
    ts: float
    money: Optional[int]
    money_raw: str
    stage: Optional[str]
    duration_sec: Optional[int]
    stage_raw: str
    error: Optional[str] = None
    purpose: str = "tick"
    stage_candidates: List[str] = field(default_factory=list)
    duration_candidates: List[int] = field(default_factory=list)
    money_source: str = "main"  # "main"=上部HUD / "rune"=ルーン画面内の所持金枠
    money_consensus: bool = False  # tesseract全閾値一致の高信頼読みか（ROI自己修復判定用）


@dataclass
class GaugeResult:
    ts: float
    state: str
    fill_ratio: float
    blue_ratio: float
    purple_ratio: float
    raw: str
    error: Optional[str] = None


# ---------- image helpers ----------

def pil_to_qimage(img: Image.Image) -> QImage:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    return QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888).copy()


def pil_to_pixmap(img: Image.Image, max_w: int = 240, max_h: int = 95) -> QPixmap:
    w, h = img.size
    scale = min(1.0, max_w / max(1, w), max_h / max(1, h))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    return QPixmap.fromImage(pil_to_qimage(img))


def capture_monitor(monitor_index: int) -> Image.Image:
    with mss.mss() as sct:
        monitors = sct.monitors
        if monitor_index >= len(monitors):
            monitor_index = 1
        shot = sct.grab(monitors[monitor_index])
        return Image.frombytes("RGB", shot.size, shot.rgb)


def capture_monitor_region(monitor_index: int, roi: Tuple[int, int, int, int]) -> Image.Image:
    with mss.mss() as sct:
        monitors = sct.monitors
        if monitor_index >= len(monitors):
            monitor_index = 1
        mon = monitors[monitor_index]
        x, y, w, h = map(int, roi)
        region = {
            "left": int(mon["left"]) + max(0, x),
            "top": int(mon["top"]) + max(0, y),
            "width": max(1, w),
            "height": max(1, h),
        }
        shot = sct.grab(region)
        return Image.frombytes("RGB", shot.size, shot.rgb)


def crop_roi(img: Image.Image, roi: Tuple[int, int, int, int]) -> Image.Image:
    x, y, w, h = map(int, roi)
    x = max(0, min(x, img.width - 1))
    y = max(0, min(y, img.height - 1))
    w = max(1, min(w, img.width - x))
    h = max(1, min(h, img.height - y))
    return img.crop((x, y, x + w, y + h))




def save_anchor_template(img: Image.Image, roi: Tuple[int, int, int, int]) -> Optional[str]:
    """Save the selected in-game anchor icon as a small template for later auto tracking."""
    try:
        ASSET_DIR.mkdir(exist_ok=True)
        crop = crop_roi(img, roi)
        # Keep template small and exact. Matching is done on grayscale after optional scaling.
        out = ASSET_DIR / "anchor_user.png"
        crop.save(out)
        return str(out)
    except Exception:
        return None


def update_anchor_offsets(cfg: dict) -> None:
    """Store every ROI as an offset from the anchor icon.

    If the game window moves, the app finds the anchor and reconstructs ROIs from these offsets.
    If the game scale changes, the offsets are multiplied by the detected template scale.
    """
    anchor = cfg.get("anchor_roi")
    if not anchor:
        return
    ax, ay, aw, ah = map(float, anchor)
    if aw <= 0 or ah <= 0:
        return
    cfg["anchor_base_size"] = [aw, ah]
    for name in ["money", "stage_num", "stage_time", "gauge", "stage"]:
        roi = cfg.get(f"{name}_roi")
        if not roi:
            continue
        x, y, w, h = map(float, roi)
        cfg[f"{name}_anchor_offset"] = [x - ax, y - ay, w, h]


def _load_anchor_template(cfg: dict) -> Optional[Image.Image]:
    paths = []
    raw = cfg.get("anchor_template_path")
    if raw:
        paths.append(Path(str(raw)))
    paths.append(DEFAULT_ANCHOR_TEMPLATE)
    if cfg.get("anchor_roi") and cfg.get("_last_screenshot_for_anchor"):
        pass
    for path in paths:
        try:
            if path.exists():
                return Image.open(path).convert("RGB")
        except Exception:
            continue
    return None


def _load_boss_template(cfg: dict) -> Optional[Image.Image]:
    paths = []
    raw = cfg.get("boss_template_path")
    if raw:
        paths.append(Path(str(raw)))
    paths.append(DEFAULT_BOSS_TEMPLATE)
    for path in paths:
        try:
            if path.exists():
                return Image.open(path).convert("RGB")
        except Exception:
            continue
    return None


def _edge_match_score(search_gray: np.ndarray, tpl_gray: np.ndarray) -> Tuple[float, Tuple[int, int]]:
    # 光り方が変わっても形状が残りやすいエッジで照合する。
    s_edge = cv2.Canny(search_gray, 40, 120)
    t_edge = cv2.Canny(tpl_gray, 40, 120)
    if t_edge.sum() <= 0 or s_edge.shape[0] < t_edge.shape[0] or s_edge.shape[1] < t_edge.shape[1]:
        return -1.0, (0, 0)
    res = cv2.matchTemplate(s_edge, t_edge, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    return float(score), (int(loc[0]), int(loc[1]))


def _boss_candidate_color_score(patch_rgb: np.ndarray, tpl_rgb: np.ndarray) -> Tuple[float, bool, str]:
    """Return foreground/color plausibility for the boss icon candidate.

    Edge matching alone can lock on to high-contrast bright backgrounds.  The boss icon has a
    distinctive red HP-like mark and gray/white skull silhouette, so use those as a cheap guard.
    This still tolerates the blue glow because the guard is loose and foreground-only.
    """
    if patch_rgb.shape[:2] != tpl_rgb.shape[:2]:
        return 0.0, False, "shape-mismatch"
    tpl_gray = cv2.cvtColor(tpl_rgb, cv2.COLOR_RGB2GRAY)
    fg = tpl_gray > 25
    if int(fg.sum()) < 10:
        return 0.0, False, "fg-empty"

    # Template red accent area, if present.
    tr, tg, tb = tpl_rgb[:, :, 0], tpl_rgb[:, :, 1], tpl_rgb[:, :, 2]
    red_mask = (tr > 110) & (tg < 90) & (tb < 90)
    pr, pg, pb = patch_rgb[:, :, 0], patch_rgb[:, :, 1], patch_rgb[:, :, 2]
    patch_red = (pr > 110) & (pg < 105) & (pb < 105)
    red_needed = int(red_mask.sum()) >= 3
    red_ok = True
    if red_needed:
        # Look at corresponding template red pixels plus total red pixels.  Glow/scale can move a
        # few pixels, so total red is also accepted.
        red_at_template = int((patch_red & red_mask).sum())
        red_total = int(patch_red.sum())
        red_ok = red_at_template >= 1 or red_total >= max(2, int(red_mask.sum() * 0.20))

    # Foreground brightness/color similarity.  Use a loose normalized MAD because glow changes color.
    patch_fg = patch_rgb[fg].astype(np.float32)
    tpl_fg = tpl_rgb[fg].astype(np.float32)
    mad = float(np.mean(np.abs(patch_fg - tpl_fg))) / 255.0
    fg_score = max(0.0, 1.0 - mad * 1.8)

    # Additional foreground contrast guard: false bright background patches often have too little
    # dark/bright structure matching the icon.
    patch_gray = cv2.cvtColor(patch_rgb, cv2.COLOR_RGB2GRAY)
    dark_count = int(((patch_gray < 70) & fg).sum())
    light_count = int(((patch_gray > 120) & fg).sum())
    structure_ok = dark_count >= 4 and light_count >= 3
    ok = bool(red_ok and structure_ok and fg_score >= 0.18)
    detail = f"fg={fg_score:.2f} red={int(red_ok)} dark={dark_count} light={light_count}"
    return fg_score, ok, detail


def locate_boss_icon_in_roi(img: Image.Image, search_roi: Tuple[int, int, int, int], cfg: dict, preferred_scale: float = 1.0) -> Optional[Tuple[int, int, int, int, float, float]]:
    """Find the lower-right boss icon inside a search region.

    v32: Edge matching alone caused false positives on bright backgrounds.  This version ranks
    multiple candidates using edge+gray template matching, then rejects candidates that do not look
    like the boss icon foreground/color structure.  It also adds a weak position prior so a plausible
    lower-right candidate wins over a similarly scored background texture.
    """
    tpl_img = _load_boss_template(cfg)
    if tpl_img is None:
        return None
    x, y, w, h = _clamp_roi(img, search_roi)
    region = crop_roi(img, (x, y, w, h))
    search = np.array(region.convert("RGB"))
    search_gray = cv2.cvtColor(search, cv2.COLOR_RGB2GRAY)
    tpl = np.array(tpl_img.convert("RGB"))
    tpl_gray0 = cv2.cvtColor(tpl, cv2.COLOR_RGB2GRAY)
    th0, tw0 = tpl_gray0.shape[:2]
    if tw0 < 6 or th0 < 6:
        return None

    candidates = sorted(set(round(preferred_scale * f, 4) for f in [0.84, 0.90, 0.96, 1.0, 1.04, 1.10, 1.16] if 0.45 <= preferred_scale * f <= 2.35))
    best = None
    debug_best = None
    for sc in candidates:
        tw = max(4, int(round(tw0 * sc)))
        th = max(4, int(round(th0 * sc)))
        if tw >= search_gray.shape[1] or th >= search_gray.shape[0]:
            continue
        tpl_rgb = cv2.resize(tpl, (tw, th), interpolation=cv2.INTER_AREA if sc < 1 else cv2.INTER_CUBIC)
        tpl_gray = cv2.cvtColor(tpl_rgb, cv2.COLOR_RGB2GRAY)
        try:
            res_gray = cv2.matchTemplate(search_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
            s_edge = cv2.Canny(search_gray, 40, 120)
            t_edge = cv2.Canny(tpl_gray, 40, 120)
            if t_edge.sum() > 0 and s_edge.shape[0] >= t_edge.shape[0] and s_edge.shape[1] >= t_edge.shape[1]:
                res_edge = cv2.matchTemplate(s_edge, t_edge, cv2.TM_CCOEFF_NORMED)
            else:
                res_edge = res_gray
        except Exception:
            continue

        # Check top candidates, not only the single best edge/gray hit.
        locs = []
        for res, weight_name in [(res_gray, "g"), (res_edge, "e")]:
            flat = res.ravel()
            if flat.size == 0:
                continue
            k = min(8, flat.size)
            idxs = np.argpartition(flat, -k)[-k:]
            for idx in idxs:
                yy, xx = divmod(int(idx), res.shape[1])
                locs.append((xx, yy))
        seen = set()
        for lx, ly in locs:
            if (lx, ly) in seen:
                continue
            seen.add((lx, ly))
            if ly + th > search.shape[0] or lx + tw > search.shape[1]:
                continue
            patch = search[ly:ly + th, lx:lx + tw]
            if patch.shape[:2] != (th, tw):
                continue
            gray_score = float(res_gray[ly, lx])
            edge_score = float(res_edge[ly, lx]) if ly < res_edge.shape[0] and lx < res_edge.shape[1] else gray_score
            fg_score, plausible, detail = _boss_candidate_color_score(patch, tpl_rgb)
            # Boss icon is expected toward the lower-right of the search window. This is only a weak
            # prior, but it helps reject bright background shapes above/left of the actual widget.
            px = (lx + tw / 2) / max(1, search.shape[1])
            py = (ly + th / 2) / max(1, search.shape[0])
            pos_prior = 0.5 * px + 0.5 * py
            combined = 0.34 * gray_score + 0.36 * edge_score + 0.22 * fg_score + 0.08 * pos_prior
            debug = f"gray={gray_score:.2f} edge={edge_score:.2f} {detail} pos={pos_prior:.2f}"
            if debug_best is None or combined > debug_best[0]:
                debug_best = (combined, debug)
            if not plausible:
                continue
            if best is None or combined > best[4]:
                best = (x + int(lx), y + int(ly), tw, th, float(combined), float(sc), debug)
    min_score = float(cfg.get("boss_min_score", 0.34))
    if best and best[4] >= min_score:
        # Store a compact debug string in cfg-like global?  Return score only for compatibility.
        return best[:6]
    return None


def locate_anchor(img: Image.Image, cfg: dict) -> Optional[Tuple[int, int, int, int, float, float]]:
    """Find the anchor icon in the current screenshot using multi-scale template matching.

    Returns (x, y, w, h, score, scale). It does not modify the game or read memory.
    """
    if not cfg.get("anchor_enabled", True):
        return None
    template_img = _load_anchor_template(cfg)
    if template_img is None:
        return None
    scr = np.array(img.convert("RGB"))
    scr_gray = cv2.cvtColor(scr, cv2.COLOR_RGB2GRAY)
    tpl = np.array(template_img.convert("RGB"))
    tpl_gray0 = cv2.cvtColor(tpl, cv2.COLOR_RGB2GRAY)
    th0, tw0 = tpl_gray0.shape[:2]
    if tw0 < 6 or th0 < 6:
        return None

    # ゲーム内UIスケールは x1 / x1.25 / x1.5 / x2 / x3。
    # default_anchor_gold.png は x1.5 で切り出したため、照合倍率は game_scale / 1.5。
    # 例: x1 => 0.666..., x1.25 => 0.833..., x1.5 => 1.0, x2 => 1.333..., x3 => 2.0
    scales = template_scale_candidates()
    best = None
    for sc in scales:
        tw = max(4, int(round(tw0 * sc)))
        th = max(4, int(round(th0 * sc)))
        if tw >= scr_gray.shape[1] or th >= scr_gray.shape[0]:
            continue
        tpl_gray = cv2.resize(tpl_gray0, (tw, th), interpolation=cv2.INTER_AREA if sc < 1 else cv2.INTER_CUBIC)
        try:
            res = cv2.matchTemplate(scr_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(res)
        except Exception:
            continue
        if best is None or score > best[4]:
            best = (int(loc[0]), int(loc[1]), tw, th, float(score), float(sc))
    min_score = float(cfg.get("anchor_min_score", 0.62))
    if best and best[4] >= min_score:
        return best
    return None


def _clamp_roi(img: Image.Image, roi: Tuple[int, int, int, int]) -> List[int]:
    x, y, w, h = map(int, roi)
    x = max(0, min(x, img.width - 1))
    y = max(0, min(y, img.height - 1))
    w = max(1, min(w, img.width - x))
    h = max(1, min(h, img.height - y))
    return [x, y, w, h]


def locate_secondary_anchor(img: Image.Image, cfg: dict, primary_xy: Tuple[float, float], min_sep_px: float, scale: float) -> Optional[Tuple[int, int, int, int, float, float]]:
    """Find a SECOND gold-coin icon (e.g. the one inside the rune screen) away from the HUD coin.

    Reuses the anchor template at (around) the already-detected HUD scale. Returns the best peak
    whose center is at least ``min_sep_px`` away from ``primary_xy`` (the HUD coin center), so we do
    not re-detect the HUD coin itself. Returns (x, y, w, h, score, scale) or None.
    """
    template_img = _load_anchor_template(cfg)
    if template_img is None:
        return None
    scr_gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    tpl_gray0 = cv2.cvtColor(np.array(template_img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    th0, tw0 = tpl_gray0.shape[:2]
    if tw0 < 6 or th0 < 6:
        return None
    # 既定をHUDアンカーより高めにする。低スコアの偽コイン(0.79前後)による誤検出を抑える保険。
    min_score = float(cfg.get("rune_coin_min_score", 0.80))
    base = float(scale or 1.0)
    best = None
    for sc in sorted(set(round(base * f, 4) for f in (0.9, 1.0, 1.1) if base * f > 0)):
        tw = max(4, int(round(tw0 * sc)))
        th = max(4, int(round(th0 * sc)))
        if tw >= scr_gray.shape[1] or th >= scr_gray.shape[0]:
            continue
        tpl_gray = cv2.resize(tpl_gray0, (tw, th), interpolation=cv2.INTER_AREA if sc < 1 else cv2.INTER_CUBIC)
        try:
            res = cv2.matchTemplate(scr_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        except Exception:
            continue
        ys, xs = np.where(res >= min_score)
        for yy, xx in zip(ys.tolist(), xs.tolist()):
            cxc = xx + tw / 2.0
            cyc = yy + th / 2.0
            if (cxc - primary_xy[0]) ** 2 + (cyc - primary_xy[1]) ** 2 < min_sep_px ** 2:
                continue  # too close to the HUD coin → this is the coin we already track
            score = float(res[yy, xx])
            if best is None or score > best[4]:
                best = (int(xx), int(yy), tw, th, score, float(sc))
    return best


def rune_money_rect_from_coin(img: Image.Image, coin: Tuple[int, int, int, int, float, float]) -> List[int]:
    """Money rectangle relative to a found coin, using the same offset as the normal HUD money ROI."""
    cx, cy, _cw, _ch, _score, cscale = coin
    dx, dy, w, h = map(float, RUNE_MONEY_OFFSET)
    return _clamp_roi(img, (
        int(round(cx + dx * cscale)),
        int(round(cy + dy * cscale)),
        int(round(w * cscale)),
        int(round(h * cscale)),
    ))


def compute_auto_rois_from_anchor(img: Image.Image, det: Tuple[int, int, int, int, float, float], cfg: dict) -> dict:
    """Compute OCR ROIs from the detected gold icon, and gauge ROI from boss icon.

    Money/stage/time use the left-top gold icon as before.
    Gauge uses the lower-right boss icon as an additional anchor, because the gauge itself can be
    very thin and may be partially clipped. The boss icon is searched only inside the expected
    lower-right region derived from the gold anchor, then the gauge rectangle is placed relative
    to the boss icon.
    """
    ax, ay, aw, ah, score, scale = det
    out = {}
    sc = float(scale or 1.0)
    for name, rect in AUTO_ROI_LAYOUT.items():
        if name == "gauge":
            continue
        dx, dy, w, h = map(float, cfg.get(f"auto_{name}_layout", rect))
        roi = (
            int(round(ax + dx * sc)),
            int(round(ay + dy * sc)),
            int(round(w * sc)),
            int(round(h * sc)),
        )
        out[f"{name}_roi"] = _clamp_roi(img, roi)

    # Internal boss search area. This does not make the final gauge ROI wide; it only finds the icon.
    bdx, bdy, bw, bh = map(float, cfg.get("boss_search_layout", BOSS_SEARCH_LAYOUT))
    boss_search = (
        int(round(ax + bdx * sc)),
        int(round(ay + bdy * sc)),
        int(round(bw * sc)),
        int(round(bh * sc)),
    )
    boss = locate_boss_icon_in_roi(img, boss_search, cfg, sc)
    if boss:
        bx, by, bww, bhh, bscore, bscale = boss
        gdx, gdy, gw, gh = map(float, cfg.get("boss_to_gauge_layout", BOSS_TO_GAUGE_LAYOUT))
        gauge_roi = (
            int(round(bx + gdx * bscale)),
            int(round(by + gdy * bscale)),
            int(round(gw * bscale)),
            int(round(gh * bscale)),
        )
        out["gauge_roi"] = _clamp_roi(img, gauge_roi)
        out["_boss_anchor_status"] = f"ボス基準 score={bscore:.2f} scale={bscale:.3f} x={bx} y={by}"
    else:
        # Fallback: previous rough gauge ROI. Used only when boss icon is not detected.
        dx, dy, w, h = map(float, cfg.get("auto_gauge_layout", AUTO_ROI_LAYOUT["gauge"]))
        roi = (
            int(round(ax + dx * sc)),
            int(round(ay + dy * sc)),
            int(round(w * sc)),
            int(round(h * sc)),
        )
        out["gauge_roi"] = _clamp_roi(img, roi)
        out["_boss_anchor_status"] = "ボス基準未検出。旧ゲージROIを使用"
    return out


def apply_anchor_rois(img: Image.Image, cfg: dict) -> dict:
    """Return a runtime config with ROIs translated/scaled from the detected anchor.

    jp16: auto layout is the primary mode. It ignores stale manual ROIs when enabled.
    """
    runtime = dict(cfg)
    det = locate_anchor(img, cfg)
    if not det:
        runtime["_anchor_status"] = "基準アイコン未検出。自動ROIを更新できません。"
        # If auto layout is enabled but anchor is missing, do not silently use stale manual ranges.
        # It is safer to fail than to read the wrong area after the game window moved.
        if bool(cfg.get("auto_rois_enabled", True)):
            for name in ["money", "stage_num", "stage_time", "gauge", "stage"]:
                runtime.pop(f"{name}_roi", None)
        return runtime

    ax, ay, aw, ah, score, scale = det
    game_scale = nearest_supported_game_scale(scale)
    runtime["anchor_roi"] = [int(ax), int(ay), int(aw), int(ah)]
    runtime["detected_game_scale"] = game_scale
    runtime["detected_template_scale"] = float(scale)
    runtime["_anchor_status"] = f"基準検出 score={score:.2f} ゲーム倍率=x{game_scale:g} template={scale:.3f} x={ax} y={ay}"

    if bool(cfg.get("auto_rois_enabled", True)):
        auto = compute_auto_rois_from_anchor(img, det, cfg)
        runtime.update(auto)
        if auto.get("_boss_anchor_status"):
            runtime["_anchor_status"] = runtime["_anchor_status"] + " / " + auto.get("_boss_anchor_status", "")
        return runtime

    # Legacy manual-offset mode kept only for compatibility with older config.json.
    for name in ["money", "stage_num", "stage_time", "gauge", "stage"]:
        off = cfg.get(f"{name}_anchor_offset")
        if not off:
            continue
        dx, dy, w, h = map(float, off[:4])
        roi = (
            int(round(ax + dx * scale)),
            int(round(ay + dy * scale)),
            int(round(w * scale)),
            int(round(h * scale)),
        )
        runtime[f"{name}_roi"] = _clamp_roi(img, roi)
    return runtime

def preprocess_simple(img: Image.Image, scale: float = OCR_PREPROCESS_SCALE, threshold: int = 0, invert: bool = False) -> Image.Image:
    arr = np.array(img.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    if abs(scale - 1.0) > 0.01:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    if int(threshold or 0) > 0:
        _, gray = cv2.threshold(gray, int(threshold), 255, cv2.THRESH_BINARY)
    else:
        _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    if invert:
        gray = 255 - gray
    return Image.fromarray(gray)


def preprocess_ocr_candidates(img: Image.Image, invert: bool, fixed_thresholds: List[int]) -> List[Tuple[str, Image.Image]]:
    candidates: List[Tuple[str, Image.Image]] = [("otsu", preprocess_simple(img, invert=invert))]
    for threshold in fixed_thresholds:
        candidates.append((f"t{threshold}", preprocess_simple(img, threshold=threshold, invert=invert)))
    return candidates



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
    """Detect TBH stage progress gauge state from the right-bottom gauge ROI.

    The app does not need OCR or network pulses for stage boundaries:
    - purple/progress state => stage is running or gauge has reset
    - blue reached state => stage reached the end
    - blue reached followed by purple => one stage finished
    """
    arr = np.array(crop.convert("RGB"))
    if arr.size == 0:
        return "unknown", 0.0, 0.0, 0.0, "empty"
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    h, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    # Exclude very dark UI frame and low-saturation background. The blue/purple bar itself is highly saturated.
    blue = (h >= 85) & (h <= 115) & (sat > 45) & (val > 95)
    purple = (h >= 125) & (h <= 155) & (sat > 45) & (val > 95)

    def width_ratio(mask: np.ndarray) -> Tuple[float, int, int]:
        ys, xs = np.where(mask)
        if len(xs) == 0:
            return 0.0, 0, 0
        width = int(xs.max() - xs.min() + 1)
        return width / max(1, crop.width), width, int(len(xs))

    blue_ratio, blue_w, blue_count = width_ratio(blue)
    purple_ratio, purple_w, purple_count = width_ratio(purple)
    # Fill is whichever colored bar is dominant horizontally.
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
        "—": "-", "–": "-", "ー": "-", "‐": "-", "‑": "-",
        "（": "(", "）": ")",
    }))



def stage_to_index(stage: Optional[str]) -> Optional[int]:
    """Convert 1-1..3-10 to 0..29."""
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
    """Pick the most plausible stage OCR result by majority vote.

    Stage OCR runs many binarization/PSM variants; a single variant can misread
    one digit (e.g. 2-3 as 2-8), so duplicates in `candidates` are meaningful
    votes. Expected stages (previous/next) win ties and near-ties, but a clear
    multi-vote majority is trusted even against expectations so a genuine stage
    change is never rewritten.
    """
    valid = [st for st in candidates if st and is_valid_stage(st)]
    if not valid:
        return None
    order: List[str] = []
    for st in valid:
        if st not in order:
            order.append(st)
    counts = {st: valid.count(st) for st in order}
    max_count = max(counts.values())

    expected: List[str] = []
    for st in cfg.get("_expected_stage_candidates", []) or []:
        if is_valid_stage(st) and st not in expected:
            expected.append(st)

    # Expected stage wins when it has comparable support. Correlated misreads can
    # produce 2+ identical wrong votes, so near-ties resolve to the expected stage,
    # while an overwhelming majority (genuine stage change) still passes through.
    exp_present = [e for e in expected if e in counts]
    if exp_present:
        best_exp = max(exp_present, key=lambda e: counts[e])
        if counts[best_exp] * 2 >= max_count:
            return best_exp

    winner = next(st for st in order if counts[st] == max_count)

    # Conservative OCR correction: x-7 is often x-1 in this font. The misread is
    # systematic across variants, so apply regardless of vote count, but only when
    # the corrected value matches a known expected stage.
    m = re.match(r"^(\d+)-7$", winner)
    if m:
        corrected = f"{m.group(1)}-1"
        if corrected in expected:
            return corrected

    # Multi-variant agreement beats expectations: the user really changed stages.
    if max_count >= 2:
        return winner

    # A single lone observation that jumps >=3 stages within the expected world is
    # more likely a misread than a real jump; keep the expected stage.
    if len(order) == 1 and expected:
        ci = stage_to_index(winner)
        for exp in expected:
            ei = stage_to_index(exp)
            if ci is not None and ei is not None and winner.split('-')[0] == exp.split('-')[0]:
                if abs(ci - ei) >= 3:
                    return exp

    return winner

def parse_stage_result(text: str) -> Tuple[Optional[str], Optional[int]]:
    t = normalize_ocr_text(text)
    t = re.sub(r"\s+", " ", t)
    stage: Optional[str] = None
    duration: Optional[int] = None

    m = re.search(r"(\d{1,3})\s*[-]\s*(\d{1,3})", t)
    if m:
        stage = f"{int(m.group(1))}-{int(m.group(2))}"

    # OCRが「ステージ 1 8 ... 130 秒」のようにハイフンを落とす場合も拾う
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
        # 先頭2つをステージ、秒数は重複/混入補正付きで読む
        stage = f"{nums[0]}-{nums[1]}"
        duration = parse_duration_text(t)
    elif len(nums) >= 1:
        # ステージは取れないが秒だけ取れる場合
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
    """Parse seconds from a small duration ROI.

    OCR often duplicates the last digit or captures nearby UI text, e.g.:
    - 148 -> 148
    - 1488 -> 148
    - 14842 -> 148
    - 821053 -> 82
    Prefer 2-3 digit plausible prefixes and reject large 4-5 digit values.
    """
    t = normalize_ocr_text(text)
    # Best case: a plausible number immediately followed by 秒/sec.
    direct = re.search(r"(\d{1,3})\s*(?:秒|sec|s)", t, flags=re.IGNORECASE)
    if direct:
        v = int(direct.group(1))
        if DURATION_MIN_SEC <= v <= DURATION_MAX_SEC:
            return v

    candidates: List[int] = []
    for x in re.findall(r"\d{1,8}", t):
        # Normal OCR result
        if 1 <= len(x) <= 3:
            v = int(x)
            if DURATION_MIN_SEC <= v <= DURATION_MAX_SEC:
                candidates.append(v)
            continue
        # Corrupted long result. Try plausible prefixes first.
        for n in (3, 2):
            if len(x) >= n:
                v = int(x[:n])
                if DURATION_MIN_SEC <= v <= DURATION_MAX_SEC:
                    candidates.append(v)
                    break
    if not candidates:
        return None
    # Duration ROI normally contains one value. Prefer the first plausible value; it is
    # usually the actual seconds before duplicated/trailing noise.
    return candidates[0]


def _most_common_first_seen(values: List[int]) -> Optional[int]:
    order: List[int] = []
    for v in values:
        if v not in order:
            order.append(v)
    if not order:
        return None
    counts = {v: values.count(v) for v in order}
    max_count = max(counts.values())
    return next(v for v in order if counts[v] == max_count)


def choose_commit_duration(ocr_candidates: List[int], measured: Optional[int]) -> Optional[int]:
    """Reconcile OCR clear-time readings with the wall-clock measured elapsed time.

    The game-displayed clear time (OCR) is the authoritative value, but OCR can pick
    up duplicated digits (89 -> 899). The measured elapsed only arbitrates: it can span
    multiple runs or pauses when gauge transitions were missed, so it must never
    override an OCR consensus; it picks among disagreeing candidates, confirms
    trailing-digit noise, and is committed alone only when OCR read nothing.
    """
    cands = [int(v) for v in ocr_candidates if DURATION_MIN_SEC <= int(v) <= DURATION_MAX_SEC]
    meas_ok = measured is not None and DURATION_MIN_SEC <= int(measured) <= DURATION_MAX_SEC
    if not cands:
        return int(measured) if meas_ok else None
    if meas_ok:
        tol = max(8, round(int(measured) * 0.25))
        near = [v for v in cands if abs(v - int(measured)) <= tol]
        if near:
            return _most_common_first_seen(near)
        # Trailing-digit salvage (89 read as 899) only for a single weak read; a
        # repeated consensus is kept even against a small bounced measurement.
        for v in cands:
            w = v // 10
            if cands.count(v) == 1 and w >= DURATION_MIN_SEC and abs(w - int(measured)) <= tol:
                return w
    return _most_common_first_seen(cands)


def _ocr_text_from_crop(crop: Image.Image, cfg: dict, whitelist: str, psm_list: List[int]) -> List[str]:
    raws: List[str] = []
    for label, img in preprocess_ocr_candidates(crop, cfg.get("stage_invert", True), [69, 100, 135, 150]):
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
    """OCR stage and clear time from separate ROIs when available.

    This is more stable than reading the whole Japanese sentence
    'ステージ1-7をクリアしました(123秒)' as one OCR target.
    """
    raw_parts: List[str] = []
    stage: Optional[str] = None
    duration: Optional[int] = None
    stage_candidates: List[str] = []
    duration_candidates: List[int] = []

    if cfg.get("stage_num_roi"):
        crop = crop_roi(img, tuple(cfg["stage_num_roi"]))
        raws = _ocr_text_from_crop(crop, cfg, "0123456789-ー‐ ", [7, 8, 13])
        for r in raws:
            st = parse_stage_number_text(r)
            raw_parts.append(f"ステージ={st or '-'} raw:{r}")
            if st:
                stage_candidates.append(st)
        if stage_candidates:
            stage = choose_stage_candidate(stage_candidates, cfg)

    if cfg.get("stage_time_roi"):
        crop = crop_roi(img, tuple(cfg["stage_time_roi"]))
        raws = _ocr_text_from_crop(crop, cfg, "0123456789秒sec()（） .", [7, 8, 13])
        for r in raws:
            dur = parse_duration_text(r)
            raw_parts.append(f"秒={dur if dur is not None else '-'} raw:{r}")
            if dur:
                duration_candidates.append(dur)
        if duration_candidates:
            duration = _most_common_first_seen(duration_candidates)

    # フォールバック: 旧来の通知ROIも一応読む
    if (stage is None or duration is None) and cfg.get("stage_roi"):
        full = ocr_stage_from_crop(crop_roi(img, tuple(cfg["stage_roi"])), cfg)
        raw_parts.append(f"全文{full.raw_text}")
        if stage is None:
            stage = full.stage
            if full.stage:
                stage_candidates.append(full.stage)
        if duration is None:
            duration = full.duration_sec
            if full.duration_sec:
                duration_candidates.append(full.duration_sec)

    return StageOCRResult(stage, duration, " / ".join(raw_parts), stage_candidates, duration_candidates)

def format_elapsed(seconds: float) -> str:
    s = int(max(0, seconds))
    h = s // 3600
    m = (s % 3600) // 60
    ss = s % 60
    return f"{h:02d}:{m:02d}:{ss:02d}"


def ocr_money_from_crop(crop: Image.Image, cfg: dict, last_money: Optional[int]) -> MoneyOCRResult:
    configs = [
        "--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789,.",
    ]
    results: List[Tuple[int, str]] = []
    raws: List[str] = []
    for label, img in preprocess_ocr_candidates(crop, cfg.get("money_invert", True), [150, 135, 100, 69]):
        for config in configs:
            raw = pytesseract.image_to_string(img, config=config).strip()
            money = parse_money(raw)
            raws.append(f"{label}:{raw!r}->{money}")
            if money is not None:
                results.append((money, f"{label}:{raw}"))
    if not results:
        return MoneyOCRResult(None, " / ".join(raws))
    # 全前処理が同一値に一致したか（テンプレ自己学習の教師に使う高信頼判定）。
    parsed_values = [r[0] for r in results]
    consensus = len(parsed_values) >= 3 and len(set(parsed_values)) == 1
    if last_money:
        sane = [r for r in results if last_money * 0.5 <= r[0] <= last_money * 3]
        if sane:
            results = sane
        # 前回確定値に最も近い候補を選ぶ。桁が増えた誤読(過大)も桁落ち(過小)も弾ける。
        # 桁数の長い順だと「余分な桁の誤読」を優先してしまうため、近さで判定する。
        results.sort(key=lambda r: abs(r[0] - last_money))
    else:
        # 初回など基準が無いときは従来どおり桁数の長い/大きい値を採用。
        results.sort(key=lambda r: (len(str(r[0])), r[0]), reverse=True)
    return MoneyOCRResult(results[0][0], f"{results[0][1]!r} => {results[0][0]}", consensus=consensus)


def ocr_money_hybrid(crop: Image.Image, cfg: dict, last_money: Optional[int], engine) -> MoneyOCRResult:
    """テンプレ照合(高速)＋tesseract(フォールバック/教師)の自己校正ハイブリッド所持金読取。

    - 0〜9 すべてのテンプレが成熟していれば、まずテンプレ照合(≈4ms)で読む。相関ゲートと
      last_money sane化を通れば即採用（ただし VERIFY_EVERY 回に1回は tesseract で検証＆再学習）。
    - それ以外は従来の tesseract(5前処理) で読み、consensus 読みのみテンプレへ学習する。
    money_source は常に "main" 相当（下流のスパイク保護・統計ロジックは不変）。raw_text に経路を残す。
    """
    if engine is not None:
        force_verify = engine.tick_should_verify()
        if not force_verify:
            tpl_val, conf = engine.read(crop)
            if tpl_val is not None:
                sane = last_money is None or (last_money * 0.5 <= tpl_val <= last_money * 3)
                if sane:
                    return MoneyOCRResult(tpl_val, f"[tpl c={conf:.2f}] => {tpl_val}")
    res = ocr_money_from_crop(crop, cfg, last_money)
    if engine is not None and res.money is not None and res.consensus:
        # consensus読みでも、前回確定値からかけ離れた一過性の誤読は教師にしない(テンプレを汚さない)。
        sane = last_money is None or (last_money * 0.5 <= res.money <= last_money * 3)
        if sane:
            engine.learn(crop, res.money)
    return res


def ocr_stage_from_crop(crop: Image.Image, cfg: dict) -> StageOCRResult:
    configs = [
        "--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789-ー‐秒ssec()（） .",
    ]
    raws: List[str] = []
    candidates: List[Tuple[str, Optional[str], Optional[int]]] = []
    for label, img in preprocess_ocr_candidates(crop, cfg.get("stage_invert", True), [69, 100, 135, 150]):
        for config in configs:
            raw = pytesseract.image_to_string(img, config=config).strip()
            stg, dur = parse_stage_result(raw)
            raws.append(f"{label}:{raw!r}->{stg},{dur}")
            if stg or dur:
                candidates.append((f"{label}:{raw}", stg, dur))
    if not candidates:
        return StageOCRResult(None, None, " / ".join(raws))
    candidates.sort(key=lambda x: (1 if x[1] else 0, 1 if x[2] else 0), reverse=True)
    raw, stg, dur = candidates[0]
    return StageOCRResult(stg, dur, f"{raw!r} => {stg},{dur}")


# ---------- Proposal B UI widgets ----------

THEME = {
    "bg_deep": "#0b0b0a",
    "bg": "#141414",
    "panel": "#1d1c1a",
    "panel_inner": "#242018",
    "border": "#3b3b37",
    "border_hi": "#6b665a",
    "gold": "#d7a642",
    "gold_hi": "#ffd05a",
    "tab": "#7b2418",
    "tab_active": "#a43a1e",
    "green": "#7ee04b",
    "warning": "#ffb13b",
    "red": "#ff4d3d",
    "blue": "#35a4ff",
    "purple": "#9a4cff",
    "bar_gold": "#e3b33d",
    "text": "#d8d0bf",
    "muted": "#928878",
}


def _clamped_ratio(value: float, maximum: float) -> float:
    try:
        if maximum <= 0:
            return 0.0
        return max(0.0, min(1.0, float(value) / float(maximum)))
    except Exception:
        return 0.0


class PixelProgressBar(QWidget):
    def __init__(self, value: float = 0.0, maximum: float = 1.0, color: str = THEME["green"], text: str = "", parent=None):
        super().__init__(parent)
        self.value = float(value or 0)
        self.maximum = float(maximum or 1)
        self.color = QColor(color)
        self.text = text
        self.setMinimumHeight(12)

    def sizeHint(self) -> QSize:
        return QSize(100, 12)

    def set_value(self, value: float, maximum: Optional[float] = None, text: Optional[str] = None):
        self.value = float(value or 0)
        if maximum is not None:
            self.maximum = float(maximum or 1)
        if text is not None:
            self.text = text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.fillRect(rect, QColor("#080807"))
        painter.setPen(QPen(QColor(THEME["border_hi"]), 1))
        painter.drawRect(rect)
        ratio = _clamped_ratio(self.value, self.maximum)
        fill = QRect(rect.x() + 2, rect.y() + 2, max(0, int((rect.width() - 3) * ratio)), max(1, rect.height() - 3))
        painter.fillRect(fill, self.color)
        if fill.width() > 8:
            painter.fillRect(QRect(fill.x(), fill.y(), fill.width(), max(1, fill.height() // 3)), QColor(self.color).lighter(135))
        if self.text:
            painter.setPen(QColor("#f5ead1"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text)


class RingGauge(QWidget):
    def __init__(self, value: float = 0.0, maximum: float = 1.0, color: str = THEME["green"], parent=None):
        super().__init__(parent)
        self.value = float(value or 0)
        self.maximum = float(maximum or 1)
        self.color = QColor(color)
        self.setMinimumSize(24, 24)
        self.setMaximumSize(28, 28)

    def sizeHint(self) -> QSize:
        return QSize(26, 26)

    def set_value(self, value: float, maximum: Optional[float] = None):
        self.value = float(value or 0)
        if maximum is not None:
            self.maximum = float(maximum or 1)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        side = max(8, min(self.width(), self.height()) - 12)
        rect = QRect((self.width() - side) // 2, (self.height() - side) // 2, side, side)
        painter.setPen(QPen(QColor("#070706"), 4))
        painter.drawEllipse(rect)
        painter.setPen(QPen(QColor(THEME["border_hi"]), 2))
        painter.drawEllipse(rect.adjusted(-3, -3, 3, 3))
        painter.setPen(QPen(QColor("#2b2925"), 4))
        painter.drawEllipse(rect)
        ratio = _clamped_ratio(self.value, self.maximum)
        painter.setPen(QPen(self.color, 4))
        painter.drawArc(rect, 90 * 16, int(-360 * ratio * 16))


class SemiCircleGauge(QWidget):
    def __init__(self, value: float = 0.0, maximum: float = 1.0, color: str = THEME["bar_gold"], parent=None):
        super().__init__(parent)
        self.value = float(value or 0)
        self.maximum = float(maximum or 1)
        self.color = QColor(color)
        self.setMinimumSize(38, 22)
        self.setMaximumSize(44, 24)

    def sizeHint(self) -> QSize:
        return QSize(40, 22)

    def set_value(self, value: float, maximum: Optional[float] = None):
        self.value = float(value or 0)
        if maximum is not None:
            self.maximum = float(maximum or 1)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = QRect(5, 4, max(16, self.width() - 10), max(16, (self.height() - 5) * 2))
        painter.setPen(QPen(QColor("#2b2925"), 4))
        painter.drawArc(rect, 180 * 16, -180 * 16)
        painter.setPen(QPen(QColor(THEME["border_hi"]), 1))
        painter.drawArc(rect.adjusted(-3, -3, 3, 3), 180 * 16, -180 * 16)
        ratio = _clamped_ratio(self.value, self.maximum)
        painter.setPen(QPen(self.color, 4))
        painter.drawArc(rect, 180 * 16, int(-180 * ratio * 16))


class KpiGaugeCard(QFrame):
    def __init__(self, title: str, icon: str, gauge: QWidget, accent: str = THEME["green"], parent=None):
        super().__init__(parent)
        self.setObjectName("kpiCard")
        self.accent = accent
        self.gauge = gauge
        self.setMinimumHeight(50)
        self.setMaximumHeight(54)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.value_lbl = QLabel("-")
        self.value_lbl.setObjectName("kpiValue")
        self.value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl = QLabel(f"{icon}  {title}")
        self.title_lbl.setObjectName("kpiTitle")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.aux_lbl = QLabel("")
        self.aux_lbl.setObjectName("kpiAux")
        self.aux_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.aux_lbl.hide()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(0)
        lay.addWidget(self.title_lbl)
        lay.addWidget(self.value_lbl)
        lay.addWidget(gauge, 0, Qt.AlignmentFlag.AlignCenter)

    def set_value_text(self, text: str):
        self.value_lbl.setText(text)

    def set_aux_text(self, text: str):
        self.aux_lbl.setText(text)


def compact_number(value: float) -> str:
    try:
        value = float(value)
    except Exception:
        return "-"
    if abs(value) >= 1000000:
        return f"{value / 1000000:.1f}m"
    if abs(value) >= 1000:
        return f"{value / 1000:.0f}k"
    if abs(value) >= 100:
        return f"{value:.0f}"
    return f"{value:.1f}".rstrip("0").rstrip(".")


class EfficiencyStageCell(QPushButton):
    def __init__(self, stage: str, parent=None):
        super().__init__(parent)
        self.stage = stage
        self.setObjectName("stageCell")
        self.setCheckable(True)
        self.setMinimumSize(68, 34)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setProperty("state", "empty")
        self.setText(f"{stage}\n-\n○")

    def set_stage_data(self, row: Optional[Tuple[float, float, int, int, int, int]], metric: str, top: bool, recommended: bool):
        if not row:
            self.setText(f"{self.stage}\n未計測\n○")
            self.setProperty("state", "empty")
            self._refresh_style()
            return
        gps, gph, adopted, total, dur, delta = row
        loops = (3600.0 / dur) if dur else 0.0
        metric_value = {
            "gps": gps,
            "gph": gph,
            "delta": delta,
            "loops": loops,
        }.get(metric, gps)
        icon = "♛" if top else ("◎" if recommended else "◆")
        second = compact_number(metric_value)
        third = f"{compact_number(gph)} GPH"
        self.setText(f"{self.stage}\n{second}\n{third} {icon}")
        self.setProperty("state", "top" if top else ("recommended" if recommended else "normal"))
        self._refresh_style()

    def set_selected_visual(self, selected: bool):
        self.setChecked(bool(selected))
        self._refresh_style()

    def _refresh_style(self):
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


# ---------- ROI label ----------

class ROIImageLabel(QLabel):
    roi_changed = Signal(QRect)

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._pixmap: Optional[QPixmap] = None
        self._image_size: Optional[Tuple[int, int]] = None
        self._display_size: Optional[Tuple[int, int]] = None
        self._start: Optional[QPoint] = None
        self._end: Optional[QPoint] = None
        self._roi_img: Optional[QRect] = None
        self._dragging = False
        self.active_roi_name = "money"
        self.named_rois: Dict[str, Tuple[int, int, int, int]] = {}

    def set_image(self, img: Image.Image, scale: float):
        self._image_size = img.size
        scale = max(0.08, min(float(scale), 1.5))
        display_w = max(1, int(img.width * scale))
        display_h = max(1, int(img.height * scale))
        self._display_size = (display_w, display_h)
        qimg = pil_to_qimage(img.resize((display_w, display_h)))
        self._pixmap = QPixmap.fromImage(qimg)
        self.setPixmap(self._pixmap)
        self.resize(display_w, display_h)
        self._start = None
        self._end = None
        self._roi_img = None
        self._dragging = False
        self.update()

    def set_named_rois(self, rois: Dict[str, Tuple[int, int, int, int]]):
        self.named_rois = dict(rois or {})
        self.update()

    def set_active_roi_name(self, name: str):
        self.active_roi_name = name
        self.update()

    def _clamp(self, p: QPoint) -> QPoint:
        if not self._display_size:
            return p
        return QPoint(max(0, min(p.x(), self._display_size[0] - 1)), max(0, min(p.y(), self._display_size[1] - 1)))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = self._clamp(event.position().toPoint())
            self._end = self._start
            self._dragging = True
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._start is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self._end = self._clamp(event.position().toPoint())
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging and self._start is not None:
            self._end = self._clamp(event.position().toPoint())
            self._dragging = False
            self._compute_roi()
            self.update()
            event.accept()
            return
        self._dragging = False
        super().mouseReleaseEvent(event)

    def _compute_roi(self):
        if not self._start or not self._end or not self._image_size or not self._display_size:
            return
        r = QRect(self._start, self._end).normalized().intersected(QRect(0, 0, self._display_size[0], self._display_size[1]))
        if r.width() < 3 or r.height() < 3:
            return
        sx = self._image_size[0] / self._display_size[0]
        sy = self._image_size[1] / self._display_size[1]
        self._roi_img = QRect(int(r.x() * sx), int(r.y() * sy), int(r.width() * sx), int(r.height() * sy))
        self.roi_changed.emit(self._roi_img)

    def current_roi(self) -> Optional[Tuple[int, int, int, int]]:
        if not self._roi_img:
            return None
        return (self._roi_img.x(), self._roi_img.y(), self._roi_img.width(), self._roi_img.height())

    def _img_to_disp_rect(self, roi: Tuple[int, int, int, int]) -> Optional[QRect]:
        if not self._image_size or not self._display_size:
            return None
        x, y, w, h = roi
        sx = self._display_size[0] / self._image_size[0]
        sy = self._display_size[1] / self._image_size[1]
        return QRect(int(x * sx), int(y * sy), int(w * sx), int(h * sy))

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._pixmap:
            return
        painter = QPainter(self)
        colors = {name: QColor(color) for name, color in ROI_COLORS.items()}
        labels = ROI_LABELS
        for name, roi in self.named_rois.items():
            r = self._img_to_disp_rect(roi)
            if not r:
                continue
            painter.setPen(QPen(colors.get(name, QColor("white")), 2))
            painter.drawRect(r)
            painter.drawText(r.topLeft() + QPoint(3, -3), labels.get(name, name))
        if self._start and self._end:
            painter.setPen(QPen(QColor("#e4572e"), 2, Qt.PenStyle.DashLine))
            painter.drawRect(QRect(self._start, self._end).normalized())


# ---------- OCR worker ----------

class WorkerSignals(QObject):
    finished = Signal(object)


class OcrWorker(QRunnable):
    def __init__(self, monitor_index: int, cfg: dict, last_money: Optional[int], purpose: str = "tick"):
        super().__init__()
        self.monitor_index = monitor_index
        self.cfg = dict(cfg)
        self.last_money = last_money
        self.purpose = purpose
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        ts = time.time()
        try:
            if not resolve_tesseract(self.cfg):
                self.signals.finished.emit(WorkerResult(ts, None, "", None, None, "", "tesseract.exe が見つかりません。OCR調整タブで tesseract.exe を指定してください。", self.purpose))
                return
            img = capture_monitor(self.monitor_index)
            runtime_cfg = self.cfg if self.cfg.get("_runtime_rois_ready") else apply_anchor_rois(img, self.cfg)
            money_res = MoneyOCRResult(None, "所持金範囲なし")
            stage_res = StageOCRResult(None, None, "通知範囲なし")
            money_source = "main"
            if runtime_cfg.get("money_roi"):
                money_res = ocr_money_hybrid(crop_roi(img, tuple(runtime_cfg["money_roi"])), runtime_cfg, self.last_money, get_money_ocr_engine())
            # ルーン画面の本来の問題は「ルーン表示中に上部HUDの読みが乱れる」こと。HUDがクリーンに
            # 読めている間はルーン側コインを見る必要がない（通常プレイ中の誤検出で一瞬ゴミ値に落ちるのを防ぐ）。
            # 日本語OCRが無いため「ルーン」文字判定の代わりにHUD読みの信頼度でゲートする＝実質ルーン画面ゲート。
            hud_trusted = money_res.money is not None and (
                str(money_res.raw_text).startswith("[tpl") or bool(getattr(money_res, "consensus", False))
            )
            if not hud_trusted:
                rune_res = self._read_rune_money(img, runtime_cfg)
                if rune_res is not None and rune_res.money is not None:
                    money_res = rune_res
                    money_source = "rune"
            if runtime_cfg.get("stage_num_roi") or runtime_cfg.get("stage_time_roi"):
                stage_res = ocr_stage_split_from_image(img, runtime_cfg)
            elif runtime_cfg.get("stage_roi"):
                stage_res = ocr_stage_from_crop(crop_roi(img, tuple(runtime_cfg["stage_roi"])), runtime_cfg)
            self.signals.finished.emit(WorkerResult(
                ts, money_res.money, money_res.raw_text, stage_res.stage, stage_res.duration_sec, stage_res.raw_text, None, self.purpose,
                stage_candidates=stage_res.stage_candidates, duration_candidates=stage_res.duration_candidates,
                money_source=money_source, money_consensus=bool(getattr(money_res, "consensus", False)),
            ))
        except Exception as e:
            self.signals.finished.emit(WorkerResult(ts, None, "", None, None, "", str(e), self.purpose))

    def _read_rune_money(self, img: Image.Image, runtime_cfg: dict) -> Optional[MoneyOCRResult]:
        """Detect the rune-screen money by finding a 2nd gold coin and reading it like the HUD money.

        Returns a MoneyOCRResult only when a secondary coin is found AND a sane money value is read;
        otherwise None (so the caller keeps the normal HUD reading). Never raises.
        """
        anchor = runtime_cfg.get("anchor_roi")
        if not anchor:
            return None
        try:
            ax, ay, aw, ah = map(float, anchor[:4])
            scale = float(runtime_cfg.get("detected_template_scale", 1.0) or 1.0)
            primary = (ax + aw / 2.0, ay + ah / 2.0)
            min_sep = aw * RUNE_COIN_MIN_SEP_FACTOR
            coin = locate_secondary_anchor(img, runtime_cfg, primary, min_sep, scale)
            if not coin:
                return None
            rect = rune_money_rect_from_coin(img, coin)
            res = ocr_money_from_crop(crop_roi(img, tuple(rect)), runtime_cfg, self.last_money)
            if res.money is None:
                return None
            # 妥当性ゲート: ルーン画面の所持金は実HUD所持金とほぼ一致する。基準(last_money)から大きく外れた値は
            # コイン誤検出による偽陽性(例 1183/0)とみなして破棄する。起動直後(基準なし)もルーンは見ない。
            if self.last_money is None:
                return None
            if not (self.last_money * 0.5 <= res.money <= self.last_money * 1.5):
                return None
            return MoneyOCRResult(res.money, f"[rune coin@{coin[0]},{coin[1]} s={coin[4]:.2f}] {res.raw_text}")
        except Exception:
            return None


class GaugeWorker(QRunnable):
    def __init__(self, monitor_index: int, cfg: dict):
        super().__init__()
        self.monitor_index = monitor_index
        self.cfg = dict(cfg)
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        ts = time.time()
        try:
            roi = self.cfg.get("gauge_roi")
            if roi and self.cfg.get("_direct_gauge_capture"):
                crop = capture_monitor_region(self.monitor_index, tuple(roi))
                state, fill, blue, purple, raw = detect_gauge_state(crop, self.cfg)
                self.signals.finished.emit(GaugeResult(ts, state, fill, blue, purple, raw))
                return
            img = capture_monitor(self.monitor_index)
            runtime_cfg = self.cfg if self.cfg.get("_runtime_rois_ready") else apply_anchor_rois(img, self.cfg)
            roi = runtime_cfg.get("gauge_roi")
            if not roi:
                self.signals.finished.emit(GaugeResult(ts, "unknown", 0.0, 0.0, 0.0, runtime_cfg.get("_anchor_status", "ゲージROIなし")))
                return
            crop = crop_roi(img, tuple(roi))
            state, fill, blue, purple, raw = detect_gauge_state(crop, runtime_cfg)
            self.signals.finished.emit(GaugeResult(ts, state, fill, blue, purple, raw))
        except Exception as e:
            self.signals.finished.emit(GaugeResult(ts, "unknown", 0.0, 0.0, 0.0, "", str(e)))


@dataclass
class ProbeResult:
    runtime_cfg: Optional[dict]  # apply_anchor_rois の結果（money_roi含む）。検出失敗時None
    money: Optional[int]
    consensus: bool
    raw: str
    error: Optional[str] = None


class AnchorProbeWorker(QRunnable):
    """アンカー検出＋所持金読取をワーカースレッドで行う（UIスレッドを塞がないための退避）。

    自動開始(計測前)とROI取り直し(計測中)の両方で使う。重い capture_monitor / apply_anchor_rois
    (4Kで~2.3s) をUIスレッドから外すのが目的。結果は ProbeResult で返す。
    """

    def __init__(self, monitor_index: int, cfg: dict, last_money: Optional[int]):
        super().__init__()
        self.monitor_index = monitor_index
        self.cfg = dict(cfg)
        self.last_money = last_money
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            if not resolve_tesseract(self.cfg):
                self.signals.finished.emit(ProbeResult(None, None, False, "", "tesseract"))
                return
            img = capture_monitor(self.monitor_index)
            runtime_cfg = apply_anchor_rois(img, self.cfg)
            if not runtime_cfg.get("money_roi"):
                self.signals.finished.emit(ProbeResult(runtime_cfg, None, False, "", None))
                return
            runtime_cfg["_runtime_rois_ready"] = True
            res = ocr_money_from_crop(crop_roi(img, tuple(runtime_cfg["money_roi"])), runtime_cfg, self.last_money)
            self.signals.finished.emit(ProbeResult(runtime_cfg, res.money, bool(res.consensus), res.raw_text, None))
        except Exception as e:
            self.signals.finished.emit(ProbeResult(None, None, False, "", str(e)))


class SortableItem(QTableWidgetItem):
    def __init__(self, text: str, sort_key=None):
        super().__init__(text)
        self.sort_key = sort_key if sort_key is not None else text

    def __lt__(self, other):
        if isinstance(other, SortableItem):
            return self.sort_key < other.sort_key
        return super().__lt__(other)


class RoiSelectionDialog(QDialog):
    def __init__(self, parent, img: Image.Image, active_target: str, cfg: dict, scale: float):
        super().__init__(parent)
        self.setWindowTitle("範囲選択")
        self.resize(900, 620)
        self.img = img
        self.cfg = cfg
        self.active_target = active_target
        self.saved_roi: Optional[Tuple[int, int, int, int]] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        head = QHBoxLayout()
        self.title = QLabel(f"{ROI_LABELS.get(active_target, active_target)}範囲を選択")
        self.title.setObjectName("section")
        head.addWidget(self.title, 1)
        head.addWidget(QLabel("表示"))
        self.scale_combo = QComboBox()
        for label, value in [("25%", 0.25), ("35%", 0.35), ("50%", 0.50), ("75%", 0.75), ("100%", 1.0), ("130%", 1.3)]:
            self.scale_combo.addItem(label, value)
        # closest
        best = min(range(self.scale_combo.count()), key=lambda i: abs(float(self.scale_combo.itemData(i))-scale))
        self.scale_combo.setCurrentIndex(best)
        self.scale_combo.currentIndexChanged.connect(self.redisplay)
        head.addWidget(self.scale_combo)
        save_btn = QPushButton("この範囲で保存")
        save_btn.setObjectName("saveBtn")
        save_btn.clicked.connect(self.accept_selection)
        head.addWidget(save_btn)
        close_btn = QPushButton("閉じる")
        close_btn.setObjectName("ghost")
        close_btn.clicked.connect(self.reject)
        head.addWidget(close_btn)
        root.addLayout(head)

        hint = QLabel("ドラッグして範囲を選択してください。所持金は数字だけ、通知は黒帯の文字1行だけを囲むと安定します。")
        hint.setObjectName("hint")
        root.addWidget(hint)

        self.label = ROIImageLabel()
        rois = {}
        for name in ROI_LABELS:
            key = f"{name}_roi"
            if cfg.get(key):
                rois[name] = tuple(cfg[key])
        self.label.set_named_rois(rois)
        self.label.set_active_roi_name(active_target)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.label)
        self.scroll.setWidgetResizable(False)
        self.scroll.setObjectName("imageScroll")
        root.addWidget(self.scroll, 1)
        self.redisplay()

    def redisplay(self):
        self.label.set_image(self.img, float(self.scale_combo.currentData()))
        rois = {}
        for name in ROI_LABELS:
            key = f"{name}_roi"
            if self.cfg.get(key):
                rois[name] = tuple(self.cfg[key])
        self.label.set_named_rois(rois)
        self.label.set_active_roi_name(self.active_target)

    def accept_selection(self):
        roi = self.label.current_roi()
        if not roi:
            QMessageBox.warning(self, "未選択", "スクショ上で範囲をドラッグしてください。")
            return
        self.saved_roi = roi
        self.accept()


class PacketPulseSignals(QObject):
    pulse = Signal(float, str)
    error = Signal(str)
    status = Signal(str)


class PacketPulseSniffer:
    """Passive metadata-only sniffer used as a stage boundary trigger.

    It does not parse, decrypt, or store packet payloads. It only watches packet
    timestamps/lengths for Steam traffic bursts. The burst is used as an
    external boundary signal for "stage cleared/failed" timing, while OCR still
    reads the visible stage/time/gold values.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.signals = PacketPulseSignals()
        self._sniffer = None
        self._events = deque()
        self._last_pulse_mono = 0.0
        self._bpf = "tcp or udp"

    @property
    def bpf_filter(self) -> str:
        return self._bpf

    def _build_filter(self) -> str:
        hosts = []
        ports = set()
        try:
            import psutil  # type: ignore
            for p in psutil.process_iter(["pid", "name"]):
                name = (p.info.get("name") or "").lower()
                if name not in {"steam.exe", "steamwebhelper.exe", "gameoverlayui64.exe"}:
                    continue
                try:
                    conns = p.net_connections(kind="inet")
                except Exception:
                    continue
                for c in conns:
                    if not c.raddr:
                        continue
                    rip = str(c.raddr.ip)
                    rport = int(c.raddr.port)
                    if rip.startswith("127.") or rip.startswith("192.168.") or rip.startswith("10.") or rip.startswith("172.16."):
                        continue
                    if ":" in rip:
                        continue
                    if rip not in hosts:
                        hosts.append(rip)
                    if rport:
                        ports.add(rport)
        except Exception:
            pass

        # Prefer detected Steam endpoints. Fallback covers the endpoint family seen during probing.
        if hosts:
            host_expr = "(" + " or ".join(f"host {h}" for h in hosts[:12]) + ")"
            if ports and len(ports) <= 20:
                port_expr = "(" + " or ".join(f"port {p}" for p in sorted(ports)) + ")"
                return f"(tcp or udp) and {host_expr} and {port_expr}"
            return f"(tcp or udp) and {host_expr}"
        return "(tcp or udp) and (port 443 or port 27020)"

    def start(self) -> bool:
        try:
            from scapy.all import AsyncSniffer  # type: ignore
        except Exception as exc:
            self.signals.error.emit(f"通信区切りを使えません。Scapy未導入: {exc}")
            return False
        self.stop()
        self._bpf = self._build_filter()
        try:
            self._sniffer = AsyncSniffer(filter=self._bpf, prn=self._handle_packet, store=False)
            self._sniffer.start()
            self.signals.status.emit(f"通信区切りON: {self._bpf}")
            return True
        except Exception as exc:
            self._sniffer = None
            self.signals.error.emit(f"通信区切り開始失敗: {exc}")
            return False

    def stop(self) -> None:
        if self._sniffer is not None:
            try:
                self._sniffer.stop()
            except Exception:
                pass
            self._sniffer = None
        self._events.clear()

    def _handle_packet(self, pkt) -> None:
        try:
            from scapy.packet import Raw  # type: ignore
        except Exception:
            return
        if Raw not in pkt:
            return
        try:
            ln = len(bytes(pkt[Raw].load))
        except Exception:
            return
        if ln < int(self.cfg.get("net_min_payload_len", 40)):
            return
        now = time.monotonic()
        win = float(self.cfg.get("net_burst_window", 1.2))
        self._events.append((now, ln))
        while self._events and now - self._events[0][0] > win:
            self._events.popleft()
        count = len(self._events)
        total = sum(x[1] for x in self._events)
        min_count = int(self.cfg.get("net_burst_min_packets", 3))
        min_bytes = int(self.cfg.get("net_burst_min_bytes", 520))
        cooldown = float(self.cfg.get("net_burst_cooldown", 8.0))
        if count >= min_count and total >= min_bytes and now - self._last_pulse_mono >= cooldown:
            self._last_pulse_mono = now
            self._events.clear()
            self.signals.pulse.emit(time.time(), f"通信パルス packets={count} bytes={total}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        init_db()
        self.cfg = load_config()
        self.ui_language = self.cfg.get("ui_language", "ja") if self.cfg.get("ui_language", "ja") in UI_LANGUAGES else "ja"
        self.game_ocr_language = self.cfg.get("game_ocr_language", "ja")
        self.setWindowTitle(f"TBH 効率ログ {DISPLAY_VERSION}")
        self.resize(700, 300)
        self.setMinimumSize(680, 280)

        self.current_screenshot: Optional[Image.Image] = None
        self.current_roi_target = "money"
        self.session_id: Optional[str] = None
        self.session_start_ts: Optional[float] = None
        self.start_money: Optional[int] = None
        self.last_money: Optional[int] = None
        self.samples: List[Tuple[float, int]] = []
        # 所持金を消費しても平均GPH/直近GPSが壊れないよう、増加分だけを累積する。
        self.session_positive_gain = 0
        self.last_stage_money: Optional[int] = None
        self.last_stage_key: Optional[Tuple[str, int]] = None
        self.last_stage_logged_at = 0.0
        # 同じステージクリア通知が数秒～十数秒残っても、1周につき1回だけ記録するためのラッチ。
        self.stage_notice_key: Optional[Tuple[str, int]] = None
        self.stage_notice_last_seen = 0.0
        self.stage_notice_logged = False
        self.ocr_busy = False
        self.ocr_busy_since = 0.0
        self.gauge_busy_since = 0.0
        self.finish_ocr_error_count = 0
        self.pending_ocr_purpose: Optional[str] = None
        self.runtime_cfg_cache: Optional[dict] = None
        self._money_miss_streak = 0  # 連続で所持金を読めなかった回数（凍結ROIの自己修復判定用）
        self.packet_sniffer: Optional[PacketPulseSniffer] = None  # legacy unused
        self.stage_pulse_active_until = 0.0
        self.last_stage_pulse_at = 0.0
        self.stage_pulse_times = deque()  # legacy unused
        self.gauge_busy = False
        self.gauge_state = "unknown"
        self.stage_state = "WAIT_START"
        self.stage_blue_seen = False
        self.current_stage_start_gold: Optional[int] = None
        self.current_stage_start_ts: Optional[float] = None
        self.gold_decreased_during_stage = False
        self.last_finish_transition_ts = 0.0
        self.pending_stage_finish_ts: Optional[float] = None
        self.running = False
        self.pool = QThreadPool.globalInstance()
        # ゲージ監視と所持金OCRを同時に走らせ、重い/失敗OCR中もゲージ判定を止めない。
        self.pool.setMaxThreadCount(2)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock_only)
        self.clock_timer.start(1000)
        self.ocr_timer = QTimer(self)
        self.ocr_timer.timeout.connect(self.request_ocr_tick)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.update_ocr_preview)
        self.gauge_timer = QTimer(self)
        self.gauge_timer.timeout.connect(self.request_gauge_tick)

        self._build_ui()
        self._load_initial()
        self.apply_ui_language()

    def _build_ui(self):
        self._apply_theme()
        root = QWidget()
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        main.setContentsMargins(4, 3, 4, 2)
        main.setSpacing(2)

        self.tabs = QTabWidget()
        self.tab_controls = QWidget()
        tab_controls_l = QHBoxLayout(self.tab_controls)
        tab_controls_l.setContentsMargins(0, 0, 0, 0)
        tab_controls_l.setSpacing(3)
        # 起動＝計測開始で確定（手動スタート/ストップは廃止）。計測は closeEvent で確定保存する。
        settings_btn = QPushButton("⚙")
        settings_btn.setObjectName("iconBtn")
        settings_btn.setToolTip("設定")
        settings_btn.clicked.connect(self.open_settings_dialog)
        tab_controls_l.addWidget(settings_btn)
        info_btn = QPushButton("i")
        info_btn.setObjectName("iconBtn")
        info_btn.setToolTip("アプリ情報")
        info_btn.clicked.connect(self.open_app_info_dialog)
        tab_controls_l.addWidget(info_btn)
        self.status_pill = QLabel("待機")
        self.status_pill.setObjectName("pill")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tab_controls_l.addWidget(self.status_pill)
        # 所持金テンプレOCRの状態（学習中の桁数 / 高速パス稼働中）を可視化。
        self.tpl_pill = QLabel("テンプレ学習 0/10")
        self.tpl_pill.setObjectName("pill")
        self.tpl_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tpl_pill.setToolTip("所持金のテンプレOCR状態。0〜10桁が成熟すると高速パス(≈120倍軽量)へ自動切替。")
        tab_controls_l.addWidget(self.tpl_pill)
        self._update_tpl_pill()  # 既存の学習データがあれば起動直後から正しい状態を表示
        self.tabs.setCornerWidget(self.tab_controls, Qt.Corner.TopRightCorner)
        main.addWidget(self.tabs, 1)
        self._build_home_tab()
        self._build_setup_tab()
        self._build_history_tab()
        # 1周ごとのステージ履歴と、ステージ別ハイスコア表示を同じ計測画面に集約。

        self.status = QStatusBar(self)
        self.status.hide()

    def open_settings_dialog(self):
        if not hasattr(self, "settings_tab"):
            return
        if not hasattr(self, "settings_dialog") or self.settings_dialog is None:
            dlg = QDialog(self)
            dlg.setWindowTitle("設定")
            dlg.resize(520, 380)
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(6, 6, 6, 6)
            lay.addWidget(self.settings_tab)
            lay.addStretch(1)
            self.settings_dialog = dlg
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def open_app_info_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("アプリ情報")
        dlg.resize(420, 220)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(10, 10, 10, 10)
        title = QLabel(f"TBH 効率ログ {DISPLAY_VERSION}")
        title.setObjectName("section")
        creator = QLabel(
            f'開発者: {APP_CREATOR_NAME}<br>'
            f'<a href="{APP_CREATOR_GITHUB}">GitHub</a><br>'
            f'<a href="{APP_CREATOR_BMAC}">Buy Me A Coffee</a>'
        )
        creator.setObjectName("hint")
        creator.setOpenExternalLinks(True)
        lay.addWidget(title)
        lay.addWidget(creator, 1)
        close_btn = QPushButton("閉じる")
        close_btn.setObjectName("ghost")
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn)
        dlg.exec()

    def _build_home_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(3, 3, 3, 2)
        lay.setSpacing(3)

        summary = QFrame()
        summary.setObjectName("summaryBar")
        summary.setMinimumHeight(24)
        summary.setMaximumHeight(26)
        summary_l = QHBoxLayout(summary)
        summary_l.setContentsMargins(6, 1, 6, 1)
        summary_l.setSpacing(5)
        current_prefix = QLabel("現在 ステージ")
        current_prefix.setObjectName("summaryItem")
        self.current_stage_name_lbl = QLabel("-")
        self.current_stage_name_lbl.setObjectName("summaryValue")
        self.current_stage_state_lbl = QLabel("待機中")
        self.current_stage_state_lbl.setObjectName("summaryBadge")
        self.current_stage_hint_lbl = QLabel("★オススメ -")
        self.current_stage_hint_lbl.setObjectName("recommendLine")
        self.current_stage_hint_lbl.setWordWrap(False)
        self.current_stage_hint_lbl.setMinimumWidth(0)
        self.current_stage_hint_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.monitor_state_lbl = QLabel("モニター: -")
        self.monitor_state_lbl.hide()
        self.target_state_lbl = QLabel("ターゲット: ゲージ")
        self.target_state_lbl.hide()
        self.ocr_state_lbl = QLabel("OCR: 確認待ち")
        self.ocr_state_lbl.setObjectName("summaryItem")
        self.ocr_state_lbl.hide()
        self.recommend_lbl = self.current_stage_hint_lbl
        self.recommend_lbl.setToolTip("現在セッションでハイスコアGPHが最も高いステージ / GPS / GPH / 周回/h")
        summary_l.addWidget(self.current_stage_state_lbl)
        summary_l.addWidget(current_prefix)
        summary_l.addWidget(self.current_stage_name_lbl)
        divider = QLabel("|")
        divider.setObjectName("summaryItem")
        summary_l.addWidget(divider)
        summary_l.addWidget(self.current_stage_hint_lbl, 1)
        lay.addWidget(summary)

        cards = QGridLayout()
        cards.setHorizontalSpacing(3)
        cards.setVerticalSpacing(2)
        self.money_gauge = SemiCircleGauge(color=THEME["bar_gold"])
        self.gain_gauge = RingGauge(color=THEME["green"])
        self.gps_gauge = RingGauge(color=THEME["green"])
        self.avg_gph_gauge = RingGauge(color=THEME["bar_gold"])
        self.loop_gauge = RingGauge(color=THEME["warning"])
        self.elapsed_gauge = RingGauge(color="#55cfc1")
        self.money_card = KpiGaugeCard("所持金", "●", self.money_gauge, THEME["bar_gold"])
        self.gain_card = KpiGaugeCard("増加G", "+", self.gain_gauge, THEME["green"])
        self.gps_card = KpiGaugeCard("直近5分GPS", "◆", self.gps_gauge, THEME["green"])
        self.avg_gph_card = KpiGaugeCard("平均GPH", "◇", self.avg_gph_gauge, THEME["bar_gold"])
        self.loop_card = KpiGaugeCard("今ステージ周回/h", "↻", self.loop_gauge, THEME["warning"])
        self.elapsed_card = KpiGaugeCard("ステージ秒", "⌛", self.elapsed_gauge, "#55cfc1")
        for i, card in enumerate([self.money_card, self.gain_card, self.gps_card, self.avg_gph_card, self.loop_card, self.elapsed_card]):
            cards.addWidget(card, 0, i)
            cards.setColumnStretch(i, 1)
        self.current_money_lbl = self.money_card.value_lbl
        self.gain_lbl = self.gain_card.value_lbl
        self.elapsed_lbl = self.elapsed_card.value_lbl
        self.gps_5m_lbl = self.gps_card.value_lbl
        self.avg_gph_lbl = self.avg_gph_card.value_lbl
        self.stage_loop_lbl = self.loop_card.value_lbl
        # backward-compatible aliases used by older methods/configs
        self.mph_5m_lbl = self.gps_5m_lbl
        self.avg_mph_lbl = self.avg_gph_lbl
        self.last_stage_lbl = self.stage_loop_lbl
        self.mph_60_lbl = QLabel("-")
        lay.addLayout(cards)

        self._build_recommend_dropdown(lay)

        lay.addStretch(1)
        self.tabs.addTab(tab, "計測")
        self.refresh_stage_summary_table()

    def _build_recommend_dropdown(self, parent_layout: QVBoxLayout):
        self.eff_metric = "gps"
        self.selected_eff_stage: Optional[str] = None
        self.eff_cells: Dict[str, EfficiencyStageCell] = {}
        panel = QFrame()
        panel.setObjectName("recommendFold")
        panel_l = QVBoxLayout(panel)
        panel_l.setContentsMargins(4, 3, 4, 4)
        panel_l.setSpacing(3)

        self.recommend_toggle_btn = QPushButton("▼ ステージ別効率")
        self.recommend_toggle_btn.setObjectName("recommendHeader")
        self.recommend_toggle_btn.clicked.connect(self.toggle_recommend_panel)
        panel_l.addWidget(self.recommend_toggle_btn)

        self.recommend_body = QFrame()
        self.recommend_body.setObjectName("panel")
        body_l = QVBoxLayout(self.recommend_body)
        body_l.setContentsMargins(4, 3, 4, 3)
        body_l.setSpacing(3)

        controls = QGridLayout()
        controls.setHorizontalSpacing(3)
        controls.setVerticalSpacing(0)
        self.eff_metric_buttons = {}
        for idx, (label, key) in enumerate([("GPS", "gps"), ("GPH", "gph"), ("増加G", "delta"), ("周回/h", "loops")]):
            btn = QPushButton(label)
            btn.setObjectName("modeActive" if key == self.eff_metric else "modeInactive")
            btn.clicked.connect(lambda checked=False, k=key: self.set_efficiency_metric(k))
            self.eff_metric_buttons[key] = btn
            controls.addWidget(btn, 0, idx)
        reset_one = QPushButton("選択リセット")
        reset_one.setObjectName("ghost")
        reset_one.clicked.connect(self.reset_selected_efficiency_stage)
        controls.addWidget(reset_one, 0, 4)
        reset_all = QPushButton("全リセット")
        reset_all.setObjectName("ghost")
        reset_all.clicked.connect(self.reset_all_efficiency_scores)
        controls.addWidget(reset_all, 0, 5)
        for col in range(6):
            controls.setColumnStretch(col, 1)
        body_l.addLayout(controls)

        matrix = QFrame()
        matrix.setObjectName("panel")
        matrix_l = QVBoxLayout(matrix)
        matrix_l.setContentsMargins(4, 3, 4, 3)
        matrix_l.setSpacing(2)
        for world in range(1, 4):
            chapter = QLabel(f"{world}章  {world}-1〜{world}-10")
            chapter.setObjectName("section")
            matrix_l.addWidget(chapter)
            grid = QGridLayout()
            grid.setHorizontalSpacing(3)
            grid.setVerticalSpacing(2)
            for num in range(1, 11):
                stage = f"{world}-{num}"
                cell = EfficiencyStageCell(stage)
                cell.clicked.connect(lambda checked=False, s=stage: self.select_efficiency_stage(s))
                self.eff_cells[stage] = cell
                grid.addWidget(cell, (num - 1) // 5, (num - 1) % 5)
                grid.setColumnStretch((num - 1) % 5, 1)
            matrix_l.addLayout(grid)
        body_l.addWidget(matrix)

        self.eff_detail_lbl = QLabel("ステージセルを選択してください。")
        self.eff_detail_lbl.setObjectName("hint")
        self.eff_detail_lbl.setWordWrap(False)
        body_l.addWidget(self.eff_detail_lbl)
        self.recommend_body.hide()
        panel_l.addWidget(self.recommend_body)
        parent_layout.addWidget(panel)
        self.refresh_efficiency_table()

    def _build_setup_tab(self):
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(5, 5, 5, 4)
        outer.setSpacing(4)

        top = QFrame()
        top.setObjectName("panel")
        top.setMinimumHeight(54)
        top.setMaximumHeight(60)
        tl = QGridLayout(top)
        tl.setContentsMargins(7, 5, 7, 5)
        tl.setHorizontalSpacing(5)
        tl.setVerticalSpacing(5)

        self.monitor_combo = QComboBox()
        self.monitor_combo.setMinimumWidth(220)
        with mss.mss() as sct:
            for i, mon in enumerate(sct.monitors):
                label = f"全画面 {mon['width']}x{mon['height']}" if i == 0 else f"画面{i} {mon['width']}x{mon['height']}"
                self.monitor_combo.addItem(label, i)
        self.monitor_label = QLabel("対象画面")
        tl.addWidget(self.monitor_label, 0, 0)
        tl.addWidget(self.monitor_combo, 0, 1, 1, 4)
        self.monitor_combo.currentIndexChanged.connect(self.update_dashboard_environment)

        self.auto_anchor_btn = QPushButton("自動設定")
        self.auto_anchor_btn.setObjectName("saveBtn")
        self.auto_anchor_btn.clicked.connect(lambda: self.auto_detect_anchor(False))
        tl.addWidget(self.auto_anchor_btn, 0, 5)

        self.view_scale_value = 1.0

        self.money_mode_btn = QPushButton("所持金")
        self.stage_num_mode_btn = QPushButton("ステージ")
        self.stage_time_mode_btn = QPushButton("秒数")
        self.gauge_mode_btn = QPushButton("ゲージ")
        for col, (btn, name) in enumerate([
            (self.money_mode_btn, "money"),
            (self.stage_num_mode_btn, "stage_num"),
            (self.stage_time_mode_btn, "stage_time"),
            (self.gauge_mode_btn, "gauge"),
        ]):
            btn.setMinimumWidth(70)
            btn.setObjectName("modeActive" if name == self.current_roi_target else "modeInactive")
            btn.clicked.connect(lambda checked=False, n=name: self.set_roi_target(n))
            tl.addWidget(btn, 1, col)
        self.anchor_enabled_check = QCheckBox("自動追従")
        self.anchor_enabled_check.setChecked(bool(self.cfg.get("anchor_enabled", True)))
        tl.addWidget(self.anchor_enabled_check, 1, 4)
        test = QPushButton("OCRテスト")
        test.setObjectName("testBtn")
        test.clicked.connect(self.test_ocr)
        tl.addWidget(test, 1, 5)
        outer.addWidget(top)

        state = QHBoxLayout()
        state.setSpacing(4)
        self.anchor_saved_lbl = QLabel("基準: 自動")
        self.money_saved_lbl = QLabel("所持金: 自動")
        self.stage_num_saved_lbl = QLabel("ステージ: 自動")
        self.stage_time_saved_lbl = QLabel("秒数: 自動")
        self.gauge_saved_lbl = QLabel("ゲージ: 自動")
        for lab in [self.anchor_saved_lbl, self.money_saved_lbl, self.stage_num_saved_lbl, self.stage_time_saved_lbl, self.gauge_saved_lbl]:
            lab.setObjectName("hint")
            lab.setMinimumWidth(0)
            lab.setWordWrap(True)
            lab.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            state.addWidget(lab)
        state.addStretch(1)
        outer.addLayout(state)

        preview_box = QFrame()
        preview_box.setObjectName("panel")
        preview_box.setMinimumHeight(94)
        preview_box.setMaximumHeight(98)
        pv = QGridLayout(preview_box)
        pv.setContentsMargins(7, 5, 7, 5)
        pv.setHorizontalSpacing(6)
        pv.addWidget(QLabel("元画像"), 0, 0)
        pv.addWidget(QLabel("OCR処理後"), 0, 1)
        self.orig_preview = QLabel("範囲未設定")
        self.proc_preview = QLabel("-")
        for lab in [self.orig_preview, self.proc_preview]:
            lab.setObjectName("preview")
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab.setMinimumSize(180, 54)
            lab.setMaximumHeight(58)
        pv.addWidget(self.orig_preview, 1, 0)
        pv.addWidget(self.proc_preview, 1, 1)
        outer.addWidget(preview_box)

        settings = QFrame()
        settings.setObjectName("panel")
        settings.setMinimumHeight(86)
        settings.setMaximumHeight(92)
        grid = QGridLayout(settings)
        grid.setContentsMargins(7, 5, 7, 5)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        self.tess_path = QLineEdit()
        self.tess_path.setPlaceholderText("tesseract.exe")
        browse = QPushButton("参照")
        browse.setObjectName("ghost")
        browse.clicked.connect(self.browse_tesseract)
        grid.addWidget(QLabel("OCR"), 0, 0)
        grid.addWidget(self.tess_path, 0, 1, 1, 4)
        grid.addWidget(browse, 0, 5)

        self.ui_lang_label = QLabel("UI言語")
        self.ui_lang_combo = QComboBox()
        self.ui_lang_combo.setMinimumWidth(90)
        for code, label in UI_LANGUAGES.items():
            self.ui_lang_combo.addItem(label, code)
        ui_idx = self.ui_lang_combo.findData(self.cfg.get("ui_language", "ja"))
        self.ui_lang_combo.setCurrentIndex(max(0, ui_idx))
        self.ui_lang_combo.currentIndexChanged.connect(self.on_ui_language_changed)
        self.game_lang_label = QLabel("ゲーム言語")
        self.game_lang_combo = QComboBox()
        self.game_lang_combo.setMinimumWidth(90)
        for code, label in GAME_LANGUAGES:
            self.game_lang_combo.addItem(label, code)
        g_idx = self.game_lang_combo.findData(self.cfg.get("game_ocr_language", "ja"))
        self.game_lang_combo.setCurrentIndex(max(0, g_idx))
        self.game_lang_combo.currentIndexChanged.connect(self.on_game_language_changed)
        grid.addWidget(self.ui_lang_label, 1, 0)
        grid.addWidget(self.ui_lang_combo, 1, 1)
        grid.addWidget(self.game_lang_label, 1, 2)
        grid.addWidget(self.game_lang_combo, 1, 3)

        self.money_invert_check = QCheckBox("所持金反転")
        self.money_invert_check.setChecked(bool(self.cfg.get("money_invert", True)))
        grid.addWidget(self.money_invert_check, 2, 0, 1, 3)
        self.money_setting_widgets = [self.money_invert_check]

        self.stage_invert_check = QCheckBox("通知反転")
        self.stage_invert_check.setChecked(bool(self.cfg.get("stage_invert", True)))
        grid.addWidget(self.stage_invert_check, 2, 0, 1, 3)
        self.stage_setting_widgets = [self.stage_invert_check]

        self.money_invert_check.stateChanged.connect(self.schedule_ocr_preview)
        self.stage_invert_check.stateChanged.connect(self.schedule_ocr_preview)
        outer.addWidget(settings)

        self.raw_lbl = QLabel("OCRテスト結果")
        self.raw_lbl.setObjectName("raw")
        self.raw_lbl.setWordWrap(True)
        self.raw_lbl.setMaximumHeight(42)
        outer.addWidget(self.raw_lbl)
        self.settings_tab = tab

    def _build_history_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(5, 5, 5, 4)
        lay.setSpacing(4)

        summary = QFrame()
        summary.setObjectName("pixelPanel")
        summary.setMinimumHeight(56)
        summary.setMaximumHeight(60)
        summary_l = QGridLayout(summary)
        summary_l.setContentsMargins(6, 4, 6, 4)
        summary_l.setHorizontalSpacing(6)
        summary_l.setVerticalSpacing(2)
        title = QLabel("セッション概要")
        title.setObjectName("panelTitle")
        summary_l.addWidget(title, 0, 0, 1, 2)
        self.session_start_lbl = QLabel("開始時刻: -")
        self.session_elapsed_lbl = QLabel("経過時間: -")
        self.session_runs_lbl = QLabel("総周回数: -")
        self.session_accept_lbl = QLabel("受理/全体: -")
        for i, lab in enumerate([self.session_start_lbl, self.session_elapsed_lbl, self.session_runs_lbl, self.session_accept_lbl]):
            lab.setObjectName("statusLine")
            summary_l.addWidget(lab, 1 + i // 2, i % 2)
        lay.addWidget(summary)

        controls = QHBoxLayout()
        controls.setSpacing(4)
        reset = QPushButton("基準リセット")
        reset.setObjectName("neutral")
        reset.clicked.connect(self.reset_baseline)
        controls.addWidget(reset)
        reset_hist = QPushButton("ステージ履歴リセット")
        reset_hist.setObjectName("ghost")
        reset_hist.clicked.connect(self.reset_stage_history)
        controls.addWidget(reset_hist)
        controls.addStretch(1)
        lay.addLayout(controls)
        log_title = QLabel("履歴（直近10件）")
        log_title.setObjectName("section")
        lay.addWidget(log_title)
        self.log_stage_table = QTableWidget(0, 6)
        self.log_stage_table.setHorizontalHeaderLabels([self._tr(x) for x in ["時刻", "ステージ", "秒", "GPS", "GPH", "増加G"]])
        self.log_stage_table.verticalHeader().setVisible(False)
        self.log_stage_table.setAlternatingRowColors(True)
        self.log_stage_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.log_stage_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.log_stage_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.log_stage_table.setSortingEnabled(True)
        self.log_stage_table.setObjectName("table")
        self.log_stage_table.setMinimumHeight(150)
        self.log_stage_table.setMaximumHeight(154)
        self.log_stage_table.verticalHeader().setDefaultSectionSize(18)
        lay.addWidget(self.log_stage_table, 2)
        self.tabs.addTab(tab, "セッション / ログ")
        self.refresh_session_log_table()

    def _apply_theme(self):
        self.setStyleSheet(r'''
            QMainWindow, QWidget {
                background:#141414;
                color:#d8d0bf;
                font-family:"Meiryo UI","Yu Gothic UI",sans-serif;
                font-size:10px;
            }
            #pill {
                background:#153a12;
                color:#7ee04b;
                border:1px solid #2f7a25;
                padding:1px 5px;
                font-weight:900;
                min-width:42px;
            }
            QTabWidget::pane {
                border:2px solid #3b3b37;
                border-top-color:#6b665a;
                background:#0b0b0a;
                margin-top:2px;
            }
            QTabBar::tab {
                background:#242018;
                color:#c8b58a;
                border:2px solid #3b3b37;
                border-bottom-color:#1d1c1a;
                padding:3px 9px;
                margin-right:1px;
                font-weight:900;
            }
            QTabBar::tab:selected {
                background:#a43a1e;
                color:#ffd05a;
                border-color:#d7a642;
            }
            #panel, #pixelPanel, #miniCard, #kpiCard {
                background:#1d1c1a;
                border:2px solid #3b3b37;
                border-top-color:#6b665a;
                border-left-color:#6b665a;
            }
            #summaryBar {
                background:#1d1c1a;
                border:2px solid #3b3b37;
                border-top-color:#6b665a;
                border-left-color:#6b665a;
            }
            #summaryItem {
                color:#d7a642;
                background:transparent;
                font-weight:900;
            }
            #summaryValue {
                color:#f5ead1;
                background:transparent;
                font-family:"Consolas","Meiryo UI";
                font-weight:900;
            }
            #recommendLine {
                color:#f5ead1;
                background:transparent;
                font-family:"Consolas","Meiryo UI";
                font-size:11px;
                font-weight:900;
            }
            #summaryBadge {
                color:#ffd05a;
                background:#4b1c59;
                border:1px solid #9a4cff;
                padding:0 4px;
                font-weight:900;
            }
            #recommendFold {
                background:#151412;
                border:2px solid #3b3b37;
                border-top-color:#6b665a;
                border-left-color:#6b665a;
            }
            #recommendHeader {
                background:#242018;
                color:#ffd05a;
                border:1px solid #7b2418;
                text-align:left;
                font-size:11px;
                padding:1px 6px;
            }
            #footerBar {
                background:#0b0b0a;
                border:1px solid #3b3b37;
            }
            #section, #panelTitle {
                font-size:11px;
                font-weight:900;
                color:#d7a642;
                background:transparent;
            }
            #hint, #statusLine {
                color:#c5bca8;
                background:transparent;
            }
            #statusLine {
                font-family:"Consolas","Meiryo UI";
            }
            #stageName {
                color:#f5ead1;
                font-size:13px;
                font-weight:900;
                background:#242018;
                border:1px solid #3b3b37;
                padding:2px 4px;
            }
            #stageBadge {
                color:#ffd05a;
                background:#4b1c59;
                border:1px solid #9a4cff;
                padding:1px 5px;
                font-weight:900;
            }
            #largePixelIcon {
                color:#ffd05a;
                background:#0b0b0a;
                border:2px solid #3b3b37;
                min-width:32px;
                min-height:32px;
                font-size:18px;
                font-weight:900;
            }
            #kpiTitle {
                color:#d7a642;
                font-size:8px;
                font-weight:900;
                background:transparent;
            }
            #kpiValue {
                color:#f7f2e9;
                font-family:"Consolas","Cascadia Mono","Meiryo UI";
                font-size:11px;
                font-weight:900;
                background:transparent;
            }
            #kpiAux {
                color:#928878;
                font-size:0px;
                background:transparent;
            }
            #miniTitle { color:#928878; font-size:10px; background:transparent; }
            #miniValue { color:#f7f2e9; font-size:16px; font-weight:900; background:transparent; }
            QPushButton {
                background:#6a3514;
                color:#ffd05a;
                border:2px solid #3b2a18;
                border-top-color:#9b6a2a;
                border-left-color:#9b6a2a;
                padding:1px 6px;
                font-weight:900;
                min-height:15px;
            }
            QPushButton:hover { background:#8a451a; }
            QPushButton:pressed {
                background:#3a1c0c;
                border-top-color:#1d1008;
                border-left-color:#1d1008;
            }
            #primary { background:#2f7a25; color:#eaffd8; }
            #danger { background:#9a2a1d; color:#ffe5df; }
            #saveBtn { background:#7b2418; color:#ffd05a; }
            #testBtn { background:#6a3514; color:#ffd05a; }
            #neutral { background:#242018; color:#d8d0bf; }
            #ghost { background:#242018; color:#d8d0bf; }
            #iconBtn {
                background:#1d1c1a;
                color:#ffd05a;
                min-width:20px;
                max-width:28px;
                padding:1px 3px;
            }
            #modeInactive { background:#242018; color:#c8b58a; border:2px solid #3b3b37; }
            #modeActive { background:#a43a1e; color:#ffd05a; border:2px solid #d7a642; }
            QPushButton#stageCell {
                background:#151412;
                color:#d8d0bf;
                border:2px solid #3b3b37;
                padding:1px 2px;
                font-family:"Consolas","Meiryo UI";
                font-size:9px;
                font-weight:900;
                text-align:center;
            }
            QPushButton#stageCell[state="empty"] {
                color:#6f7f88;
                border-color:#2f3d44;
            }
            QPushButton#stageCell[state="normal"] {
                color:#d8d0bf;
                border-color:#3b3b37;
            }
            QPushButton#stageCell[state="recommended"] {
                color:#ffd05a;
                border-color:#d7a642;
                background:#242018;
            }
            QPushButton#stageCell[state="top"] {
                color:#ffd05a;
                border-color:#d7a642;
                background:#2d2110;
            }
            QPushButton#stageCell:checked {
                background:#7b2418;
                color:#ffd05a;
                border-color:#ffd05a;
            }
            #toggleOff { background:#242018; color:#c8b58a; border:1px solid #3b3b37; }
            #toggleOn { background:#7b2418; color:#ffd05a; border:2px solid #d7a642; }
            QComboBox, QLineEdit {
                background:#0b0b0a;
                color:#f5ead1;
                border:2px solid #3b3b37;
                padding:2px 5px;
            }
            QCheckBox { background:transparent; }
            #saveState { color:#7ee04b; background:transparent; font-weight:900; }
            #imageScroll { background:#0b0b0a; border:2px solid #3b3b37; }
            #preview { background:#070706; color:#eee; border:2px solid #3b3b37; }
            #raw { background:#0b0b0a; border:2px solid #3b3b37; padding:6px; color:#d8d0bf; }
            #table {
                background:#11100f;
                alternate-background-color:#191714;
                color:#d8d0bf;
                border:2px solid #3b3b37;
                gridline-color:#3b3b37;
                selection-background-color:#7b2418;
                selection-color:#ffd05a;
            }
            QTableWidget::item { padding:0px 2px; }
            QHeaderView::section {
                background:#242018;
                color:#d7a642;
                border:1px solid #3b3b37;
                padding:1px 2px;
                font-weight:900;
            }
            QStatusBar {
                background:#0b0b0a;
                color:#c5bca8;
                border-top:1px solid #3b3b37;
            }
        ''')

    def _card(self, grid: QGridLayout, row: int, col: int, title: str, value: str) -> QLabel:
        frame = QFrame()
        frame.setObjectName("miniCard")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(7, 4, 7, 4)
        lay.setSpacing(0)
        t = QLabel(title)
        t.setObjectName("miniTitle")
        v = QLabel(value)
        v.setObjectName("miniValue")
        lay.addWidget(t)
        lay.addWidget(v)
        grid.addWidget(frame, row, col)
        return v

    def _spin(self, lo: int, hi: int, val: int) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(int(val))
        s.valueChanged.connect(self.update_ocr_preview)
        return s

    def _dspin(self, lo: float, hi: float, step: float, val: float) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setValue(float(val))
        s.valueChanged.connect(self.update_ocr_preview)
        return s


    def on_ui_language_changed(self):
        try:
            lang = self.ui_lang_combo.currentData() or "ja"
        except Exception:
            lang = "ja"
        self.ui_language = str(lang)
        self.cfg["ui_language"] = self.ui_language
        save_config(self.cfg)
        self.apply_ui_language()
        self.update_dashboard_environment()

    def on_game_language_changed(self):
        try:
            lang = self.game_lang_combo.currentData() or "ja"
        except Exception:
            lang = "ja"
        self.game_ocr_language = str(lang)
        self.cfg["game_ocr_language"] = self.game_ocr_language
        # Stage and seconds OCR stay numeric-first so coordinates are stable across languages.
        # Full-notice OCR is kept as debug/fallback only.
        save_config(self.cfg)
        try:
            label = dict(GAME_LANGUAGES).get(self.game_ocr_language, self.game_ocr_language)
            self.status.showMessage(f"Game OCR language: {label} / number-first")
        except Exception:
            pass
        self.update_dashboard_environment()

    def _tr(self, key: str) -> str:
        return ui_text(key, getattr(self, "ui_language", "ja"))

    def apply_ui_language(self):
        """Translate visible UI labels without changing the game OCR language."""
        lang = getattr(self, "ui_language", self.cfg.get("ui_language", "ja"))
        try:
            self.setWindowTitle(f"{self._tr('TBH 効率ログ')} {DISPLAY_VERSION}")
            if hasattr(self, "title_lbl"):
                self.title_lbl.setText(f"{self._tr('TBH 効率ログ')} {DISPLAY_VERSION}")
        except Exception:
            pass
        # Translate direct text widgets by reverse lookup; dynamic numeric labels stay untouched.
        widgets = []
        for cls in (QLabel, QPushButton, QCheckBox):
            try:
                widgets.extend(self.findChildren(cls))
            except Exception:
                pass
        for w in widgets:
            try:
                txt = w.text()
                if not txt or any(ch.isdigit() for ch in txt):
                    continue
                key = source_key_from_text(txt)
                new = ui_text(key, lang)
                if new != txt:
                    w.setText(new)
            except Exception:
                pass
        if hasattr(self, "tabs"):
            for i in range(self.tabs.count()):
                txt = self.tabs.tabText(i)
                self.tabs.setTabText(i, ui_text(source_key_from_text(txt), lang))
        # Table headers are refreshed from Japanese keys; translate here after construction.
        self.translate_table_headers()

    def translate_table_headers(self):
        lang = getattr(self, "ui_language", "ja")
        for table_name in ["stage_table", "eff_table", "log_stage_table"]:
            table = getattr(self, table_name, None)
            if table is None:
                continue
            for c in range(table.columnCount()):
                item = table.horizontalHeaderItem(c)
                if not item:
                    continue
                key = source_key_from_text(item.text())
                item.setText(ui_text(key, lang))

    def _load_initial(self):
        if self.cfg.get("anchor_roi"):
            update_anchor_offsets(self.cfg)
        tess = resolve_tesseract(self.cfg) or ""
        self.tess_path.setText(tess)
        if tess:
            save_config(self.cfg)
        self.monitor_combo.setCurrentIndex(int(self.cfg.get("monitor_index", 1)) if self.monitor_combo.count() > 1 else 0)
        self.refresh_roi_state()
        self.update_dashboard_environment()
        self.update_footer_links()

    def update_dashboard_environment(self):
        if not hasattr(self, "monitor_state_lbl"):
            return
        try:
            self.monitor_state_lbl.setText(f"モニター: {self.monitor_combo.currentText()}")
        except Exception:
            self.monitor_state_lbl.setText("モニター: -")
        try:
            if hasattr(self, "game_lang_state_lbl"):
                self.game_lang_state_lbl.setText(f"ゲーム言語: {dict(GAME_LANGUAGES).get(self.game_ocr_language, self.game_ocr_language)}")
            if hasattr(self, "ui_lang_state_lbl"):
                self.ui_lang_state_lbl.setText(f"UI言語: {UI_LANGUAGES.get(self.ui_language, self.ui_language)}")
        except Exception:
            pass
        tess_ok = bool(self.cfg.get("tesseract_path") and Path(str(self.cfg.get("tesseract_path"))).exists())
        self.ocr_state_lbl.setText("OCR 正常" if tess_ok else "OCR 未設定")

    def update_footer_links(self):
        return

    def update_session_summary_labels(self):
        if not hasattr(self, "session_start_lbl"):
            return
        if not self.session_id or not self.session_start_ts:
            self.session_start_lbl.setText("開始時刻: -")
            self.session_elapsed_lbl.setText("経過時間: -")
            self.session_runs_lbl.setText("総周回数: -")
            self.session_accept_lbl.setText("受理/全体: -")
            return
        elapsed = max(0.001, time.time() - self.session_start_ts)
        try:
            start_text = datetime.fromtimestamp(float(self.session_start_ts)).strftime("%Y/%m/%d %H:%M:%S")
        except Exception:
            start_text = "-"
        runs = 0
        accepted = 0
        total = 0
        try:
            with db_connect() as con:
                runs = int(con.execute("SELECT COUNT(*) FROM stage_runs WHERE session_id=?", (self.session_id,)).fetchone()[0] or 0)
                row = con.execute("SELECT COALESCE(SUM(accepted),0), COUNT(*) FROM samples WHERE session_id=?", (self.session_id,)).fetchone()
                accepted, total = int(row[0] or 0), int(row[1] or 0)
        except Exception:
            pass
        self.session_start_lbl.setText(f"開始時刻: {start_text}")
        self.session_elapsed_lbl.setText(f"経過時間: {format_elapsed(elapsed)}")
        self.session_runs_lbl.setText(f"総周回数: {runs:,}")
        self.session_accept_lbl.setText(f"受理/全体: {accepted:,} / {total:,}")

    def refresh_session_log_table(self):
        if not hasattr(self, "log_stage_table"):
            return
        self.log_stage_table.setSortingEnabled(False)
        self.log_stage_table.setRowCount(0)
        if not self.session_id:
            self.log_stage_table.setSortingEnabled(True)
            return
        try:
            with db_connect() as con:
                rows = con.execute(
                    """
                    SELECT stage, duration_sec, COALESCE(money_delta, 0), COALESCE(mps, 0), COALESCE(mph, 0), ts
                    FROM stage_runs
                    WHERE session_id=?
                    ORDER BY ts DESC
                    LIMIT 10
                    """,
                    (self.session_id,),
                ).fetchall()
            max_gps = max([float(r[3] or 0) for r in rows] + [1.0])
            max_gph = max([float(r[4] or 0) for r in rows] + [1.0])
            for stage, dur, delta, gps, gph, ts in rows:
                row = self.log_stage_table.rowCount()
                self.log_stage_table.insertRow(row)
                loops = (3600 / float(dur)) if dur else 0.0
                try:
                    time_text = datetime.fromtimestamp(float(ts)).strftime("%H:%M")
                except Exception:
                    time_text = "-"
                vals = [
                    (time_text, float(ts or 0)),
                    (stage or "-", self._stage_sort_key(stage or "")),
                    ("-" if not dur else f"{int(dur)}", int(dur or 0)),
                    ("-" if not gps else f"{float(gps):,.2f}", float(gps or 0)),
                    ("-" if not gph else f"{float(gph):,.0f}", float(gph or 0)),
                    (f"+{int(delta or 0):,} G", int(delta or 0)),
                ]
                for c, (text, key) in enumerate(vals):
                    self.log_stage_table.setItem(row, c, SortableItem(text, key))
                if gps:
                    self.log_stage_table.setCellWidget(row, 3, PixelProgressBar(float(gps), max_gps, THEME["green"], f"{float(gps):,.0f}"))
                if gph:
                    self.log_stage_table.setCellWidget(row, 4, PixelProgressBar(float(gph), max_gph, THEME["bar_gold"], f"{float(gph):,.0f}"))
        except Exception as e:
            self.status.showMessage(f"ログ表示エラー: {e}")
        self.log_stage_table.setSortingEnabled(True)

    def build_runtime_cfg(self) -> dict:
        cfg = dict(self.cfg)
        for key in [
            "money_scale",
            "money_threshold",
            "stage_scale",
            "stage_threshold",
            "poll_interval",
            "light_mode",
        ]:
            cfg.pop(key, None)
        tess_input = self.tess_path.text().strip().strip('"')
        if not tess_input or not Path(tess_input).exists():
            tess_input = find_tesseract() or tess_input
        cfg.update({
            "tesseract_path": tess_input,
            "money_invert": self.money_invert_check.isChecked(),
            "stage_invert": self.stage_invert_check.isChecked(),
            "monitor_index": self.monitor_combo.currentIndex(),
            "ui_language": getattr(self, "ui_language", cfg.get("ui_language", "ja")),
            "game_ocr_language": getattr(self, "game_ocr_language", cfg.get("game_ocr_language", "ja")),
            "ocr_mode": "number_first",
            "anchor_enabled": self.anchor_enabled_check.isChecked() if hasattr(self, "anchor_enabled_check") else bool(cfg.get("anchor_enabled", True)),
            "auto_rois_enabled": True,
            "use_network_stage_trigger": False,
            "gauge_blue_reached_ratio": float(cfg.get("gauge_blue_reached_ratio", 0.55)),
            "gauge_purple_ratio": float(cfg.get("gauge_purple_ratio", 0.18)),
            "gauge_min_pixels": int(cfg.get("gauge_min_pixels", 35)),
        })
        cfg["_expected_stage_candidates"] = self._current_expected_stages()
        return cfg

    def _current_expected_stages(self) -> List[str]:
        expected: List[str] = []
        if getattr(self, "last_stage_key", None) and self.last_stage_key[0]:
            expected.append(self.last_stage_key[0])
            nxt = next_stage_after(self.last_stage_key[0])
            if nxt:
                expected.append(nxt)
        return expected

    def save_settings(self):
        self.sync_runtime_cfg_from_ui()
        save_config(self.cfg)
        self.update_footer_links()
        self.update_dashboard_environment()

    def sync_runtime_cfg_from_ui(self):
        self.cfg = self.build_runtime_cfg()

    def refresh_roi_state(self):
        if hasattr(self, "anchor_saved_lbl"):
            gs = self.cfg.get("detected_game_scale")
            if self.cfg.get("anchor_enabled", True):
                self.anchor_saved_lbl.setText(f"基準: x{gs:g}" if gs else "基準: 自動追従ON")
            else:
                self.anchor_saved_lbl.setText("基準: OFF")
            self.money_saved_lbl.setText("所持金: 自動")
            self.stage_num_saved_lbl.setText("ステージ: 自動")
            self.stage_time_saved_lbl.setText("秒数: 自動")
            if hasattr(self, "gauge_saved_lbl"):
                self.gauge_saved_lbl.setText("ゲージ: 自動")
            buttons = {
                "money": self.money_mode_btn,
                "stage_num": self.stage_num_mode_btn,
                "stage_time": self.stage_time_mode_btn,
                "gauge": self.gauge_mode_btn,
            }
            for name, btn in buttons.items():
                btn.setObjectName("modeActive" if self.current_roi_target == name else "modeInactive")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                btn.update()
        self.update_target_settings_visibility()
        if hasattr(self, "next_action_lbl"):
            if self.cfg.get("anchor_roi"):
                self.next_action_lbl.setText("")
            else:
                self.next_action_lbl.setText("『自動設定』で左上ゴールドアイコンを検出してください。")

    def update_target_settings_visibility(self):
        """Show only the OCR settings relevant to the selected target."""
        is_money = self.current_roi_target == "money"
        is_stage_like = self.current_roi_target in ("stage_num", "stage_time", "stage")
        for w in getattr(self, "money_setting_widgets", []):
            w.setVisible(is_money)
        for w in getattr(self, "stage_setting_widgets", []):
            w.setVisible(is_stage_like)
        if hasattr(self, "orig_preview"):
            if self.current_roi_target == "stage_num":
                self.orig_preview.setToolTip("ステージ番号のみの自動範囲を表示します。")
            elif self.current_roi_target == "stage_time":
                self.orig_preview.setToolTip("秒数のみの自動範囲を表示します。")
            else:
                self.orig_preview.setToolTip("")

    def update_gauge_detection_info(
        self,
        roi: Optional[Tuple[int, int, int, int]] = None,
        state: str = "-",
        fill: Optional[float] = None,
        blue: Optional[float] = None,
        purple: Optional[float] = None,
        raw: str = "",
    ):
        if not hasattr(self, "gauge_roi_info_lbl"):
            return
        if roi:
            x, y, w, h = map(int, roi)
            self.gauge_roi_info_lbl.setText(f"ROI: x={x}, y={y}, w={w}, h={h}")
        else:
            self.gauge_roi_info_lbl.setText("ROI: 未検出")
        if fill is None:
            self.gauge_value_info_lbl.setText("値: -")
            self.gauge_ratio_info_lbl.setText("fill: - / blue: - / purple: -")
        else:
            self.gauge_value_info_lbl.setText(f"値: {fill * 100:.1f}%")
            self.gauge_ratio_info_lbl.setText(f"fill: {fill:.2f} / blue: {float(blue or 0):.2f} / purple: {float(purple or 0):.2f}")
        detail = f"状態: {state}"
        if raw:
            detail += f" / {raw}"
        self.gauge_state_info_lbl.setText(detail)

    def set_roi_target(self, name: str):
        # 切替時に毎回スクショ/テンプレート照合を走らせると数秒固まるため、
        # UI表示だけ切り替え、プレビューは軽い遅延更新にする。
        self.current_roi_target = name
        self.refresh_roi_state()
        self.schedule_ocr_preview()

    def schedule_ocr_preview(self):
        if not hasattr(self, "preview_timer"):
            return
        # プレビュー調整は一時反映のみにして、保存は明示操作時だけ行う。
        try:
            self.sync_runtime_cfg_from_ui()
        except Exception:
            pass
        # 対象切替時にスクショ取得まで走ると重い。プレビュー画像がある時だけ遅延更新。
        if self.current_screenshot is None:
            return
        self.preview_timer.start(180)

    def auto_detect_anchor(self, silent: bool = False) -> bool:
        """Detect the gold icon and regenerate all OCR ROIs automatically.

        jp16: stale manual ranges are overwritten. This makes the tool usable after moving
        or resizing the game window without reselecting each area.
        """
        try:
            idx = int(self.monitor_combo.currentData())
            img = capture_monitor(idx)
            self.current_screenshot = img
            probe_cfg = self.build_runtime_cfg()
            probe_cfg["anchor_enabled"] = True
            probe_cfg["auto_rois_enabled"] = True
            if not probe_cfg.get("anchor_template_path") or not Path(str(probe_cfg.get("anchor_template_path"))).exists():
                probe_cfg["anchor_template_path"] = str(DEFAULT_ANCHOR_TEMPLATE)
            det = locate_anchor(img, probe_cfg)
            if not det:
                self.status.showMessage("自動設定失敗: ゴールドアイコン未検出")
                return False
            x, y, w, h, score, scale = det
            game_scale = nearest_supported_game_scale(scale)
            auto_rois = compute_auto_rois_from_anchor(img, det, probe_cfg)
            self.cfg["anchor_roi"] = [int(x), int(y), int(w), int(h)]
            self.cfg["anchor_template_path"] = str(DEFAULT_ANCHOR_TEMPLATE)
            self.cfg["anchor_enabled"] = True
            self.cfg["auto_rois_enabled"] = True
            # Overwrite old manually-selected ROIs and offsets. Old ranges caused wrong readings after auto mode.
            for k in [
                "money_roi", "stage_num_roi", "stage_time_roi", "gauge_roi", "stage_roi",
                "money_anchor_offset", "stage_num_anchor_offset", "stage_time_anchor_offset", "gauge_anchor_offset", "stage_anchor_offset",
            ]:
                self.cfg.pop(k, None)
            self.cfg.update(auto_rois)
            self.cfg["anchor_base_size"] = [int(w), int(h)]
            self.cfg["detected_game_scale"] = game_scale
            self.cfg["detected_template_scale"] = float(scale)
            if hasattr(self, "anchor_enabled_check"):
                self.anchor_enabled_check.setChecked(True)
            save_config(self.cfg)
            self.refresh_roi_state()
            self.schedule_ocr_preview()
            msg = f"自動設定OK x{game_scale:g} score={score:.2f}"
            self.status.showMessage(msg)
            return True
        except Exception as e:
            self.status.showMessage(f"自動設定エラー: {e}")
            return False

    def ensure_anchor_after_roi_save(self) -> None:
        # jp16では手動範囲選択を通常運用から外し、自動設定を優先する。
        # 互換用に残すが、重い自動検出はここでは走らせない。
        return

    def open_roi_selector(self):
        try:
            idx = int(self.monitor_combo.currentData())
            self.current_screenshot = capture_monitor(idx)
            dlg = RoiSelectionDialog(self, self.current_screenshot, self.current_roi_target, self.cfg, float(getattr(self, "view_scale_value", 1.0)))
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.saved_roi:
                self.cfg[f"{self.current_roi_target}_roi"] = list(dlg.saved_roi)
                if self.current_roi_target == "anchor":
                    tpl = save_anchor_template(self.current_screenshot, dlg.saved_roi)
                    if tpl:
                        self.cfg["anchor_template_path"] = tpl
                    self.cfg["anchor_enabled"] = True
                    if hasattr(self, "anchor_enabled_check"):
                        self.anchor_enabled_check.setChecked(True)
                else:
                    self.ensure_anchor_after_roi_save()
                update_anchor_offsets(self.cfg)
                self.save_settings()
                self.refresh_roi_state()
                self.update_ocr_preview()
                self.status.showMessage("範囲を保存しました。" + (" 基準追従用の相対座標も更新しました。" if self.cfg.get("anchor_roi") else ""))
        except Exception as e:
            QMessageBox.critical(self, "範囲選択エラー", str(e))

    def capture_screenshot(self):
        try:
            idx = int(self.monitor_combo.currentData())
            self.current_screenshot = capture_monitor(idx)
            self.redisplay_screenshot()
            self.update_ocr_preview()
            self.status.showMessage("スクショ取得")
        except Exception as e:
            QMessageBox.critical(self, "スクショ失敗", str(e))

    def redisplay_screenshot(self):
        if not self.current_screenshot:
            return
        self.image_label.set_image(self.current_screenshot, float(getattr(self, "view_scale_value", 1.0)))
        self.refresh_roi_state()

    def on_roi_changed(self, rect: QRect):
        self.status.showMessage(f"選択: x={rect.x()} y={rect.y()} w={rect.width()} h={rect.height()}")

    def save_current_roi(self):
        roi = self.image_label.current_roi()
        if not roi:
            QMessageBox.warning(self, "未選択", "スクショ上で範囲をドラッグしてください。")
            return
        self.cfg[f"{self.current_roi_target}_roi"] = list(roi)
        if self.current_roi_target == "anchor" and self.current_screenshot:
            tpl = save_anchor_template(self.current_screenshot, roi)
            if tpl:
                self.cfg["anchor_template_path"] = tpl
            self.cfg["anchor_enabled"] = True
        elif self.current_roi_target != "anchor":
            self.ensure_anchor_after_roi_save()
        update_anchor_offsets(self.cfg)
        self.save_settings()
        self.refresh_roi_state()
        self.update_ocr_preview()
        self.status.showMessage("範囲を保存しました。")

    def selected_crop(self) -> Optional[Image.Image]:
        # プレビュー用。ここでテンプレート照合を毎回走らせると、対象切替が重くなる。
        # 直近の「自動設定」またはOCRテストで保存されたROIをそのまま表示する。
        if not self.current_screenshot:
            try:
                self.current_screenshot = capture_monitor(int(self.monitor_combo.currentData()))
            except Exception:
                return None
        roi = self.cfg.get(f"{self.current_roi_target}_roi")
        if not roi:
            return None
        return crop_roi(self.current_screenshot, tuple(roi))

    def update_ocr_preview(self):
        crop = self.selected_crop()
        if not crop:
            self.orig_preview.setText("範囲なし")
            self.proc_preview.setText("-")
            if self.current_roi_target == "gauge":
                self.update_gauge_detection_info()
            return
        if self.current_roi_target == "money":
            proc = preprocess_simple(crop, invert=self.money_invert_check.isChecked())
        elif self.current_roi_target == "gauge":
            proc = gauge_mask_preview(crop)
            state, fill, blue, purple, raw = detect_gauge_state(crop, self.build_runtime_cfg())
            self.raw_lbl.setText(f"ゲージ: {raw}")
            roi = self.cfg.get("gauge_roi")
            self.update_gauge_detection_info(tuple(roi) if roi else None, state, fill, blue, purple, raw)
        else:
            proc = preprocess_simple(crop, invert=self.stage_invert_check.isChecked())
        self.orig_preview.setPixmap(pil_to_pixmap(crop))
        self.proc_preview.setPixmap(pil_to_pixmap(proc))

    def browse_tesseract(self):
        path, _ = QFileDialog.getOpenFileName(self, "tesseract.exeを選択", r"C:\Program Files\Tesseract-OCR", "tesseract.exe (tesseract.exe);;All files (*.*)")
        if path:
            self.tess_path.setText(path)
            self.save_settings()

    def test_ocr(self):
        self.save_settings()
        if not resolve_tesseract(self.cfg):
            QMessageBox.warning(self, "OCRエンジン未設定", "tesseract.exe が見つかりません。OCR調整タブの『参照』から tesseract.exe を選択してください。\n\n通常の場所: C:\\Program Files\\Tesseract-OCR\\tesseract.exe")
            return
        self.tess_path.setText(self.cfg.get("tesseract_path", ""))
        try:
            idx = int(self.monitor_combo.currentData())
            img = capture_monitor(idx)
            runtime_cfg = apply_anchor_rois(img, self.build_runtime_cfg())
            msgs = []
            if runtime_cfg.get("_anchor_status"):
                msgs.append("基準OK")
            if runtime_cfg.get("money_roi"):
                res = ocr_money_from_crop(crop_roi(img, tuple(runtime_cfg["money_roi"])), runtime_cfg, self.last_money)
                msgs.append(f"G={res.money if res.money is not None else '-'} raw:{res.raw_text}")
                if res.money is not None:
                    self.current_money_lbl.setText(f"{res.money:,} G")
                    if hasattr(self, "money_gauge"):
                        self.money_gauge.set_value(float(res.money), max(float(res.money) * 1.25, 1.0))
            else:
                msgs.append("所持金: 範囲なし")
            anchor = runtime_cfg.get("anchor_roi")
            if anchor:
                ax, ay, aw, ah = map(float, anchor[:4])
                sc = float(runtime_cfg.get("detected_template_scale", 1.0) or 1.0)
                coin = locate_secondary_anchor(img, runtime_cfg, (ax + aw / 2.0, ay + ah / 2.0), aw * RUNE_COIN_MIN_SEP_FACTOR, sc)
                if coin:
                    rres = ocr_money_from_crop(crop_roi(img, tuple(rune_money_rect_from_coin(img, coin))), runtime_cfg, self.last_money)
                    msgs.append(f"ルーンG={rres.money if rres.money is not None else '-'} (coin score={coin[4]:.2f})")
                else:
                    msgs.append("ルーン: コイン未検出(画面が閉じている等)")
            if runtime_cfg.get("gauge_roi"):
                crop = crop_roi(img, tuple(runtime_cfg["gauge_roi"]))
                state, fill, blue, purple, raw = detect_gauge_state(crop, runtime_cfg)
                msgs.append(f"ゲージ {raw}")
                self.update_gauge_detection_info(tuple(runtime_cfg["gauge_roi"]), state, fill, blue, purple, raw)
            else:
                msgs.append("ゲージ: 範囲なし")
                self.update_gauge_detection_info()
            if runtime_cfg.get("stage_num_roi") or runtime_cfg.get("stage_time_roi"):
                res2 = ocr_stage_split_from_image(img, runtime_cfg)
                msgs.append(f"ステージ={res2.stage or '-'} 秒={res2.duration_sec or '-'} / {res2.raw_text}")
            elif runtime_cfg.get("stage_roi"):
                res2 = ocr_stage_from_crop(crop_roi(img, tuple(runtime_cfg["stage_roi"])), runtime_cfg)
                msgs.append(f"通知={res2.stage or '-'} 秒={res2.duration_sec or '-'} / {res2.raw_text}")
            else:
                msgs.append("ステージ/秒数: 範囲なし")
            self.raw_lbl.setText("\n".join(msgs))
            self.status.showMessage("OCRテスト完了")
        except Exception as e:
            QMessageBox.critical(self, "OCRエラー", str(e))

    def request_gauge_tick(self):
        if not self.running or not self.session_id:
            return
        if self.gauge_busy:
            # ワーカーのコールバックが失われた場合の保険。固まったままにしない。
            if time.time() - (self.gauge_busy_since or 0.0) <= 10.0:
                return
            self.gauge_busy = False
        self.gauge_busy = True
        self.gauge_busy_since = time.time()
        try:
            cfg = dict(self.runtime_cfg_cache or self.build_runtime_cfg())
            if cfg.get("gauge_roi"):
                cfg["_direct_gauge_capture"] = True
                cfg["_runtime_rois_ready"] = True
            worker = GaugeWorker(int(self.monitor_combo.currentData()), cfg)
            worker.signals.finished.connect(self.on_gauge_finished)
            self.pool.start(worker)
        except Exception as exc:
            self.gauge_busy = False
            self.status.showMessage(f"ゲージ監視エラー: {exc}")

    def request_ocr_purpose(self, purpose: str) -> bool:
        if not self.running or not self.session_id:
            return False
        if self.ocr_busy:
            # ワーカーのコールバックが失われた場合の保険。固まったままにしない。
            if time.time() - (self.ocr_busy_since or 0.0) <= 20.0:
                if purpose == "stage_finish":
                    self.pending_ocr_purpose = "stage_finish"
                return False
            self.ocr_busy = False
        self.ocr_busy = True
        self.ocr_busy_since = time.time()
        try:
            cfg = dict(self.runtime_cfg_cache or self.build_runtime_cfg())
            cfg["_expected_stage_candidates"] = self._current_expected_stages()
            worker = OcrWorker(int(self.monitor_combo.currentData()), cfg, self.last_money, purpose)
            worker.signals.finished.connect(self.on_worker_finished)
            self.pool.start(worker)
        except Exception as exc:
            self.ocr_busy = False
            self.status.showMessage(f"OCR起動エラー: {exc}")
            return False
        return True

    def _refresh_stage_views(self):
        self.refresh_stage_summary_table()
        self.refresh_session_log_table()
        self.refresh_efficiency_table()
        self.update_recommendation()

    def _set_stage_wait_start(self):
        self.stage_state = "WAIT_START"
        self.stage_blue_seen = False
        self.pending_stage_finish_ts = None

    def _set_stage_running(self, start_gold: Optional[int], ts: float):
        self.current_stage_start_gold = start_gold
        self.current_stage_start_ts = ts
        self.stage_state = "RUNNING"
        self.stage_blue_seen = False
        self.pending_stage_finish_ts = None

    def _set_stage_finish_pending(self, ts: float):
        self.pending_stage_finish_ts = ts
        self.stage_state = "FINISH_PENDING"

    def _set_stage_finishing(self, ts: float):
        self.pending_stage_finish_ts = ts
        self.last_finish_transition_ts = ts
        self.stage_state = "FINISHING"
        self.stage_blue_seen = False

    def _begin_session_runtime(self, session_id: str, start_ts: float, result: MoneyOCRResult):
        self.session_id = session_id
        self.session_start_ts = start_ts
        self.start_money = result.money
        self.last_money = result.money
        self.last_stage_money = result.money
        self.samples = [(start_ts, result.money)]
        self.session_positive_gain = 0
        self.last_stage_key = None
        self.last_stage_logged_at = 0.0
        self.stage_notice_key = None
        self.stage_notice_last_seen = 0.0
        self.stage_notice_logged = False
        self.stage_pulse_active_until = 0.0
        self.last_stage_pulse_at = 0.0
        self.current_stage_start_gold = None
        self.current_stage_start_ts = None
        self.gold_decreased_during_stage = False
        self.last_finish_transition_ts = 0.0
        self.pending_ocr_purpose = None
        self.finish_ocr_error_count = 0
        self._money_miss_streak = 0
        self._pending_money = None
        self._set_stage_wait_start()

    def _persist_session_start(self, result: MoneyOCRResult):
        if not self.session_id or self.session_start_ts is None:
            return
        with db_connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO sessions(session_id, started_at, start_money) VALUES(?,?,?)",
                (self.session_id, now_iso(), result.money),
            )
            con.execute(
                "INSERT INTO samples(session_id, ts, ts_iso, money, raw_text, accepted, note) VALUES(?,?,?,?,?,?,?)",
                (self.session_id, self.session_start_ts, now_iso(), result.money, result.raw_text, 1, "session_start"),
            )

    def _persist_session_stop(self, elapsed: float, gain: int, avg_mps: float):
        if not self.session_id:
            return
        with db_connect() as con:
            con.execute(
                "UPDATE sessions SET ended_at=?, end_money=?, gain=?, elapsed=?, avg_mps=?, avg_mph=? WHERE session_id=?",
                (now_iso(), self.last_money, gain, elapsed, avg_mps, avg_mps * 3600, self.session_id),
            )

    def _apply_money_result(self, result: WorkerResult) -> Tuple[int, str]:
        accepted = 0
        note = ""
        if result.money is None:
            return accepted, note
        # ルーン画面表示中はルーン枠の値が正値なのでスパイク保留を通さず信用する。
        # ただしルーン画面中はfarming中ではないため、表示と基準(last_money)だけ更新し、
        # 増加G(session_positive_gain)や直近5分のsamplesには加えない(統計を歪めない)。
        if getattr(result, "money_source", "main") == "rune":
            self._pending_money = None
            if self.last_money is not None and result.money < self.last_money and self.stage_state in ("RUNNING", "FINISHING", "FINISH_PENDING"):
                self.gold_decreased_during_stage = True
            self.last_money = result.money
            self.update_stats(result.money)
            return 1, "rune_money"
        # 単発のOCR誤読(余分な桁/桁落ち)で所持金が跳ねると、増加G/GPH/直近5分が壊れる。
        # 上振れ・下振れどちらの大きな急変も1フレームでは信用せず、次の読み取りで同程度の値が
        # 再確認できたときだけ採用する。一過性のスパイク(例 320000→66→320000)は保留して
        # 統計に入れない(last_money/サンプル/gainを更新しない)。
        prev_for_spike = self.last_money
        if prev_for_spike is not None:
            cur = int(result.money)
            jump = abs(cur - int(prev_for_spike))
            implausible = jump >= 50000 and (cur >= prev_for_spike * 1.5 or cur <= prev_for_spike * 0.5)
            if implausible:
                pending = getattr(self, "_pending_money", None)
                if pending is not None and abs(cur - pending) <= max(1, int(pending * 0.02)):
                    self._pending_money = None  # 2連続で同程度 → 本物の急変として採用
                else:
                    self._pending_money = cur  # 初出の急変(上振れ/下振れ)は保留
                    return 0, "money_spike_held"
        self._pending_money = None
        if self.last_money is not None and result.money < max(0, self.last_money * 0.5):
            # Large drops can be OCR misses or real spending. Keep the live UI/sample moving,
            # but exclude the active stage from scoring so the monitor never appears frozen.
            note = "large_gold_drop_candidate"
            if self.stage_state in ("RUNNING", "FINISHING", "FINISH_PENDING"):
                self.gold_decreased_during_stage = True

        if self.last_money is not None and result.money < self.last_money:
            # Real spending or a small OCR wobble. Accept current gold for display, but mark the
            # current stage as unsafe so it is not scored with a negative/understated delta.
            note = "gold_decrease_detected"
            if self.stage_state in ("RUNNING", "FINISHING", "FINISH_PENDING"):
                self.gold_decreased_during_stage = True

        accepted = 1
        prev_money_for_gain = self.last_money
        if prev_money_for_gain is not None:
            self.session_positive_gain += max(0, int(result.money) - int(prev_money_for_gain))
        self.last_money = result.money
        self.samples.append((result.ts, result.money))
        cutoff = result.ts - 900
        self.samples = [(t, m) for t, m in self.samples if t >= cutoff]
        self.update_stats(result.money)
        return accepted, note

    def _persist_worker_sample(self, result: WorkerResult, accepted: int, note: str):
        if not self.session_id:
            return
        with db_connect() as con:
            con.execute(
                "INSERT INTO samples(session_id, ts, ts_iso, money, raw_text, accepted, note) VALUES(?,?,?,?,?,?,?)",
                (self.session_id, result.ts, now_iso(), result.money, result.money_raw, accepted, note),
            )

    def _handle_worker_purpose(self, result: WorkerResult):
        if result.purpose == "stage_start":
            if result.money is not None:
                self.current_stage_start_gold = result.money
                self.current_stage_start_ts = result.ts
                self.gold_decreased_during_stage = False
            return
        if result.purpose == "stage_finish":
            self.finish_ocr_error_count = 0
            self.commit_stage_from_finish_ocr(result)

    def _show_worker_debug(self, result: WorkerResult):
        if result.purpose == "tick" and hasattr(self, "tabs") and self.tabs.currentIndex() not in (2, 3):
            return
        debug_text = f"[{result.purpose}] 所持金: {result.money} / {result.money_raw}\nステージ/秒数: {result.stage} / {result.duration_sec}秒 / {result.stage_raw}"
        self.raw_lbl.setText(debug_text)

    # Stage state machine entrypoint. UI changes should not alter this flow casually.
    def begin_stage_run(self, ts: float, source: str = "gauge"):
        """Start a stage measurement. Uses the latest accepted gold immediately, then tries one OCR refresh."""
        if self.current_stage_start_ts and ts - self.current_stage_start_ts < 2.0:
            return
        self._set_stage_running(self.last_money, ts)
        self.gold_decreased_during_stage = False
        self.status.showMessage(f"開始G={self.current_stage_start_gold if self.current_stage_start_gold is not None else '-'}")
        # Rare OCR at stage start improves gold accuracy without running OCR continuously.
        self.request_ocr_purpose("stage_start")

    # Completes the gauge-driven stage boundary and may request a finish OCR sample.
    def finish_stage_run(self, ts: float):
        if ts - float(self.last_finish_transition_ts or 0.0) < 1.0:
            return
        # OCRが別処理中ならFINISHINGで固めず、空いた瞬間に再実行する。
        if self.ocr_busy:
            self._set_stage_finish_pending(ts)
            self.status.showMessage("終了OCR待機中")
            return
        self._set_stage_finishing(ts)
        self.status.showMessage("終了OCR")
        if not self.request_ocr_purpose("stage_finish"):
            self._set_stage_finish_pending(ts)

    def next_gauge_interval_sec(self, result: GaugeResult) -> float:
        """Adaptive gauge polling.

        The gauge check only decides whether a stage finished. When the gauge is far
        from completion, poll slowly; near the end and during blue state, poll faster.
        """
        if result.state in ("blue", "blue_reached"):
            return 0.8
        if result.fill_ratio >= 0.65:
            return 1.2
        if result.state == "unknown":
            return 2.5
        return 2.0

    def apply_next_gauge_interval(self, result: GaugeResult):
        if not hasattr(self, "gauge_timer") or not self.running:
            return
        sec = self.next_gauge_interval_sec(result)
        self.gauge_timer.setInterval(int(sec * 1000))
        if self.current_roi_target == "gauge":
            self.raw_lbl.setText(f"ゲージ {result.raw} / 次{sec:g}s")
            self.update_gauge_detection_info(self.cfg.get("gauge_roi"), result.state, result.fill_ratio, result.blue_ratio, result.purple_ratio, f"{result.raw} / 次{sec:g}s")

    @Slot(object)
    # Gauge callbacks drive stage segmentation; UI tweaks should avoid changing this logic.
    def on_gauge_finished(self, result: GaugeResult):
        self.gauge_busy = False
        if not self.running:
            return
        if result.error:
            self.status.showMessage(f"ゲージエラー: {result.error}")
            return
        prev = self.gauge_state
        self.gauge_state = result.state
        self.apply_next_gauge_interval(result)
        # State machine:
        # purple -> stage running/start; blue_reached -> end reached; blue_reached then purple -> stage finished.
        if self.stage_state in ("WAIT_START", "IDLE"):
            if result.state == "purple":
                self.begin_stage_run(result.ts, "purple")
            return
        if self.stage_state == "RUNNING":
            if result.state == "blue_reached":
                self.stage_blue_seen = True
                self.status.showMessage("到達")
            elif self.stage_blue_seen and result.state != "blue_reached":
                # 到達後に紫/空/不明へ戻ったら1ステージ終了。
                # 画像1のようにバーがほぼ空でpurple幅が小さい場合も拾う。
                self.finish_stage_run(result.ts)
            return
        if self.stage_state in ("FINISHING", "FINISH_PENDING"):
            # Wait for finish OCR to commit. The current purple state will become next RUNNING after commit.
            # ただし終了OCRのコールバック消失や連続エラーで停滞した場合は、ゲージ側から計測を再開する
            # (ここが固まると以後の所持金・ステージ更新がすべて止まる)。
            anchor_ts = float(self.pending_stage_finish_ts or self.last_finish_transition_ts or 0.0)
            if anchor_ts and result.ts - anchor_ts > 25.0:
                self.status.showMessage("終了処理が停滞したため計測を再開します")
                self.finish_ocr_error_count = 0
                self._set_stage_running(self.last_money, result.ts)
            return

    def correct_stage_for_context(self, stage: Optional[str], raw_text: str = "", candidates: Optional[List[str]] = None) -> Optional[str]:
        """Correct obvious stage OCR slips using recent stage context.

        Example: the font can read 2-1 as 2-7.  If the previous/expected stage is
        2-1, keep 2-1 instead of logging a sudden jump to 2-7. When the full
        per-variant candidate list is available, the majority vote re-runs here
        with commit-time context instead of judging a single value.
        """
        if not stage:
            return None
        if not is_valid_stage(stage):
            return None
        cand_list = [c for c in (candidates or []) if is_valid_stage(c)] or [stage]
        corrected = choose_stage_candidate(cand_list, {"_expected_stage_candidates": self._current_expected_stages()})
        if corrected != stage:
            self.status.showMessage(f"ステージOCR補正: {stage}→{corrected}")
        return corrected

    # Commits one stage record. This is coupled to scoring, dedupe, and DB persistence.
    def commit_stage_from_finish_ocr(self, result: WorkerResult):
        """Commit one row for one finished stage.

        jp24:
        - If the same gauge transition is detected twice, merge the second gold delta into the previous
          row instead of creating a split row.
        - This fixes logs like 344 + 1505 being displayed as two clears, even though they were one clear.
        """
        if not self.session_id:
            return
        end_money = result.money if result.money is not None else self.last_money
        if end_money is None:
            self.status.showMessage("終了OCRで所持金が読めませんでした")
            self._set_stage_wait_start()
            return
        start_gold = self.current_stage_start_gold
        if start_gold is None:
            start_gold = self.last_stage_money if self.last_stage_money is not None else self.start_money
        if start_gold is None:
            start_gold = end_money
        measured_elapsed = int(max(1, round(result.ts - self.current_stage_start_ts))) if self.current_stage_start_ts else None
        ocr_durs = list(result.duration_candidates) or ([int(result.duration_sec)] if result.duration_sec else [])
        dur = choose_commit_duration(ocr_durs, measured_elapsed)
        stage = self.correct_stage_for_context(result.stage, result.stage_raw, result.stage_candidates)
        delta = int(end_money - start_gold)
        if delta < 0 or getattr(self, "gold_decreased_during_stage", False):
            # Spending gold during/around the run makes the clear efficiency unknowable from holdings.
            # Do not create negative GPS/GPH. Reset the baseline to the current gold and continue.
            raw = f"spend_or_decrease_excluded start={start_gold} end={end_money} delta={delta} measured={measured_elapsed}s / {result.stage_raw}"
            self.last_stage_money = end_money
            self._set_stage_running(end_money, result.ts)
            self.gold_decreased_during_stage = False
            self.status.showMessage("G減少を検出: この周回は集計除外")
            self._refresh_stage_views()
            return
        valid = bool(stage and dur and dur > 0 and delta >= 0)
        gps = (delta / dur) if valid else None
        gph = (gps * 3600) if gps is not None else None
        raw = f"start={start_gold} end={end_money} measured={measured_elapsed}s / {result.stage_raw}"

        merged = False
        if valid:
            # If the gauge/finish transition bounces, the same clear can be split into two rows.
            # Merge only very recent rows with the same stage+duration. Real consecutive clears of the same
            # time are normally separated by approximately duration seconds, not a few seconds.
            merge_window = max(6.0, min(45.0, float(dur) * 0.35))
            try:
                with db_connect() as con:
                    row = con.execute(
                        """
                        SELECT id, ts, COALESCE(money_delta,0), raw_text
                        FROM stage_runs
                        WHERE session_id=? AND stage=? AND duration_sec=?
                        ORDER BY ts DESC
                        LIMIT 1
                        """,
                        (self.session_id, stage, int(dur)),
                    ).fetchone()
                    if row:
                        rid, prev_ts, prev_delta, prev_raw = row
                        if 0 <= float(result.ts) - float(prev_ts) <= merge_window:
                            new_delta = int(prev_delta or 0) + int(delta)
                            new_gps = new_delta / float(dur)
                            new_gph = new_gps * 3600.0
                            con.execute(
                                """
                                UPDATE stage_runs
                                SET ts=?, ts_iso=?, money=?, money_delta=?, mps=?, mph=?, raw_text=?
                                WHERE id=?
                                """,
                                (
                                    result.ts,
                                    now_iso(),
                                    end_money,
                                    new_delta,
                                    new_gps,
                                    new_gph,
                                    f"{prev_raw} / MERGED_SPLIT +{delta}G / {raw}",
                                    rid,
                                ),
                            )
                            merged = True
                            gps = new_gps
                            gph = new_gph
                            delta = new_delta
            except Exception as exc:
                self.status.showMessage(f"重複マージ確認エラー: {exc}")

        if not merged:
            with db_connect() as con:
                con.execute(
                    "INSERT INTO stage_runs(session_id, ts, ts_iso, stage, duration_sec, money, money_delta, mps, mph, raw_text) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (self.session_id, result.ts, now_iso(), stage, dur, end_money, delta, gps, gph, raw),
                )

        self.last_stage_money = end_money
        self.last_stage_key = (stage, dur) if stage and dur else None
        self.last_stage_logged_at = result.ts
        if stage and dur:
            loops_per_hour = 3600 / dur
            self.stage_loop_lbl.setText(f"{stage}  {loops_per_hour:,.1f}回")
            if hasattr(self, "loop_gauge"):
                self.loop_gauge.set_value(loops_per_hour, max(12.0, loops_per_hour * 1.25))
            if hasattr(self, "current_stage_name_lbl"):
                self.current_stage_name_lbl.setText(str(stage))
                self.current_stage_state_lbl.setText("周回中")
        # Do not immediately treat the same purple/reset frame as a new clear.
        # The next run starts from this end gold, but a new log requires a fresh blue_reached transition.
        self._set_stage_running(end_money, result.ts)
        self._refresh_stage_views()
        action = "ステージ記録を統合" if merged else "ステージ記録"
        self.status.showMessage(action + ": " + (f"{stage} {dur}s +{delta}G" if valid else f"未確定 +{delta}G"))

    # Session bootstrap touches OCR, runtime ROI resolution, timers, and persistence together.
    def begin_autostart(self):
        """起動＝計測開始で確定。前提が整うまでダイアログを出さず静かにリトライする。

        重いアンカー検出は AnchorProbeWorker でワーカースレッドに退避し、UIスレッドは塞がない
        （ゴールド非表示時にウィンドウ移動が固まらないように）。
        """
        self.save_settings()
        self._probe_busy = False
        self._autostart_timer = QTimer(self)
        self._autostart_timer.timeout.connect(self._autostart_tick)
        self._autostart_timer.start(2000)  # probeは非同期。busyガードで多重起動を防ぐ。
        self._request_anchor_probe()  # 初回は即時に投げる

    def _autostart_tick(self):
        if self.running:
            self._autostart_timer.stop()
            return
        self._request_anchor_probe()

    def _request_anchor_probe(self):
        """アンカー検出＋所持金読取をワーカーへ投げる（UIスレッドは即return）。"""
        if getattr(self, "_probe_busy", False):
            return
        if not resolve_tesseract(self.cfg):
            self.status_pill.setText("tesseract未設定")
            return
        self.tess_path.setText(self.cfg.get("tesseract_path", ""))
        try:
            idx = int(self.monitor_combo.currentData())
        except Exception:
            return
        self._probe_busy = True
        worker = AnchorProbeWorker(idx, self.build_runtime_cfg(), self.last_money)
        worker.signals.finished.connect(self._on_probe_finished)
        self.pool.start(worker)

    def _on_probe_finished(self, res: "ProbeResult"):
        """AnchorProbeWorker の結果をUIスレッドで処理（軽量）。"""
        self._probe_busy = False
        if not self.running:
            # --- 自動開始 ---
            if res.error == "tesseract":
                self.status_pill.setText("tesseract未設定")
                return
            if res.error:
                self.status_pill.setText("計測準備中…")
                return
            if not (res.runtime_cfg and res.runtime_cfg.get("money_roi")):
                self.status_pill.setText("範囲検出待ち")
                return
            # 高信頼(全閾値一致)で読めたときだけ開始する。ズレたROIの断片誤読(例 ",4"→4)で
            # 計測を始めると、誤った基準値に固定されて以降ずっと更新が壊れるのを防ぐ。
            if res.money is None or not res.consensus:
                self.status_pill.setText("所持金待ち(高信頼)")
                return
            self.runtime_cfg_cache = dict(res.runtime_cfg)
            self._start_session_from_result(MoneyOCRResult(res.money, res.raw, res.consensus))
            if hasattr(self, "_autostart_timer"):
                self._autostart_timer.stop()
        else:
            # --- 計測中のROI取り直し（自己修復） ---
            if res.runtime_cfg and res.runtime_cfg.get("money_roi"):
                self.runtime_cfg_cache = dict(res.runtime_cfg)
            else:
                self.runtime_cfg_cache = None  # 次tickは素のアンカー検出に委ねる

    def _reacquire_rois(self):
        """凍結ROIが古い/誤検出で所持金を読めないとき、アンカーを取り直す（非同期）。

        計測中にゲーム窓が動いた・誤ROIで凍結した等を自己修復する。重い検出は
        AnchorProbeWorker に退避し、結果は _on_probe_finished が runtime_cfg_cache に反映する。
        """
        self._request_anchor_probe()

    def _start_session_from_result(self, res: MoneyOCRResult):
        """高信頼の所持金読み取りからセッションを開始する（UIスレッド・軽量）。"""
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_start_ts = time.time()
        self._begin_session_runtime(session_id, session_start_ts, res)
        self._persist_session_start(res)
        self.running = True
        # jp21: steam通信パルスは廃止。右下進捗ゲージの青到達→紫戻りでステージ区切りを判定。
        self.status_pill.setText("計測中")
        if hasattr(self, "current_stage_state_lbl"):
            self.current_stage_state_lbl.setText("監視中")
        self.status.showMessage(f"開始 G={res.money:,}")
        self._refresh_stage_views()
        self.update_stats(res.money)
        self.gauge_timer.start(900)
        # 所持金/増加G/平均GPHをステージ境界だけでなく定期的に更新する。
        # 間隔は poll_interval 設定を再利用（未設定なら2秒）。tick はステージ履歴を作らない。
        self.ocr_timer.start(max(500, int(float(self.cfg.get("poll_interval", 2.0)) * 1000)))
        self.request_gauge_tick()

    # Session shutdown also finalizes aggregates in the DB; keep UI-only edits out of here.
    # アプリ終了時(closeEvent)に呼ばれ、計測集計を確定保存する。手動停止UIは廃止。
    def stop_session(self):
        if not self.running:
            return
        self.running = False
        if hasattr(self, "_autostart_timer"):
            self._autostart_timer.stop()
        if hasattr(self, "ocr_timer"):
            self.ocr_timer.stop()
        self.gauge_timer.stop()
        self.stop_packet_pulse_sniffer()  # legacy no-op unless an old sniffer was active
        if self.session_id and self.session_start_ts and self.start_money is not None and self.last_money is not None:
            elapsed = max(0.001, time.time() - self.session_start_ts)
            gain = int(max(0, getattr(self, "session_positive_gain", 0)))
            avg_mps = gain / elapsed
            self._persist_session_stop(elapsed, gain, avg_mps)
        self.status_pill.setText("停止")
        if hasattr(self, "current_stage_state_lbl"):
            self.current_stage_state_lbl.setText("停止中")
        self.status.showMessage("停止しました")

    def closeEvent(self, event):
        """アプリ終了で計測を確定保存し、テンプレOCRの学習も書き出す。"""
        try:
            self.stop_session()
        except Exception:
            pass
        try:
            get_money_ocr_engine().flush()
        except Exception:
            pass
        super().closeEvent(event)

    def request_ocr_tick(self):
        if not self.running or not self.session_id:
            return
        if self.stage_state in ("FINISH_PENDING", "FINISHING"):
            self.request_ocr_purpose("stage_finish")
            return
        self.request_ocr_purpose("tick")

    def recent_packet_pulse_age(self, ts: float) -> Optional[float]:
        """Return seconds since the latest packet pulse near this OCR result.

        Network traffic is noisy, so this is only a sampling hint, not a commit trigger.
        A stage log is committed only when stage/time OCR is also visible.
        """
        if not getattr(self, "stage_pulse_times", None):
            return None
        window = float(self.cfg.get("stage_pulse_accept_window", 4.0))
        best = None
        for p in list(self.stage_pulse_times):
            age = ts - float(p)
            if -0.25 <= age <= window:
                if best is None or age < best:
                    best = age
        return best

    # OCR worker results update live money, stage state, and sample persistence in one place.
    def on_worker_finished(self, result: WorkerResult):
        self.ocr_busy = False
        if not self.running:
            return
        if result.error:
            self.status.showMessage(f"OCRエラー: {result.error}")
        else:
            accepted, note = self._apply_money_result(result)
            # 凍結ROIが古い/誤検出だと、読めない(None)か断片の低信頼値(例 ",4")を読み続けて
            # 無言で更新が壊れる。高信頼でない読みが連続したらROIを取り直して自己修復する。
            # 信頼扱い: テンプレ高速パス[tpl] / ルーン枠 / tesseract全閾値一致(consensus)。
            raw = result.money_raw or ""
            trusted = result.money is not None and (
                result.money_source == "rune"
                or raw.startswith("[tpl")
                or result.money_consensus
            )
            if trusted:
                self._money_miss_streak = 0
            else:
                self._money_miss_streak += 1
                if self._money_miss_streak >= 3:
                    self._money_miss_streak = 0
                    self._reacquire_rois()
            self._persist_worker_sample(result, accepted, note)
            self._handle_worker_purpose(result)
            # jp21: 通常OCR tickではステージ履歴を作らない。
            # ステージ履歴は右下ゲージの「青到達→紫戻り」1回につき1行だけ作る。
            # 生ログは常時更新しすぎない。最後のOCR結果だけ表示。
            self._show_worker_debug(result)
            self._update_tpl_pill(result)
        pending = self.pending_ocr_purpose
        self.pending_ocr_purpose = None
        if self.running and pending == "stage_finish":
            QTimer.singleShot(0, lambda: self.request_ocr_purpose("stage_finish"))
        elif self.running and self.stage_state == "FINISH_PENDING" and self.pending_stage_finish_ts:
            # 次イベントループで終了OCRを再試行。これが2周目以降が出ない主因だった
            # 「終了検知時に通常OCR中でFINISHINGに固まる」状態を防ぐ。
            QTimer.singleShot(40, lambda: self.finish_stage_run(float(self.pending_stage_finish_ts or time.time())))
        elif self.running and result.error and self.stage_state == "FINISHING":
            # 終了OCRが一時的なエラー(キャプチャ失敗等)で返っても、ここで復旧しないと
            # FINISHINGのまま全計測が固まる。数回再試行し、ダメならこの周回は諦めて続行。
            self.finish_ocr_error_count += 1
            if self.finish_ocr_error_count <= 3:
                QTimer.singleShot(300, lambda: self.request_ocr_purpose("stage_finish"))
            else:
                self.finish_ocr_error_count = 0
                self.status.showMessage("終了OCR連続失敗: この周回は記録せず計測を続行します")
                self._set_stage_running(self.last_money, time.time())

    def _update_tpl_pill(self, result: Optional[WorkerResult] = None):
        """所持金テンプレOCRの状態をピルに反映（学習進捗 / 高速パス稼働中）。"""
        if not hasattr(self, "tpl_pill"):
            return
        try:
            engine = get_money_ocr_engine()
            if engine.is_complete():
                used_fast = str(getattr(result, "money_raw", "")).startswith("[tpl")
                self.tpl_pill.setText("テンプレOCR ⚡稼働中" if used_fast else "テンプレOCR ✓検証中")
            else:
                mature = sum(1 for c in engine.coverage().values() if c >= MIN_SAMPLES_PER_DIGIT)
                self.tpl_pill.setText(f"テンプレ学習 {mature}/10")
        except Exception:
            pass

    def set_stage_table_headers(self, headers: List[str]):
        if not hasattr(self, "stage_table"):
            return
        translated = [self._tr(h) if hasattr(self, "_tr") else h for h in headers]
        current = [self.stage_table.horizontalHeaderItem(i).text() for i in range(self.stage_table.columnCount()) if self.stage_table.horizontalHeaderItem(i)]
        if self.stage_table.columnCount() != len(headers) or current != translated:
            self.stage_table.setSortingEnabled(False)
            self.stage_table.setColumnCount(len(headers))
            self.stage_table.setHorizontalHeaderLabels(translated)
            self.stage_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def fixed_stage_list(self) -> List[str]:
        # 互換用。jp11では固定ステージ表ではなく、時間区切りの集計ログを表示する。
        return [f"{area}-{stage}" for area in range(1, 4) for stage in range(1, 11)]




    def refresh_stage_window_buttons(self):
        # jp24: 1分/3分/5分や集計/フル切替は廃止。
        return

    def toggle_recommend_panel(self):
        if not hasattr(self, "recommend_body"):
            return
        expanded = not self.recommend_body.isVisible()
        self.recommend_body.setVisible(expanded)
        if hasattr(self, "recommend_toggle_btn"):
            text = self.recommend_toggle_btn.text()
            marker = "▲" if expanded else "▼"
            self.recommend_toggle_btn.setText(re.sub(r"^[▲▼]\s*", marker + " ", text))
        if expanded and self.height() < 640:
            self.resize(max(self.width(), 700), 640)
        elif not expanded and self.height() > 340:
            self.resize(max(self.width(), 700), 300)

    def refresh_stage_summary_table(self):
        """Refresh session summary labels. The 計測 tab no longer renders a per-run
        table; the full run history lives in the セッション / ログ tab."""
        if not hasattr(self, "stage_table"):
            self.update_session_summary_labels()
            return
        self.set_stage_table_headers(["時刻", "ステージ", "秒", "GPS", "GPH", "増加G"])
        self.stage_table.setSortingEnabled(False)
        self.stage_table.setRowCount(0)
        if not self.session_id:
            self.update_session_summary_labels()
            self.stage_table.setSortingEnabled(True)
            return
        try:
            with db_connect() as con:
                rows = con.execute(
                    """
                    SELECT stage, duration_sec, COALESCE(money_delta, 0), COALESCE(mps, 0), COALESCE(mph, 0), ts
                    FROM stage_runs
                    WHERE session_id=?
                    ORDER BY ts DESC
                    LIMIT 5
                    """,
                    (self.session_id,),
                ).fetchall()
            max_gps = max([float(r[3] or 0) for r in rows] + [1.0])
            max_gph = max([float(r[4] or 0) for r in rows] + [1.0])
            for stage, dur, delta, gps, gph, ts in rows:
                row = self.stage_table.rowCount()
                self.stage_table.insertRow(row)
                loops = (3600 / float(dur)) if dur else 0.0
                try:
                    time_text = datetime.fromtimestamp(float(ts)).strftime("%H:%M")
                except Exception:
                    time_text = "-"
                vals = [
                    (time_text, float(ts or 0)),
                    (stage or "-", self._stage_sort_key(stage or "")),
                    ("-" if not dur else f"{int(dur)}", int(dur or 0)),
                    ("-" if not gps else f"{float(gps):,.2f}", float(gps or 0)),
                    ("-" if not gph else f"{float(gph):,.0f}", float(gph or 0)),
                    (f"+{int(delta or 0):,} G", int(delta or 0)),
                ]
                for c, (text, key) in enumerate(vals):
                    self.stage_table.setItem(row, c, SortableItem(text, key))
                if gps:
                    self.stage_table.setCellWidget(row, 3, PixelProgressBar(float(gps), max_gps, THEME["green"], f"{float(gps):,.0f}"))
                if gph:
                    self.stage_table.setCellWidget(row, 4, PixelProgressBar(float(gph), max_gph, THEME["bar_gold"], f"{float(gph):,.0f}"))
            self.update_session_summary_labels()
        except Exception as e:
            self.status.showMessage(f"ステージ履歴表示エラー: {e}")
        self.stage_table.setSortingEnabled(True)

    def _stage_sort_key(self, st: str):
        try:
            a, b = str(st).split("-", 1)
            return (int(a), int(b))
        except Exception:
            return (999, 999)

    def _reset_cutoff_for_stage(self, stage: str) -> float:
        try:
            with db_connect() as con:
                row = con.execute("SELECT reset_after_ts FROM stage_highscore_resets WHERE stage=?", (stage,)).fetchone()
            return float(row[0]) if row else 0.0
        except Exception:
            return 0.0

    def _filtered_run_rows(self, stage: str):
        """Return filtered valid runs for one stage.

        Rows are tuples: (gph, gps, duration_sec, money_delta, ts).
        If there are fewer than 3 logs, no outlier filter is applied.
        From 3 logs onward, IQR + loose median guard removes unusually high/low OCR mistakes.
        """
        cutoff = self._reset_cutoff_for_stage(stage)
        try:
            with db_connect() as con:
                rows = con.execute(
                    """
                    SELECT COALESCE(mph,0), COALESCE(mps,0), duration_sec, money_delta, ts
                    FROM stage_runs
                    WHERE stage=? AND ts>? AND duration_sec IS NOT NULL AND duration_sec>0
                      AND money_delta IS NOT NULL AND money_delta>0 AND mps IS NOT NULL AND mph IS NOT NULL
                    ORDER BY ts ASC
                    """,
                    (stage, cutoff),
                ).fetchall()
        except Exception:
            return [], 0
        vals = []
        for gph, gps, dur, delta, ts in rows:
            try:
                vals.append((float(gph), float(gps), int(dur), int(delta), float(ts)))
            except Exception:
                pass
        total_count = len(vals)
        if total_count < 3:
            return vals, total_count
        gphs = [v[0] for v in vals]
        try:
            q1, q3 = statistics.quantiles(gphs, n=4)[0], statistics.quantiles(gphs, n=4)[2]
            iqr = q3 - q1
            med = statistics.median(gphs)
            if iqr <= 0:
                low, high = med * 0.45, med * 2.20
            else:
                low, high = max(0.0, q1 - 1.5 * iqr), q3 + 1.5 * iqr
                # OCR mistakes can still survive IQR when the data is small; add a loose median guard.
                low = max(low, med * 0.35)
                high = min(high, med * 2.80)
            filt = [v for v in vals if low <= v[0] <= high]
            # If the filter is too aggressive, prefer showing data over hiding it.
            if len(filt) >= max(4, total_count // 2):
                return filt, total_count
        except Exception:
            pass
        return vals, total_count

    def _stage_efficiency_rows(self) -> Dict[str, Tuple[float, float, int, int, int, int]]:
        """Return stage -> (best_gps, best_gph, adopted_count, total_count, best_duration, best_delta).

        jp24: efficiency table and recommendation use high score, not average.
        """
        out: Dict[str, Tuple[float, float, int, int, int, int]] = {}
        for stage in self.fixed_stage_list():
            rows, total_count = self._filtered_run_rows(stage)
            if not rows:
                continue
            best = max(rows, key=lambda r: r[0])
            out[stage] = (best[1], best[0], len(rows), total_count, best[2], best[3])
        return out

    def _eff_metric_value(self, row: Tuple[float, float, int, int, int, int], metric: Optional[str] = None) -> float:
        gps, gph, adopted, total, dur, delta = row
        metric = metric or getattr(self, "eff_metric", "gps")
        if metric == "gph":
            return float(gph)
        if metric == "delta":
            return float(delta)
        if metric == "loops":
            return (3600.0 / float(dur)) if dur else 0.0
        return float(gps)

    def set_efficiency_metric(self, metric: str):
        self.eff_metric = metric
        for key, btn in getattr(self, "eff_metric_buttons", {}).items():
            btn.setObjectName("modeActive" if key == metric else "modeInactive")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()
        self.refresh_efficiency_table()

    def select_efficiency_stage(self, stage: str):
        self.selected_eff_stage = stage
        self.refresh_efficiency_table()

    def update_efficiency_detail(self, data: Dict[str, Tuple[float, float, int, int, int, int]]):
        if not hasattr(self, "eff_detail_lbl"):
            return
        stage = getattr(self, "selected_eff_stage", None)
        if not stage:
            self.eff_detail_lbl.setText("ステージセルを選択してください。")
            return
        row = data.get(stage)
        if not row:
            self.eff_detail_lbl.setText(f"{stage}: 未計測")
            return
        gps, gph, adopted, total, dur, delta = row
        loops = (3600.0 / dur) if dur else 0.0
        self.eff_detail_lbl.setText(
            f"{stage} | GPS {gps:,.2f} | GPH {gph:,.0f} | {dur}s | +{delta:,}G | {loops:,.1f}周/h | {adopted}/{total}"
        )

    def refresh_efficiency_table(self):
        if not hasattr(self, "eff_cells"):
            return
        data = self._stage_efficiency_rows()
        top_stage = None
        if data:
            top_stage = max(data.items(), key=lambda kv: self._eff_metric_value(kv[1]))[0]
        recommended = None
        if data:
            recommended = max(data.items(), key=lambda kv: kv[1][1])[0]
        for stage, cell in self.eff_cells.items():
            cell.set_stage_data(data.get(stage), getattr(self, "eff_metric", "gps"), stage == top_stage, stage == recommended)
            cell.set_selected_visual(stage == getattr(self, "selected_eff_stage", None))
        self.update_efficiency_detail(data)

    def update_recommendation(self):
        # ★オススメはサマリーバー (recommend_lbl) のみに表示する。展開トグルは開閉用の
        # 汎用ラベルに固定し、推奨の二重表示を避ける。
        if not hasattr(self, "recommend_lbl"):
            return
        data = self._stage_efficiency_rows()
        if not data:
            self.recommend_lbl.setText("★オススメ -")
            return
        stage, (gps, gph, adopted, total, dur, delta) = max(data.items(), key=lambda kv: kv[1][1])
        runh = (3600.0 / dur) if dur else 0.0
        self.recommend_lbl.setText(f"★オススメ {stage} / GPS {gps:,.2f} / GPH {gph:,.0f} / {runh:,.1f}周")

    def reset_selected_efficiency_stage(self):
        stage = getattr(self, "selected_eff_stage", None)
        if not stage and hasattr(self, "eff_table"):
            row = self.eff_table.currentRow()
            if row >= 0:
                item = self.eff_table.item(row, 0)
                stage = item.text().strip() if item else None
        if not stage:
            QMessageBox.information(self, "ステージ未選択", "効率表でリセットしたいステージ行を選択してください。")
            return
        if not re.match(r"^\d+-\d+$", stage):
            return
        with db_connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO stage_highscore_resets(stage, reset_after_ts, reset_at_iso) VALUES(?,?,?)",
                (stage, time.time(), now_iso()),
            )
        self.refresh_efficiency_table()
        self.update_recommendation()
        self.status.showMessage(f"{stage} のハイスコアをリセットしました")

    def reset_all_efficiency_scores(self):
        if QMessageBox.question(self, "全リセット", "効率表の全ステージハイスコアをリセットしますか？") != QMessageBox.StandardButton.Yes:
            return
        now = time.time()
        with db_connect() as con:
            for stage in self.fixed_stage_list():
                con.execute(
                    "INSERT OR REPLACE INTO stage_highscore_resets(stage, reset_after_ts, reset_at_iso) VALUES(?,?,?)",
                    (stage, now, now_iso()),
                )
        self.refresh_efficiency_table()
        self.update_recommendation()
        self.status.showMessage("効率表のハイスコアを全リセットしました")

    def maybe_clear_stage_notice(self, ts: float):
        """ステージクリア通知が消えたら、同じステージ/秒数でも次回は新規クリアとして受け付ける。"""
        if not getattr(self, "stage_notice_key", None):
            return
        # OCRが1～2回失敗しただけで解除しないよう、最低8秒は保持する。
        if ts - float(getattr(self, "stage_notice_last_seen", 0.0)) > 15.0:
            self.stage_notice_key = None
            self.stage_notice_logged = False

    def handle_stage_result(self, res: StageOCRResult, ts: float, trigger: str = "ocr"):
        """ステージクリア1回につき1行だけ記録する。

        旧版はOCR読取間隔ごとに同じクリア通知を拾い、
        その時点までの増加ゴールドをクリア秒数で割っていたためGPS/GPHが低く出た。
        jp20では通信パルスを確定条件にせず、画面OCRのステージ/秒数を必須条件にする。
        同じ通知は原則再記録せず、同ステージ同秒の連続クリアだけ時間差で許可する。
        """
        if not res.stage or not re.match(r"^\d{1,2}-\d{1,2}$", res.stage):
            self.maybe_clear_stage_notice(ts)
            return
        if not res.duration_sec or not (1 <= int(res.duration_sec) <= 3600):
            self.maybe_clear_stage_notice(ts)
            return
        if self.last_money is None:
            return

        dur = max(1, int(res.duration_sec or 1))
        key = (str(res.stage), dur)

        # 同じ通知が表示され続けている間は、同じクリアとして扱う。
        # ただし同ステージ同秒で本当に次周回したケースに備え、
        # 「前回ログからクリア秒数に近い時間が経過」かつ「別パケットパルス由来」の場合だけ新規候補にする。
        elapsed_since_last = ts - float(self.last_stage_logged_at or 0.0)
        min_same_stage_gap = max(12.0, min(300.0, dur * float(self.cfg.get("same_stage_repeat_ratio", 0.70))))
        same_stage_recent = (
            self.last_stage_key is not None
            and self.last_stage_key[0] == str(res.stage)
            and elapsed_since_last < min_same_stage_gap
        )
        if self.stage_notice_key == key and self.stage_notice_logged and elapsed_since_last < min_same_stage_gap:
            self.stage_notice_last_seen = ts
            return
        if same_stage_recent:
            self.stage_notice_key = key
            self.stage_notice_last_seen = ts
            self.stage_notice_logged = True
            return

        prev = self.last_stage_money if self.last_stage_money is not None else self.start_money
        if prev is None:
            prev = self.last_money
        delta = int(self.last_money - prev)
        # 明らかなマイナスは所持金OCRの揺れなのでステージログ化しない。
        if delta < 0:
            self.stage_notice_key = key
            self.stage_notice_last_seen = ts
            self.stage_notice_logged = True
            return

        gps = delta / dur
        gph = gps * 3600
        loops_per_hour = 3600 / dur
        self.last_stage_money = self.last_money
        self.last_stage_key = key
        self.last_stage_logged_at = ts
        self.stage_notice_key = key
        self.stage_notice_last_seen = ts
        self.stage_notice_logged = True
        self.stage_loop_lbl.setText(f"{res.stage}  {loops_per_hour:,.1f}回")
        with db_connect() as con:
            con.execute(
                "INSERT INTO stage_runs(session_id, ts, ts_iso, stage, duration_sec, money, money_delta, mps, mph, raw_text) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (self.session_id, ts, now_iso(), res.stage, dur, self.last_money, delta, gps, gph, res.raw_text),
            )
        self.refresh_stage_summary_table()
        self.refresh_session_log_table()
        self.refresh_efficiency_table()
        self.update_recommendation()

    def start_packet_pulse_sniffer(self):
        self.stop_packet_pulse_sniffer()
        if not bool(self.cfg.get("use_network_stage_trigger", True)):
            return
        sniffer = PacketPulseSniffer(self.cfg)
        sniffer.signals.pulse.connect(self.on_packet_pulse)
        sniffer.signals.error.connect(lambda msg: self.status.showMessage(msg))
        sniffer.signals.status.connect(lambda msg: self.status.showMessage(msg))
        self.packet_sniffer = sniffer
        sniffer.start()

    def stop_packet_pulse_sniffer(self):
        if self.packet_sniffer is not None:
            self.packet_sniffer.stop()
            self.packet_sniffer = None

    @Slot(float, str)
    def on_packet_pulse(self, ts: float, note: str):
        if not self.running:
            return
        # jp20: パルスはクリア確定ではない。ステージクリア以外でも飛ぶため、
        # 「今すぐOCRを走らせる候補信号」としてのみ使う。
        # 実際のログ化は画面OCRでステージ/秒数が取れた場合だけ行う。
        self.last_stage_pulse_at = ts
        self.stage_pulse_times.append(ts)
        self.stage_pulse_active_until = ts + float(self.cfg.get("stage_pulse_accept_window", 4.0))
        self.status.showMessage(note + " → OCR確認")
        self.request_ocr_tick()

    def update_clock_only(self):
        if self.running and self.session_id and self.session_start_ts:
            stage_elapsed = 0.0
            if self.current_stage_start_ts:
                stage_elapsed = max(0.0, time.time() - self.current_stage_start_ts)
            self.elapsed_lbl.setText("-" if not self.current_stage_start_ts else f"{int(stage_elapsed)}s")
            if hasattr(self, "elapsed_gauge"):
                self.elapsed_gauge.set_value(stage_elapsed, max(180.0, stage_elapsed * 1.25))
            self.update_session_summary_labels()

    def update_stats(self, money: int):
        self.current_money_lbl.setText(f"{money:,} G")
        if hasattr(self, "money_gauge"):
            base = max(float(self.start_money or money or 1), 1.0)
            self.money_gauge.set_value(float(money or 0), max(base * 1.5, float(money or 1)))
        if not self.session_start_ts or self.start_money is None:
            return
        elapsed = max(0.001, time.time() - self.session_start_ts)
        gain = int(max(0, getattr(self, "session_positive_gain", 0)))
        # 表示用の増加G/平均GPHは「現在所持金 - 開始所持金」ではなく、
        # サンプル間の正の増加だけを累積した値を使う。
        # これにより、買い物などでゴールドを消費しても平均GPHが壊れない。
        self.gain_lbl.setText(f"+{gain:,} G")
        stage_elapsed = max(0.0, time.time() - self.current_stage_start_ts) if self.current_stage_start_ts else 0.0
        self.elapsed_lbl.setText("-" if not self.current_stage_start_ts else f"{int(stage_elapsed)}s")
        avg_gps = gain / elapsed
        avg_gph = avg_gps * 3600
        self.avg_gph_lbl.setText(f"{avg_gph:,.0f}")
        gps5 = self.window_mps(300)
        self.gps_5m_lbl.setText("-" if gps5 is None else f"{gps5:,.2f}")
        if hasattr(self, "gain_gauge"):
            self.gain_gauge.set_value(gain, max(gain * 1.25, 1))
            self.avg_gph_gauge.set_value(avg_gph, max(avg_gph * 1.25, 1))
            gps_val = float(gps5 or 0.0)
            self.gps_gauge.set_value(gps_val, max(gps_val * 1.25, 1))
            self.elapsed_gauge.set_value(stage_elapsed, max(180.0, stage_elapsed * 1.25))
        self.update_session_summary_labels()

    def window_mps(self, seconds: int) -> Optional[float]:
        if len(self.samples) < 2:
            return None
        now = time.time()
        recent = [(t, m) for t, m in self.samples if t >= now - seconds]
        if len(recent) < 2:
            return None
        dt = recent[-1][0] - recent[0][0]
        if dt <= 0:
            return None
        # Spending decreases holdings, but GPS should represent earned gold speed.
        # Ignore negative steps instead of showing negative GPS.
        positive_gain = 0
        for (_, prev_m), (_, cur_m) in zip(recent, recent[1:]):
            positive_gain += max(0, int(cur_m) - int(prev_m))
        return positive_gain / dt

    def add_stage_row(self, ts: float, stage: str, dur: int, money: int, delta: int, mps: float, mph: float):
        # jp11では細かい行追加ではなく、指定分数の時間区切りで再集計します。
        self.refresh_stage_summary_table()

    def reset_stage_history(self):
        if self.session_id:
            with db_connect() as con:
                con.execute("DELETE FROM stage_runs WHERE session_id=?", (self.session_id,))
        self.last_stage_key = None
        self.last_stage_logged_at = 0.0
        self.stage_notice_key = None
        self.stage_notice_last_seen = 0.0
        self.stage_notice_logged = False
        self.last_stage_money = self.last_money if self.last_money is not None else self.start_money
        self.current_stage_start_gold = self.last_money if self.last_money is not None else self.start_money
        self.current_stage_start_ts = time.time() if self.running else None
        self.stage_state = "WAIT_START"
        self.stage_blue_seen = False
        self.stage_loop_lbl.setText("-")
        self.refresh_stage_summary_table()
        self.refresh_session_log_table()
        self.refresh_efficiency_table()
        self.update_recommendation()
        self.status.showMessage("ステージ履歴をリセットしました")

    def reset_baseline(self):
        if self.last_money is None:
            return
        self.start_money = self.last_money
        self.last_stage_money = self.last_money
        self.session_start_ts = time.time()
        self.samples = [(self.session_start_ts, self.last_money)]
        self.session_positive_gain = 0
        self.update_stats(self.last_money)
        self.status.showMessage("基準を現在所持金にリセット")


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    # 起動＝計測開始で確定。ウィンドウ表示後に自動開始（前提が整うまで静かにリトライ）。
    QTimer.singleShot(0, win.begin_autostart)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
