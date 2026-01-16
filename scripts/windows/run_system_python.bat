@echo off
REM ============================================
REM WebAppChat - Network Drive Workaround
REM Uses system Python to bypass venv restrictions
REM ============================================

cd /d "%~dp0"

echo.
echo ========================================
echo   WebAppChat - Starting from Network Drive
echo ========================================
echo.
echo Location: %CD%
echo Python:   C:\Program Files\Python312\python.exe
echo Packages: .venv\Lib\site-packages
echo.
echo Server will start on: http://127.0.0.1:5000
echo.
echo Press Ctrl+C to stop the server
echo ========================================
echo.

REM Set Python path to include venv packages
set "PYTHONPATH=%~dp0.venv\Lib\site-packages"

REM Start the application
"C:\Program Files\Python312\python.exe" app.py

echo.
echo Server stopped.
pause
