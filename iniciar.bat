@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  echo BoviFlow: abra http://localhost:8000 no navegador.
  py -3 app.py
) else (
  echo BoviFlow: abra http://localhost:8000 no navegador.
  python app.py
)
pause
