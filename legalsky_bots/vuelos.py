"""Bot de vuelos baratos desde Madrid-Barajas y Barcelona-El Prat.

Claude lee los precios en Google Flights con el Chrome de Fede; aquí están las reglas:
- Nunca un vuelo que salga en menos de 2 h 30 min.
- Lo principal es el precio; a igual precio, mejor si sale dentro de 8 a 12 horas.
- 5 opciones por búsqueda.

Las terminales salen de la lista oficial de Aena (aerolíneas por terminal, nov-2026). Son por
aerolínea, no por vuelo: una aerolínea puede cambiar de terminal, así que hay que confirmarla
en la tarjeta de embarque. T4 incluye el satélite T4S.
"""

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("Europe/Madrid")
MINIMO_ANTES_DE_SALIR = timedelta(hours=2, minutes=30)
IDEAL_DESDE = timedelta(hours=8)
IDEAL_HASTA = timedelta(hours=12)
MAXIMO_ANTES_DE_SALIR = timedelta(hours=12)  # para ampliar la búsqueda, cambiar solo este número
OPCIONES = 5

AEROPUERTOS = {"MAD": "Madrid-Barajas", "BCN": "Barcelona-El Prat"}

AEROLINEAS_POR_TERMINAL = {
    ("MAD", "T1"): """aerolineas argentinas|aeromexico|air arabia|air cairo|air canada|air china|air europa|
        air serbia|air transat|ajet|alba star|azul|china eastern|condor|delta|easyjet|egyptair|estelar|ethiopian|
        hainan|iberojet|km malta|korean air|kuwait airways|laser|medsky|middle east airlines|nesma|nile air|pegasus|
        privilege style|riyadh air|ryanair|saudia|sichuan|singapore airlines|sunexpress|tarom|titan|tunisair|
        turkish|united""",
    ("MAD", "T2"): """aegean|air europa|air france|alba star|binter|brussels airlines|croatia airlines|eurowings|
        ita|klm|lot|lufthansa|norwegian|privilege style|sas|scandinavian|sky express|smartwings|swiss|tap|
        transavia|volotea|wizz""",
    ("MAD", "T4"): """aer lingus|air algerie|air baltic|airbaltic|air nostrum|american|avianca|boa|boliviana|
        british airways|bulgaria air|cathay|china southern|el al|emirates|etihad|finnair|iberia|israir|latam|
        luxair|plus ultra|qatar|royal air maroc|royal jordanian|vueling|world2fly""",
    ("BCN", "T1"): """aegean|aeromexico|air algerie|air canada|air china|air europa|air france|air nostrum|
        american|arkia|asiana|austrian|avianca|british airways|brussels airlines|china eastern|croatia airlines|
        delta|egyptair|el al|emirates|etihad|finnair|iberia|ita|klm|latam|lot|lufthansa|qatar|royal air maroc|
        royal jordanian|saudia|sas|scandinavian|shenzhen|singapore airlines|swiss|tap|tunisair|turkish|united|
        vueling""",
    ("BCN", "T2"): """aer lingus|air arabia|air baltic|airbaltic|air cairo|air horizont|air serbia|air transat|
        azerbaijan|blue bird|easyjet|eurowings|iberojet|icelandair|jet2|kuwait airways|luxair|nesma|nile air|
        norwegian|pegasus|ryanair|sky express|smartwings|sunexpress|transavia|trinity|volotea|wizz""",
}
TERMINALES = {"MAD": ["T1", "T2", "T4"], "BCN": ["T1", "T2"]}

DESTINOS = {
    ("MAD", "nacional"): ["BCN", "AGP", "SVQ", "PMI", "VLC", "BIO", "ALC", "LPA", "TFN", "SCQ", "IBZ", "OVD"],
    ("BCN", "nacional"): ["MAD", "AGP", "SVQ", "PMI", "BIO", "ALC", "LPA", "TFN", "SCQ", "IBZ", "GRX", "OVD"],
    ("MAD", "internacional"): ["LIS", "OPO", "LON", "PAR", "ROM", "MIL", "BRU", "AMS", "FRA", "DUB", "CMN", "GVA"],
    ("BCN", "internacional"): ["LIS", "LON", "PAR", "ROM", "MIL", "BRU", "AMS", "FRA", "DUB", "CMN", "GVA", "BER"],
}


