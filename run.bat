@echo off
chcp 65001 >nul
rem Move to this file's own folder, then run the script.
cd /d "%~dp0"

python pull_whop.py
if errorlevel 1 (
  echo.
  echo [!] python not found, trying py launcher...
  py pull_whop.py
)

echo.
echo Done. Press any key to close.
pause >nul
