"""Lectura de PDF sin clave de API: el propio Claude (Claude Code con la cuenta de Fede)
lee los PDF y este script hace todo lo demás.

    python scripts/cola_pdf.py bajar [MAXIMO]
        Baja a trabajo/pdfs/ los PDF de los próximos MAXIMO correos pendientes (por defecto 15)
        y escribe trabajo/lote.json con la lista. Imprime cuántos correos quedan en total.
    python scripts/cola_pdf.py registrar trabajo/extraccion.json
        Registra lo que Claude leyó: Drive, hoja de control y etiquetas de Gmail
        (lector de billetes + recolector de facturas). Luego borra trabajo/pdfs/.

Formato de trabajo/extraccion.json (lo escribe Claude):
    [{"id_correo": "...", "archivo": "nombre.pdf", "datos": {campos de DocumentoVuelo} | null}, ...]
"datos": null = no se pudo leer (el correo queda con la etiqueta LegalSky/Revisar).
"""

import json
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from pydantic import ValidationError  # noqa: E402

from legalsky_bots import config  # noqa: E402
from legalsky_bots.modelos import DocumentoVuelo  # noqa: E402
from legalsky_bots.procesador import Correo, Procesador  # noqa: E402

TRABAJO = RAIZ / "trabajo"
PDFS = TRABAJO / "pdfs"
LOTE = TRABAJO / "lote.json"


def normalizar(datos: dict | None) -> DocumentoVuelo | None:
    """Acepta lo que escribió Claude aunque falten campos (se rellenan con vacío)."""
    if not isinstance(datos, dict):
        return None
    completo = {campo: None for campo in DocumentoVuelo.model_fields}
    completo["numeros_billete"] = []
    completo["confianza"] = "media"
    completo.update({k: v for k, v in datos.items() if k in DocumentoVuelo.model_fields})
    try:
        return DocumentoVuelo.model_validate(completo)
    except ValidationError:
        return None


class ExtractorDesdeArchivo:
    """Devuelve lo que Claude ya leyó, en lugar de llamar a la API."""

    def __init__(self, filas: list[dict]):
        self._por_clave = {(f.get("id_correo"), f.get("archivo")): normalizar(f.get("datos")) for f in filas}

    def extraer(self, pdf: bytes, nombre_archivo: str, id_correo: str = "") -> DocumentoVuelo | None:
        return self._por_clave.get((id_correo, nombre_archivo))


class BuzonDeLote:
    """Solo los correos que Claude leyó; el resto se queda para el siguiente lote."""

    def __init__(self, buzon, ids: list[str]):
        self._buzon, self._ids = buzon, ids

    def correos_pendientes(self, busqueda: str) -> list[Correo]:
        return [self._buzon.leer(i) for i in self._ids]

    def etiquetar(self, id_correo: str, etiqueta: str) -> None:
        self._buzon.etiquetar(id_correo, etiqueta)


def _servicios():
    from legalsky_bots.google_servicios import AlmacenDrive, BuzonGmail, HojaSheets, credenciales

    cfg = config.cargar()
    creds = credenciales(cfg.google_token_json)
    return cfg, BuzonGmail(creds), AlmacenDrive(creds, cfg.drive_carpeta_raiz_id), HojaSheets(creds, cfg.hoja_control_id)


def bajar(maximo: int) -> dict:
    cfg, buzon, _, _ = _servicios()
    ids = buzon.ids_pendientes(cfg.gmail_busqueda)
    shutil.rmtree(PDFS, ignore_errors=True)
    lote = []
    for id_correo in ids[:maximo]:
        correo = buzon.leer(id_correo)
        carpeta = PDFS / id_correo
        carpeta.mkdir(parents=True, exist_ok=True)
        adjuntos = []
        for n, adjunto in enumerate(correo.adjuntos, start=1):
            ruta = carpeta / f"{n}.pdf"
            ruta.write_bytes(adjunto.contenido)
            adjuntos.append({"archivo": adjunto.nombre, "ruta": str(ruta.relative_to(RAIZ))})
        lote.append({"id_correo": id_correo, "asunto": correo.asunto, "adjuntos": adjuntos})
    TRABAJO.mkdir(exist_ok=True)
    LOTE.write_text(json.dumps(lote, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"en_este_lote": len(lote), "pendientes_en_total": len(ids), "lote": str(LOTE.relative_to(RAIZ))}


def registrar(ruta_extraccion: str) -> dict:
    filas = json.loads(Path(ruta_extraccion).read_text(encoding="utf-8"))
    ids = list(dict.fromkeys(f["id_correo"] for f in filas))
    cfg, buzon, almacen, hoja = _servicios()
    procesador = Procesador(
        buzon=BuzonDeLote(buzon, ids), almacen=almacen, hoja=hoja,
        extractor=ExtractorDesdeArchivo(filas), empresa_cif=cfg.empresa_cif,
        dias_alerta=cfg.dias_alerta_sin_factura,
    )
    resumen = procesador.ejecutar(cfg.gmail_busqueda)
    shutil.rmtree(PDFS, ignore_errors=True)
    return resumen.__dict__


def main(argv: list[str]) -> None:
    if argv[:1] == ["bajar"]:
        print(json.dumps(bajar(int(argv[1]) if len(argv) > 1 else 15), ensure_ascii=False, indent=2))
    elif len(argv) == 2 and argv[0] == "registrar":
        print(json.dumps(registrar(argv[1]), ensure_ascii=False, indent=2))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
