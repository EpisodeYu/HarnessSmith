@echo off
REM One-click launcher for the HarnessForge wizard (opens the spec wizard in your browser).
REM Prefers uv (auto-syncs the [wizard] extra); offers to install uv if it's missing.
echo [HarnessForge] Wizard launcher
cd /d "%~dp0"
echo [HarnessForge] Folder: %CD%
echo.

echo [HarnessForge] Step 1/4: looking for uv on PATH ...
where uv >nul 2>nul
if not errorlevel 1 goto :run

echo [HarnessForge] Step 2/4: checking known uv install locations ...
if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
where uv >nul 2>nul
if not errorlevel 1 goto :run

REM Look for the installed console script by its .exe name on purpose: a bare
REM `harnessforge` would resolve to THIS file (HarnessForge.bat) first, since
REM Windows searches the current dir and is case-insensitive -> infinite relaunch.
echo [HarnessForge] Step 3/4: looking for an installed harnessforge command ...
where harnessforge.exe >nul 2>nul
if not errorlevel 1 goto :run_cmd

echo [HarnessForge] Step 4/4: uv is not installed yet.
echo.
echo   The wizard needs uv - a small tool that manages Python and dependencies for
echo   you (user-level install, no admin required). How would you like to install it?
echo     [1] Standard - winget or the official installer (downloads from GitHub)
echo     [2] China mirror - pip + Tsinghua mirror (needs Python already installed)
echo     [n] Don't install
set "CHOICE=1"
set /p "CHOICE=  Choose [1/2/n]: "
if /i "%CHOICE%"=="n" goto :manual
if "%CHOICE%"=="2" goto :install_cn

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
goto :manual

:install_cn
echo [HarnessForge] China mirror: installing uv from the Tsinghua PyPI mirror ...
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [HarnessForge] No Python found - the China-mirror path needs Python first.
    goto :manual_cn
)
%PY% -m pip install --user uv -i https://pypi.tuna.tsinghua.edu.cn/simple
%PY% -m uv --version >nul 2>nul
if errorlevel 1 (
    echo [HarnessForge] pip did not produce a runnable uv.
    goto :manual_cn
)
echo [HarnessForge] uv installed. Using the Tsinghua mirror + your system Python.
set "UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
set "UV_PYTHON_PREFERENCE=only-system"
goto :run_py

:manual
echo.
echo [HarnessForge] Could not find or install uv. Install it manually (user-level, no admin):
echo     winget install astral-sh.uv
echo     - or -  powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
echo   then double-click this again.
echo.
pause
goto :eof

:manual_cn
echo.
echo [HarnessForge] The China-mirror path needs Python. Options:
echo     1) Install Python (https://www.python.org/downloads/ , reachable in China),
echo        then run this again and choose [2].
echo     2) Or with Python present:  pip install uv -i https://pypi.tuna.tsinghua.edu.cn/simple
echo     3) Or use a VPN/proxy and choose [1].
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
echo [HarnessForge] Launching: harnessforge.exe wizard --open
echo.
harnessforge.exe wizard --open
echo.
echo [HarnessForge] Process exited (code %errorlevel%). Press a key to close.
pause >nul
goto :eof

:run_py
echo [HarnessForge] Launching: %PY% -m uv run --extra wizard harnessforge wizard --open
echo.
%PY% -m uv run --extra wizard harnessforge wizard --open
echo.
echo [HarnessForge] Process exited (code %errorlevel%). Press a key to close.
pause >nul
goto :eof
