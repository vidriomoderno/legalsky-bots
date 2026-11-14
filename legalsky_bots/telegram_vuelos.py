"""Bot de Telegram para buscar vuelos baratos desde el móvil (se publica en Render).

Variables de entorno:
    TELEGRAM_TOKEN          el que da @BotFather
    SERPAPI_KEY             clave de serpapi.com
    USUARIOS_PERMITIDOS     números de usuario de Telegram separados por comas (los asesores)
    WEBHOOK_SECRETO         texto secreto cualquiera (Telegram lo manda en cada aviso)
    RENDER_EXTERNAL_URL     lo pone Render solo; dirección pública del servicio

Arranque local:  uvicorn legalsky_bots.telegram_vuelos:app --port 8000
"""

import hashlib
import html
import logging
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl

import httpx
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Route

from legalsky_bots import vuelos_serpapi as serp
from legalsky_bots.vuelos import (
    AEROPUERTOS, OPCIONES, TERMINALES, Busqueda, ahora_en_espana, dominio, en_horario_ideal, url_google_flights,
)

log = logging.getLogger("legalsky.telegram")
CADUCA = 3 * 3600  # las búsquedas guardadas en memoria duran 3 horas

_busquedas: dict[str, tuple[float, Busqueda, list[serp.Opcion]]] = {}
_redirecciones: dict[str, tuple[float, dict]] = {}


def _env(nombre: str) -> str:
    return os.environ.get(nombre, "").strip()


def secreto_telegram() -> str:
    """Telegram solo acepta letras, números, _ y - en el secreto: se usa un resumen del de Render."""
    secreto = _env("WEBHOOK_SECRETO")
    return hashlib.sha256(secreto.encode()).hexdigest() if secreto else ""


def usuarios_de_render() -> set[int]:
    return {int(x) for x in _env("USUARIOS_PERMITIDOS").replace(" ", "").split(",") if x.isdigit()}


def usuarios_permitidos() -> set[int]:
    """Los de Render (fijos) más los aceptados con el botón de Telegram."""
    return usuarios_de_render() | set(_aprobados)


# ------------------------------------------------------------ Lista de acceso
# Los aceptados con el botón se guardan en un mensaje fijado del chat del administrador con el bot:
# así no se pierden cuando Render reinicia el servicio (el plan gratis no tiene disco).
CABECERA_LISTA = "📋 Usuarios con acceso al bot (no borres ni desfijes este mensaje):"
_aprobados: dict[int, str] = {}
_lista = {"cargada": False, "chat": None, "mensaje": None}


def leer_lista(texto: str) -> dict[int, str]:
    usuarios = {}
    for linea in texto.splitlines():
        m = re.match(r"^• (.*) — id (\d+)$", linea.strip())
        if m:
            usuarios[int(m.group(2))] = m.group(1)
    return usuarios


def texto_lista() -> str:
    filas = [f"• {nombre} — id {uid}" for uid, nombre in sorted(_aprobados.items(), key=lambda x: x[1].lower())]
    return CABECERA_LISTA + "\n" + ("\n".join(filas) if filas else "(nadie todavía)")


async def cargar_lista():
    if _lista["cargada"]:
        return
    for admin in administradores():
        r = await telegram("getChat", chat_id=admin)
        fijado = (r.get("result") or {}).get("pinned_message") or {}
        if fijado.get("text", "").startswith(CABECERA_LISTA):
            _aprobados.update(leer_lista(fijado["text"]))
            _lista.update(chat=admin, mensaje=fijado["message_id"])
            break
    _lista["cargada"] = True


async def guardar_lista():
    if _lista["mensaje"]:
        r = await telegram("editMessageText", chat_id=_lista["chat"], message_id=_lista["mensaje"], text=texto_lista())
        if r.get("ok") or "not modified" in str(r.get("description", "")):
            return
    admins = administradores()
    if not admins:
        return
    r = await telegram("sendMessage", chat_id=admins[0], text=texto_lista(), disable_notification=True)
    mensaje = (r.get("result") or {}).get("message_id")
    if mensaje:
        _lista.update(chat=admins[0], mensaje=mensaje)
        await telegram("pinChatMessage", chat_id=admins[0], message_id=mensaje, disable_notification=True)


def _nombre(persona: dict) -> str:
    nombre = " ".join(x for x in (persona.get("first_name"), persona.get("last_name")) if x) or "Sin nombre"
    return nombre + (f" (@{persona['username']})" if persona.get("username") else "")


