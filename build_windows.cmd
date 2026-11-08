@echo off
cd /d "%~dp0"
echo YTDLP Studio - Windows x64 portable build
echo Requires Python 3.11-3.13 x64 (3.12 recommended) and internet access.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1"
if errorlevel 1 (
  echo.
  echo BUILD FAILED. Read the error messages above.
) else (
  echo.
  echo BUILD COMPLETE. Check the dist folder.
)
pause
