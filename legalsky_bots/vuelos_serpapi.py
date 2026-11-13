"""Búsqueda de vuelos baratos con SerpApi (resultados de Google Flights), para el bot de Telegram.

Mismas reglas que el bot del PC (legalsky_bots/vuelos.py): mínimo 2 h 30 min antes de salir,
máximo 12 h, terminal por aerolínea y las 5 opciones más baratas.

Gasto en SerpApi (plan gratis: 250 consultas al mes):
- buscar(): 1 consulta por cada día que toca la ventana (1 o 2), con los 12 destinos a la vez.
- enlace_aerolinea(): 1 consulta, solo cuando el asesor pide el enlace de un vuelo.
SerpApi no cobra la misma consulta repetida dentro de 1 hora (caché).
"""

import re
from dataclasses import dataclass
from datetime import datetime

import httpx

from legalsky_bots.vuelos import DESTINOS, ZONA, Busqueda, Vuelo, enlace_de_aerolinea, mejores

API = "https://serpapi.com/search.json"

# Google Flights quiere aeropuertos, no códigos de ciudad: cada ciudad con sus aeropuertos.
AEROPUERTOS_DE_CIUDAD = {
    "LON": ["LHR", "LGW", "STN", "LTN"],
    "PAR": ["CDG", "ORY", "BVA"],
    "ROM": ["FCO", "CIA"],
    "MIL": ["MXP", "LIN", "BGY"],
}
CIUDAD_DE_AEROPUERTO = {a: c for c, lista in AEROPUERTOS_DE_CIUDAD.items() for a in lista}


@dataclass(frozen=True)
class Opcion:
    vuelo: Vuelo
    booking_token: str  # para pedir después el enlace de la aerolínea


class ErrorSerpApi(Exception):
    pass


def aeropuertos_destino(aeropuerto: str, tipo: str) -> str:
    codigos = []
    for d in DESTINOS[(aeropuerto, tipo)]:
        codigos += AEROPUERTOS_DE_CIUDAD.get(d, [d])
    return ",".join(codigos)


def dias(b: Busqueda) -> list[str]:
    return sorted({b.desde.date().isoformat(), b.hasta.date().isoformat()})


def _parametros(b: Busqueda, dia: str, clave: str) -> dict:
    return {
        "engine": "google_flights", "departure_id": b.aeropuerto,
        "arrival_id": aeropuertos_destino(b.aeropuerto, b.tipo), "outbound_date": dia,
        "type": "2", "hl": "es", "gl": "es", "currency": "EUR", "api_key": clave,
    }


def opciones_desde_respuesta(datos: dict) -> list[Opcion]:
    """Convierte la respuesta de SerpApi en vuelos (hora local de España, precio en euros)."""
    salida = []
    for item in (datos.get("best_flights") or []) + (datos.get("other_flights") or []):
        tramos = item.get("flights") or []
        if not tramos or item.get("price") is None:
            continue
        try:
            hora = datetime.strptime(tramos[0]["departure_airport"]["time"], "%Y-%m-%d %H:%M").replace(tzinfo=ZONA)
            llegada_aeropuerto = tramos[-1]["arrival_airport"]["id"]
            llegada = tramos[-1]["arrival_airport"].get("time", "")[-5:]
            precio = float(item["price"])
        except (KeyError, TypeError, ValueError):
            continue
        vuelo = Vuelo(
            aerolinea=str(tramos[0].get("airline") or ""),
            destino=CIUDAD_DE_AEROPUERTO.get(llegada_aeropuerto, llegada_aeropuerto),
            salida=hora, precio=precio, escalas=len(tramos) - 1, llegada=llegada,
        )
        salida.append(Opcion(vuelo, str(item.get("booking_token") or "")))
    return salida


def mejores_opciones(opciones: list[Opcion], b: Busqueda) -> list[Opcion]:
    elegidos = mejores([o.vuelo for o in opciones], b)
    # Un mismo vuelo puede salir varias veces; mejores() se queda con uno por (aerolínea, destino, hora).
    por_vuelo = {}
    for o in opciones:
        por_vuelo.setdefault(o.vuelo, o)
    return [por_vuelo[v] for v in elegidos]


def _consultar(cliente: httpx.Client, parametros: dict) -> dict:
    r = cliente.get(API, params=parametros, timeout=60)
    datos = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200 or datos.get("error"):
        error = datos.get("error") or f"HTTP {r.status_code}"
        if "hasn't returned any results" in str(error):
            return {}
        raise ErrorSerpApi(error)
    return datos


def buscar(b: Busqueda, clave: str, cliente: httpx.Client | None = None) -> list[Opcion]:
    with cliente or httpx.Client() as c:
        opciones = []
        for dia in dias(b):
            opciones += opciones_desde_respuesta(_consultar(c, _parametros(b, dia, clave)))
    return mejores_opciones(opciones, b)


def _normaliza(texto: str) -> str:
    return re.sub(r"[^a-z0-9]", "", texto.lower())


def opcion_de_la_aerolinea(datos: dict, aerolinea: str) -> dict | None:
    """La opción de reserva de la propia aerolínea (no de una agencia)."""
    nombre = _normaliza(aerolinea)
    for opcion in datos.get("booking_options") or []:
        juntos = opcion.get("together") or {}
        vendedor = _normaliza(str(juntos.get("book_with") or ""))
        if vendedor and nombre and (vendedor in nombre or nombre in vendedor) and juntos.get("booking_request"):
            return juntos
    return None


def resolver_enlace(peticion: dict, cliente: httpx.Client) -> str:
    """Google da un formulario (POST) que redirige a la aerolínea: devuelve la dirección final."""
    url, cuerpo = peticion.get("url"), peticion.get("post_data") or ""
    if not url:
        return ""
    r = cliente.post(url, content=cuerpo, headers={"Content-Type": "application/x-www-form-urlencoded"},
                     follow_redirects=False, timeout=30)
    destino = r.headers.get("location", "")
    if not destino:
        m = re.search(r"""(?:url=|location\.(?:href|replace)\(?\s*=?\s*)['"]?(https://[^'"\s>]+)""", r.text or "")
        destino = m.group(1) if m else ""
    return enlace_de_aerolinea(destino)


def enlace_aerolinea(b: Busqueda, opcion: Opcion, clave: str, cliente: httpx.Client | None = None) -> tuple[str, dict | None]:
    """Devuelve (enlace directo de la aerolínea o "", petición de Google para abrirla desde el móvil)."""
    if not opcion.booking_token:
        return "", None
    with cliente or httpx.Client() as c:
        parametros = {**_parametros(b, opcion.vuelo.salida.date().isoformat(), clave),
                      "booking_token": opcion.booking_token}
        juntos = opcion_de_la_aerolinea(_consultar(c, parametros), opcion.vuelo.aerolinea)
        if not juntos:
            return "", None
        peticion = juntos["booking_request"]
        try:
            return resolver_enlace(peticion, c), peticion
        except httpx.HTTPError:
            return "", peticion
