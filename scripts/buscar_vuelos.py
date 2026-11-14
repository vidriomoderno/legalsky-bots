"""Búsqueda de vuelos baratos.

    python scripts/buscar_vuelos.py preparar MAD T4 nacional
        Calcula la ventana de horas y escribe trabajo/busqueda.json con las consultas de
        Google Flights que Claude tiene que leer.
    python scripts/buscar_vuelos.py resultado trabajo/vuelos_leidos.json
        Aplica las reglas y deja las 5 mejores opciones en resultados/ y en trabajo/elegidos.json.
    python scripts/buscar_vuelos.py enlaces trabajo/enlaces_aerolinea.json
        Añade a cada opción el enlace de la web de la aerolínea y rehace la página.
        Formato: [{"opcion": 1, "enlace": "https://www.iberia.com/..."}, ...]

Formato de trabajo/vuelos_leidos.json (lo escribe Claude):
    [{"aerolinea": "Vueling", "destino": "BCN", "salida": "2026-11-05T10:10", "llegada": "11:30",
      "precio": 136, "escalas": 0, "escalas_en": "", "enlace": "<url de la consulta>"}, ...]
"""

import html
import json
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from legalsky_bots.vuelos import (  # noqa: E402
    AEROPUERTOS, OPCIONES, Busqueda, a_dict, ahora_en_espana, consultas, dominio, en_horario_ideal,
    enlace_de_aerolinea, mejores, vuelo_desde_dict,
)

TRABAJO = RAIZ / "trabajo"
RESULTADOS = RAIZ / "resultados"
BUSQUEDA = TRABAJO / "busqueda.json"
ELEGIDOS = TRABAJO / "elegidos.json"


def preparar(aeropuerto: str, terminal: str, tipo: str) -> dict:
    b = Busqueda(aeropuerto.upper(), terminal.upper(), tipo.lower(), ahora_en_espana())
    datos = {
        "aeropuerto": b.aeropuerto, "terminal": b.terminal, "tipo": b.tipo, "ahora": b.ahora.isoformat(),
        "desde": b.desde.isoformat(), "hasta": b.hasta.isoformat(), "consultas": consultas(b),
    }
    TRABAJO.mkdir(exist_ok=True)
    BUSQUEDA.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"archivo": str(BUSQUEDA.relative_to(RAIZ)), "consultas": len(datos["consultas"]),
            "desde": b.desde.strftime("%d/%m %H:%M"), "hasta": b.hasta.strftime("%d/%m %H:%M")}


def _texto(v, b) -> str:
    escalas = "directo" if v.escalas == 0 else f"{v.escalas} escala(s)"
    ideal = "  [horario ideal]" if en_horario_ideal(v, b) else ""
    return f"{v.precio:>7.2f} EUR  {v.salida:%d/%m %H:%M}  {b.aeropuerto}-{v.destino}  {v.aerolinea} ({escalas}){ideal}"


def _enlaces_html(v) -> str:
    partes = []
    if v.enlace_aerolinea:
        partes.append(f"<a class='comprar' href='{html.escape(v.enlace_aerolinea, quote=True)}'>"
                      f"Ir a {html.escape(dominio(v.enlace_aerolinea))}</a>")
    if v.enlace:
        partes.append(f"<a class='google' href='{html.escape(v.enlace, quote=True)}'>Ver en Google Flights</a>")
    return "<br>".join(partes)


