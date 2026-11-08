@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo YTDLP Studio - Windows x64 portable build
echo Szukseges: Python 3.11-3.13 x64 es internetkapcsolat.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1" %*
if errorlevel 1 (
  echo.
  echo A BUILD NEM SIKERULT. Lasd a fenti hibauzenetet.
) else (
  echo.
  echo A BUILD KESZ. Az eredmeny a dist mappaban van.
)
pause
