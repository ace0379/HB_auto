@echo off
setlocal

set "APP_NAME=HB_Automation"
set "TARGET_DIR=%LOCALAPPDATA%\%APP_NAME%"

echo Uninstalling %APP_NAME%...

del "%USERPROFILE%\Desktop\HB Automation.lnk" >nul 2>nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\HB Automation.lnk" >nul 2>nul

if exist "%TARGET_DIR%" rmdir /s /q "%TARGET_DIR%"

echo.
echo Uninstall completed.
echo.
pause
