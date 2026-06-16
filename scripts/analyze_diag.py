"""Phase A 診断ログ(_play_samples/diag/*.jsonl)を時系列に要約する。

TBH_DIAG=1 で本体(run.bat)を動かして 通常クリア/失敗/別ステージ手動変更/同ステージ手動再開 を
再現したあと、これを実行して「各境界でゲージが何を返し、ステージ秒の起点(set_running)がいつ更新されたか」を
人間が読める形に圧縮する。Phase B の統一ロジック設計の根拠データになる。

使い方:
  .venv\\Scripts\\python.exe scripts\\analyze_diag.py            # 最新の jsonl を解析
  .venv\\Scripts\\python.exe scripts\\analyze_diag.py <path.jsonl>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIAG = ROOT / "_play_samples" / "diag"


def latest_jsonl() -> Path | None:
    files = sorted(DIAG.glob("diag_*.jsonl"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def load(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def fmt_gauge(r: dict) -> str:
    return (f"GAUGE {r.get('state','?'):>12} fill={r.get('fill',0):.2f} blue={r.get('blue',0):.2f} "
            f"pur={r.get('purple',0):.2f} | sm={r.get('stage_state','?'):>12} "
            f"blue_seen={int(bool(r.get('blue_seen')))} max={r.get('max_fill',0):.2f} "
            f"absent={r.get('absent_streak',0)} elapsed={r.get('stage_elapsed')}")


def fmt_tick(r: dict) -> str:
    return (f"TICK  {str(r.get('purpose','?')):>12} sm={r.get('stage_state','?'):>12} "
            f"money={r.get('money')} kind={r.get('kind')} stage={r.get('stage')} "
            f"last_kind={r.get('last_kind')} elapsed={r.get('stage_elapsed')}")


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_jsonl()
    if not path or not path.exists():
        print(f"診断ログが見つかりません: {DIAG}")
        return
    rows = load(path)
    if not rows:
        print(f"空のログ: {path}")
        return
    t0 = rows[0]["t"]
    print("=" * 100)
    print(f"diag: {path.name}  rows={len(rows)}  duration={rows[-1]['t']-t0:.1f}s")
    print("=" * 100)

    # --- 全イベントを時系列で（gauge/tick は1行、reset/finish/commit/session は強調）---
    EVENT = {"set_running", "finish_call", "commit_record", "commit_skip", "session_start"}
    counts: dict[str, int] = {}
    for r in rows:
        src = r.get("src", "?")
        counts[src] = counts.get(src, 0) + 1
        rel = r["t"] - t0
        if src == "gauge":
            print(f"[{rel:7.1f}] {fmt_gauge(r)}")
        elif src == "tick":
            print(f"[{rel:7.1f}] {fmt_tick(r)}")
        elif src == "tick_raw":
            continue  # worker側生データは冗長なので既定は省略（必要時にgrep）
        elif src in EVENT:
            extra = {k: v for k, v in r.items() if k not in ("t", "src")}
            print(f"[{rel:7.1f}] ***** {src.upper():>14} {extra}")
        else:
            print(f"[{rel:7.1f}] {src}: {r}")

    print("=" * 100)
    print("件数:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    # --- リセット(set_running)サマリ: 起点更新ごとに直前の経過と状態を一覧 ---
    print("-" * 100)
    print("RESET(set_running) 一覧 [いつ・直前経過・直前状態・直前max_fill]:")
    for r in rows:
        if r.get("src") == "set_running":
            print(f"  [{r['t']-t0:7.1f}] prev_state={r.get('prev_state')} prev_elapsed={r.get('prev_elapsed')} "
                  f"max_fill={r.get('max_fill')} blue_seen={int(bool(r.get('blue_seen')))}")

    # --- ゲージの absent(=unknown or 低fill) ラン: 境界ごとの状態遷移を可視化 ---
    print("-" * 100)
    print("ゲージ absent ラン [充填中→空/消失 の境界。startで何が起きたか]:")
    in_absent = False
    run_start = 0.0
    pre_max = 0.0
    for r in rows:
        if r.get("src") != "gauge":
            continue
        rel = r["t"] - t0
        present = r.get("state") in ("purple", "blue", "blue_reached") and float(r.get("fill", 0)) >= 0.05
        if not present and not in_absent:
            in_absent = True
            run_start = rel
            pre_max = float(r.get("max_fill", 0))
        elif present and in_absent:
            in_absent = False
            print(f"  absent {run_start:7.1f}s → {rel:7.1f}s ({rel-run_start:4.1f}s) pre_max={pre_max:.2f} 再出現state={r.get('state')}")


if __name__ == "__main__":
    main()
