"""Búsqueda de vuelos baratos con SerpApi (resultados de Google Flights), para el bot de Telegram.

Mismas reglas que el bot del PC (legalsky_bots/vuelos.py): mínimo 2 h 30 min antes de salir,
máximo 12 h, terminal por aerolínea y las 5 opciones más baratas.

Gasto en SerpApi (plan gratis: 250 consultas al mes):
- buscar(): por cada día que toca la ventana (1 o 2), 4 consultas en nacional y 7 en internacional
  (todos los aeropuertos de AEROPUERTOS_TELEGRAM, en grupos de 7).
- enlace_aerolinea(): 1 consulta, solo cuando el asesor pide el enlace de un vuelo.
SerpApi no cobra la misma consulta repetida dentro de 1 hora (caché).

Cuando se acaban las consultas gratis de SerpApi del mes, sigue con HasData (otro servicio que lee
Google Flights, 1.000 créditos gratis al mes = unas 66 consultas). Los vuelos de HasData no traen
enlace de la aerolínea: el bot ofrece abrirlos en Google Flights.
"""

import html
import re
from dataclasses import dataclass
from datetime import datetime

import httpx

from legalsky_bots.vuelos import ZONA, Busqueda, Vuelo, enlace_de_aerolinea, mejores

API = "https://serpapi.com/search.json"
API_HASDATA = "https://api.hasdata.com/scrape/google/flights"

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
    fuente: str = "serpapi"  # serpapi | hasdata


class ErrorSerpApi(Exception):
    pass


class SinConsultas(ErrorSerpApi):
    """El servicio ya no tiene consultas este mes."""


# Todos los aeropuertos con vuelo directo frecuente desde Madrid o Barcelona (no solo las ciudades
# grandes: en nov-2026 se escapó un Madrid-Florencia de 64 € porque Florencia no estaba en la lista).
AEROPUERTOS_TELEGRAM = {
    "nacional": """MAD BCN AGP SVQ PMI VLC BIO ALC LPA TFN TFS ACE FUE SCQ VGO LCG OVD SDR IBZ MAH GRX XRY
        MLN EAS SPC LEI""".split(),
    "internacional": """LIS OPO FAO LHR LGW STN LTN MAN EDI DUB CDG ORY BVA NCE LYS MRS TLS BOD FCO CIA MXP LIN
        BGY FLR VCE NAP BLQ PMO BRU CRL AMS FRA MUC BER DUS ZRH GVA BSL VIE CPH PRG BUD WAW ATH IST OTP
        CMN RAK TNG""".split(),
}

POR_CONSULTA = 7  # con 12 destinos a la vez Google Flights no devuelve nada; con 7 sí (probado nov-2026)


def aeropuertos_destino(aeropuerto: str, tipo: str) -> list[str]:
    """Los aeropuertos de destino en grupos de POR_CONSULTA, cada grupo es una consulta ("A,B,C")."""
    codigos = [a for a in AEROPUERTOS_TELEGRAM[tipo] if a != aeropuerto]
    return [",".join(codigos[i:i + POR_CONSULTA]) for i in range(0, len(codigos), POR_CONSULTA)]


def dias(b: Busqueda) -> list[str]:
    return sorted({b.desde.date().isoformat(), b.hasta.date().isoformat()})


def franja(b: Busqueda, dia: str) -> str:
    """Horas de salida que interesan ese día ("19,23"), para que Google no recorte los vuelos útiles."""
    inicio = b.desde.hour if b.desde.date().isoformat() == dia else 0
    fin = b.hasta.hour if b.hasta.date().isoformat() == dia else 23
    return f"{inicio},{fin}"


