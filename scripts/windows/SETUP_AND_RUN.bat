@echo off
REM ============================================
REM One-time setup and run for WebAppChat
REM ============================================

cd /d "%~dp0"

echo.
echo ========================================
echo   WebAppChat - Setup and Run
echo ========================================
echo.

REM Check if packages are installed
if not exist ".venv\Lib\site-packages\flask\" (
    echo Flask not found in venv. Installing packages...
    echo.
    echo Installing requirements to .venv\Lib\site-packages...
    "C:\Program Files\Python312\python.exe" -m pip install --target=".venv\Lib\site-packages" -r requirements.txt
    echo.
    echo Installation complete!
    echo.
)

echo Starting WebAppChat...
echo Location: %CD%
echo Python:   C:\Program Files\Python312\python.exe
echo Packages: .venv\Lib\site-packages
echo.
echo Server will start on: http://127.0.0.1:5000
echo.
echo Press Ctrl+C to stop the server
echo ========================================
echo.

REM Set Python path and run
set "PYTHONPATH=%~dp0.venv\Lib\site-packages"
"C:\Program Files\Python312\python.exe" app.py

echo.
echo Server stopped.
pause
