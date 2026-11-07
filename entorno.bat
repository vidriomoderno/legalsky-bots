@echo off
rem ======================================================================
rem  Preparacion comun de los bots (la llaman pedir_facturas.bat y
rem  buscar_vuelos.bat). Deja en PY y CLAUDE como ejecutar Python y Claude,
rem  actualiza el programa y pide iniciar sesion en Claude si hace falta.
rem  Devuelve error (1) si algo no esta listo.
rem ======================================================================

call :buscar_python
if not defined PY (echo  No se encuentra Python. Haz doble clic en instalar.bat. & exit /b 1)
call :buscar_claude
if not defined CLAUDE (echo  No se encuentra Claude Code. Haz doble clic en instalar.bat. & exit /b 1)
for %%D in ("%CLAUDE%") do set "PATH=%%~dpD;%PATH%"

if not exist "%~dp0.env" goto :faltan_secretos
if not exist "%~dp0token.json" goto :faltan_secretos

rem Actualiza el programa (no toca los .bat ni los secretos). Si no hay internet, sigue igual.
if exist "%~dp0.instalado_por_bat" if not defined LEGALSKY_SIN_ACTUALIZAR call :actualizar

call "%CLAUDE%" auth status >nul 2>nul
if not errorlevel 1 exit /b 0
echo.
echo  Ahora se abre el navegador para entrar con tu cuenta de Claude (Pro o Max).
echo  1. Entra con la cuenta y pulsa Autorizar.
echo  2. Si la pagina te muestra un CODIGO, pulsa "Copiar", vuelve a esta ventana,
echo     haz clic derecho para pegarlo y pulsa Enter.
call "%CLAUDE%" auth login
call "%CLAUDE%" auth status >nul 2>nul
if errorlevel 1 (echo  No se pudo iniciar sesion en Claude. Llama a Juan Fernando. & exit /b 1)
exit /b 0

:faltan_secretos
echo  Faltan los archivos .env o token.json. Haz doble clic en instalar.bat junto a esos archivos.
exit /b 1

:actualizar
set "ORIGEN=https://github.com/vidriomoderno/legalsky-bots/archive/refs/heads/main.zip"
if exist "%~dp0.origen" set /p ORIGEN=<"%~dp0.origen"
if defined LEGALSKY_ORIGEN set "ORIGEN=%LEGALSKY_ORIGEN%"
set "DESTINO=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $tmp = Join-Path $env:TEMP ('legalsky_' + [guid]::NewGuid()); New-Item -ItemType Directory $tmp | Out-Null;" ^
  "$zip = Join-Path $tmp 'codigo.zip';" ^
  "if ($env:ORIGEN -match '^https?://') { Invoke-WebRequest -UseBasicParsing $env:ORIGEN -OutFile $zip } else { Copy-Item $env:ORIGEN $zip };" ^
  "Expand-Archive $zip (Join-Path $tmp 'x');" ^
  "$raiz = Get-ChildItem (Join-Path $tmp 'x') -Recurse -Filter 'requirements.txt' | Select-Object -First 1;" ^
  "if ($raiz) { Copy-Item (Join-Path $raiz.DirectoryName '*') $env:DESTINO -Recurse -Force -Exclude '*.bat','.env','token.json' };" ^
  "Remove-Item $tmp -Recurse -Force } catch { Write-Host '  (Sin actualizar: se usa la version instalada.)' }"
%PY% -m pip install --quiet --disable-pip-version-check -r "%~dp0requirements.txt" >nul 2>nul
exit /b 0

:buscar_python
set "PY="
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python" && exit /b
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul || exit /b
for /f "delims=" %%D in ('py -3 -c "import sys, os; print(os.path.dirname(sys.executable))"') do set "PATH=%%D;%%D\Scripts;%PATH%"
set "PY=python"
exit /b

:buscar_claude
set "CLAUDE="
for /f "delims=" %%C in ('where claude.exe claude.cmd 2^>nul') do if not defined CLAUDE set "CLAUDE=%%C"
for %%C in ("%USERPROFILE%\.local\bin\claude.exe" "%APPDATA%\npm\claude.cmd" "%LOCALAPPDATA%\Microsoft\WinGet\Links\claude.exe") do (
  if not defined CLAUDE if exist "%%~C" set "CLAUDE=%%~C"
)
exit /b
