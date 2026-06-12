@echo off
REM One-click launcher for the HarnessSmith setup wizard.
REM Lets you pick how to configure your harness: the Web form (opens in a browser)
REM or an interactive CLI wizard (right here in the terminal). Prefers uv (auto-syncs
REM the [wizard] extra for the web form); offers to install uv if it's missing.
echo [HarnessSmith] Setup launcher
cd /d "%~dp0"
echo [HarnessSmith] Folder: %CD%
echo.

REM --- Reuse the system proxy (corporate networks) so the curl probe below, the
REM official uv install, and uv's own sync all reach the net the same way. Only when
REM none is already set; curl/uv don't read the Windows WinINET proxy on their own,
REM whereas the wizard's urllib probe DOES - so without this the curl probe could
REM wrongly report PyPI unreachable and pin a mirror the proxy can't even reach.
if defined HTTP_PROXY goto :proxy_done
if defined HTTPS_PROXY goto :proxy_done
for /f "usebackq delims=" %%p in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue; if ($s.ProxyEnable -eq 1 -and $s.ProxyServer) { $p=[string]$s.ProxyServer; if ($p -match 'https?=([^;]+)') { $p=$matches[1] }; if ($p -notmatch '://') { $p='http://'+$p }; $p }"`) do set "HTTP_PROXY=%%p"
if not defined HTTP_PROXY goto :proxy_done
set "HTTPS_PROXY=%HTTP_PROXY%"
echo [HarnessSmith] Using system proxy: %HTTP_PROXY%
echo.
:proxy_done

REM Web form (browser) vs interactive CLI wizard (this terminal). Web is the
REM default on Windows (a browser is normally present). Set HARNESSMITH_MODE to
REM web or cli to skip the prompt (e.g. for automation). Flat goto flow only.
set "MODE=web"
if defined HARNESSMITH_MODE goto :mode_env
echo [HarnessSmith] How do you want to set up your harness?
echo     [1] Web wizard - fill a form in your browser
echo     [2] CLI wizard - interactive setup in this terminal
set /p "MODE=  Choose [1/2] (Enter = web): "
if "%MODE%"=="2" set "MODE=cli"
if not "%MODE%"=="cli" set "MODE=web"
goto :mode_done
:mode_env
set "MODE=%HARNESSMITH_MODE%"
:mode_done
echo.

echo [HarnessSmith] Step 1/4: looking for uv on PATH ...
where uv >nul 2>nul
if not errorlevel 1 goto :run

echo [HarnessSmith] Step 2/4: checking known uv install locations ...
if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
where uv >nul 2>nul
if not errorlevel 1 goto :run

REM Look for the installed console script by its .exe name on purpose: a bare
REM `harnessmith` would resolve to THIS file (HarnessSmith.bat) first, since
REM Windows searches the current dir and is case-insensitive -> infinite relaunch.
echo [HarnessSmith] Step 3/4: looking for an installed harnessmith command ...
where harnessmith.exe >nul 2>nul
if not errorlevel 1 goto :run_cmd

echo [HarnessSmith] Step 4/4: uv is not installed yet.
echo.
echo   The wizard needs uv - a small tool that manages Python and dependencies for
echo   you (user-level install, no admin required). How would you like to install it?
echo     [1] Standard - official installer (downloads uv from GitHub)
echo     [2] China mirror - pip + Tsinghua mirror (needs Python already installed)
echo     [n] Don't install
set "CHOICE=1"
set /p "CHOICE=  Choose [1/2/n]: "
if /i "%CHOICE%"=="n" goto :manual
if "%CHOICE%"=="2" goto :install_cn

REM Use the official installer directly (NOT winget): winget first updates its
REM own source CDN, which hangs for a long time and fails on some networks (e.g.
REM behind the GFW) even when the GitHub download itself works fine.
echo [HarnessSmith] Installing uv via the official installer ...
powershell -ExecutionPolicy Bypass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if not errorlevel 1 goto :run
goto :manual

:install_cn
echo [HarnessSmith] China mirror: installing uv from the Tsinghua PyPI mirror ...
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [HarnessSmith] No Python found - the China-mirror path needs Python first.
    goto :manual_cn
)
%PY% -m pip install --user uv -i https://pypi.tuna.tsinghua.edu.cn/simple
%PY% -m uv --version >nul 2>nul
if errorlevel 1 (
    echo [HarnessSmith] pip did not produce a runnable uv.
    goto :manual_cn
)
echo [HarnessSmith] uv installed. Using the Tsinghua mirror + your system Python.
set "UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
set "UV_PYTHON_PREFERENCE=only-system"
goto :run_py

:manual
echo.
echo [HarnessSmith] Could not find or install uv. Install it manually (user-level, no admin):
echo     winget install astral-sh.uv
echo     - or -  powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
echo   then double-click this again.
echo.
pause
goto :eof

:manual_cn
echo.
echo [HarnessSmith] The China-mirror path needs Python. Options:
echo     1) Install Python (https://www.python.org/downloads/ , reachable in China),
echo        then run this again and choose [2].
echo     2) Or with Python present:  pip install uv -i https://pypi.tuna.tsinghua.edu.cn/simple
echo     3) Or use a VPN/proxy and choose [1].
echo.
pause
goto :eof

:run
REM Auto-pick the package index: when no index is pinned and the official PyPI is
REM unreachable (e.g. behind the GFW), use the Tsinghua mirror for this run so the
REM first `uv sync` can still fetch deps. An explicit UV_DEFAULT_INDEX always wins;
REM we only probe when curl is present (ships with Windows 10 1803+).
if defined UV_DEFAULT_INDEX goto :run_go
where curl >nul 2>nul
if errorlevel 1 goto :run_go
echo [HarnessSmith] Checking whether PyPI is reachable ...
curl -sS -m 3 -I https://pypi.org/simple/ >nul 2>nul
if not errorlevel 1 goto :run_go
echo [HarnessSmith] PyPI looks unreachable - using the Tsinghua mirror this run.
set "UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
:run_go
if "%MODE%"=="cli" goto :run_go_cli
echo [HarnessSmith] Launching: uv run --extra wizard harnessmith wizard --open
echo.
uv run --extra wizard harnessmith wizard --open
goto :after_run
:run_go_cli
echo [HarnessSmith] Launching: uv run harnessmith new
echo.
uv run harnessmith new
goto :after_run

:run_cmd
if "%MODE%"=="cli" goto :run_cmd_cli
echo [HarnessSmith] Launching: harnessmith.exe wizard --open
echo.
harnessmith.exe wizard --open
goto :after_run
:run_cmd_cli
echo [HarnessSmith] Launching: harnessmith.exe new
echo.
harnessmith.exe new
goto :after_run

:run_py
if "%MODE%"=="cli" goto :run_py_cli
echo [HarnessSmith] Launching: %PY% -m uv run --extra wizard harnessmith wizard --open
echo.
%PY% -m uv run --extra wizard harnessmith wizard --open
goto :after_run
:run_py_cli
echo [HarnessSmith] Launching: %PY% -m uv run harnessmith new
echo.
%PY% -m uv run harnessmith new
goto :after_run

:after_run
echo.
echo [HarnessSmith] Process exited (code %errorlevel%). Press a key to close.
pause >nul
goto :eof
