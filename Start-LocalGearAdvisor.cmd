@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\local-gear-advisor.exe" (
  echo Local Gear Advisor ist noch nicht eingerichtet.
  echo Bitte zuerst im Projektordner ausfuehren: uv sync --group dev
  pause
  exit /b 2
)
".venv\Scripts\local-gear-advisor.exe" gui
set "LGA_EXIT=%ERRORLEVEL%"
if not "%LGA_EXIT%"=="0" (
  echo.
  echo Local Gear Advisor wurde mit Fehlercode %LGA_EXIT% beendet.
  pause
)
exit /b %LGA_EXIT%
