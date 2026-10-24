@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
  set PYTHON=python
) else (
  where py >nul 2>nul
  if %errorlevel%==0 (
    set PYTHON=py -3
  ) else (
    echo Python was not found. Please install Python 3.10 or newer first.
    exit /b 1
  )
)

%PYTHON% scripts\run_all.py
