@echo off
rem Lee ahora el Gmail de compras: anota billetes y facturas nuevos en la hoja de control.
rem Para PEDIR las facturas en Iberia y Air Europa, abre Claude en esta carpeta y escribe /pedir-facturas
cd /d "%~dp0"
python -m legalsky_bots.main
echo.
python scripts\cola_pc.py resumen
echo.
pause
