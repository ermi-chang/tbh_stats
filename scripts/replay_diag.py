"""Phase C オフライン再生検証: 録画した実ゲージ系列に Phase B の新ロジックを通し、旧挙動と比較する。

診断JSONL(_play_samples/diag/*.jsonl)の gauge ポーリング系列を時系列に再生し、新しい
on_gauge_finished RUNNING ロジック（fillの空エッジで即リセット＝起点貼り直し）で
current_stage_start_ts がどう動くかを計算する。記録に残っている旧 stage_elapsed（=旧ロジックの
経過秒）と並べ、失敗/遷移の境界で「旧=20〜54秒climb / 新=即≈0」になることを確認する。

使い方:
  .venv\\Scripts\\python.exe scripts\\replay_diag.py            # 最新jsonl
  .venv\\Scripts\\python.exe scripts\\replay_diag.py <path>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:  # 日本語コンソール(cp932)でも壊れないように
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DIAG = ROOT / "_play_samples" / "diag"

# Phase B の定数（app.py と一致させる：ヒステリシス2値）
GAUGE_REACH_BLUE = 0.45
GAUGE_MISSED_CLEAR_FILL = 0.85
GAUGE_EMPTY_FILL = 0.08
GAUGE_ACTIVE_FILL = 0.25
GAUGE_ACTIVE_ARM = 2


def latest() -> Path | None:
    fs = sorted(DIAG.glob("diag_*.jsonl"), key=lambda p: p.stat().st_mtime)
    return fs[-1] if fs else None


def load_gauges(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("src") == "gauge":
            out.append(r)
    return out


def replay(gauges: list[dict]) -> None:
    if not gauges:
        print("gauge行がありません")
        return
    t0 = gauges[0]["t"]
    # 新ロジックの状態（app.py の on_gauge_finished RUNNING ヒステリシスと一致させる）
    stage_state = "WAIT_START"
    start_ts = None       # None=非アクティブ(表示「-」)
    blue_seen = False
    max_fill = 0.0
    active = False
    fill_rise = None
    active_streak = 0
    clears = []
    begins = []
    idles = []
    nav_false_count = 0.0  # 非アクティブ中に表示が0より進んでしまった最大秒（あってはならない＝②の誤カウント）

    print(f"{'rel':>7} {'state':>8} {'fill':>5} {'blue':>5} | {'OLD el':>7} {'NEW disp':>9}  event")
    print("-" * 80)
    for r in gauges:
        rel = r["t"] - t0
        ts = r["t"]
        gstate = r.get("state", "unknown")
        fill = float(r.get("fill", 0.0))
        blue = float(r.get("blue", 0.0))
        present = gstate in ("purple", "blue", "blue_reached")
        old_elapsed = r.get("stage_elapsed")
        event = ""

        if stage_state in ("WAIT_START", "IDLE"):
            if gstate == "purple":
                stage_state = "RUNNING"
                active = True
                start_ts = ts
                blue_seen = False
                max_fill = 0.0
                fill_rise = None
                event = "begin(purple)"
        elif stage_state == "RUNNING":
            max_fill = max(max_fill, fill)
            if blue >= GAUGE_REACH_BLUE:
                if not blue_seen:
                    blue_seen = True
                    event = "到達(blue)"
            elif blue_seen:
                # クリア確定 → 記録 → set_running(active, start=ts)
                clears.append(rel)
                active = True
                start_ts = ts
                blue_seen = False
                max_fill = 0.0
                fill_rise = None
                event = "CLEAR記録"
            elif active:
                if max_fill >= GAUGE_MISSED_CLEAR_FILL and fill <= GAUGE_EMPTY_FILL:
                    clears.append(rel)
                    active = True
                    start_ts = ts
                    blue_seen = False
                    max_fill = 0.0
                    fill_rise = None
                    event = "取り逃しCLEAR記録"
                elif not present and fill <= GAUGE_EMPTY_FILL:
                    # state=unknown かつ 空 = ステージ終了 → アイドル（表示「-」）
                    active = False
                    start_ts = None
                    max_fill = 0.0
                    fill_rise = None
                    idles.append((rel, old_elapsed))
                    event = "idle(空→ステージ秒=「-」)"
            else:
                # 非アクティブ: state=purple/blue が連続したら本物の充填として計測開始（起点=立ち上がり時刻）
                if fill <= GAUGE_EMPTY_FILL:
                    fill_rise = None
                elif fill_rise is None:
                    fill_rise = ts
                active_streak = active_streak + 1 if present else 0
                if active_streak >= GAUGE_ACTIVE_ARM:
                    active = True
                    start_ts = fill_rise or ts
                    blue_seen = False
                    max_fill = fill
                    fill_rise = None
                    active_streak = 0
                    begins.append(rel)
                    event = "begin(state purple x2)"

        disp = (ts - start_ts) if start_ts else None
        # 非アクティブ中に表示が進んでいないか（②の誤カウント検出）
        if not active and disp is not None:
            nav_false_count = max(nav_false_count, disp)

        if event or (old_elapsed and disp and abs(old_elapsed - disp) > 8):
            oe = f"{old_elapsed:.1f}" if isinstance(old_elapsed, (int, float)) else "-"
            ne = f"{disp:.1f}" if disp is not None else "-"
            print(f"{rel:7.1f} {gstate:>8} {fill:5.2f} {blue:5.2f} | {oe:>7} {ne:>9}  {event}")

    print("-" * 80)
    print(f"CLEAR記録={len(clears)}  begin(active)={len(begins)}  idle(空でステージ秒=「-」)={len(idles)}")
    print(f"非アクティブ中の最大表示秒(0であるべき)= {nav_false_count:.1f}s "
          + ("OK(誤カウントなし)" if nav_false_count < 1.0 else "<<< まだ誤カウントしている"))
    if idles:
        print("\nアイドル化(=失敗/遷移/再開でステージ秒が「-」に戻った点):")
        for rel, old_el in idles:
            oe = f"{old_el:.1f}s" if isinstance(old_el, (int, float)) else "-"
            print(f"  [{rel:7.1f}] 旧この時点のelapsed={oe} → 新は即「-」")


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else latest()
    if not path or not path.exists():
        print(f"診断ログが見つかりません: {DIAG}")
        return
    print(f"replay: {path.name}")
    replay(load_gauges(path))


if __name__ == "__main__":
    main()
