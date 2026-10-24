@echo off
setlocal
set "AFIRE_COUNTY_PROJECT_ROOT=%~dp0"
cd /d "%~dp0"

echo ============================================================
echo Afire v6.2 - Step 3: Continue after Census validation
echo ============================================================

python -c "import json, pathlib, sys; p=pathlib.Path(r'%~dp0logs/census_status_v6_2.json'); sys.exit(0 if p.exists() and json.loads(p.read_text(encoding='utf-8')).get('status')=='ready' else 1)"
if errorlevel 1 (
  echo ERROR: Census has not passed validation.
  echo Run 01_setup_census.bat first.
  pause
  exit /b 1
)

echo [1/7] NOAA temperature and precipitation...
python scripts\download_real_covariates.py --source noaa
if errorlevel 1 goto :failed

echo [2/7] CDC/EPA total PM2.5...
python scripts\download_real_covariates.py --source pm25
if errorlevel 1 goto :failed

echo [3/7] CDC/EPA ozone ^(optional^)...
python scripts\download_real_covariates.py --source ozone
if errorlevel 1 echo Warning: ozone failed; core models may still continue.

echo [4/7] CDC PLACES smoking ^(optional sensitivity^)...
python scripts\download_real_covariates.py --source places
if errorlevel 1 echo Warning: PLACES failed; core models may still continue.

echo [5/7] External-data diagnostics...
python scripts\diagnose_external_covariates.py

echo [6/7] Build county-year covariate panel...
python scripts\build_real_covariate_panel.py
if errorlevel 1 goto :failed

echo [7/7] Run all available multiple-imputation COPD models...
python scripts\run_full_realdata_models_v6.py
if errorlevel 1 goto :failed

echo.
echo Pipeline completed.
echo Census validation: tables\census_validation_v6_2.csv
echo Model status:      tables\full_model_run_status_v6_1.csv
echo Model results:     tables\copd_full_realdata_models_v6_1.csv
pause
exit /b 0

:failed
echo.
echo The remaining pipeline failed. Census files are preserved and do not need to be downloaded again.
pause
exit /b 1
