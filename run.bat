@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
python -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>&1
if not errorlevel 1 (
  set "PYTHON=python"
  goto run
)
py -3 -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>&1
if not errorlevel 1 (
  set "PYTHON=py -3"
  goto run
)
echo Python 3.9+ not found. Please install Python first.
pause
exit /b 1
:run
if "%~1"=="" (
  %PYTHON% pull_whop.py --interactive
) else (
  %PYTHON% pull_whop.py %*
)
set "RESULT=%ERRORLEVEL%"
echo.
echo Finished with exit code %RESULT%. Press any key to close.
pause >nul
exit /b %RESULT%
