@echo off
setlocal
cd /d "%~dp0"
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv || goto :fail
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || goto :fail
set /p EMAIL=SEC User-Agent contact email: 
if "%EMAIL%"=="" goto :fail
python download_all.py --mode discover --email "%EMAIL%" --output "%~dp0DOWNLOADED_DATA"
pause
exit /b 0
:fail
pause
exit /b 1
