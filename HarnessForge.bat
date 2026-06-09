@echo off
REM One-click launcher for the HarnessForge wizard (opens the spec wizard in your browser).
REM Prefers uv (auto-syncs the optional [wizard] extra); falls back to a harnessforge command.
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if not errorlevel 1 (
    uv run --extra wizard harnessforge wizard --open
    goto :done
)
where harnessforge >nul 2>nul
if not errorlevel 1 (
    harnessforge wizard --open
    goto :done
)
echo Could not find "uv" or "harnessforge" on your PATH.
echo Install uv ^(https://docs.astral.sh/uv/^) and run this from the repo, or
echo pip install "harnessforge[wizard]" then run "harnessforge wizard --open".
pause
exit /b 1

:done
