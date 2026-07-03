@echo off
setlocal

set "APP_NAME=HB_Automation"
set "SRC_DIR=%~dp0app"
set "LAUNCHER_SRC=%~dp0launch.cmd"
set "TARGET_DIR=%LOCALAPPDATA%\%APP_NAME%"
set "EXE=%TARGET_DIR%\HB_Automation.exe"
set "LAUNCHER=%TARGET_DIR%\launch.cmd"

if not exist "%SRC_DIR%\HB_Automation.exe" (
  echo [ERROR] app\HB_Automation.exe not found.
  echo Please extract the whole zip file first, then run install.cmd again.
  pause
  exit /b 1
)

if not exist "%SRC_DIR%\_internal\base_library.zip" (
  echo [ERROR] app\_internal\base_library.zip not found.
  echo The embedded Python standard library is missing. Extract the whole zip again,
  echo or ask IT/security to restore quarantined files.
  pause
  exit /b 1
)

if not exist "%LAUNCHER_SRC%" (
  echo [ERROR] launch.cmd not found next to install.cmd.
  echo Please extract the whole zip file first, then run install.cmd again.
  pause
  exit /b 1
)

echo Installing %APP_NAME%...
if exist "%TARGET_DIR%" rmdir /s /q "%TARGET_DIR%"
mkdir "%TARGET_DIR%"
xcopy "%SRC_DIR%\*" "%TARGET_DIR%\" /e /i /y >nul
copy /y "%LAUNCHER_SRC%" "%LAUNCHER%" >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws=New-Object -ComObject WScript.Shell; " ^
  "$desktop=[Environment]::GetFolderPath('Desktop'); " ^
  "$start=[Environment]::GetFolderPath('StartMenu') + '\Programs'; " ^
  "$launcher='%LAUNCHER%'; " ^
  "$lnk=$ws.CreateShortcut((Join-Path $desktop 'HB Automation.lnk')); " ^
  "$lnk.TargetPath=$launcher; $lnk.WorkingDirectory='%TARGET_DIR%'; $lnk.Save(); " ^
  "$lnk=$ws.CreateShortcut((Join-Path $start 'HB Automation.lnk')); " ^
  "$lnk.TargetPath=$launcher; $lnk.WorkingDirectory='%TARGET_DIR%'; $lnk.Save();"

echo.
echo Installation completed.
echo Desktop shortcut: HB Automation
echo.
pause