@echo off
setlocal enabledelayedexpansion

set "FLORABOT_ROOT=%~dp0"
cd /d "%FLORABOT_ROOT%"

echo ========================================================
echo        Starting FloraBot Development Workspace
echo ========================================================

:: 1. Copy .env if missing
if not exist "%FLORABOT_ROOT%backend\.env" (
    echo [Setup] Creating backend\.env from example...
    copy "%FLORABOT_ROOT%backend\.env.example" "%FLORABOT_ROOT%backend\.env" >nul
)

:: 2. Find a valid host Python
set "PYTHON_CMD="
py -3.11 -c "import sys; exit(0)" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3.11"
) else (
    py -3 -c "import sys; exit(0)" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=py -3"
    ) else (
        python -c "import sys; exit(0)" >nul 2>&1
        if not errorlevel 1 (
            set "PYTHON_CMD=python"
        )
    )
)

if "%PYTHON_CMD%"=="" (
    echo [ERROR] No working Python installation found in PATH.
    echo Please install Python 3.11 or later from python.org and try again.
    pause
    exit /b 1
)

:: 3. Check or recreate virtual environment
set "VENV_DIR=%FLORABOT_ROOT%backend\.venv311"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

set "RECREATE_VENV=0"
if not exist "%VENV_PY%" (
    set "RECREATE_VENV=1"
) else (
    "%VENV_PY%" -c "import sys" >nul 2>&1
    if errorlevel 1 (
        echo [Setup] Detected invalid or relocated virtualenv. Recreating...
        set "RECREATE_VENV=1"
    )
)

if "%RECREATE_VENV%"=="1" (
    echo [Setup] Creating fresh Python virtual environment using %PYTHON_CMD%...
    if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%" >nul 2>&1
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    if exist "%VENV_DIR%\flora-deps-installed" del "%VENV_DIR%\flora-deps-installed"
)

:: 4. Install backend dependencies
if not exist "%VENV_DIR%\flora-deps-installed" (
    echo [Setup] Installing backend dependencies from requirements.txt...
    pushd "%FLORABOT_ROOT%backend"
    "%VENV_PY%" -m pip install --upgrade pip
    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        popd
        echo [ERROR] Backend dependency installation failed.
        pause
        exit /b 1
    )
    type nul > "%VENV_DIR%\flora-deps-installed"
    popd
)

:: 5. Install frontend dependencies
if not exist "%FLORABOT_ROOT%node_modules" (
    echo [Setup] Installing frontend dependencies via npm...
    pushd "%FLORABOT_ROOT%"
    call npm install
    if errorlevel 1 (
        popd
        echo [ERROR] Node.js and npm are required. Install Node.js 18+ and try again.
        pause
        exit /b 1
    )
    popd
)

:: 6. Launch FloraBot services
echo [Startup] Launching FloraBot API backend on http://localhost:8001 ...
start "FloraBot API" /D "%FLORABOT_ROOT%backend" cmd /k ""%VENV_PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload"

echo [Startup] Launching FloraBot Web frontend on http://localhost:5190 ...
start "FloraBot Web" /D "%FLORABOT_ROOT%" cmd /k "npm run dev"

timeout /t 3 /nobreak >nul
start "" http://localhost:5190

echo ========================================================
echo   FloraBot is starting up! Check the two open windows.
echo ========================================================
endlocal
