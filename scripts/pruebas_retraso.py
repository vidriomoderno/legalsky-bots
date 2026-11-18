"""Ayudas para la skill pruebas-retraso (prueba del retraso de cada vuelo del CRM).

    python scripts/pruebas_retraso.py buscar CODIGO
        -> JSON con la aerolínea y el número que hay que buscar en FlightStats
           (en vuelos con escala, el último tramo: el que llega al destino).
    python scripts/pruebas_retraso.py pdf IMAGEN --vuelo FR7958 --fecha 2026-11-16 --ruta ORK-BCN --url URL
        -> convierte la captura en PDF (trabajo/pruebas/FR7958_2026-11-16_ORK-BCN.pdf) con una
           cabecera que dice de dónde sale y cuándo se capturó. Imprime la ruta del PDF.
    python scripts/pruebas_retraso.py anotar ID_CRM CODIGO ESTADO "DETALLE"
        ESTADO: subida | menos_3h | no_encontrado | revisar
    python scripts/pruebas_retraso.py hechos
        -> ids del CRM que ya tienen prueba subida por el bot (para no gastar créditos otra vez).
    python scripts/pruebas_retraso.py resumen
        -> lo anotado hoy, agrupado por estado.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parents[1]
TRABAJO = RAIZ / "trabajo"
CARPETA_PDF = TRABAJO / "pruebas"
REGISTRO = TRABAJO / "pruebas_retraso.json"
ZONA = ZoneInfo("Europe/Madrid")
ESTADOS = ("subida", "menos_3h", "no_encontrado", "revisar")


def vuelo_a_buscar(codigo: str) -> dict | None:
    """'FR7958' -> FR 7958; 'IB1048-563' -> IB 563 (último tramo). None si no se puede saber."""
    c = codigo.strip().upper().replace(" ", "")
    m = re.fullmatch(r"([A-Z0-9]{2})(\d{1,4})((?:-\d{1,4})*)", c)
    if not m or not re.search(r"[A-Z]", m.group(1)):
        return None  # CONEXIONES, códigos con "/", vacíos...
    tramos = [m.group(2)] + [t for t in m.group(3).split("-") if t]
    return {"aerolinea": m.group(1), "numero": tramos[-1].lstrip("0") or "0",
            "con_escala": len(tramos) > 1, "tramos": len(tramos)}


def nombre_pdf(vuelo: str, fecha: str, ruta: str) -> str:
    limpio = lambda s: re.sub(r"[^A-Za-z0-9-]", "", s.upper())  # noqa: E731
    return f"{limpio(vuelo)}_{fecha}_{limpio(ruta)}.pdf"


def crear_pdf(imagen: Path, destino: Path, cabecera: list[str]) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    captura = Image.open(imagen).convert("RGB")
    try:
        letra = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        letra = ImageFont.load_default()
    alto_linea, margen = 28, 16
    alto_cab = margen * 2 + alto_linea * len(cabecera)
    hoja = Image.new("RGB", (captura.width, captura.height + alto_cab), "white")
    dibujo = ImageDraw.Draw(hoja)
    for i, linea in enumerate(cabecera):
        dibujo.text((margen, margen + i * alto_linea), linea, fill="black", font=letra)
    hoja.paste(captura, (0, alto_cab))
    destino.parent.mkdir(parents=True, exist_ok=True)
    hoja.save(destino, "PDF", resolution=110)
    return destino


def _leer() -> dict:
    return json.loads(REGISTRO.read_text(encoding="utf-8")) if REGISTRO.exists() else {}


def anotar(id_crm: str, codigo: str, estado: str, detalle: str) -> None:
    if estado not in ESTADOS:
        sys.exit(f"Estado no válido: {estado}. Usa: {', '.join(ESTADOS)}")
    datos = _leer()
    datos[str(id_crm)] = {"codigo": codigo, "estado": estado, "detalle": detalle,
                          "fecha": datetime.now(ZONA).strftime("%Y-%m-%d %H:%M")}
    TRABAJO.mkdir(exist_ok=True)
    REGISTRO.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def resumen() -> str:
    hoy = datetime.now(ZONA).strftime("%Y-%m-%d")
    del_dia = {k: v for k, v in _leer().items() if v["fecha"].startswith(hoy)}
    if not del_dia:
        return "Hoy no se ha anotado ningún vuelo."
    lineas = []
    for estado in ESTADOS:
        items = [v for v in del_dia.values() if v["estado"] == estado]
        if items:
            lineas.append(f"{estado}: {len(items)}")
            lineas += [f"  - {v['codigo']}: {v['detalle']}" for v in items]
    return "\n".join(lineas)


def main(argv: list[str]) -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="orden", required=True)
    b = sub.add_parser("buscar")
    b.add_argument("codigo")
    f = sub.add_parser("pdf")
    f.add_argument("imagen")
    f.add_argument("--vuelo", required=True)
    f.add_argument("--fecha", required=True)
    f.add_argument("--ruta", required=True)
    f.add_argument("--url", required=True)
    f.add_argument("--fuente", default="FlightStats (Historical Flight Status)")
    a = sub.add_parser("anotar")
    a.add_argument("id_crm")
    a.add_argument("codigo")
    a.add_argument("estado")
    a.add_argument("detalle", nargs="?", default="")
    sub.add_parser("hechos")
    sub.add_parser("resumen")
    args = p.parse_args(argv)

    if args.orden == "buscar":
        print(json.dumps(vuelo_a_buscar(args.codigo)))
    elif args.orden == "pdf":
        ahora = datetime.now(ZONA).strftime("%d/%m/%Y %H:%M")
        destino = CARPETA_PDF / nombre_pdf(args.vuelo, args.fecha, args.ruta)
        crear_pdf(Path(args.imagen), destino, [
            f"Vuelo {args.vuelo} - {args.fecha} - {args.ruta}",
            f"Fuente: {args.fuente} - {args.url}",
            f"Capturado el {ahora} (hora de España)",
        ])
        print(destino)
    elif args.orden == "anotar":
        anotar(args.id_crm, args.codigo, args.estado, args.detalle)
        print("ok")
    elif args.orden == "hechos":
        print(json.dumps(sorted(k for k, v in _leer().items() if v["estado"] in ("subida", "menos_3h"))))
    else:
        print(resumen())


if __name__ == "__main__":
    main(sys.argv[1:])
