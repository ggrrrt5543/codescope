@echo off
cd /d "%~dp0"
if not exist .venv python -m venv .venv
if errorlevel 1 exit /b 1
.venv\Scripts\python -m pip install -r requirements-lock.txt
if errorlevel 1 exit /b 1
.venv\Scripts\python -m pip install --no-deps .
if errorlevel 1 exit /b 1
.venv\Scripts\codescope serve
