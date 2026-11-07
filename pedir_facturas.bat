@echo off
setlocal
chcp 65001 >nul
title LegalSky - Pedir facturas
rem ======================================================================
rem  LegalSky - Pedir facturas de billetes (Iberia y Air Europa)
rem  Antes: Google Chrome abierto con la extension Claude in Chrome.
rem  La primera vez se instala con instalar.bat.
rem ======================================================================
cd /d "%~dp0"
if not exist "scripts\cola_pdf.py" cd /d "%USERPROFILE%\Documents\bot legal sky" 2>nul
if not exist "scripts\cola_pdf.py" (echo. & echo  Primero haz doble clic en instalar.bat. & goto :fin)

echo.
echo  ==========  LegalSky - Pedir facturas  ==========
echo.
call entorno.bat || goto :fin

echo.
echo  Leyendo el Gmail de compras y pidiendo las facturas pendientes...
echo  (Claude trabaja en pestanas nuevas de Chrome; no las cierres mientras tanto)
echo.
rem Permisos justos: los scripts del programa, leer los PDF, escribir en trabajo\ y Chrome.
rem Claude lee los PDF con la cuenta de Claude de Fede: no hace falta clave de API.
call "%CLAUDE%" -p "Usa la skill pedir-facturas y siguela completa. Al final escribe el resumen en espanol." --chrome ^
  --allowedTools "Skill(pedir-facturas)" "Read" "Edit(./trabajo/**)" "Bash(python scripts/cola_pdf.py:*)" "Bash(python scripts\cola_pdf.py:*)" "Bash(python scripts/cola_pc.py:*)" "Bash(python scripts\cola_pc.py:*)" "mcp__claude-in-chrome"
echo.
echo ------------------------------------------------------------
%PY% scripts\cola_pc.py resumen
echo ------------------------------------------------------------

:fin
echo.
if not defined LEGALSKY_SIN_PAUSA pause
