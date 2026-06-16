from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from .ocr_core import crop_roi
from .runtime_env import DEFAULT_ANCHOR_TEMPLATE, DEFAULT_BOSS_TEMPLATE, user_anchor_template_path


ANCHOR_TEMPLATE_GAME_SCALE = 1.5
SUPPORTED_GAME_SCALES = [1.0, 1.25, 1.5]  # x2/x3 はゲームアップデートで廃止

AUTO_ROI_LAYOUT = {
    "money": [36, -1, 112, 31],
    "stage": [4, 713, 430, 34],
    "stage_num": [94, 717, 58, 25],
    "stage_time": [318, 717, 72, 25],
    "gauge": [420, 840, 100, 60],
}

BOSS_SEARCH_LAYOUT = [375, 800, 180, 135]
BOSS_TO_GAUGE_LAYOUT = [20, 14, 78, 16]


def template_scale_candidates() -> List[float]:
    base = [gs / ANCHOR_TEMPLATE_GAME_SCALE for gs in SUPPORTED_GAME_SCALES]
    extra = []
    for v in base:
        extra.extend([v * 0.96, v, v * 1.04])
    return sorted(set(round(x, 4) for x in extra if 0.45 <= x <= 2.25))


def nearest_supported_game_scale(relative_template_scale: float) -> float:
    game_scale = float(relative_template_scale) * ANCHOR_TEMPLATE_GAME_SCALE
    return min(SUPPORTED_GAME_SCALES, key=lambda x: abs(x - game_scale))


def save_anchor_template(img: Image.Image, roi: Tuple[int, int, int, int]) -> Optional[str]:
    """Save the selected in-game anchor icon as a small template for later auto tracking."""
    try:
        crop = crop_roi(img, roi)
        out = user_anchor_template_path()
        crop.save(out)
        return str(out)
    except Exception:
        return None


def update_anchor_offsets(cfg: dict) -> None:
    """Store every ROI as an offset from the anchor icon."""
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


def _clamp_roi(img: Image.Image, roi: Tuple[int, int, int, int]) -> List[int]:
    x, y, w, h = map(int, roi)
    x = max(0, min(x, img.width - 1))
    y = max(0, min(y, img.height - 1))
    w = max(1, min(w, img.width - x))
    h = max(1, min(h, img.height - y))
    return [x, y, w, h]


def _boss_candidate_color_score(patch_rgb: np.ndarray, tpl_rgb: np.ndarray) -> Tuple[float, bool, str]:
    if patch_rgb.shape[:2] != tpl_rgb.shape[:2]:
        return 0.0, False, "shape-mismatch"
    tpl_gray = cv2.cvtColor(tpl_rgb, cv2.COLOR_RGB2GRAY)
    fg = tpl_gray > 25
    if int(fg.sum()) < 10:
        return 0.0, False, "fg-empty"

    tr, tg, tb = tpl_rgb[:, :, 0], tpl_rgb[:, :, 1], tpl_rgb[:, :, 2]
    red_mask = (tr > 110) & (tg < 90) & (tb < 90)
    pr, pg, pb = patch_rgb[:, :, 0], patch_rgb[:, :, 1], patch_rgb[:, :, 2]
    patch_red = (pr > 110) & (pg < 105) & (pb < 105)
    red_needed = int(red_mask.sum()) >= 3
    red_ok = True
    if red_needed:
        red_at_template = int((patch_red & red_mask).sum())
        red_total = int(patch_red.sum())
        red_ok = red_at_template >= 1 or red_total >= max(2, int(red_mask.sum() * 0.20))

    patch_fg = patch_rgb[fg].astype(np.float32)
    tpl_fg = tpl_rgb[fg].astype(np.float32)
    mad = float(np.mean(np.abs(patch_fg - tpl_fg))) / 255.0
    fg_score = max(0.0, 1.0 - mad * 1.8)

    patch_gray = cv2.cvtColor(patch_rgb, cv2.COLOR_RGB2GRAY)
    dark_count = int(((patch_gray < 70) & fg).sum())
    light_count = int(((patch_gray > 120) & fg).sum())
    structure_ok = dark_count >= 4 and light_count >= 3
    ok = bool(red_ok and structure_ok and fg_score >= 0.18)
    detail = f"fg={fg_score:.2f} red={int(red_ok)} dark={dark_count} light={light_count}"
    return fg_score, ok, detail


