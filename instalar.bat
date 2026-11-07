@echo off
setlocal
chcp 65001 >nul
title LegalSky - Instalar bots
rem ======================================================================
rem  LegalSky - Instalador de los bots (facturas y vuelos)
rem  Doble clic una vez. Instala Python y Claude Code si faltan, baja el
rem  programa a Documentos\bot legal sky, inicia sesion en Claude y crea
rem  los accesos directos del Escritorio. Se puede repetir sin problema.
rem  Necesita junto a este archivo: .env y token.json
rem ======================================================================

set "ORIGEN=https://github.com/vidriomoderno/legalsky-bots/archive/refs/heads/main.zip"
if defined LEGALSKY_ORIGEN set "ORIGEN=%LEGALSKY_ORIGEN%"
set "EXTENSION_CHROME=https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn"
if not defined LEGALSKY_DESTINO set "LEGALSKY_DESTINO=%USERPROFILE%\Documents\bot legal sky"
set "DESTINO=%LEGALSKY_DESTINO%"
set "AQUI=%~dp0"

echo.
echo  ==========  LegalSky - Instalar bots  ==========
echo.

rem ---------------------------------------------------------------- 1. Python
call :buscar_python
if defined PY goto :python_ok
echo [1/6] Instalando Python (tarda unos minutos)...
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
call :buscar_python
if not defined PY (echo. & echo  No se pudo instalar Python. Llama a Juan Fernando. & goto :fin_error)
:python_ok
echo [1/6] Python listo.

rem ----------------------------------------------------------- 2. Claude Code
call :buscar_claude
if defined CLAUDE goto :claude_ok
echo [2/6] Instalando Claude Code...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex"
call :buscar_claude
if not defined CLAUDE (echo. & echo  No se pudo instalar Claude Code. Llama a Juan Fernando. & goto :fin_error)
:claude_ok
for %%D in ("%CLAUDE%") do set "CLAUDE_DIR=%%~dpD"
set "PATH=%CLAUDE_DIR%;%PATH%"
rem Deja la carpeta de Claude en el PATH del usuario para siempre.
if not defined LEGALSKY_PRUEBA powershell -NoProfile -Command ^
  "$d = $env:CLAUDE_DIR.TrimEnd('\'); $p = [Environment]::GetEnvironmentVariable('Path','User');" ^
  "if (-not $p) { $p = '' }; if (($p -split ';') -notcontains $d) { [Environment]::SetEnvironmentVariable('Path', ($p.TrimEnd(';') + ';' + $d).TrimStart(';'), 'User') }"
echo [2/6] Claude Code listo.

rem ------------------------------------------------------- 3. Programa
echo [3/6] Descargando la ultima version del programa...
call :descargar
if errorlevel 1 (
  if exist "%DESTINO%\legalsky_bots\main.py" (
    echo     No se pudo actualizar; se usa la version que ya estaba instalada.
  ) else (
    echo. & echo  No se pudo descargar el programa. Revisa internet o llama a Juan Fernando.
    goto :fin_error
  )
)
echo instalado> "%DESTINO%\.instalado_por_bat"
rem De donde se actualiza despues (lo lee entorno.bat).
>"%DESTINO%\.origen" echo %ORIGEN%
if /i not "%AQUI%"=="%DESTINO%\" copy /y "%~f0" "%DESTINO%\instalar.bat" >nul
cd /d "%DESTINO%"
%PY% -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (echo. & echo  No se pudieron instalar los componentes. Revisa internet o llama a Juan Fernando. & goto :fin_error)
copy /y requirements.txt .requirements_instalados >nul
echo [3/6] Programa listo en "%DESTINO%".

rem ------------------------------------------------- 4. Archivos secretos
for %%F in (.env token.json) do (
  if exist "%AQUI%%%F" if /i not "%AQUI%"=="%DESTINO%\" copy /y "%AQUI%%%F" "%DESTINO%\%%F" >nul
)
if not exist "%DESTINO%\.env" goto :faltan_secretos
if not exist "%DESTINO%\token.json" goto :faltan_secretos
echo [4/6] Configuracion lista.

rem ------------------------------------------------- 5. Accesos directos
if not defined LEGALSKY_PRUEBA powershell -NoProfile -Command ^
  "$e = [Environment]::GetFolderPath('Desktop'); $w = New-Object -ComObject WScript.Shell;" ^
  "foreach ($a in @(@('Pedir facturas LegalSky','pedir_facturas.bat'), @('Buscar vuelos LegalSky','buscar_vuelos.bat'))) {" ^
  " $s = $w.CreateShortcut((Join-Path $e ($a[0] + '.lnk'))); $s.TargetPath = (Join-Path $env:DESTINO $a[1]);" ^
  " $s.WorkingDirectory = $env:DESTINO; $s.Save() }" >nul 2>nul
