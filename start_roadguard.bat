@echo off
title RoadGuard AI Server
echo.
echo Starting RoadGuard AI...
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python environment. This only happens the first time...
  python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
echo.
echo RoadGuard AI is running at http://127.0.0.1:5000
echo Keep this window open while using the website.
echo.
python server.py
