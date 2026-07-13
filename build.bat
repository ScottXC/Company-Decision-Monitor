@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE="

call conda activate cdm-desktop >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_EXE=python"
) else (
  echo Info: conda environment cdm-desktop not active; trying next Python candidate.
)

if "%PYTHON_EXE%"=="" (
  call conda activate cdm >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_EXE=python"
  ) else (
    echo Info: conda environment cdm not active; trying local Python paths.
  )
)

if "%PYTHON_EXE%"=="" (
  if exist "%USERPROFILE%\.conda\envs\cdm-desktop\python.exe" (
    set "PYTHON_EXE=%USERPROFILE%\.conda\envs\cdm-desktop\python.exe"
    set "PATH=%USERPROFILE%\.conda\envs\cdm-desktop;%USERPROFILE%\.conda\envs\cdm-desktop\Scripts;%PATH%"
  )
)

if "%PYTHON_EXE%"=="" (
  if exist "%USERPROFILE%\.conda\envs\cdm\python.exe" (
    set "PYTHON_EXE=%USERPROFILE%\.conda\envs\cdm\python.exe"
    set "PATH=%USERPROFILE%\.conda\envs\cdm;%USERPROFILE%\.conda\envs\cdm\Scripts;%PATH%"
  )
)

if "%PYTHON_EXE%"=="" (
  echo Info: using current Python environment.
  python --version >nul 2>nul
  if errorlevel 1 (
    echo Python is not available in the current environment.
    exit /b 1
  )
  set "PYTHON_EXE=python"
)

set PYTHONPATH=%CD%\src;%PYTHONPATH%
set PYTHONUNBUFFERED=1
"%PYTHON_EXE%" scripts\build_windows.py
if errorlevel 1 exit /b 1

endlocal