def _html(lista, b) -> str:
    filas = "".join(
        f"<tr><td><b>{v.precio:.2f} €</b></td><td>{v.salida:%d/%m %H:%M}</td>"
        f"<td>{html.escape(v.destino)}</td><td>{html.escape(v.aerolinea)}</td>"
        f"<td>{'Directo' if v.escalas == 0 else str(v.escalas) + ' escala(s)'}</td>"
        f"<td>{'Sí' if en_horario_ideal(v, b) else ''}</td>"
        f"<td>{_enlaces_html(v)}</td></tr>"
        for v in lista
    )
    return f"""<!doctype html><meta charset="utf-8"><title>Vuelos más baratos</title>
<style>body{{font:16px system-ui;margin:24px;color:#222}}table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #ddd;padding:10px;text-align:left}}th{{background:#1F4E79;color:#fff}}
a.comprar{{display:inline-block;background:#1F4E79;color:#fff;padding:6px 10px;border-radius:6px;text-decoration:none}}
a.google{{font-size:13px;color:#555}}</style>
<h1>Vuelos más baratos</h1>
<p>{AEROPUERTOS[b.aeropuerto]} · terminal {b.terminal} · {b.tipo} · buscado el {b.ahora:%d/%m/%Y %H:%M}</p>
<table><tr><th>Precio</th><th>Salida</th><th>Destino</th><th>Aerolínea</th><th>Escalas</th>
<th>Horario ideal (8-12 h)</th><th></th></tr>{filas}</table>
<p>El botón azul abre la web de la aerolínea con ese vuelo. Si el enlace ha caducado, repite la
búsqueda en esa web o usa "Ver en Google Flights". Confirma la terminal en la tarjeta de embarque.
Los precios pueden cambiar al comprar.</p>"""


def _busqueda() -> Busqueda:
    datos = json.loads(BUSQUEDA.read_text(encoding="utf-8"))
    return Busqueda(datos["aeropuerto"], datos["terminal"], datos["tipo"], datetime.fromisoformat(datos["ahora"]))


def _guardar(lista, b) -> Path:
    """Escribe la página de resultados y trabajo/elegidos.json (las opciones numeradas desde 1)."""
    RESULTADOS.mkdir(exist_ok=True)
    salida = RESULTADOS / f"vuelos_{b.aeropuerto}_{b.terminal}_{b.tipo}_{b.ahora:%Y%m%d_%H%M}.html"
    salida.write_text(_html(lista, b), encoding="utf-8")
    TRABAJO.mkdir(exist_ok=True)
    (TRABAJO / "ultimo.txt").write_text(str(salida), encoding="utf-8")  # buscar_vuelos.bat lo abre al terminar
    elegidos = [{"opcion": n, **a_dict(v)} for n, v in enumerate(lista, 1)]
    ELEGIDOS.write_text(json.dumps(elegidos, ensure_ascii=False, indent=2), encoding="utf-8")
    return salida


def resultado(ruta: str) -> list[str]:
    b = _busqueda()
    vuelos = [vuelo_desde_dict(d) for d in json.loads(Path(ruta).read_text(encoding="utf-8"))]
    lista = mejores(vuelos, b)
    salida = _guardar(lista, b)
    lineas = [f"{len(lista)} de {OPCIONES} opciones ({len(vuelos)} vuelos leídos):"]
    lineas += [f"{n}. {_texto(v, b)}" for n, v in enumerate(lista, 1)]
    lineas += [str(salida), f"Opciones guardadas en {ELEGIDOS.relative_to(RAIZ)}"]
    return lineas


def enlaces(ruta: str) -> list[str]:
    """Añade a las opciones elegidas el enlace de la web de la aerolínea y rehace la página."""
    b = _busqueda()
    lista = [vuelo_desde_dict(d) for d in json.loads(ELEGIDOS.read_text(encoding="utf-8"))]
    nuevos = {}
    for d in json.loads(Path(ruta).read_text(encoding="utf-8")):
        try:
            nuevos[int(d["opcion"])] = enlace_de_aerolinea(d.get("enlace", ""))
        except (KeyError, TypeError, ValueError):
            continue
    lista = [replace(v, enlace_aerolinea=nuevos[n]) if nuevos.get(n) else v for n, v in enumerate(lista, 1)]
    salida = _guardar(lista, b)
    lineas = []
    for n, v in enumerate(lista, 1):
        destino = v.enlace_aerolinea or "(sin enlace de la aerolínea: solo Google Flights)"
        lineas.append(f"{n}. {v.aerolinea} {b.aeropuerto}-{v.destino} {v.salida:%d/%m %H:%M}: {destino}")
    lineas.append(str(salida))
    return lineas


def main(argv: list[str]) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) == 4 and argv[0] == "preparar":
        print(json.dumps(preparar(*argv[1:]), ensure_ascii=False, indent=2))
    elif len(argv) == 2 and argv[0] == "resultado":
        print("\n".join(resultado(argv[1])))
    elif len(argv) == 2 and argv[0] == "enlaces":
        print("\n".join(enlaces(argv[1])))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
