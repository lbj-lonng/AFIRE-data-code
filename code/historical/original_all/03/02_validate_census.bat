@echo off
setlocal
set "AFIRE_COUNTY_PROJECT_ROOT=%~dp0"
cd /d "%~dp0"

echo ============================================================
echo Afire v6.2 - Step 2: Validate local Census data only
echo ============================================================
python "%~dp0scripts\validate_census_only.py"
if errorlevel 1 goto :failed

echo.
echo Census validation passed. No new download was required.
pause
exit /b 0

:failed
echo.
echo Census validation failed. Run 01_setup_census.bat again.
pause
exit /b 1
