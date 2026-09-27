@echo off
setlocal

cd /d "%~dp0"

set "VENV_DIR=.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

if exist "%PYTHON_EXE%" goto install

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv "%VENV_DIR%"
) else (
    python -m venv "%VENV_DIR%"
)

if errorlevel 1 (
    echo Failed to create the virtual environment.
    echo Install Python 3.10 or later, then run this file again.
    pause
    exit /b 1
)

:install
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed to upgrade pip.
    pause
    exit /b 1
)

"%PYTHON_EXE%" -m pip install -e .
if errorlevel 1 (
    echo Failed to install pyTaskFlow.
    pause
    exit /b 1
)

echo.
echo Setup complete.
echo Double-click run_pytaskflow.vbs to start pyTaskFlow.
pause
