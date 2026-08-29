@echo off
rem ── SPX Paper Trader — double-click to start ─────────────────────────────
rem Installs dependencies (first run only takes a minute), starts the
rem dashboard, and opens it in your browser. Close this window to stop.
cd /d %~dp0

where python >nul 2>nul
if %errorlevel%==0 (set PY=python) else (set PY=py -3)

%PY% -m pip install -q -r requirements.txt

start "" http://127.0.0.1:5250/
%PY% paper_dashboard.py
pause
