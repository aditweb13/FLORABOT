@echo off
setlocal
set "FLORABOT_ROOT=%~dp0"
if not exist "%FLORABOT_ROOT%backend\.env" copy "%FLORABOT_ROOT%backend\.env.example" "%FLORABOT_ROOT%backend\.env" >nul
if not exist "%FLORABOT_ROOT%backend\.venv\Scripts\python.exe" (
  echo Creating FloraBot Python environment...
  py -3 -m venv "%FLORABOT_ROOT%backend\.venv"
  if errorlevel 1 (echo Python 3.10+ is required. Install Python and try again.& pause & exit /b 1)
)
if not exist "%FLORABOT_ROOT%backend\.venv\flora-deps-installed" (
  echo Installing FloraBot backend dependencies...
  pushd "%FLORABOT_ROOT%backend"
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 (popd & echo Backend dependency installation failed.& pause & exit /b 1)
  type nul > .venv\flora-deps-installed
  popd
)
if not exist "%FLORABOT_ROOT%node_modules" (
  echo Installing FloraBot frontend dependencies...
  pushd "%FLORABOT_ROOT%"
  call npm install
  if errorlevel 1 (popd & echo Node.js and npm are required. Install them and try again.& pause & exit /b 1)
  popd
)
start "FloraBot API" /D "%FLORABOT_ROOT%backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --reload"
start "FloraBot Web" /D "%FLORABOT_ROOT%" cmd /k "npm run dev"
timeout /t 3 /nobreak >nul
start "" http://localhost:5173
endlocal
