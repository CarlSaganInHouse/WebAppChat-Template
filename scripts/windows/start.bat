@echo off
cd /d "%~dp0"
echo.
echo ========================================
echo   WebAppChat - Starting Application
echo ========================================
echo.

:: Check if virtual environment exists
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found at .venv\
    echo Please create a virtual environment first:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo Using virtual environment: .venv\Scripts\python.exe
echo.
echo Starting Flask server...
echo Web interface will open at: http://127.0.0.1:5000
echo.
echo Press Ctrl+C to stop the server
echo ========================================
echo.

:: Start browser (delayed to let server start)
start "" /min timeout /t 2 /nobreak && start "" http://127.0.0.1:5000

:: Run the application
".venv\Scripts\python.exe" app.py

pause
