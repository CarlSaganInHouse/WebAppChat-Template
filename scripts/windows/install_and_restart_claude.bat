@echo off
REM Script to install Anthropic SDK and restart WebAppChat
REM Run this as Administrator

echo ========================================
echo Installing Anthropic SDK for Claude
echo ========================================

cd /d R:\WebAppChat

echo.
echo Step 1: Activating virtual environment...
call .venv\Scripts\activate.bat

echo.
echo Step 2: Installing anthropic package...
python -m pip install anthropic>=0.39.0

echo.
echo Step 3: Verifying installation...
python -c "import anthropic; print('✓ Anthropic SDK version:', anthropic.__version__)"

echo.
echo Step 4: Killing existing Python processes...
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul

echo.
echo Step 5: Starting WebAppChat...
start "WebAppChat" python app.py

echo.
echo ========================================
echo Done! WebAppChat is starting...
echo ========================================
echo.
echo Please wait 5-10 seconds, then try accessing:
echo http://192.168.50.5:5000
echo.
echo Claude models should now work!
echo.
pause
