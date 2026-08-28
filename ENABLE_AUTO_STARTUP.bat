@echo off
title FET STORE - Enable Auto-Startup
color 0a

echo ===================================================================
echo     FET STORE - Setup Bot Auto-Start with Windows
echo ===================================================================
echo.

set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set TARGET_VBS=C:\Users\azeal\.gemini\antigravity\scratch\FET_BOT_DASHBOARD\RUN_SILENT_STARTUP.vbs

copy /y "%TARGET_VBS%" "%STARTUP_DIR%\FET_BOT_STARTUP.vbs" >nul

echo [OK] Auto-startup enabled successfully!
echo The Bot and Dashboard will now start automatically whenever your PC boots up!
echo.
pause