echo [5/6] Accesos directos creados en el Escritorio.

rem ------------------------------------------------- 6. Cuenta de Claude
call "%CLAUDE%" auth status >nul 2>nul
if not errorlevel 1 goto :sesion_ok
echo.
echo  Ahora se abre el navegador para entrar con tu cuenta de Claude (Pro o Max).
echo  1. Entra con la cuenta y pulsa Autorizar.
echo  2. Si la pagina te muestra un CODIGO, pulsa "Copiar", vuelve a esta ventana,
echo     haz clic derecho para pegarlo y pulsa Enter.
call "%CLAUDE%" auth login
call "%CLAUDE%" auth status >nul 2>nul
if errorlevel 1 (echo. & echo  No se pudo iniciar sesion en Claude. Vuelve a intentarlo o llama a Juan Fernando. & goto :fin_error)
:sesion_ok
echo [6/6] Sesion de Claude iniciada.

if not defined LEGALSKY_PRUEBA (
  echo.
  echo  ULTIMO PASO: en Chrome se abre la extension "Claude in Chrome".
  echo  Pulsa "Anadir a Chrome" y entra con tu MISMA cuenta de Claude.
  call :abrir_en_chrome "%EXTENSION_CHROME%"
)
echo.
echo  ============================================================
echo   LISTO. Ya puedes usar los iconos del Escritorio:
echo     - Pedir facturas LegalSky
echo     - Buscar vuelos LegalSky
echo   Antes de usarlos, abre siempre Google Chrome.
echo  ============================================================
goto :fin_ok

:faltan_secretos
echo.
echo  Faltan los archivos secretos ".env" y "token.json".
echo  Pideselos a Juan Fernando, guardalos junto a este archivo y vuelve a hacer doble clic.
if not defined LEGALSKY_PRUEBA start "" explorer "%AQUI%"
goto :fin_error

rem ------------------------------------------------------------------ utilidades
:descargar
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$tmp = Join-Path $env:TEMP ('legalsky_' + [guid]::NewGuid()); New-Item -ItemType Directory $tmp | Out-Null;" ^
  "$zip = Join-Path $tmp 'codigo.zip';" ^
  "if ($env:ORIGEN -match '^https?://') { Invoke-WebRequest -UseBasicParsing $env:ORIGEN -OutFile $zip } else { Copy-Item $env:ORIGEN $zip };" ^
  "Expand-Archive $zip (Join-Path $tmp 'x');" ^
  "$raiz = Get-ChildItem (Join-Path $tmp 'x') -Recurse -Filter 'requirements.txt' | Select-Object -First 1;" ^
  "if (-not $raiz) { throw 'El ZIP no contiene el programa' };" ^
  "New-Item -ItemType Directory -Force $env:DESTINO | Out-Null;" ^
  "Copy-Item (Join-Path $raiz.DirectoryName '*') $env:DESTINO -Recurse -Force -Exclude '.env','token.json','instalar.bat';" ^
  "Remove-Item $tmp -Recurse -Force"
exit /b %errorlevel%

:buscar_python
set "PY="
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python" && exit /b
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul || exit /b
for /f "delims=" %%D in ('py -3 -c "import sys, os; print(os.path.dirname(sys.executable))"') do set "PATH=%%D;%%D\Scripts;%PATH%"
set "PY=python"
exit /b

:abrir_en_chrome
rem La extension es de Chrome: abre la pagina en Chrome aunque el navegador predeterminado sea Edge.
for %%C in ("%ProgramFiles%\Google\Chrome\Application\chrome.exe" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe") do (
  if exist "%%~C" (start "" "%%~C" "%~1" & exit /b)
)
start "" "%~1"
exit /b

:buscar_claude
rem Claude Code puede estar en varios sitios segun como se instalo.
set "CLAUDE="
for /f "delims=" %%C in ('where claude.exe claude.cmd 2^>nul') do if not defined CLAUDE set "CLAUDE=%%C"
for %%C in ("%USERPROFILE%\.local\bin\claude.exe" "%APPDATA%\npm\claude.cmd" "%LOCALAPPDATA%\Microsoft\WinGet\Links\claude.exe") do (
  if not defined CLAUDE if exist "%%~C" set "CLAUDE=%%~C"
)
exit /b

:fin_ok
echo.
if not defined LEGALSKY_SIN_PAUSA pause
exit /b 0

:fin_error
echo.
if not defined LEGALSKY_SIN_PAUSA pause
exit /b 1
