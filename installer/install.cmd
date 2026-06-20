@echo off
setlocal

set "APP_NAME=HB_Automation"
set "SRC_DIR=%~dp0app"
set "TARGET_DIR=%LOCALAPPDATA%\%APP_NAME%"
set "EXE=%TARGET_DIR%\HB_Automation.exe"

if not exist "%SRC_DIR%\HB_Automation.exe" (
  echo [ERROR] app\HB_Automation.exe not found.
  echo Please extract the whole zip file first, then run install.cmd again.
  pause
  exit /b 1
)

echo Installing %APP_NAME%...
if exist "%TARGET_DIR%" rmdir /s /q "%TARGET_DIR%"
mkdir "%TARGET_DIR%"
xcopy "%SRC_DIR%\*" "%TARGET_DIR%\" /e /i /y >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws=New-Object -ComObject WScript.Shell; " ^
  "$desktop=[Environment]::GetFolderPath('Desktop'); " ^
  "$start=[Environment]::GetFolderPath('StartMenu') + '\Programs'; " ^
  "$exe='%EXE%'; " ^
  "$lnk=$ws.CreateShortcut((Join-Path $desktop 'HB Automation.lnk')); " ^
  "$lnk.TargetPath=$exe; $lnk.WorkingDirectory='%TARGET_DIR%'; $lnk.Save(); " ^
  "$lnk=$ws.CreateShortcut((Join-Path $start 'HB Automation.lnk')); " ^
  "$lnk.TargetPath=$exe; $lnk.WorkingDirectory='%TARGET_DIR%'; $lnk.Save();"

echo.
echo Installation completed.
echo Desktop shortcut: HB Automation
echo.
pause
