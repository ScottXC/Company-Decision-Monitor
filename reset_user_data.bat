@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\reset_user_data.ps1"
if errorlevel 1 (
    echo Failed to reset Company Decision Monitor local user data.
    exit /b 1
)

echo Reset complete.
endlocal