def _limpiar():
    limite = time.time() - CADUCA
    for d in (_busquedas, _redirecciones):
        for k in [k for k, v in d.items() if v[0] < limite]:
            d.pop(k, None)


def _guardar(diccionario: dict, *valor) -> str:
    _limpiar()
    clave = secrets.token_urlsafe(6)
    diccionario[clave] = (time.time(), *valor)
    return clave


# ------------------------------------------------------------------ Telegram
async def telegram(metodo: str, **datos) -> dict:
    async with httpx.AsyncClient() as c:
        r = await c.post(f"https://api.telegram.org/bot{_env('TELEGRAM_TOKEN')}/{metodo}", json=datos, timeout=30)
    respuesta = r.json()
    if not respuesta.get("ok"):
        log.warning("Telegram %s: %s", metodo, respuesta.get("description"))
    return respuesta


def botones(filas: list[list[tuple[str, str]]]) -> dict:
    """Botones: (texto, "dato") pulsa un paso; (texto, "https://...") abre una web."""
    return {"inline_keyboard": [
        [{"text": t, "url": d} if d.startswith("https://") else {"text": t, "callback_data": d} for t, d in fila]
        for fila in filas
    ]}


def teclado_aeropuertos() -> dict:
    return botones([[(nombre, f"a|{codigo}")] for codigo, nombre in AEROPUERTOS.items()])


def teclado_terminales(aeropuerto: str) -> dict:
    fila = [(t, f"t|{aeropuerto}|{t}") for t in TERMINALES[aeropuerto]]
    return botones([fila, [("Todas las terminales", f"t|{aeropuerto}|TODAS")]])


def teclado_tipo(aeropuerto: str, terminal: str) -> dict:
    return botones([[("Nacional", f"x|{aeropuerto}|{terminal}|nacional"),
                     ("Internacional", f"x|{aeropuerto}|{terminal}|internacional")]])


def texto_resultado(b: Busqueda, opciones: list[serp.Opcion]) -> str:
    terminal = "todas las terminales" if b.terminal == "TODAS" else f"terminal {b.terminal}"
    cabecera = (f"✈️ <b>{html.escape(AEROPUERTOS[b.aeropuerto])}</b> · {terminal} · {b.tipo}\n"
                f"Salidas entre las {b.desde:%H:%M} y las {b.hasta:%H:%M} ({b.hasta:%d/%m})\n")
    if not opciones:
        return cabecera + "\nNo hay vuelos que cumplan las reglas ahora mismo."
    lineas = []
    for n, o in enumerate(opciones, 1):
        v = o.vuelo
        escalas = "directo" if v.escalas == 0 else f"{v.escalas} escala(s)"
        ideal = " ⭐" if en_horario_ideal(v, b) else ""
        lineas.append(f"<b>{n}. {v.precio:.0f} €</b> · {v.salida:%H:%M} → {html.escape(v.destino)} · "
                      f"{html.escape(v.aerolinea)} · {escalas}{ideal}")
    pie = ("\n\n⭐ = sale dentro de 8 a 12 horas.\nPulsa un vuelo para abrirlo en la web de la aerolínea. "
           "Confirma la terminal en la tarjeta de embarque.")
    if len(opciones) < OPCIONES:
        pie = f"\n\nSolo hay {len(opciones)} vuelo(s) que cumplen las reglas." + pie
    return cabecera + "\n" + "\n".join(lineas) + pie


async def buscar_y_responder(chat: int, mensaje: int, aeropuerto: str, terminal: str, tipo: str):
    b = Busqueda(aeropuerto, terminal, tipo, ahora_en_espana())
    try:
        opciones = await run_in_threadpool(serp.buscar, b, _env("SERPAPI_KEY"))
    except Exception as e:  # noqa: BLE001 - al asesor se le explica y se registra
        log.exception("Error buscando vuelos")
        await telegram("editMessageText", chat_id=chat, message_id=mensaje,
                       text=f"No se pudo buscar ahora mismo ({html.escape(str(e))[:200]}). Prueba otra vez en un minuto.")
        return
    clave = _guardar(_busquedas, b, opciones)
    filas = [[(f"🔗 {n}. {o.vuelo.aerolinea} · {o.vuelo.precio:.0f} €", f"e|{clave}|{n}")]
             for n, o in enumerate(opciones, 1)]
    filas.append([("🔄 Nueva búsqueda", "inicio")])
    await telegram("editMessageText", chat_id=chat, message_id=mensaje, text=texto_resultado(b, opciones),
                   parse_mode="HTML", reply_markup=botones(filas))


