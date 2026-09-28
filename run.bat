@echo off
REM ETIP one-command launcher (Windows).
REM Creates the virtual environment, installs, migrates, seeds demo data on first
REM run, starts the server in a new window, and opens the dashboard.
setlocal
cd /d "%~dp0"

if not defined PORT set PORT=8000
if not defined DATABASE_URL set DATABASE_URL=sqlite:///./etip_demo.db
if not defined JWT_SECRET_KEY set JWT_SECRET_KEY=demo-secret-key-32-bytes-minimum-xxxx

REM 1. Virtual environment
if not exist .venv (
  echo ==^> Creating virtual environment ^(.venv^)...
  python -m venv .venv
)
call .venv\Scripts\activate.bat

REM 2. Install the project (only if not already importable)
python -c "import app" >nul 2>&1
if errorlevel 1 (
  echo ==^> Installing ETIP and dependencies ^(first run only^)...
  python -m pip install -q --upgrade pip
  pip install -q -e .
)

REM 4. Database schema
echo ==^> Applying database migrations...
alembic upgrade head

REM 5. Start the server in a new window
echo ==^> Starting server on http://localhost:%PORT% ...
start "ETIP server" cmd /k "call .venv\Scripts\activate.bat && set DATABASE_URL=%DATABASE_URL%&& set JWT_SECRET_KEY=%JWT_SECRET_KEY%&& uvicorn app.main:app --port %PORT%"

REM 6. Give it a few seconds to come up
echo ==^> Waiting for the server...
timeout /t 8 /nobreak >nul

REM 7. Seed demo data unless the demo admin already logs in.
REM     Probe the login endpoint rather than checking for the DB file, because
REM     migrations create the file before any data exists.
for /f %%C in ('curl -s -o nul -w "%%{http_code}" -X POST "http://localhost:%PORT%/api/v1/auth/login" -H "Content-Type: application/json" --data-binary "{\"organization_slug\":\"demo-transformation-co\",\"email\":\"admin@demo.co\",\"password\":\"Str0ng-Passphrase!1\"}"') do set LOGIN_CODE=%%C
if not "%LOGIN_CODE%"=="200" (
  echo ==^> Seeding demo data ^(login probe returned %LOGIN_CODE%^)...
  python scripts\seed_demo.py
) else (
  echo ==^> Demo data already present; skipping seed.
)

echo.
echo ======================================================================
echo   ETIP is running:   http://localhost:%PORT%/
echo   API browser:       http://localhost:%PORT%/docs
echo.
echo   Sign in ^(admin^):   organization  demo-transformation-co
echo                      email         admin@demo.co
echo                      password      Str0ng-Passphrase!1
echo   Read-only viewer:  viewer@demo.co  ^(same org / password^)
echo.
echo   Close the "ETIP server" window to stop.
echo ======================================================================

REM 8. Open the browser
start "" http://localhost:%PORT%/
pause
