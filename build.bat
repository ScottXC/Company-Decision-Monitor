@echo off
setlocal
cd /d "%~dp0"

call conda activate cdm-desktop >nul 2>nul
if errorlevel 1 (
  echo Warning: failed to activate conda environment cdm-desktop.
  echo Continuing with the current Python environment.
  python --version >nul 2>nul
  if errorlevel 1 (
    echo Python is not available in the current environment.
    exit /b 1
  )
)

set PYTHONPATH=%CD%\src;%PYTHONPATH%
set PYTHONUNBUFFERED=1
python scripts\build_windows.py
if errorlevel 1 exit /b 1

endlocal
