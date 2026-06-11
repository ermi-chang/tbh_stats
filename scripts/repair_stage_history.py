# -*- coding: utf-8 -*-
"""One-off repair for stage_runs rows corrupted by old OCR selection bugs.

- Stage: the old code picked the first-seen OCR variant and then rewrote later
  correct reads to match the previous (possibly wrong) stage. raw_text keeps all
  per-variant reads ("ステージ=2-2 raw:..."), so the per-row majority is recoverable.
- Duration: the old code picked the first-seen duration candidate, letting
  digit-noise like 772/472 (real: 77/47) through. raw_text keeps the candidates
  ("秒=77 raw:...") and the measured elapsed ("measured=80s").

Dry-run by default; pass --apply to write changes. Backs up the DB first when applying.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "tbh_ocr_stats.sqlite3"

DURATION_MIN_SEC = 3
DURATION_MAX_SEC = 900

STAGE_RE = re.compile(r"ステージ=(\d{1,2}-\d{1,2})")
DUR_RE = re.compile(r"秒=(\d{1,4})")
MEASURED_RE = re.compile(r"measured=(\d+)s")


def is_valid_stage(stage: str) -> bool:
    m = re.match(r"^(\d{1,2})-(\d{1,2})$", stage)
    if not m:
        return False
    world, num = int(m.group(1)), int(m.group(2))
    return 1 <= world <= 3 and 1 <= num <= 10


def most_common_first_seen(values):
    order = []
    for v in values:
        if v not in order:
            order.append(v)
    if not order:
        return None
    counts = {v: values.count(v) for v in order}
    max_count = max(counts.values())
    return next(v for v in order if counts[v] == max_count)


def choose_commit_duration(ocr_candidates, measured):
    # Mirror of app.choose_commit_duration (kept standalone so the script runs without the app deps).
    cands = [int(v) for v in ocr_candidates if DURATION_MIN_SEC <= int(v) <= DURATION_MAX_SEC]
    meas_ok = measured is not None and DURATION_MIN_SEC <= int(measured) <= DURATION_MAX_SEC
    if not cands:
        return int(measured) if meas_ok else None
    if meas_ok:
        tol = max(8, round(int(measured) * 0.25))
        near = [v for v in cands if abs(v - int(measured)) <= tol]
        if near:
            return most_common_first_seen(near)
        # Trailing-digit salvage (89 read as 899) only for a single weak read; a
        # repeated consensus is kept even against a small bounced measurement.
        for v in cands:
            w = v // 10
            if cands.count(v) == 1 and w >= DURATION_MIN_SEC and abs(w - int(measured)) <= tol:
                return w
    return most_common_first_seen(cands)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    parser.add_argument("--db", default=str(DB_PATH), help="path to tbh_ocr_stats.sqlite3")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB not found: {db_path}")
        return 1

    if args.apply:
        backup = db_path.with_suffix(db_path.suffix + "." + datetime.now().strftime("%Y%m%d%H%M%S") + ".bak")
        shutil.copy2(db_path, backup)
        print(f"backup: {backup}")

    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT id, ts_iso, stage, duration_sec, money_delta, raw_text FROM stage_runs ORDER BY ts"
    ).fetchall()

    changes = []
    for rid, ts_iso, stage, dur, delta, raw in rows:
        raw = raw or ""
        stage_reads = [s for s in STAGE_RE.findall(raw) if is_valid_stage(s)]
        new_stage = most_common_first_seen(stage_reads) or stage

        dur_reads = [int(s) for s in DUR_RE.findall(raw)]
        m = MEASURED_RE.search(raw)
        measured = int(m.group(1)) if m else None
        new_dur = choose_commit_duration(dur_reads, measured) if (dur_reads or measured is not None) else dur

        if new_stage == stage and new_dur == dur:
            continue

        new_mps = new_mph = None
        if new_stage and new_dur and delta is not None and delta >= 0:
            new_mps = delta / new_dur
            new_mph = new_mps * 3600
        changes.append((rid, ts_iso, stage, new_stage, dur, new_dur, new_mps, new_mph))

    if not changes:
        print("no rows need repair")
        return 0

    print(f"{len(changes)} row(s) to repair:")
    for rid, ts_iso, stage, new_stage, dur, new_dur, _, _ in changes:
        marks = []
        if new_stage != stage:
            marks.append(f"stage {stage} -> {new_stage}")
        if new_dur != dur:
            marks.append(f"duration {dur} -> {new_dur}")
        print(f"  id={rid} {ts_iso}: " + ", ".join(marks))

    if not args.apply:
        print("dry-run only. re-run with --apply to write.")
        return 0

    for rid, _, _, new_stage, _, new_dur, new_mps, new_mph in changes:
        con.execute(
            "UPDATE stage_runs SET stage=?, duration_sec=?, mps=?, mph=? WHERE id=?",
            (new_stage, new_dur, new_mps, new_mph, rid),
        )
    con.commit()
    print("applied.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
