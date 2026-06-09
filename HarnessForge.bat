@echo off
REM One-click launcher for the HarnessForge wizard (opens the spec wizard in your browser).
REM Prefers uv (auto-syncs the [wizard] extra); offers to install uv if it's missing.
cd /d "%~dp0"

REM 1) uv already on PATH?
where uv >nul 2>nul
if not errorlevel 1 goto :run

REM 2) uv at a known user-level install location? add it to PATH for this run.
if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
where uv >nul 2>nul
if not errorlevel 1 goto :run

REM 3) an already-installed harnessforge command works too.
where harnessforge >nul 2>nul
if not errorlevel 1 goto :run_cmd

REM 4) offer to install uv (user-level, no admin).
echo.
echo   The HarnessForge wizard needs uv - a small, self-contained tool that manages
echo   Python and dependencies for you (user-level install, no admin required).
set "REPLY=Y"
set /p "REPLY=  Install uv now? [Y/n] "
if /i "%REPLY%"=="n" goto :manual

where winget >nul 2>nul
if not errorlevel 1 (
    echo   Installing uv via winget ...
    winget install --id astral-sh.uv -e --accept-package-agreements --accept-source-agreements
)
if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
where uv >nul 2>nul
if not errorlevel 1 goto :run

echo   Installing uv via the official installer ...
powershell -ExecutionPolicy Bypass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if not errorlevel 1 goto :run

:manual
echo.
echo   Could not find or install uv. Install it manually (user-level, no admin):
echo     winget install astral-sh.uv
echo     - or -  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
echo   then double-click this again.
pause
goto :eof

:run
uv run --extra wizard harnessforge wizard --open
goto :eof

:run_cmd
harnessforge wizard --open
goto :eof
