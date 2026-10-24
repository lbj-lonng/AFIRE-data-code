@echo off
set AFIRE_COUNTY_PROJECT_ROOT=%~dp0
python "%~dp0scripts\run_v6_pipeline.py"
if errorlevel 1 pause
