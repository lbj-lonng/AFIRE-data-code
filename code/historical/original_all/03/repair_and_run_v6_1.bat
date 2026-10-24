@echo off
setlocal
set AFIRE_COUNTY_PROJECT_ROOT=%~dp0

echo ============================================================
echo Afire v6.1 real-data repair and complete model run
echo ============================================================

echo [0/8] Running local self-test...
python "%~dp0scripts\self_test_v6_1.py"
if errorlevel 1 goto :failed

echo [1/8] Checking/downloading Census ACS and county land area...
python "%~dp0scripts\download_real_covariates.py" --source census
if errorlevel 1 goto :failed

echo [2/8] Downloading correct NOAA temperature and precipitation...
python "%~dp0scripts\download_real_covariates.py" --source noaa --force
if errorlevel 1 goto :failed

echo [3/8] Downloading CDC/EPA PM2.5 for AZ CA CO ID OR WA...
python "%~dp0scripts\download_real_covariates.py" --source pm25 --force
if errorlevel 1 goto :failed

echo [4/8] Downloading CDC/EPA ozone for the six states...
python "%~dp0scripts\download_real_covariates.py" --source ozone --force
if errorlevel 1 echo Warning: ozone download failed; ozone is optional and the core model can continue.

echo [5/8] Downloading genuine CDC PLACES smoking estimates for 2018-2020...
python "%~dp0scripts\download_real_covariates.py" --source places --force
if errorlevel 1 echo Warning: PLACES smoking failed; smoking is an optional sensitivity analysis.

echo [6/8] Diagnosing external data coverage...
python "%~dp0scripts\diagnose_external_covariates.py"

echo [7/8] Building the real county-year covariate panel...
python "%~dp0scripts\build_real_covariate_panel.py"
if errorlevel 1 goto :failed

echo [8/8] Running all available multiple-imputation COPD models...
python "%~dp0scripts\run_full_realdata_models_v6.py"
if errorlevel 1 goto :failed

echo.
echo Completed.
echo Main diagnostics: tables\external_data_diagnostics_v6_1.csv
echo Model status:     tables\full_model_run_status_v6_1.csv
echo Model results:    tables\copd_full_realdata_models_v6_1.csv
pause
exit /b 0

:failed
echo.
echo The repair/run failed. Read the last error and inspect the logs folder.
pause
exit /b 1
