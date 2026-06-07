from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import pytesseract


SOURCE_ROOT = Path(__file__).resolve().parents[2]
if getattr(sys, "frozen", False):
    RUNTIME_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", RUNTIME_DIR))
else:
    RUNTIME_DIR = SOURCE_ROOT
    BUNDLE_DIR = SOURCE_ROOT

APP_DIR = RUNTIME_DIR
CONFIG_PATH = RUNTIME_DIR / "config.json"
DATA_DIR = RUNTIME_DIR / "data"
EXPORT_DIR = RUNTIME_DIR / "exports"
DB_PATH = DATA_DIR / "tbh_ocr_stats.sqlite3"
BUNDLED_ASSET_DIR = BUNDLE_DIR / "assets"
USER_ASSET_DIR = RUNTIME_DIR / "assets"
DEFAULT_ANCHOR_TEMPLATE = BUNDLED_ASSET_DIR / "default_anchor_gold.png"
DEFAULT_BOSS_TEMPLATE = BUNDLED_ASSET_DIR / "default_boss_icon.png"


def bundled_tesseract_candidates() -> List[Path]:
    """Return likely bundled tesseract.exe locations for folder/exe distributions."""
    roots: List[Path] = []

    def add_root(path: Optional[Path]) -> None:
        if path and path not in roots:
            roots.append(path)

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        add_root(Path(meipass))
    try:
        add_root(Path(sys.executable).resolve().parent)
    except Exception:
        pass
    add_root(RUNTIME_DIR)
    add_root(BUNDLE_DIR)

    rel_paths = [
        Path("tesseract.exe"),
        Path("tesseract") / "tesseract.exe",
        Path("Tesseract-OCR") / "tesseract.exe",
        Path("third_party") / "tesseract" / "tesseract.exe",
        Path("vendor") / "tesseract" / "tesseract.exe",
    ]
    candidates: List[Path] = []
    for root in roots:
        for rel in rel_paths:
            candidate = root / rel
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def find_tesseract() -> Optional[str]:
    """Locate tesseract.exe without requiring the user to reselect it after every zip update."""
    candidates: List[str] = []

    def add(value: Optional[str]) -> None:
        if value and value not in candidates:
            candidates.append(value)

    for path in bundled_tesseract_candidates():
        add(str(path))

    add(shutil.which("tesseract"))
    add(shutil.which("tesseract.exe"))

    for path in [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Users\%USERNAME%\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    ]:
        add(str(Path(path.replace("%USERNAME%", Path.home().name))))

    try:
        parent = APP_DIR.parent
        for cfg_path in parent.glob("tbh_ocr_stats*/config.json"):
            if cfg_path == CONFIG_PATH:
                continue
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                add(cfg.get("tesseract_path"))
            except Exception:
                pass
    except Exception:
        pass

    for candidate in candidates:
        try:
            if candidate and Path(candidate).exists():
                return str(Path(candidate))
        except Exception:
            continue
    return None


def normalize_tesseract_path(value: Optional[str]) -> str:
    return (value or "").strip().strip('"')


def resolve_tesseract_path(cfg: dict, preferred: Optional[str] = None) -> Optional[str]:
    """Resolve the best tesseract.exe path, preferring an explicit UI value when valid."""
    candidate = normalize_tesseract_path(preferred)
    if candidate and Path(candidate).exists():
        cfg["tesseract_path"] = candidate
        return candidate

    configured = normalize_tesseract_path(cfg.get("tesseract_path"))
    if configured and Path(configured).exists():
        cfg["tesseract_path"] = configured
        return configured

    found = find_tesseract()
    if found:
        cfg["tesseract_path"] = found
        return found
    return None


def configure_tesseract(cfg: dict, preferred: Optional[str] = None) -> Optional[str]:
    """Resolve and apply pytesseract's executable path."""
    resolved = resolve_tesseract_path(cfg, preferred=preferred)
    if resolved:
        pytesseract.pytesseract.tesseract_cmd = resolved
    return resolved


def load_config() -> dict:
    """Load config while preserving user settings across extracted versions."""
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    try:
        parent = APP_DIR.parent
        candidates = []
        for cfg_path in parent.glob("tbh_ocr_stats*/config.json"):
            if cfg_path == CONFIG_PATH:
                continue
            try:
                candidates.append((cfg_path.stat().st_mtime, cfg_path))
            except Exception:
                pass
        if candidates:
            _, latest = max(candidates, key=lambda item: item[0])
            return json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def db_connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    with db_connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                ts REAL NOT NULL,
                ts_iso TEXT NOT NULL,
                money INTEGER,
                raw_text TEXT,
                accepted INTEGER NOT NULL,
                note TEXT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                start_money INTEGER,
                end_money INTEGER,
                gain INTEGER,
                elapsed REAL,
                avg_mps REAL,
                avg_mph REAL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS stage_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                ts REAL NOT NULL,
                ts_iso TEXT NOT NULL,
                stage TEXT,
                duration_sec INTEGER,
                money INTEGER,
                money_delta INTEGER,
                mps REAL,
                mph REAL,
                raw_text TEXT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS stage_highscore_resets (
                stage TEXT PRIMARY KEY,
                reset_after_ts REAL NOT NULL,
                reset_at_iso TEXT NOT NULL
            )
            """
        )


def user_anchor_template_path() -> Path:
    USER_ASSET_DIR.mkdir(exist_ok=True)
    return USER_ASSET_DIR / "anchor_user.png"


def session_export_paths(session_id: str) -> Tuple[Path, Path]:
    EXPORT_DIR.mkdir(exist_ok=True)
    return (
        EXPORT_DIR / f"stage_runs_{session_id}.csv",
        EXPORT_DIR / f"money_samples_{session_id}.csv",
    )
