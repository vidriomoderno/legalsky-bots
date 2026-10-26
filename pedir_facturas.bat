@echo off
setlocal
chcp 65001 >nul
title LegalSky - Pedir facturas
rem ======================================================================
rem  LegalSky - Pedir facturas de billetes (Iberia y Air Europa)
rem
rem  La PRIMERA vez instala todo solo: Python, Claude Code, el programa
rem  (en Documentos\bot legal sky) y un acceso directo en el Escritorio.
rem  Las siguientes veces actualiza el programa y pide las facturas.
rem
rem  Antes de ejecutar: Google Chrome abierto con la extension
rem  Claude in Chrome conectada.
rem ======================================================================

rem ---- Configuracion (la cambia Juan Fernando) ----
rem ZIP con el codigo del programa (repositorio de GitHub de LegalSky).
set "ORIGEN=https://github.com/vidriomoderno/legalsky-bots/archive/refs/heads/main.zip"
if defined LEGALSKY_ORIGEN set "ORIGEN=%LEGALSKY_ORIGEN%"
set "EXTENSION_CHROME=https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn"
if not defined LEGALSKY_DESTINO set "LEGALSKY_DESTINO=%USERPROFILE%\Documents\bot legal sky"

set "AQUI=%~dp0"
set "DESTINO=%LEGALSKY_DESTINO%"
rem Si este archivo ya esta dentro de la carpeta del programa, se usa esa carpeta.
if exist "%AQUI%legalsky_bots\main.py" set "DESTINO=%AQUI:~0,-1%"

echo.
echo  ==========  LegalSky - Pedir facturas  ==========
echo.

rem ---------------------------------------------------------------- 1. Python
call :buscar_python
if defined PY goto :python_ok
echo [1/5] Instalando Python (solo la primera vez, tarda unos minutos)...
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
call :buscar_python
if not defined PY (
  echo.
  echo  No se pudo instalar Python. Llama a Juan Fernando.
  goto :fin_error
)
:python_ok
echo [1/5] Python listo.

rem ----------------------------------------------------------- 2. Claude Code
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where claude >nul 2>nul && goto :claude_ok
echo [2/5] Instalando Claude Code (solo la primera vez)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex"
where claude >nul 2>nul || (
  echo.
  echo  No se pudo instalar Claude Code. Llama a Juan Fernando.
  goto :fin_error
)
:claude_ok
echo [2/5] Claude Code listo.

rem ----------------------------------------------- 3. Programa (descarga/actualiza)
if not exist "%DESTINO%\legalsky_bots\main.py" goto :descargar
if exist "%DESTINO%\.instalado_por_bat" goto :descargar
echo [3/5] Programa listo (carpeta de desarrollo, no se actualiza).
goto :programa_ok
:descargar
echo [3/5] Descargando la ultima version del programa...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$tmp = Join-Path $env:TEMP ('legalsky_' + [guid]::NewGuid());" ^
  "New-Item -ItemType Directory $tmp | Out-Null;" ^
  "$zip = Join-Path $tmp 'codigo.zip';" ^
  "if ($env:ORIGEN -match '^https?://') { Invoke-WebRequest -UseBasicParsing $env:ORIGEN -OutFile $zip } else { Copy-Item $env:ORIGEN $zip };" ^
  "Expand-Archive $zip (Join-Path $tmp 'x');" ^
  "$raiz = Get-ChildItem (Join-Path $tmp 'x') -Recurse -Filter 'requirements.txt' | Select-Object -First 1;" ^
  "if (-not $raiz) { throw 'El ZIP no contiene el programa' };" ^
  "New-Item -ItemType Directory -Force $env:DESTINO | Out-Null;" ^
  "Copy-Item (Join-Path $raiz.DirectoryName '*') $env:DESTINO -Recurse -Force -Exclude '.env','token.json';" ^
  "Remove-Item $tmp -Recurse -Force"
