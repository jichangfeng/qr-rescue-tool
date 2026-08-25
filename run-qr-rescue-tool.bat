@echo off
setlocal
cd /d "%~dp0"

for /f "delims=" %%F in ('dir /b /a:-d /o:-d "dist\qr-rescue-tool-v*-windows-x64.exe" 2^>nul') do (
  start "" "dist\%%F" %*
  exit /b 0
)

where uv >nul 2>nul
if errorlevel 1 (
  echo uv is required to run this project from source.
  echo Install it from https://docs.astral.sh/uv/getting-started/installation/
  echo Then open a new terminal and run this script again.
  pause
  exit /b 1
)

set "VENV_PYTHON=.venv\Scripts\python.exe"
set "CREATE_VENV=0"

if not exist "%VENV_PYTHON%" set "CREATE_VENV=1"

if exist "%VENV_PYTHON%" (
  "%VENV_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)" >nul 2>nul
  if errorlevel 1 set "CREATE_VENV=1"
)

if "%CREATE_VENV%"=="1" (
  if exist ".venv" (
    echo Recreating .venv with Python 3.13...
    rmdir /s /q ".venv"
    if exist ".venv" goto :error
  ) else (
    echo Creating .venv with Python 3.13...
  )

  uv venv --python 3.13
  if errorlevel 1 goto :error
)

echo Checking project dependencies...
uv pip install --link-mode copy -r requirements.txt
if errorlevel 1 goto :error

if not exist ".venv\Scripts\pythonw.exe" goto :error

echo Starting QR Rescue Tool...
start "" ".venv\Scripts\pythonw.exe" qr_rescue.py %*
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo Initialization or startup failed.
echo Make sure uv and the network connection are available, then try:
echo   uv venv --python 3.13
echo   uv pip install -r requirements.txt
pause
exit /b 1
