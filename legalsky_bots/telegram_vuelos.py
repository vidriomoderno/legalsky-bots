"""Bot de Telegram para buscar vuelos baratos desde el móvil (se publica en Render).

Variables de entorno:
    TELEGRAM_TOKEN          el que da @BotFather
    SERPAPI_KEY             clave de serpapi.com
    USUARIOS_PERMITIDOS     números de usuario de Telegram separados por comas (los asesores)
    WEBHOOK_SECRETO         texto secreto cualquiera (Telegram lo manda en cada aviso)
    RENDER_EXTERNAL_URL     lo pone Render solo; dirección pública del servicio

Arranque local:  uvicorn legalsky_bots.telegram_vuelos:app --port 8000
"""

import html
import logging
import os
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


def usuarios_permitidos() -> set[int]:
    return {int(x) for x in _env("USUARIOS_PERMITIDOS").replace(" ", "").split(",") if x.isdigit()}


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


async def atender(aviso: dict):
    """Un aviso de Telegram: un mensaje escrito o un botón pulsado."""
    if "callback_query" in aviso:
        q = aviso["callback_query"]
        usuario, dato = q["from"]["id"], q.get("data", "")
        chat, mensaje = q["message"]["chat"]["id"], q["message"]["message_id"]
        if usuario not in usuarios_permitidos():
            await telegram("answerCallbackQuery", callback_query_id=q["id"], text="No tienes acceso.")
            return
        partes = dato.split("|")
        if partes[0] == "inicio":
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
    if not m.get("from") or "chat" not in m:
        return
    chat, usuario = m["chat"]["id"], m["from"]["id"]
    if usuario not in usuarios_permitidos():
        await telegram("sendMessage", chat_id=chat,
                       text=f"Este bot es solo para el equipo de LegalSky.\nTu número de usuario es {usuario}: "
                            "pásaselo a Fede para que te dé acceso.")
        return
    await telegram("sendMessage", chat_id=chat, text="Hola 👋 ¿Desde qué aeropuerto buscamos vuelos?",
                   reply_markup=teclado_aeropuertos())


# ------------------------------------------------------------------ Web
async def webhook(request: Request):
    secreto = _env("WEBHOOK_SECRETO")
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
        r = await telegram("setWebhook", url=f"{base.rstrip('/')}/telegram", secret_token=_env("WEBHOOK_SECRETO"),
                           allowed_updates=["message", "callback_query"])
        print(f"[arranque] setWebhook: ok={r.get('ok')} {r.get('description', '')}", flush=True)
        await telegram("setMyCommands", commands=[{"command": "vuelos", "description": "Buscar vuelos baratos"}])
    yield


app = Starlette(
    routes=[Route("/", salud), Route("/telegram", webhook, methods=["POST"]), Route("/ir/{clave}", ir)],
    lifespan=_ciclo,
)