async def enviar_enlace(chat: int, clave: str, n: int):
    guardada = _busquedas.get(clave)
    if not guardada or not 1 <= n <= len(guardada[2]):
        await telegram("sendMessage", chat_id=chat, text="Esta búsqueda ha caducado. Haz una nueva con /vuelos.")
        return
    _, b, opciones = guardada
    o = opciones[n - 1]
    v = o.vuelo
    google = url_google_flights(b.aeropuerto, v.destino, v.salida.date().isoformat())
    titulo = f"<b>{n}. {html.escape(v.aerolinea)}</b> · {b.aeropuerto} → {html.escape(v.destino)} · {v.salida:%d/%m %H:%M} · {v.precio:.0f} €"
    try:
        enlace, peticion = await run_in_threadpool(serp.enlace_aerolinea, b, o, _env("SERPAPI_KEY"))
    except Exception:  # noqa: BLE001
        log.exception("Error pidiendo el enlace")
        enlace, peticion = "", None
    if enlace:
        texto, boton = f"{titulo}\n\nWeb de la aerolínea:", (f"Abrir en {dominio(enlace)}", enlace)
    elif peticion and _env("RENDER_EXTERNAL_URL").startswith("https://"):
        ir = _guardar(_redirecciones, peticion)
        texto = f"{titulo}\n\nEl botón te lleva a la web de {html.escape(v.aerolinea)}:"
        boton = (f"Abrir en la web de {v.aerolinea}", f"{_env('RENDER_EXTERNAL_URL').rstrip('/')}/ir/{ir}")
    else:
        texto = (f"{titulo}\n\n{html.escape(v.aerolinea)} no vende este vuelo directamente a través de Google. "
                 "Ábrelo en Google Flights o búscalo en su web.")
        boton = ("Ver en Google Flights", google)
    await telegram("sendMessage", chat_id=chat, text=texto, parse_mode="HTML", reply_markup=botones([[boton]]),
                   disable_web_page_preview=True)


_solicitudes_avisadas: set[int] = set()


def administradores() -> list[int]:
    """Quién recibe los avisos de acceso: ADMINISTRADORES o, si no, el primero de USUARIOS_PERMITIDOS."""
    propios = [int(x) for x in _env("ADMINISTRADORES").replace(" ", "").split(",") if x.isdigit()]
    if propios:
        return propios
    primero = _env("USUARIOS_PERMITIDOS").replace(" ", "").split(",")[0]
    return [int(primero)] if primero.isdigit() else []


async def avisar_solicitud(persona: dict):
    """Avisa al administrador (una vez por persona) de que alguien quiere usar el bot."""
    if persona["id"] in _solicitudes_avisadas:
        return
    _solicitudes_avisadas.add(persona["id"])
    for admin in administradores():
        await telegram("sendMessage", chat_id=admin,
                       text=f"🔔 Solicitud de acceso al bot de vuelos:\n{_nombre(persona)}\nNúmero de usuario: {persona['id']}",
                       reply_markup=botones([[("✅ Dar acceso", f"ok|{persona['id']}"),
                                              ("❌ Rechazar", f"no|{persona['id']}")]]))


async def responder_solicitud(q: dict, aceptar: bool, uid: int):
    """El administrador pulsa Dar acceso o Rechazar en el aviso."""
    chat, mensaje = q["message"]["chat"]["id"], q["message"]["message_id"]
    lineas = (q["message"].get("text") or "").splitlines()
    nombre = lineas[1] if len(lineas) > 1 else f"Usuario {uid}"
    if aceptar:
        _aprobados[uid] = nombre
        await guardar_lista()
        await telegram("answerCallbackQuery", callback_query_id=q["id"], text="Acceso dado")
        await telegram("editMessageText", chat_id=chat, message_id=mensaje, text=f"✅ Acceso dado a {nombre}.")
        await telegram("sendMessage", chat_id=uid, text="✅ Ya tienes acceso. ¿Desde qué aeropuerto buscamos vuelos?",
                       reply_markup=teclado_aeropuertos())
    else:
        await telegram("answerCallbackQuery", callback_query_id=q["id"], text="Rechazado")
        await telegram("editMessageText", chat_id=chat, message_id=mensaje, text=f"❌ Rechazada la solicitud de {nombre}.")


