@echo off
REM Workaround for network drive execution restrictions
REM This runs the app using system Python with venv site-packages

cd /d "%~dp0"
echo.
echo Starting WebAppChat from network drive...
echo Using system Python with venv packages
echo.

REM Add venv site-packages to Python path and run
set PYTHONPATH=%~dp0.venv\Lib\site-packages
"C:\Program Files\Python312\python.exe" app.py

pause
