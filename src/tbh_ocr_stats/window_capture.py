"""TaskBarHero ゲームウィンドウの直接キャプチャ（hwnd + PrintWindow）。

別アプリ「青箱お知らせくん」(tbh_box_notification/detector.py) のウィンドウ探索＋
PrintWindow 多段フォールバックを移植・整理したもの。本体はこれまで mss でモニタ丸ごとを
取得していた（4K=2171msでUIフリーズ／モニタ選択必須）が、本モジュールに切り替えることで
**ゲーム窓だけ**を取得する。利点:
  - 取得対象が小さくなり高速・低負荷（フリーズ要因の解消）。
  - ゲームが他ウィンドウの背面（バックグラウンド）でも PrintWindow で描画を取得できる。
  - どのモニタに置いてあっても hwnd で追えるためモニタ選択設定が不要。

公開 API:
  capture_game_window() -> Optional[PIL.Image]  # RGB。窓が無ければ None。
  ※ 戻り型は本体 capture_monitor() と同じ（PIL RGB）なので呼び出し側を変えずに差し替えできる。
"""
from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes
from typing import List, Optional

import numpy as np
from PIL import Image

import win32api
import win32con
import win32gui
import win32process
import win32ui

# --- Toolhelp32（管理者権限プロセスも名前で安全に判定するためのスナップショット） ---
TH32CS_SNAPPROCESS = 0x00000002


class _PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


# ウィンドウタイトルの候補（PID/プロセス名で取れない場合のフォールバック）。
_WINDOW_TITLE_KEYWORDS = ["Task Bar Hero", "TaskBarHero", "TaskBarHero.exe"]

# 直近で有効だった hwnd をキャッシュし、毎キャプチャの全ウィンドウ列挙コストを避ける。
_hwnd_lock = threading.Lock()
_cached_hwnd: Optional[int] = None


def _get_game_pids() -> List[int]:
    """システム上の TaskBarHero.exe / tbh.exe の PID 一覧を返す。"""
    pids: List[int] = []
    snap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1 or snap is None:
        return pids
    pe32 = _PROCESSENTRY32()
    pe32.dwSize = ctypes.sizeof(_PROCESSENTRY32)
    try:
        if ctypes.windll.kernel32.Process32First(snap, ctypes.byref(pe32)):
            while True:
                try:
                    exe_name = pe32.szExeFile.decode("ansi").lower()
                except Exception:
                    exe_name = ""
                if "taskbarhero" in exe_name or exe_name == "tbh.exe":
                    pids.append(int(pe32.th32ProcessID))
                if not ctypes.windll.kernel32.Process32Next(snap, ctypes.byref(pe32)):
                    break
    finally:
        ctypes.windll.kernel32.CloseHandle(snap)
    return pids


def find_game_window() -> Optional[int]:
    """TaskBarHero のウィンドウハンドルを返す（PID一致＞プロセス名一致＞タイトル一致の優先度）。

    タスクバーゲーム特有の非表示扱いや子ウィンドウ配置にも対応するため、トップレベルと
    子ウィンドウの両方を列挙する。サイズが有効（10x10超）な最大面積のウィンドウを採用する。
    """
    try:
        my_pid = os.getpid()
    except Exception:
        my_pid = None

    game_pids = _get_game_pids()
    pid_matched: List[int] = []
    proc_matched: List[int] = []
    title_matched: List[int] = []

    def process_window(hwnd: int) -> None:
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            return
        if my_pid is not None and pid == my_pid:
            return
        # 1) ゲームPIDと一致（最優先）
        if pid in game_pids:
            if hwnd not in pid_matched:
                pid_matched.append(hwnd)
            return
        # 2) プロセス名で判定
        try:
            handle = win32api.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            process_name = win32process.GetModuleFileNameEx(handle, 0)
            win32api.CloseHandle(handle)
            exe_name = os.path.basename(process_name).lower()
            if "taskbarhero" in exe_name or "task bar hero" in exe_name or exe_name == "tbh.exe":
                if hwnd not in proc_matched:
                    proc_matched.append(hwnd)
                return
        except Exception:
            pass
        # 3) タイトルで判定
        title = win32gui.GetWindowText(hwnd)
        if title:
            low = title.lower()
            for kw in _WINDOW_TITLE_KEYWORDS:
                if kw.lower() in low:
                    if hwnd not in title_matched:
                        title_matched.append(hwnd)
                    break

    def enum_child(hwnd, _extra):
        process_window(hwnd)
        return True

    def enum_top(hwnd, _extra):
        process_window(hwnd)
        try:
            win32gui.EnumChildWindows(hwnd, enum_child, None)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(enum_top, None)
    except Exception:
        return None

    for candidates in (pid_matched, proc_matched, title_matched):
        if not candidates:
            continue
        best, best_area = None, 0
        for h in candidates:
            try:
                left, top, right, bottom = win32gui.GetClientRect(h)
                w, ht = right - left, bottom - top
                if w > 10 and ht > 10 and w * ht > best_area:
                    best, best_area = h, w * ht
            except Exception:
                continue
        return best if best is not None else candidates[0]
    return None