async def mostrar_usuarios(chat: int):
    """/usuarios (solo administrador): lista con botón para quitar a cada uno."""
    fijos = sorted(usuarios_de_render())
    texto = (f"👥 Usuarios con acceso:\n" + "\n".join(f"• {n}" for n in _aprobados.values())
             + (f"\n• {len(fijos)} fijo(s) en Render (ids: {', '.join(map(str, fijos))})" if fijos else ""))
    filas = [[(f"Quitar a {n[:40]}", f"qt|{uid}")] for uid, n in _aprobados.items()]
    extra = {"reply_markup": botones(filas)} if filas else {}
    await telegram("sendMessage", chat_id=chat, text=texto, **extra)


async def atender(aviso: dict):
    """Un aviso de Telegram: un mensaje escrito o un botón pulsado."""
    await cargar_lista()
    if "callback_query" in aviso:
        q = aviso["callback_query"]
        usuario, dato = q["from"]["id"], q.get("data", "")
        chat, mensaje = q["message"]["chat"]["id"], q["message"]["message_id"]
        if usuario not in usuarios_permitidos():
            await telegram("answerCallbackQuery", callback_query_id=q["id"], text="No tienes acceso.")
            return
        partes = dato.split("|")
        es_admin = usuario in administradores()
        if partes[0] in ("ok", "no", "qt") and len(partes) == 2 and partes[1].isdigit():
            if not es_admin:
                await telegram("answerCallbackQuery", callback_query_id=q["id"], text="Solo el administrador.")
            elif partes[0] == "qt":
                nombre = _aprobados.pop(int(partes[1]), None)
                await guardar_lista()
                await telegram("answerCallbackQuery", callback_query_id=q["id"], text="Quitado")
                await telegram("editMessageText", chat_id=chat, message_id=mensaje,
                               text=f"🚫 Quitado el acceso a {nombre or partes[1]}.")
            else:
                await responder_solicitud(q, partes[0] == "ok", int(partes[1]))
        elif partes[0] == "inicio":
            await telegram("answerCallbackQuery", callback_query_id=q["id"])
            await telegram("sendMessage", chat_id=chat, text="¿Desde qué aeropuerto?", reply_markup=teclado_aeropuertos())
        elif partes[0] == "a" and len(partes) == 2 and partes[1] in AEROPUERTOS:
            await telegram("answerCallbackQuery", callback_query_id=q["id"])
            await telegram("editMessageText", chat_id=chat, message_id=mensaje,
                           text=f"{AEROPUERTOS[partes[1]]}. ¿Qué terminal?", reply_markup=teclado_terminales(partes[1]))
        elif partes[0] == "t" and len(partes) == 3:
            await telegram("answerCallbackQuery", callback_query_id=q["id"])
            await telegram("editMessageText", chat_id=chat, message_id=mensaje,
                           text=f"{AEROPUERTOS.get(partes[1], partes[1])} · {partes[2]}. ¿Nacional o internacional?",
                           reply_markup=teclado_tipo(partes[1], partes[2]))
        elif partes[0] == "x" and len(partes) == 4:
            await telegram("answerCallbackQuery", callback_query_id=q["id"], text="Buscando…")
            await telegram("editMessageText", chat_id=chat, message_id=mensaje,
                           text="🔎 Buscando los vuelos más baratos… (unos segundos)")
            await buscar_y_responder(chat, mensaje, partes[1], partes[2], partes[3])
        elif partes[0] == "e" and len(partes) == 3 and partes[2].isdigit():
            await telegram("answerCallbackQuery", callback_query_id=q["id"], text="Buscando el enlace de la aerolínea…")
            await enviar_enlace(chat, partes[1], int(partes[2]))
        else:
            await telegram("answerCallbackQuery", callback_query_id=q["id"])
        return

    m = aviso.get("message") or {}
    if not m.get("from") or "chat" not in m or m["from"].get("is_bot") or "text" not in m:
        return  # avisos de sistema (p. ej. "mensaje fijado") o de otros bots
    chat, usuario = m["chat"]["id"], m["from"]["id"]
    if usuario not in usuarios_permitidos():
        await telegram("sendMessage", chat_id=chat,
                       text=f"Este bot es solo para el equipo de LegalSky. Ya hemos avisado para que te den acceso; "
                            f"te escribiremos cuando esté listo.\n(Tu número de usuario: {usuario})")
        await avisar_solicitud(m["from"])
        return
    texto = (m.get("text") or "").strip()
    if texto.startswith("/usuarios") and usuario in administradores():
        await mostrar_usuarios(chat)
        return
    dar = re.match(r"^/dar\s+(\d+)\s*(.*)$", texto)
    if dar and usuario in administradores():
        uid = int(dar.group(1))
        _aprobados[uid] = dar.group(2).strip() or f"Usuario {uid}"
        await guardar_lista()
        await telegram("sendMessage", chat_id=chat, text=f"✅ Acceso dado a {_aprobados[uid]}.")
        await telegram("sendMessage", chat_id=uid, text="✅ Ya tienes acceso. ¿Desde qué aeropuerto buscamos vuelos?",
                       reply_markup=teclado_aeropuertos())
        return
    await telegram("sendMessage", chat_id=chat, text="Hola 👋 ¿Desde qué aeropuerto buscamos vuelos?",
                   reply_markup=teclado_aeropuertos())


