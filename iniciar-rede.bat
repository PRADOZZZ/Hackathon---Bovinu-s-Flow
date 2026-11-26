@echo off
cd /d "%~dp0"
echo Use somente uma rede privada de demonstracao.
set /p BOVIFLOW_TOKEN=Defina um codigo de acesso temporario: 
if not defined BOVIFLOW_TOKEN exit /b 1
ipconfig
echo Abra http://localhost:8000 no PC e http://IP-DO-PC:8000/staff no celular.
where py >nul 2>nul
if %errorlevel%==0 (py -3 app.py --host 0.0.0.0) else (python app.py --host 0.0.0.0)
pause
