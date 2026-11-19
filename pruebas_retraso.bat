@echo off
setlocal
chcp 65001 >nul
title LegalSky - Pruebas de retraso
rem ======================================================================
rem  LegalSky - Sube al CRM la prueba del retraso de cada vuelo (FlightStats)
rem  Antes: Google Chrome abierto con la extension Claude in Chrome y con la
rem  sesion iniciada en crmlegalsky.com y en flightstats.com.
rem  La primera vez se instala con instalar.bat.
rem ======================================================================
cd /d "%~dp0"
if not exist "scripts\pruebas_retraso.py" cd /d "%USERPROFILE%\Documents\bot legal sky" 2>nul
if not exist "scripts\pruebas_retraso.py" (echo. & echo  Primero haz doble clic en instalar.bat. & goto :fin)

echo.
echo  ==========  LegalSky - Pruebas de retraso  ==========
echo.
call "%~dp0entorno.bat" || goto :fin

echo.
echo  Buscando en FlightStats los vuelos del CRM sin prueba y subiendo los PDF...
echo  (Claude trabaja en pestanas nuevas de Chrome; no las cierres mientras tanto)
echo.
rem Argumentos opcionales: dias hacia atras (p. ej. 7), max=N (como mucho N vuelos), prueba.
call "%CLAUDE%" -p "Usa la skill pruebas-retraso con estos argumentos: %* . Siguela completa. Al final escribe el resumen en espanol." --chrome ^
  --allowedTools "Skill(pruebas-retraso)" "Read" "Bash(python scripts/pruebas_retraso.py *)" "Bash(python scripts\pruebas_retraso.py *)" ^
  "PowerShell(python scripts/pruebas_retraso.py *)" "PowerShell(python scripts\pruebas_retraso.py *)" "mcp__claude-in-chrome"
echo.
echo ------------------------------------------------------------
%PY% scripts\pruebas_retraso.py resumen
echo ------------------------------------------------------------

:fin
echo.
if not defined LEGALSKY_SIN_PAUSA pause