# ------------------------------------------------------------------ Web
async def webhook(request: Request):
    secreto = secreto_telegram()
    if not secreto or not secrets.compare_digest(request.headers.get("x-telegram-bot-api-secret-token", ""), secreto):
        return PlainTextResponse("no", status_code=403)
    aviso = await request.json()
    # Se contesta a Telegram enseguida y la búsqueda sigue en segundo plano.
    return JSONResponse({"ok": True}, background=BackgroundTask(_atender_seguro, aviso))


async def _atender_seguro(aviso: dict):
    try:
        await atender(aviso)
    except Exception:  # noqa: BLE001
        log.exception("Error atendiendo el aviso de Telegram")


async def ir(request: Request):
    """Abre en el móvil la redirección de Google hacia la web de la aerolínea (es un formulario POST)."""
    guardada = _redirecciones.get(request.path_params["clave"])
    if not guardada:
        return HTMLResponse("<p>Este enlace ha caducado. Haz una nueva búsqueda en Telegram.</p>", status_code=404)
    peticion = guardada[1]
    campos = "".join(
        f'<input type="hidden" name="{html.escape(k, quote=True)}" value="{html.escape(v, quote=True)}">'
        for k, v in _campos(peticion.get("post_data") or "")
    )
    return HTMLResponse(
        f'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        f'<title>Abriendo la aerolínea…</title><p>Abriendo la web de la aerolínea…</p>'
        f'<form id="f" method="post" action="{html.escape(peticion["url"], quote=True)}">{campos}'
        f'<button>Continuar</button></form><script>document.getElementById("f").submit()</script>'
    )


def _campos(post_data: str) -> list[tuple[str, str]]:
    return parse_qsl(post_data, keep_blank_values=True)


async def salud(request: Request):
    return PlainTextResponse("LegalSky vuelos: funcionando")


@asynccontextmanager
async def _ciclo(app):
    logging.basicConfig(level=logging.INFO, force=True)
    base = _env("RENDER_EXTERNAL_URL")
    faltan = [n for n in ("RENDER_EXTERNAL_URL", "TELEGRAM_TOKEN", "WEBHOOK_SECRETO", "SERPAPI_KEY", "USUARIOS_PERMITIDOS")
              if not _env(n)]
    print(f"[arranque] direccion publica: {base or '(ninguna)'}; variables vacias: {faltan or 'ninguna'}", flush=True)
    if base.startswith("https://") and _env("TELEGRAM_TOKEN") and _env("WEBHOOK_SECRETO"):
        r = await telegram("setWebhook", url=f"{base.rstrip('/')}/telegram", secret_token=secreto_telegram(),
                           allowed_updates=["message", "callback_query"])
        print(f"[arranque] setWebhook: ok={r.get('ok')} {r.get('description', '')}", flush=True)
        await telegram("setMyCommands", commands=[{"command": "vuelos", "description": "Buscar vuelos baratos"}])
    yield


app = Starlette(
    routes=[Route("/", salud), Route("/telegram", webhook, methods=["POST"]), Route("/ir/{clave}", ir)],
    lifespan=_ciclo,
)
