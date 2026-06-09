@echo off
REM One-click launcher for the HarnessForge wizard (opens the spec wizard in your browser).
REM Prefers uv (auto-syncs the [wizard] extra); offers to install uv if it's missing.
echo [HarnessForge] Wizard launcher
cd /d "%~dp0"
echo [HarnessForge] Folder: %CD%
echo.

echo [HarnessForge] Step 1/4: looking for uv on PATH ...
where uv >nul 2>nul
if not errorlevel 1 (
    echo [HarnessForge] Found uv on PATH.
    goto :run
)

echo [HarnessForge] Step 2/4: checking known uv install locations ...
if exist "%USERPROFILE%\.local\bin\uv.exe" (
    echo [HarnessForge] Found uv in %USERPROFILE%\.local\bin - adding to PATH for this run.
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" (
    echo [HarnessForge] Found uv in the WinGet Links folder - adding to PATH for this run.
    set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
)
where uv >nul 2>nul
if not errorlevel 1 goto :run

echo [HarnessForge] Step 3/4: looking for an installed harnessforge command ...
where harnessforge >nul 2>nul
if not errorlevel 1 (
    echo [HarnessForge] Found the harnessforge command.
    goto :run_cmd
)

echo [HarnessForge] Step 4/4: uv is not installed yet.
echo.
echo   The HarnessForge wizard needs uv - a small, self-contained tool that manages
echo   Python and dependencies for you (user-level install, no admin required).
set "REPLY=Y"
set /p "REPLY=  Install uv now? [Y/n] "
if /i "%REPLY%"=="n" goto :manual

where winget >nul 2>nul
if not errorlevel 1 (
    echo [HarnessForge] Installing uv via winget ...
    winget install --id astral-sh.uv -e --accept-package-agreements --accept-source-agreements
)
if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
where uv >nul 2>nul
if not errorlevel 1 goto :run

echo [HarnessForge] Installing uv via the official installer ...
powershell -ExecutionPolicy Bypass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if not errorlevel 1 goto :run

:manual
echo.
echo [HarnessForge] Could not find or install uv. Install it manually (user-level, no admin):
echo     winget install astral-sh.uv
echo     - or -  powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
echo   then double-click this again.
echo.
pause
goto :eof

:run
echo [HarnessForge] Launching: uv run --extra wizard harnessforge wizard --open
echo.
uv run --extra wizard harnessforge wizard --open
echo.
echo [HarnessForge] Process exited (code %errorlevel%). Press a key to close.
pause >nul
goto :eof

:run_cmd
echo [HarnessForge] Launching: harnessforge wizard --open
echo.
harnessforge wizard --open
echo.
echo [HarnessForge] Process exited (code %errorlevel%). Press a key to close.
pause >nul
goto :eof
