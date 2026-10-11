@echo off
REM Double-click this file to start ReFrame and open it in your browser.
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
echo Starting ReFrame. Keep this window open while you use it. Close it to stop ReFrame.
echo.
"%PY%" -m reframe serve
pause
