@echo off
REM ---------------------------------------------------------------------------
REM Builds the Windows installer:  output\STM32DeviceTool-Setup-1.0.0.exe
REM
REM Needs on the build PC (one-time):
REM   - Python 3.13 (64-bit, x64) from python.org, "Add python.exe to PATH" ticked
REM   - Inno Setup 6.3+ in its default install location
REM Run it by double-clicking, or from a Command Prompt in this folder.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

if not exist .venv (
    py -3.13 -m venv .venv || py -3 -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
python -m pip install -r requirements-build.txt || goto :error

python -m pytest -q || goto :error
if not exist resources\icon.ico python tools\make_icon.py || goto :error

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
pyinstaller --noconfirm device_tool.spec || goto :error

REM The frozen app has no console, so its output is captured in a file.
dist\STM32DeviceTool\STM32DeviceTool.exe --selftest > selftest.log 2>&1
type selftest.log
findstr /C:"SELFTEST PASSED" selftest.log >nul || goto :error

"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer_windows.iss || goto :error

echo.
echo Done: output\STM32DeviceTool-Setup-1.0.0.exe
pause
exit /b 0

:error
echo.
echo BUILD FAILED - see the messages above.
pause
exit /b 1
