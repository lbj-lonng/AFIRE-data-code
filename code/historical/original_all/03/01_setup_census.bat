@echo off
setlocal
set "AFIRE_COUNTY_PROJECT_ROOT=%~dp0"
cd /d "%~dp0"

echo ============================================================
echo Afire v6.2 - Step 1: Configure and download Census ACS
echo ============================================================

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python was not found in PATH.
  echo Install Python 3.9+ or activate the project environment first.
  pause
  exit /b 1
)

python -c "import pandas, requests" >nul 2>nul
if errorlevel 1 (
  echo Installing the minimal Census dependencies...
  python -m pip install -r requirements_census.txt
  if errorlevel 1 goto :failed
)

if defined CENSUS_API_KEY goto :download
if exist "%~dp0config\census_api_key.env" goto :download

echo.
echo No local Census key was found.
echo The next prompt hides your input and validates the key online.
python "%~dp0scripts\configure_census_key.py"
if errorlevel 1 goto :failed

:download
echo.
echo Downloading or validating ACS 5-year files for 2009-2020...
python "%~dp0scripts\census_first_download.py"
if errorlevel 1 goto :failed

echo.
echo Census stage completed successfully.
echo Standardized data:
echo   data_external\processed\census_county_year_six_states_2009_2020.csv
echo Validation table:
echo   tables\census_validation_v6_2.csv
echo Status:
echo   logs\census_status_v6_2.json
echo.
echo Next command: 03_run_remaining_pipeline.bat
pause
exit /b 0

:failed
echo.
echo Census setup/download failed.
echo Review the error above. Common causes are an unactivated key,
echo blocked access to api.census.gov, or an interrupted download.
pause
exit /b 1
