@echo off
setlocal
chcp 65001 >nul
title LegalSky - Buscar vuelos baratos
cd /d "%~dp0"
rem Si se abre desde otra carpeta (por ejemplo la del ZIP), se usa el programa ya instalado.
if not exist "scripts\buscar_vuelos.py" cd /d "%USERPROFILE%\Documents\bot legal sky" 2>nul
if not exist "scripts\buscar_vuelos.py" (echo Primero haz doble clic en pedir_facturas.bat para instalar el programa. & pause & exit /b 1)
set "PATH=%USERPROFILE%\.local\bin;%LOCALAPPDATA%\Programs\Python\Python312;%PATH%"

where claude >nul 2>nul || (echo No se encuentra Claude Code. Ejecuta primero pedir_facturas.bat. & pause & exit /b 1)
where python >nul 2>nul || (echo No se encuentra Python. Ejecuta primero pedir_facturas.bat. & pause & exit /b 1)

echo.
echo  ==========  LegalSky - Buscar vuelos baratos  ==========
echo  Antes de seguir: Google Chrome abierto con la extension Claude in Chrome.
echo.
echo  Aeropuerto:
echo    1. Madrid-Barajas
echo    2. Barcelona-El Prat
choice /c 12 /n /m "  Elige 1 o 2: "
if errorlevel 2 goto :barcelona

set "AEROPUERTO=MAD"
echo.
echo  Terminal de Madrid:
echo    1. T1
echo    2. T2
echo    3. T4 (incluye T4S)
echo    4. Todas
choice /c 1234 /n /m "  Elige 1, 2, 3 o 4: "
if errorlevel 4 (set "TERMINAL=TODAS") else if errorlevel 3 (set "TERMINAL=T4") else if errorlevel 2 (set "TERMINAL=T2") else (set "TERMINAL=T1")
goto :tipo

:barcelona
set "AEROPUERTO=BCN"
echo.
echo  Terminal de Barcelona:
echo    1. T1
echo    2. T2
echo    3. Todas
choice /c 123 /n /m "  Elige 1, 2 o 3: "
if errorlevel 3 (set "TERMINAL=TODAS") else if errorlevel 2 (set "TERMINAL=T2") else (set "TERMINAL=T1")

:tipo
echo.
echo  Tipo de vuelo:
echo    1. Nacional
echo    2. Internacional
choice /c 12 /n /m "  Elige 1 o 2: "
if errorlevel 2 (set "TIPO=internacional") else (set "TIPO=nacional")

echo.
echo  Buscando vuelos: %AEROPUERTO%, terminal %TERMINAL%, %TIPO%.
echo  Claude trabaja en una pestana nueva de Chrome: no la cierres. Tarda unos minutos.
echo.
if exist trabajo\ultimo.txt del trabajo\ultimo.txt
rem Permisos justos: el script de vuelos, leer y escribir en trabajo\ y Chrome. No compra nada.
claude -p "Usa la skill buscar-vuelos con aeropuerto %AEROPUERTO%, terminal %TERMINAL% y tipo %TIPO%. Siguela completa y escribe el resumen en espanol." --chrome ^
  --allowedTools "Skill(buscar-vuelos)" "Read" "Write(./trabajo/**)" "Bash(python scripts/buscar_vuelos.py:*)" "Bash(python scripts\buscar_vuelos.py:*)" "mcp__claude-in-chrome"

echo.
if exist trabajo\ultimo.txt (
  set /p RESULTADO=<trabajo\ultimo.txt
  call start "" "%%RESULTADO%%"
) else (
  echo  No se generaron resultados. Revisa que Chrome este abierto y vuelve a intentarlo.
)
echo.
pause
