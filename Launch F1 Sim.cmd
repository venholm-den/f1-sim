@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Project Python environment not found. See docs\simulation-centre.md for setup.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m portable_app.web_main
if errorlevel 1 (
  echo The app could not start. See the error above and docs\simulation-centre.md.
  pause
)