@dataclass(frozen=True)
class Busqueda:
    aeropuerto: str  # MAD | BCN
    terminal: str  # T1, T2, T4 o TODAS
    tipo: str  # nacional | internacional
    ahora: datetime

    def __post_init__(self):
        if self.aeropuerto not in AEROPUERTOS:
            raise ValueError(f"Aeropuerto no válido: {self.aeropuerto}")
        if self.terminal != "TODAS" and self.terminal not in TERMINALES[self.aeropuerto]:
            raise ValueError(f"{AEROPUERTOS[self.aeropuerto]} no tiene terminal {self.terminal}")
        if self.tipo not in ("nacional", "internacional"):
            raise ValueError(f"Tipo no válido: {self.tipo}")

    @property
    def desde(self) -> datetime:
        return self.ahora + MINIMO_ANTES_DE_SALIR

    @property
    def hasta(self) -> datetime:
        return self.ahora + MAXIMO_ANTES_DE_SALIR


@dataclass(frozen=True)
class Vuelo:
    aerolinea: str
    destino: str
    salida: datetime  # hora local de España
    precio: float  # euros
    escalas: int = 0
    llegada: str = ""
    enlace: str = ""  # la búsqueda de Google Flights
    enlace_aerolinea: str = ""  # la página de la aerolínea con ese vuelo (paso 4 de la skill)


def ahora_en_espana() -> datetime:
    return datetime.now(ZONA).replace(second=0, microsecond=0)


def url_google_flights(origen: str, destino: str, dia: str) -> str:
    consulta = f"vuelos de {origen} a {destino} el {dia} solo ida"
    return f"https://www.google.com/travel/flights?q={quote(consulta)}&hl=es&gl=es&curr=EUR"


def consultas(b: Busqueda) -> list[dict]:
    """Una consulta de Google Flights por destino y por cada día que toca la ventana."""
    dias = sorted({b.desde.date().isoformat(), b.hasta.date().isoformat()})
    return [
        {"destino": d, "dia": dia, "url": url_google_flights(b.aeropuerto, d, dia)}
        for d in DESTINOS[(b.aeropuerto, b.tipo)] for dia in dias
    ]


def _aerolineas(aeropuerto: str, terminal: str) -> list[str]:
    return [a.strip() for a in AEROLINEAS_POR_TERMINAL[(aeropuerto, terminal)].split("|")]


def sale_de_terminal(aerolinea: str, aeropuerto: str, terminal: str) -> bool:
    if terminal == "TODAS":
        return True
    nombre = aerolinea.lower().replace(".", "").replace("-", " ")
    return any(re.search(rf"\b{re.escape(a)}", nombre) for a in _aerolineas(aeropuerto, terminal))


def en_horario_ideal(v: Vuelo, b: Busqueda) -> bool:
    return b.ahora + IDEAL_DESDE <= v.salida <= b.ahora + IDEAL_HASTA


def mejores(vuelos: list[Vuelo], b: Busqueda) -> list[Vuelo]:
    """Las 5 opciones más baratas que cumplen las reglas, sin repetir el mismo vuelo."""
    validos = {}
    for v in vuelos:
        if b.desde <= v.salida <= b.hasta and sale_de_terminal(v.aerolinea, b.aeropuerto, b.terminal):
            clave = (v.aerolinea.lower(), v.destino, v.salida)
            if clave not in validos or v.precio < validos[clave].precio:
                validos[clave] = v
    orden = sorted(validos.values(), key=lambda v: (v.precio, not en_horario_ideal(v, b), v.salida))
    return orden[:OPCIONES]


def vuelo_desde_dict(d: dict) -> Vuelo:
    salida = datetime.fromisoformat(d["salida"])
    return Vuelo(
        aerolinea=str(d["aerolinea"]), destino=str(d["destino"]),
        salida=salida.replace(tzinfo=ZONA) if salida.tzinfo is None else salida,
        precio=float(d["precio"]), escalas=int(d.get("escalas") or 0),
        llegada=str(d.get("llegada") or ""), enlace=str(d.get("enlace") or ""),
        enlace_aerolinea=str(d.get("enlace_aerolinea") or ""),
    )


def enlace_de_aerolinea(url: str) -> str:
    """El enlace si es una página web de verdad fuera de Google (la de la aerolínea); si no, ""."""
    partes = urlsplit(str(url or "").strip())
    host = (partes.hostname or "").lower()
    if partes.scheme != "https" or not host or re.search(r"(^|\.)google\.[a-z.]+$", host):
        return ""
    return partes.geturl()


def dominio(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def a_dict(v: Vuelo) -> dict:
    return {**asdict(v), "salida": v.salida.isoformat()}
