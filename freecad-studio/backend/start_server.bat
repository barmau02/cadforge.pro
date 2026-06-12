@echo off
cd /d "%~dp0"
"C:\Program Files\FreeCAD 1.1\bin\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8787