@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM --- Config ---
set "WSL_DISTRO="
set "APP_DIR=/home/aiman/.openclaw/workspace-jarvis/conv-proxy"
set "PORT=37374"
set "LOG=/tmp/conv-proxy.log"

if not "%~1"=="" set "PORT=%~1"

echo [conv-proxy] Killing old uvicorn/webapp processes...
wsl %WSL_DISTRO% bash -lc "pkill -f 'uvicorn webapp.app:app' || true; pkill -f 'python.*webapp.app:app' || true"

echo [conv-proxy] Starting on port %PORT% ...
wsl %WSL_DISTRO% bash -lc "cd %APP_DIR% && source .venv-kokoro/bin/activate && export $(grep -v '^#' .env | xargs) && PYTHONPATH=. nohup uvicorn webapp.app:app --host 0.0.0.0 --port %PORT% > %LOG% 2>&1 & echo $! > /tmp/conv-proxy.pid"

echo [conv-proxy] Waiting for health endpoint...
set "OK=0"
for /L %%i in (1,1,25) do (
  wsl %WSL_DISTRO% bash -lc "curl -fsS --max-time 2 http://localhost:%PORT%/api/status > /tmp/conv-proxy-status.json" >nul 2>&1
  if !errorlevel! EQU 0 (
    set "OK=1"
    goto :HEALTHY
  )
  timeout /t 1 >nul
)

:HEALTHY
if "%OK%"=="1" (
  echo [conv-proxy] UP. Status:
  wsl %WSL_DISTRO% bash -lc "cat /tmp/conv-proxy-status.json"
) else (
  echo [conv-proxy] FAILED to start. Tail log:
  wsl %WSL_DISTRO% bash -lc "tail -n 80 %LOG%"
  exit /b 1
)

echo.
echo [conv-proxy] Monitoring (Ctrl+C to exit monitor, service keeps running)...
:MONITOR
wsl %WSL_DISTRO% bash -lc "if curl -fsS --max-time 2 http://localhost:%PORT%/api/status >/dev/null; then echo [ok] %DATE% %TIME%; else echo [down] %DATE% %TIME%; fi"
timeout /t 5 >nul
goto :MONITOR
