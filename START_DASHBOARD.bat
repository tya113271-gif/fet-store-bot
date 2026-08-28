@echo off
title FET STORE - Bot Dashboard Launcher
color 0a

echo ===================================================================
echo             FET STORE - Discord Bot & Web Dashboard
echo ===================================================================
echo.
echo Starting Web Server on http://localhost:5000 ...
echo.

set PYTHON_PATH=%LOCALAPPDATA%\Programs\Python\Python312\python.exe

if not exist "%PYTHON_PATH%" (
    python app.py
) else (
    "%PYTHON_PATH%" app.py
)

pause
