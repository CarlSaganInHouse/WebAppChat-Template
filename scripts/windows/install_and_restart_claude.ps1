# PowerShell script to install Anthropic SDK and restart WebAppChat
# Run as Administrator

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Installing Anthropic SDK for Claude" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Set-Location "R:\WebAppChat"

Write-Host "Step 1: Installing anthropic in virtual environment..." -ForegroundColor Yellow
& "R:\WebAppChat\.venv\Scripts\python.exe" -m pip install "anthropic>=0.39.0"

Write-Host ""
Write-Host "Step 2: Verifying installation..." -ForegroundColor Yellow
& "R:\WebAppChat\.venv\Scripts\python.exe" -c "import anthropic; print('Anthropic SDK version:', anthropic.__version__)"

Write-Host ""
Write-Host "Step 3: Stopping existing Python processes..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

Write-Host ""
Write-Host "Step 4: Starting WebAppChat..." -ForegroundColor Yellow
Start-Process -FilePath "R:\WebAppChat\.venv\Scripts\python.exe" -ArgumentList "app.py" -WorkingDirectory "R:\WebAppChat" -WindowStyle Hidden

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Done! WebAppChat is starting..." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Please wait 5-10 seconds, then try accessing:" -ForegroundColor White
Write-Host "http://192.168.50.5:5000" -ForegroundColor Cyan
Write-Host ""
Write-Host "Claude models should now work!" -ForegroundColor Green
Write-Host ""