def _parametros(b: Busqueda, dia: str, destinos: str, clave: str) -> dict:
    return {
        "engine": "google_flights", "departure_id": b.aeropuerto,
        "arrival_id": destinos, "outbound_date": dia,
        "type": "2",  # solo ida
        "stops": "1" if b.tipo == "internacional" else "0",  # internacional: solo directos; nacional: cualquiera
        "hl": "es", "gl": "es", "currency": "EUR", "api_key": clave,
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
            llegada = tramos[-1]["arrival_airport"].get("time", "").split(" ")[-1]
            precio = float(item["price"])
            escalas_en = ",".join(t["arrival_airport"]["id"] for t in tramos[:-1])
        except (KeyError, TypeError, ValueError):
            continue
        vuelo = Vuelo(
            aerolinea=str(tramos[0].get("airline") or ""),
            destino=CIUDAD_DE_AEROPUERTO.get(llegada_aeropuerto, llegada_aeropuerto),
            salida=hora, precio=precio, escalas=len(tramos) - 1, llegada=llegada, escalas_en=escalas_en,
        )
        salida.append(Opcion(vuelo, str(item.get("booking_token") or ""), str(datos.get("_fuente") or "serpapi")))
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
        if "run out of searches" in str(error) or r.status_code == 429:
            raise SinConsultas(error)
        raise ErrorSerpApi(error)
    return datos


def _tramo_hasdata(t: dict) -> dict:
    return {"departure_airport": t.get("departureAirport") or {}, "arrival_airport": t.get("arrivalAirport") or {},
            "airline": t.get("airline")}


def respuesta_hasdata(datos: dict) -> dict:
    """Pasa la respuesta de HasData (camelCase) al formato de SerpApi que entiende opciones_desde_respuesta."""
    def lista(nombre):
        return [{"flights": [_tramo_hasdata(t) for t in item.get("flights") or []], "price": item.get("price"),
                 "booking_token": ""} for item in datos.get(nombre) or []]
    return {"best_flights": lista("bestFlights"), "other_flights": lista("otherFlights"), "_fuente": "hasdata"}


def _consultar_hasdata(cliente: httpx.Client, parametros: dict, clave: str) -> dict:
    p = {"departureId": parametros["departure_id"], "arrivalId": parametros["arrival_id"],
         "outboundDate": parametros["outbound_date"], "type": "oneWay", "currency": "EUR", "gl": "es", "hl": "es"}
    if parametros.get("stops") == "1":
        p["stops"] = "nonStop"
    if parametros.get("outbound_times"):
        p["outboundTimes"] = parametros["outbound_times"]
    r = cliente.get(API_HASDATA, params=p, headers={"x-api-key": clave}, timeout=120)
    if r.status_code == 403:
        raise SinConsultas("HasData: créditos del mes agotados")
    if r.status_code != 200:
        raise ErrorSerpApi(f"HasData HTTP {r.status_code}: {r.text[:200]}")
    return respuesta_hasdata(r.json())


# Si SerpApi se queda sin consultas, no se le vuelve a preguntar hasta el mes siguiente.
_serpapi_agotada_en: str = ""


def _consultar_vuelos(c: httpx.Client, parametros: dict, clave_hasdata: str) -> dict:
    global _serpapi_agotada_en
    mes = datetime.now(ZONA).strftime("%Y-%m")
    if _serpapi_agotada_en != mes:
        try:
            return _consultar(c, parametros)
        except SinConsultas:
            if not clave_hasdata:
                raise
            _serpapi_agotada_en = mes
    if not clave_hasdata:
        raise SinConsultas("SerpApi sin consultas este mes")
    return _consultar_hasdata(c, parametros, clave_hasdata)


def buscar(b: Busqueda, clave: str, cliente: httpx.Client | None = None, clave_hasdata: str = "") -> list[Opcion]:
    with cliente or httpx.Client() as c:
        opciones = []
        for dia in dias(b):
            for grupo in aeropuertos_destino(b.aeropuerto, b.tipo):
                parametros = {**_parametros(b, dia, grupo, clave), "outbound_times": franja(b, dia)}
                opciones += opciones_desde_respuesta(_consultar_vuelos(c, parametros, clave_hasdata))
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
    return enlace_de_aerolinea(html.unescape(destino))


def enlace_aerolinea(b: Busqueda, opcion: Opcion, clave: str, cliente: httpx.Client | None = None) -> tuple[str, dict | None]:
    """Devuelve (enlace directo de la aerolínea o "", petición de Google para abrirla desde el móvil)."""
    if not opcion.booking_token or opcion.fuente != "serpapi":
        return "", None
    with cliente or httpx.Client() as c:
        destino = ",".join(AEROPUERTOS_DE_CIUDAD.get(opcion.vuelo.destino, [opcion.vuelo.destino]))
        parametros = {**_parametros(b, opcion.vuelo.salida.date().isoformat(), destino, clave),
                      "booking_token": opcion.booking_token}
        juntos = opcion_de_la_aerolinea(_consultar(c, parametros), opcion.vuelo.aerolinea)
        if not juntos:
            return "", None
        peticion = juntos["booking_request"]
        try:
            return resolver_enlace(peticion, c), peticion
        except httpx.HTTPError:
            return "", peticion