def _capture_hwnd(hwnd: int) -> Optional[Image.Image]:
    """指定 hwnd のクライアント領域をキャプチャして PIL(RGB) を返す。

    背面ウィンドウでも取れるよう PrintWindow を 3 段（PW_RENDERFULLCONTENT=3 → CLIENTONLY=2 →
    通常=0）→ 最後に BitBlt の順でフォールバックする。すべて真っ黒なら None。
    """
    try:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        w, h = right - left, bottom - top
        if w <= 0 or h <= 0:
            return None

        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        save_bmp = win32ui.CreateBitmap()
        save_bmp.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(save_bmp)

        img = None
        try:
            for pw_flag in (3, 2, 0):
                try:
                    ctypes.windll.user32.PrintWindow(hwnd, int(save_dc.GetSafeHdc()), pw_flag)
                except Exception:
                    pass
                buf = save_bmp.GetBitmapBits(True)
                arr = np.frombuffer(buf, dtype="uint8").reshape(h, w, 4)
                if int(arr[:, :, :3].sum()) != 0:
                    img = arr
                    break
            if img is None:
                # 最終手段: BitBlt（手前にある時のみ有効）
                try:
                    save_dc.BitBlt((0, 0), (w, h), mfc_dc, (0, 0), win32con.SRCCOPY)
                    buf = save_bmp.GetBitmapBits(True)
                    arr = np.frombuffer(buf, dtype="uint8").reshape(h, w, 4)
                    if int(arr[:, :, :3].sum()) != 0:
                        img = arr
                except Exception:
                    pass
        finally:
            try:
                win32gui.ReleaseDC(hwnd, hwnd_dc)
                mfc_dc.DeleteDC()
                save_dc.DeleteDC()
                win32gui.DeleteObject(save_bmp.GetSafeHandle())
            except Exception:
                pass

        if img is None:
            return None
        # BGRA バッファ → RGB（チャンネル並べ替え）。copy() で frombuffer の読み取り専用を解除。
        rgb = img[:, :, 2::-1].copy()
        return Image.fromarray(rgb, mode="RGB")
    except Exception:
        return None


def capture_game_window() -> Optional[Image.Image]:
    """TaskBarHero のゲーム窓を取得して PIL(RGB) を返す。見つからない/取得失敗なら None。

    直近の有効 hwnd をキャッシュし、無効化・取得失敗時のみ再探索する。
    """
    global _cached_hwnd
    with _hwnd_lock:
        hwnd = _cached_hwnd
        if hwnd is not None:
            try:
                if not win32gui.IsWindow(hwnd):
                    hwnd = None
            except Exception:
                hwnd = None
        if hwnd is None:
            hwnd = find_game_window()
            _cached_hwnd = hwnd
        if hwnd is None:
            return None

    img = _capture_hwnd(hwnd)
    if img is not None:
        return img

    # キャッシュが古い可能性。再探索して一度だけ再試行。
    with _hwnd_lock:
        hwnd = find_game_window()
        _cached_hwnd = hwnd
    if hwnd is None:
        return None
    return _capture_hwnd(hwnd)