if errorlevel 1 (
  if exist "%DESTINO%\legalsky_bots\main.py" (
    echo     No se pudo actualizar; se usa la version que ya estaba instalada.
  ) else (
    echo.
    echo  No se pudo descargar el programa. Revisa internet o llama a Juan Fernando.
    goto :fin_error
  )
)
echo instalado > "%DESTINO%\.instalado_por_bat"
if /i not "%AQUI%"=="%DESTINO%\" copy /y "%~f0" "%DESTINO%\pedir_facturas.bat" >nul
if not defined LEGALSKY_SOLO_INSTALAR powershell -NoProfile -Command ^
  "$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Pedir facturas LegalSky.lnk';" ^
  "if (-not (Test-Path $lnk)) { $s=(New-Object -ComObject WScript.Shell).CreateShortcut($lnk);" ^
  "$s.TargetPath=(Join-Path $env:DESTINO 'pedir_facturas.bat'); $s.WorkingDirectory=$env:DESTINO; $s.Save() }" >nul 2>nul
:programa_ok

cd /d "%DESTINO%"
echo [3/5] Instalando componentes del programa...
%PY% -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo  No se pudieron instalar los componentes. Revisa internet o llama a Juan Fernando.
  goto :fin_error
)

rem ------------------------------------------------- 4. Archivos secretos
for %%F in (.env token.json) do (
  if not exist "%DESTINO%\%%F" if exist "%AQUI%%%F" copy /y "%AQUI%%%F" "%DESTINO%\%%F" >nul
)
if not exist "%DESTINO%\.env" goto :faltan_secretos
if not exist "%DESTINO%\token.json" goto :faltan_secretos
echo [4/5] Configuracion lista.

if defined LEGALSKY_SOLO_INSTALAR (
  echo.
  echo  Instalacion comprobada. No se piden facturas ^(LEGALSKY_SOLO_INSTALAR^).
  goto :fin_ok
)

rem ------------------------------------------------- 5. Cuenta de Claude y facturas
claude auth status >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Ahora se abre el navegador para entrar con tu cuenta de Claude.
  echo  Entra, vuelve a esta ventana y espera.
  claude auth login
  claude auth status >nul 2>nul || (
    echo  No se pudo iniciar sesion en Claude. Llama a Juan Fernando.
    goto :fin_error
  )
)

if not exist "%DESTINO%\.extension_avisada" (
  echo.
  echo  PRIMERA VEZ: instala la extension "Claude in Chrome" en Chrome,
  echo  entra con tu cuenta de Claude y vuelve aqui.
  start "" "%EXTENSION_CHROME%"
  echo extension > "%DESTINO%\.extension_avisada"
  pause
)

echo.
echo [5/5] Pidiendo las facturas. Claude trabaja en pestanas nuevas de Chrome:
echo       no las cierres ni las toques hasta que termine.
echo.
rem Permisos justos: los scripts del programa, leer los PDF, escribir en trabajo\ y Chrome.
rem Claude lee los PDF con la cuenta de Claude de Fede: no hace falta clave de API.
claude -p "Usa la skill pedir-facturas y siguela completa. Al final escribe el resumen en espanol." --chrome ^
  --allowedTools "Skill(pedir-facturas)" "Read" "Write(./trabajo/**)" "Bash(python scripts/cola_pdf.py:*)" "Bash(python scripts\cola_pdf.py:*)" "Bash(python scripts/cola_pc.py:*)" "Bash(python scripts\cola_pc.py:*)" "mcp__claude-in-chrome"
echo.
echo ------------------------------------------------------------
%PY% scripts\cola_pc.py resumen
echo ------------------------------------------------------------
goto :fin_ok

:faltan_secretos
echo.
echo  Faltan los archivos secretos ".env" y "token.json".
echo  Pideselos a Juan Fernando, guardalos junto a este archivo
echo  y vuelve a hacer doble clic.
start "" explorer "%AQUI%"
goto :fin_error

rem ------------------------------------------------------------------ utilidades
:buscar_python
set "PY="
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python" && exit /b
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul || exit /b
rem Solo existe "py": se pone su Python en el PATH para que "python" funcione tambien dentro de Claude.
for /f "delims=" %%D in ('py -3 -c "import sys, os; print(os.path.dirname(sys.executable))"') do set "PATH=%%D;%%D\Scripts;%PATH%"
set "PY=python"
exit /b

:fin_ok
echo.
echo  Listo. Puedes cerrar esta ventana.
if not defined LEGALSKY_SIN_PAUSA pause
exit /b 0

:fin_error
echo.
if not defined LEGALSKY_SIN_PAUSA pause
exit /b 1
