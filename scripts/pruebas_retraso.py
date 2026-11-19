"""Ayudas para la skill pruebas-retraso (prueba del retraso de cada vuelo del CRM).

    python scripts/pruebas_retraso.py buscar CODIGO
        -> JSON con los tramos (aerolínea y número) que hay que buscar en FlightStats.
           Con escala (IB1048-563) son todos los tramos, en orden, como hace la asesora.
    python scripts/pruebas_retraso.py pdf IMAGEN [IMAGEN ...] --vuelo FR7958 --fecha 2026-11-16
            --ruta ORK-BCN --url URL [--url URL2 ...] [--titulo T1 --titulo T2 ...]
        -> un PDF (trabajo/pruebas/FR7958_2026-11-16_ORK-BCN.pdf) con una página por captura y
           una cabecera que dice de dónde sale y cuándo se capturó. Imprime la ruta del PDF.
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
    """'FR7958' -> un tramo FR 7958; 'IB1048-563' -> dos tramos, IB 1048 y IB 563, en orden.

    Como hace la asesora, en un vuelo con escala se capturan TODOS los tramos: el primero es el
    vuelo retrasado y el siguiente la conexión perdida. None si el código no se puede buscar.
    """
    c = codigo.strip().upper().replace(" ", "")
    m = re.fullmatch(r"([A-Z0-9]{2})(\d{1,4})((?:-\d{1,4})*)", c)
    if not m or not re.search(r"[A-Z]", m.group(1)):
        return None  # CONEXIONES, códigos con "/", vacíos...
    numeros = [m.group(2)] + [t for t in m.group(3).split("-") if t]
    tramos = [{"aerolinea": m.group(1), "numero": n.lstrip("0") or "0"} for n in numeros]
    return {"tramos": tramos, "con_escala": len(tramos) > 1}


def nombre_pdf(vuelo: str, fecha: str, ruta: str) -> str:
    limpio = lambda s: re.sub(r"[^A-Za-z0-9-]", "", s.upper())  # noqa: E731
    return f"{limpio(vuelo)}_{fecha}_{limpio(ruta)}.pdf"


def medidas_jpeg(datos: bytes) -> tuple[int, int]:
    """Ancho y alto de un JPEG (lee la cabecera SOF, sin librerías)."""
    if datos[:2] != b"\xff\xd8":
        raise ValueError("La captura no es un JPEG")
    i = 2
    while i < len(datos):
        while datos[i] == 0xFF:
            i += 1
        marca = datos[i]
        largo = int.from_bytes(datos[i + 1:i + 3], "big")
        if 0xC0 <= marca <= 0xCF and marca not in (0xC4, 0xC8, 0xCC):
            alto = int.from_bytes(datos[i + 4:i + 6], "big")
            ancho = int.from_bytes(datos[i + 6:i + 8], "big")
            return ancho, alto
        i += 1 + largo
    raise ValueError("JPEG sin medidas")


def _texto_pdf(s: str) -> bytes:
    s = s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return s.encode("cp1252", "replace")


def crear_pdf(paginas: list[tuple[Path, list[str]]], destino: Path) -> Path:
    """PDF con una página por captura: cabecera de texto y debajo la captura (JPEG).

    Sin librerías externas (el Python del PC puede no tener Pillow).
    """
    escala, linea, margen = 0.75, 16, 14  # píxeles -> puntos
    n = len(paginas)
    # Objetos: 1 catálogo, 2 páginas, 3 fuente; luego por página: página, contenido, imagen.
    kids = " ".join(f"{4 + 3 * i} 0 R" for i in range(n)).encode()
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, n),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    for i, (imagen, cabecera) in enumerate(paginas):
        jpg = imagen.read_bytes()
        ancho, alto = medidas_jpeg(jpg)
        w, h_img = ancho * escala, alto * escala
        h = h_img + margen * 2 + linea * len(cabecera)
        textos = b"".join(b"BT /F1 11 Tf %.1f %.1f Td (%s) Tj ET\n" % (margen, h - margen - 11 - k * linea, _texto_pdf(t))
                          for k, t in enumerate(cabecera))
        contenido = textos + b"q %.2f 0 0 %.2f 0 0 cm /Im1 Do Q\n" % (w, h_img)
        pag = 4 + 3 * i
        objetos += [
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Contents %d 0 R "
            b"/Resources << /Font << /F1 3 0 R >> /XObject << /Im1 %d 0 R >> >> >>" % (w, h, pag + 1, pag + 2),
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(contenido), contenido),
            b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB "
            b"/BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n%s\nendstream" % (ancho, alto, len(jpg), jpg),
        ]
    salida = bytearray(b"%PDF-1.4\n")
    posiciones = []
    for n, obj in enumerate(objetos, 1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n%s\nendobj\n" % (n, obj)
    xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    salida += b"".join(b"%010d 00000 n \n" % p for p in posiciones)
    salida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, xref)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(bytes(salida))
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
    f.add_argument("imagenes", nargs="+")
    f.add_argument("--vuelo", required=True)
    f.add_argument("--fecha", required=True)
    f.add_argument("--ruta", required=True)
    f.add_argument("--url", action="append", required=True, help="una por captura, en el mismo orden")
    f.add_argument("--titulo", action="append", default=[], help="opcional, uno por captura")
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
        n = len(args.imagenes)
        if len(args.url) != n or (args.titulo and len(args.titulo) != n):
            sys.exit(f"Hay {n} capturas: hace falta una --url por captura (y un --titulo por captura si se usa).")
        ahora = datetime.now(ZONA).strftime("%d/%m/%Y %H:%M")
        destino = CARPETA_PDF / nombre_pdf(args.vuelo, args.fecha, args.ruta)
        paginas = []
        for i, imagen in enumerate(args.imagenes):
            cabecera = [f"Vuelo {args.vuelo} - {args.fecha} - {args.ruta}"]
            if args.titulo:
                cabecera.append(args.titulo[i])
            cabecera += [f"Fuente: {args.fuente} - {args.url[i]}", f"Capturado el {ahora} (hora de España)"]
            paginas.append((Path(imagen), cabecera))
        crear_pdf(paginas, destino)
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
