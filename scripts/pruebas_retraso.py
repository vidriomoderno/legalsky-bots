"""Ayudas para la skill pruebas-retraso (prueba del retraso de cada vuelo del CRM).

    python scripts/pruebas_retraso.py buscar CODIGO
        -> JSON con los tramos (aerolínea y número) que hay que buscar en FlightStats.
           Con escala (IB1048-563) son todos los tramos, en orden, como hace la asesora.
    python scripts/pruebas_retraso.py pdf IMAGEN [IMAGEN ...] --vuelo FR7958 --fecha 2026-11-16
            --ruta ORK-BCN --url URL [--url URL2 ...] [--titulo T1 --titulo T2 ...]
        -> un PDF A4 como el de la asesora (trabajo/pruebas/FR7958_2026-11-16_ORK-BCN.pdf):
           "DOCUMENTO 3", y por captura su título, la URL de donde sale y la captura. Sin --titulo:
           "FR7958 - VUELO RETRASADO" (con escala, los siguientes "CONEXIÓN PERDIDA").
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


# Anchos de Helvetica (milésimas de em) para ASCII 32..126, para medir la URL.
_ANCHOS = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278] + [556] * 10 + [
    278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722,
    778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500,
    556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500,
    500, 500, 334, 260, 334, 584]


def ancho_helvetica(s: str, tam: float) -> float:
    return sum(_ANCHOS[ord(c) - 32] if 32 <= ord(c) <= 126 else 556 for c in s) * tam / 1000


def titulos_por_defecto(vuelo: str, n: int) -> list[str]:
    """Como la asesora: 'IB1048 - VUELO RETRASADO', 'IB563 - CONEXIÓN PERDIDA'."""
    v = vuelo_a_buscar(vuelo)
    if v and len(v["tramos"]) == n:
        codigos = [t["aerolinea"] + t["numero"] for t in v["tramos"]]
    else:
        codigos = [vuelo.upper()] * n
    return [f"{c} - {'VUELO RETRASADO' if i == 0 else 'CONEXIÓN PERDIDA'}" for i, c in enumerate(codigos)]


# A4 vertical, como el Word de la asesora.
A4_ANCHO, A4_ALTO, MARGEN = 595.28, 841.89, 56.0


def crear_pdf(bloques: list[dict], destino: Path, documento: str = "3", pie: str = "") -> Path:
    """PDF A4 como el de la asesora: "DOCUMENTO 3" arriba y, por cada captura, su título en
    negrita, la URL de donde sale (en azul, se puede pulsar) y la captura a lo ancho de la
    página. Varias capturas van en la misma página si caben. bloques: [{imagen, titulo, url}].

    Sin librerías externas (el Python del PC puede no tener Pillow).
    """
    util = A4_ANCHO - 2 * MARGEN
    paginas: list[dict] = []  # cada una: {"ops": [bytes], "imgs": [(nombre, num_obj)], "links": [(rect, url)]}
    imagenes: list[bytes] = []  # objetos imagen, se numeran al final

    def nueva():
        paginas.append({"ops": [], "imgs": [], "links": []})
        return A4_ALTO - MARGEN

    def texto(y, t, tam, negrita=False, color=None):
        col = b"%.3f %.3f %.3f rg " % color if color else b"0 g "
        paginas[-1]["ops"].append(b"BT %s/%s %.1f Tf %.2f %.2f Td (%s) Tj ET\n" % (
            col, b"F2" if negrita else b"F1", tam, MARGEN, y, _texto_pdf(t)))

    y = nueva()
    if documento:
        y -= 13
        texto(y, f"DOCUMENTO {documento}", 13, negrita=True)
        y -= 14
    for b in bloques:
        jpg = Path(b["imagen"]).read_bytes()
        ancho, alto = medidas_jpeg(jpg)
        h_img = util * alto / ancho
        url = b.get("url") or ""
        tam_url = min(10.0, 10.0 * util / max(ancho_helvetica(url, 10.0), 1))
        alto_bloque = 18 + (tam_url + 10 if url else 0) + 8 + h_img
        if y - alto_bloque < MARGEN + 14 and paginas[-1]["imgs"]:
            y = nueva()
        y -= 18
        if b.get("titulo"):
            texto(y, b["titulo"], 11, negrita=True)
        if url:
            y -= tam_url + 10
            texto(y, url, tam_url, color=(0.02, 0.39, 0.76))
            largo = ancho_helvetica(url, tam_url)
            paginas[-1]["ops"].append(b"0.02 0.39 0.76 RG 0.6 w %.2f %.2f m %.2f %.2f l S\n" % (
                MARGEN, y - 1.5, MARGEN + largo, y - 1.5))
            paginas[-1]["links"].append(((MARGEN, y - 3, MARGEN + largo, y + tam_url), url))
        y -= 8 + h_img
        nombre = b"Im%d" % len(imagenes)
        imagenes.append(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB "
                        b"/BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n%s\nendstream"
                        % (ancho, alto, len(jpg), jpg))
        paginas[-1]["imgs"].append((nombre, len(imagenes) - 1))
        paginas[-1]["ops"].append(b"q 0.5 g %.2f %.2f %.2f %.2f re f Q\n" % (MARGEN - 0.5, y - 0.5, util + 1, h_img + 1))
        paginas[-1]["ops"].append(b"q %.2f 0 0 %.2f %.2f %.2f cm /%s Do Q\n" % (util, h_img, MARGEN, y, nombre))
    if pie:
        for pg in paginas:
            pg["ops"].append(b"BT 0.4 g /F1 8 Tf %.2f %.2f Td (%s) Tj ET\n" % (MARGEN, MARGEN / 2, _texto_pdf(pie)))

    # Objetos: 1 catálogo, 2 páginas, 3 y 4 fuentes, luego imágenes, luego (página, contenido) por página.
    n_img0 = 5
    n_pag0 = n_img0 + len(imagenes)
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
            b" ".join(b"%d 0 R" % (n_pag0 + 2 * i) for i in range(len(paginas))), len(paginas)),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ] + imagenes
    for i, pg in enumerate(paginas):
        xobj = b" ".join(b"/%s %d 0 R" % (nom, n_img0 + k) for nom, k in pg["imgs"])
        annots = b" ".join(
            b"<< /Type /Annot /Subtype /Link /Rect [%.2f %.2f %.2f %.2f] /Border [0 0 0] /A << /S /URI /URI (%s) >> >>"
            % (*r, _texto_pdf(u)) for r, u in pg["links"])
        contenido = b"".join(pg["ops"])
        objetos += [
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Contents %d 0 R "
            b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> /XObject << %s >> >> /Annots [%s] >>"
            % (A4_ANCHO, A4_ALTO, n_pag0 + 2 * i + 1, xobj, annots),
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(contenido), contenido),
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
    f.add_argument("--capturado", default="", help='"dd/mm/AAAA HH:MM" si la captura no es de ahora')
    f.add_argument("--documento", default="3", help='"DOCUMENTO 3" arriba, como la asesora; "" para quitarlo')
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
        ahora = args.capturado or datetime.now(ZONA).strftime("%d/%m/%Y %H:%M")
        destino = CARPETA_PDF / nombre_pdf(args.vuelo, args.fecha, args.ruta)
        titulos = args.titulo or titulos_por_defecto(args.vuelo, n)
        bloques = [{"imagen": img, "titulo": t, "url": u} for img, t, u in zip(args.imagenes, titulos, args.url)]
        pie = (f"Vuelo {args.vuelo} - {args.fecha} - {args.ruta} | Fuente: {args.fuente} | "
               f"Capturado el {ahora} (hora de España)")
        crear_pdf(bloques, destino, documento=args.documento, pie=pie)
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
