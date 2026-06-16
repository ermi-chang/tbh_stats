@echo off
setlocal
cd /d "%~dp0"
REM === Phase A diagnostic mode (temporary; for stage-seconds reset investigation) ===
REM Logs detector state per poll/tick to _play_samples\diag\diag_*.jsonl
REM Use run.bat for normal startup. This file is only for the investigation.
set TBH_DIAG=1
REM Gauge crop + context PNGs (heavier). Uncomment only when recalibrating the gauge ROI.
REM set TBH_DIAG_FRAMES=1
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)
echo ==========================================================
echo   DIAG MODE ON   TBH_DIAG=%TBH_DIAG%
echo   log output: _play_samples\diag\diag_*.jsonl
echo   If you see this banner, logging is active.
echo ==========================================================
.venv\Scripts\python.exe -m src.tbh_ocr_stats.app
pause