def locate_boss_icon_in_roi(
    img: Image.Image,
    search_roi: Tuple[int, int, int, int],
    cfg: dict,
    preferred_scale: float = 1.0,
) -> Optional[Tuple[int, int, int, int, float, float]]:
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

    candidates = sorted(set(
        round(preferred_scale * f, 4)
        for f in [0.84, 0.90, 0.96, 1.0, 1.04, 1.10, 1.16]
        if 0.45 <= preferred_scale * f <= 2.35
    ))
    best = None
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

        locs = []
        for res in (res_gray, res_edge):
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
            fg_score, plausible, _ = _boss_candidate_color_score(patch, tpl_rgb)
            px = (lx + tw / 2) / max(1, search.shape[1])
            py = (ly + th / 2) / max(1, search.shape[0])
            pos_prior = 0.5 * px + 0.5 * py
            combined = 0.34 * gray_score + 0.36 * edge_score + 0.22 * fg_score + 0.08 * pos_prior
            if not plausible:
                continue
            if best is None or combined > best[4]:
                best = (x + int(lx), y + int(ly), tw, th, float(combined), float(sc))
    min_score = float(cfg.get("boss_min_score", 0.34))
    if best and best[4] >= min_score:
        return best
    return None


def locate_anchor(img: Image.Image, cfg: dict) -> Optional[Tuple[int, int, int, int, float, float]]:
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


def compute_auto_rois_from_anchor(
    img: Image.Image,
    det: Tuple[int, int, int, int, float, float],
    cfg: dict,
) -> dict:
    ax, ay, _, _, _, scale = det
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

    bdx, bdy, bw, bh = map(float, cfg.get("boss_search_layout", BOSS_SEARCH_LAYOUT))
    boss_search = (
        int(round(ax + bdx * sc)),
        int(round(ay + bdy * sc)),
        int(round(bw * sc)),
        int(round(bh * sc)),
    )
    boss = locate_boss_icon_in_roi(img, boss_search, cfg, sc)
    if boss:
        bx, by, _, _, bscore, bscale = boss
        gdx, gdy, gw, gh = map(float, cfg.get("boss_to_gauge_layout", BOSS_TO_GAUGE_LAYOUT))
        gauge_roi = (
            int(round(bx + gdx * bscale)),
            int(round(by + gdy * bscale)),
            int(round(gw * bscale)),
            int(round(gh * bscale)),
        )
        out["gauge_roi"] = _clamp_roi(img, gauge_roi)
        out["_boss_anchor_status"] = f"繝懊せ蝓ｺ貅・score={bscore:.2f} scale={bscale:.3f} x={bx} y={by}"
    else:
        dx, dy, w, h = map(float, cfg.get("auto_gauge_layout", AUTO_ROI_LAYOUT["gauge"]))
        roi = (
            int(round(ax + dx * sc)),
            int(round(ay + dy * sc)),
            int(round(w * sc)),
            int(round(h * sc)),
        )
        out["gauge_roi"] = _clamp_roi(img, roi)
        out["_boss_anchor_status"] = "繝懊せ蝓ｺ貅匁悴讀懷・縲よ立繧ｲ繝ｼ繧ｸROI繧剃ｽｿ逕ｨ"
    return out


def apply_anchor_rois(img: Image.Image, cfg: dict) -> dict:
    runtime = dict(cfg)
    det = locate_anchor(img, cfg)
    if not det:
        runtime["_anchor_status"] = "蝓ｺ貅悶い繧､繧ｳ繝ｳ譛ｪ讀懷・縲り・蜍紐OI繧呈峩譁ｰ縺ｧ縺阪∪縺帙ｓ縲・"
        if bool(cfg.get("auto_rois_enabled", True)):
            for name in ["money", "stage_num", "stage_time", "gauge", "stage"]:
                runtime.pop(f"{name}_roi", None)
        return runtime

    ax, ay, aw, ah, score, scale = det
    game_scale = nearest_supported_game_scale(scale)
    runtime["anchor_roi"] = [int(ax), int(ay), int(aw), int(ah)]
    runtime["detected_game_scale"] = game_scale
    runtime["detected_template_scale"] = float(scale)
    runtime["_anchor_status"] = f"蝓ｺ貅匁､懷・ score={score:.2f} 繧ｲ繝ｼ繝蛟咲紫=x{game_scale:g} template={scale:.3f} x={ax} y={ay}"

    if bool(cfg.get("auto_rois_enabled", True)):
        auto = compute_auto_rois_from_anchor(img, det, cfg)
        runtime.update(auto)
        if auto.get("_boss_anchor_status"):
            runtime["_anchor_status"] = runtime["_anchor_status"] + " / " + auto.get("_boss_anchor_status", "")
        return runtime

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
