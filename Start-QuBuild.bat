@echo off
title QuBuild
cd /d "%~dp0"
echo Starting QuBuild...
echo.
python -m streamlit run app.py
if errorlevel 1 (
  echo.
  echo QuBuild could not start. Install what it needs with:
  echo     pip install -r requirements.txt
  pause
)
