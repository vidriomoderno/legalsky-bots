# LegalSky — bots de billetes y facturas

> **Regla general: LegalSky es una empresa en España.** Facturas a nombre de la sociedad
> con su CIF y domicilio fiscal en España, IVA español y euros.

Este repositorio tiene, por ahora, los bots 1 y 3 del diseño:

- **Lector de billetes:** lee cada PDF que llega al Gmail de compras, lo guarda en Drive
  (`Billetes/AAAA/MM`) y lo anota en la hoja de control como *Factura pendiente*.
- **Recolector de facturas:** cuando llega la factura, la guarda en `Facturas/AAAA/MM`,
  comprueba que vaya al CIF de la empresa y la empareja con su billete por número de
  billete o localizador. El billete pasa a *Facturado*.

Si un billete lleva más de 7 días sin factura, pasa a *Factura pendiente (atrasada)*. Los
correos ya procesados quedan con la etiqueta `LegalSky/Procesado`. Los que necesitan
que alguien los mire quedan con `LegalSky/Revisar`.

Claude (`claude-opus-5-5`) solo lee los PDF y devuelve los datos. Todas las reglas
(duplicados, CIF, emparejado, estados) son código normal y tienen tests.

## Estructura

| Archivo | Qué hace |
| --- | --- |
| `legalsky_bots/procesador.py` | La lógica de los dos bots |
| `legalsky_bots/extractor.py` | La llamada a Claude con el PDF |
| `legalsky_bots/modelos.py` | Los campos que se extraen |
| `legalsky_bots/google_servicios.py` | Gmail, Drive y Sheets |
| `legalsky_bots/main.py` | Una pasada completa con la API de Claude (opcional, necesita `ANTHROPIC_API_KEY`) |
| `scripts/cola_pdf.py` | Lectura de PDF sin clave: baja los PDF a `trabajo/` y registra lo que Claude leyó |
| `scripts/preparar.py` | Autorización inicial y creación de carpeta y hoja |
| `tests/` | Tests con servicios simulados; no gastan API |

## Puesta en marcha (una sola vez)

Todo con las cuentas de Federico. Tú entras como colaborador.

1. **Google Cloud:** crea un proyecto (p. ej. `legalsky-bots`) con facturación y activa
   las APIs de Gmail, Drive, Sheets, Cloud Run, Cloud Scheduler y Secret Manager.
2. **Pantalla de consentimiento OAuth:** tipo *Externo*, añade el Gmail de compras como
   usuario y **ponla en "En producción"**. Si se queda en "Prueba", el token caduca cada
   7 días y el bot deja de funcionar. Google mostrará un aviso de "app no verificada" al
   autorizar; es normal para uso interno.
3. **Credenciales OAuth** de tipo *Aplicación de escritorio*: descarga el `client_secret.json`.
4. En un PC con Python 3.12+:

   ```bash
   pip install -r requirements.txt
   python scripts/preparar.py client_secret.json
   ```

   Inicia sesión **con el Gmail de compras**. El script crea la carpeta
   "LegalSky - Billetes y facturas", la hoja de control y `token.json`, y te muestra los IDs.
5. **Secret Manager:** crea los secretos `google-token` (contenido de `token.json`) y
   `anthropic-api-key` (clave de Anthropic Console de LegalSky). Después borra `token.json`
   del PC.

## Desplegar en Google Cloud

Región `europe-west1` (UE, por protección de datos).

```bash
gcloud run jobs deploy legalsky-lector --source . --region europe-west1 \
  --set-secrets GOOGLE_TOKEN_JSON=google-token:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest \
  --set-env-vars EMPRESA_RAZON_SOCIAL="...",EMPRESA_CIF="...",DRIVE_CARPETA_RAIZ_ID="...",HOJA_CONTROL_ID="..." \
  --max-retries 0 --task-timeout 15m
```

Programarlo cada 15 minutos:

```bash
gcloud scheduler jobs create http legalsky-lector-15min --location europe-west1 \
  --schedule "*/15 * * * *" --time-zone "Europe/Madrid" --http-method POST \
  --uri "https://run.googleapis.com/v2/projects/PROYECTO/locations/europe-west1/jobs/legalsky-lector:run" \
  --oauth-service-account-email CUENTA_DE_SERVICIO@PROYECTO.iam.gserviceaccount.com
```

La cuenta de servicio necesita el rol *Cloud Run Invoker*.

## Desarrollo

```bash
pip install -r requirements.txt pytest
pytest
```

Para probar contra el Gmail real desde un PC, copia `.env.example` a `.env`, rellénalo,
carga las variables y ejecuta `python -m legalsky_bots.main` (requiere `ANTHROPIC_API_KEY`). Ojo: etiqueta los correos
y escribe en la hoja de verdad.

## Bot 2: pedir la factura en la web (apagado)

`legalsky_bots/solicitud_facturas.py` tiene las recetas de los formularios, revisadas a
mano en octubre de 2026:

- **Iberia** (`iberia.com/es/facturas/`): nombre, primer apellido y número de billete
  (el campo ya trae "075-"), y luego los datos fiscales. Al terminar sale "Tu factura está
  en camino". Si el billete ya tiene factura, solo ofrece "Solicitar un duplicado"; el bot no
  lo pide y lo marca para revisar.
