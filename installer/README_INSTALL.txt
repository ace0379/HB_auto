HB Automation Install Guide
===========================

1. Extract the zip file.
2. Double-click install.cmd.
3. Run "HB Automation" from the desktop shortcut.

Install location:
  %LOCALAPPDATA%\HB_Automation

Uninstall:
  Double-click uninstall.cmd.

Notes:
  Do not copy install.cmd or HB_Automation.exe alone. Keep the app folder and launch.cmd next to install.cmd.
  The desktop shortcut starts launch.cmd, which clears PYTHONHOME and PYTHONPATH before running the embedded Python app.
  For no-zip builds, app\_internal\encodings is used instead of app\_internal\base_library.zip. Copy the whole package folder, not just HB_Automation.exe.