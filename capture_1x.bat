@echo off
setlocal
cd /d "%~dp0"
REM === Capture full game-window frames at the CURRENT game zoom (set the game to 1x first) ===
REM Saves to _play_samples\zoomcap\  (used to fix telop detection across 1x/1.25x/1.5x).
set TAG=zoomcap
set SECONDS=12
set INTERVAL=0.5
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)
echo ==========================================================
echo   Capturing FULL frames for %SECONDS%s at the current zoom
echo   Output: _play_samples\zoomcap\
echo   Make sure the game is running and a stage telop is on screen.
echo ==========================================================
.venv\Scripts\python.exe scripts\capture_play.py
pause