- **Air Europa** (`aireuropa.com/es/es/mytrips/invoice`): país España, localizador y fecha
  de salida en un calendario, y luego `…/invoice/LOCALIZADOR/FECHA/passengers`. Solo deja
  pedirla 24-48 h después de emitir el billete (el bot espera 2 días). La pantalla de
  pasajeros aún no se ha visto con una reserva sin facturar.

**Las dos webs devuelven 403 a los navegadores automáticos desde un servidor** (protección
antibots). No se intenta saltar esa protección. Por eso `SOLICITAR_FACTURAS` está apagado
por defecto en la nube.

### Cómo lo ejecuta Fede: doble clic en `pedir_facturas.bat`

Con **Google Chrome abierto**, doble clic en `pedir_facturas.bat`. Claude (Claude Code, con la
cuenta de Claude de Fede) hace la skill `pedir-facturas`:

1. **Lee el Gmail sin clave de API:** `scripts/cola_pdf.py bajar` baja los PDF de 15 en 15 a
   `trabajo/`, Claude los lee y escribe `trabajo/extraccion.json`, y
   `scripts/cola_pdf.py registrar` los guarda en Drive, la hoja y las etiquetas de Gmail.
2. **Pide las facturas** en pestañas nuevas de Chrome siguiendo `tarea_pc/INSTRUCCIONES.md`.
3. Muestra un resumen.

Solo tiene permiso para los scripts del proyecto, leer los PDF, escribir en `trabajo/` y
Chrome. La primera vez hay unos 190 correos de los últimos 6 meses, así que tarda bastante
más que las siguientes.

**Instalación en el PC de Fede: la hace el propio `.bat`.** Se le mandan tres archivos
(`pedir_facturas.bat`, `.env` y `token.json`), los guarda juntos y hace doble clic. La primera
vez el `.bat`:

1. Instala Python 3.12 con `winget` si no hay un Python 3.10+.
2. Instala Claude Code con el instalador oficial (`irm https://claude.ai/install.ps1 | iex`).
3. Descarga el código desde `ORIGEN` (el ZIP del repositorio de GitHub) a
   `Documentos\bot legal sky`, instala `requirements.txt` y crea el acceso directo
   "Pedir facturas LegalSky" en el Escritorio.
4. Copia `.env` y `token.json` a esa carpeta.
5. Si Claude no tiene sesión, abre `claude auth login`; y abre la página de la extensión
   Claude in Chrome para instalarla.

Las siguientes veces vuelve a descargar el código (así se actualiza solo) sin tocar `.env` ni
`token.json`. Si no hay internet, usa la versión ya instalada. En la carpeta de desarrollo
(sin el archivo `.instalado_por_bat`) nunca descarga nada.

**Antes de repartirlo:** cambiar `ORIGEN` en el `.bat` por la URL del ZIP del repositorio
(`https://github.com/USUARIO/REPO/archive/refs/heads/main.zip`). El repositorio tiene que ser
público para que la descarga funcione sin contraseña; el código no lleva secretos (están en
`.env` y `token.json`, que no se suben).

Para probar el instalador sin tocar nada: `LEGALSKY_ORIGEN` (ruta a un ZIP local),
`LEGALSKY_DESTINO` (carpeta de prueba), `LEGALSKY_SOLO_INSTALAR=1` (no pide facturas ni crea
el acceso directo) y `LEGALSKY_SIN_PAUSA=1`.

La primera vez, en la extensión de Chrome conviene permitir siempre iberia.com y
aireuropa.com. Para probar sin enviar nada: `claude` en la carpeta y `/pedir-facturas prueba`.

Si una aerolínea muestra un CAPTCHA o bloquea, Claude no lo intenta saltar: deja ese billete
como *revisar* y sigue con los demás.

### Alternativa: tarea programada en el PC

Una tarea programada de Claude Desktop en el PC de Federico usa su Chrome real (Claude in
Chrome), que las webs sí aceptan:

1. `python scripts/cola_pc.py pendientes` saca de la hoja los billetes listos para pedir
   (Air Europa solo a partir de 48 h tras la emisión).
2. Claude sigue `tarea_pc/INSTRUCCIONES.md` en cada web.
3. `python scripts/cola_pc.py anotar FILA RESULTADO "DETALLE"` deja el resultado en la hoja.
   Tras 5 intentos fallidos el billete pasa a *Revisar: pedir la factura a mano*.
4. Cuando la factura llega al Gmail, el recolector (en la nube) marca el billete *Facturado*.

**Instalación en el PC:** Claude Desktop con la cuenta de Federico, la extensión Claude in
Chrome conectada, este repositorio clonado, Python 3.12+ con `pip install -r requirements.txt`,
y un `.env` con `GOOGLE_TOKEN_JSON`, `HOJA_CONTROL_ID` y los datos fiscales. En Claude Desktop
se crea una tarea programada **semanal** (día y hora por definir, zona Europe/Madrid) cuyo
mensaje es "Sigue tarea_pc/INSTRUCCIONES.md en la carpeta del proyecto". El PC tiene que estar
encendido y con Chrome abierto a esa hora; si no lo está, se hace en la siguiente pasada.
Con una pasada por semana, el aviso de factura atrasada conviene subirlo a 14 días
(`DIAS_ALERTA_SIN_FACTURA=14`).

## Pendiente

- Verificar la pantalla de pasajeros de Air Europa con una reserva sin facturar.
- Consultar a Iberia y Air Europa si emiten facturas automáticas a empresas registradas.
- Bot 4: envío periódico al gestor (frecuencia por definir).
