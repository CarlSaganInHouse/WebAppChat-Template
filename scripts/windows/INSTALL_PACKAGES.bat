@echo off
REM ============================================
REM Install packages to venv using system Python
REM ============================================

cd /d "%~dp0"

echo.
echo ========================================
echo   Installing WebAppChat Dependencies
echo ========================================
echo.
echo This will install packages to: .venv\Lib\site-packages
echo Using pip from: C:\Program Files\Python312\python.exe
echo.

REM Install packages directly to the venv site-packages
"C:\Program Files\Python312\python.exe" -m pip install --target=".venv\Lib\site-packages" -r requirements.txt

echo.
echo ========================================
echo   Installation Complete!
echo ========================================
echo.
echo You can now run: run_system_python.bat
echo.
pause
