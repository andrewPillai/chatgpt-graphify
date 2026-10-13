@echo off
setlocal
set "SOURCE_DIR=%~dp0.."
set "INSTALL_DIR=%LOCALAPPDATA%\ChatGPT Graphify"
set "VENV_DIR=%INSTALL_DIR%\venv"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  set "PYTHON=py -3"
) else (
  where python >nul 2>nul
  if not %ERRORLEVEL% EQU 0 (
    echo Python 3.9 or newer is required. Install it from https://www.python.org/downloads/windows/ and run this installer again.
    pause
    exit /b 1
  )
  set "PYTHON=python"
)

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if not exist "%VENV_DIR%\Scripts\python.exe" %PYTHON% -m venv "%VENV_DIR%"
call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install "%SOURCE_DIR%"

set "LAUNCHER=%VENV_DIR%\Scripts\pythonw.exe"
set "SHORTCUT=%USERPROFILE%\Desktop\ChatGPT Graphify.lnk"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut('%SHORTCUT%'); $s.TargetPath='%LAUNCHER%'; $s.Arguments='-m chatgpt_graphify.desktop'; $s.WorkingDirectory='%INSTALL_DIR%'; $s.IconLocation='%LAUNCHER%'; $s.Save()"

echo.
echo ChatGPT Graphify is installed. A desktop shortcut was created.
start "" "%LAUNCHER%" -m chatgpt_graphify.desktop
endlocal
