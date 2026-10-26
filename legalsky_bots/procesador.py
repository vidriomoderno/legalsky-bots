"""Bot 1 (lector de billetes), bot 2 (solicitud de facturas) y bot 3 (recolector).

Recorre los correos con PDF del Gmail de compras, clasifica cada PDF con Claude,
lo guarda en Drive y lo anota en la hoja de control. Después pide en la web de
la aerolínea la factura de cada billete pendiente. Las facturas que llegan se
emparejan con su billete por número de billete o localizador.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol

from .modelos import Billete, DocumentoVuelo, Respuesta, Resultado, aerolinea_soportada

log = logging.getLogger(__name__)

PESTANA_BILLETES = "Billetes"
PESTANA_FACTURAS = "Facturas"

COLUMNAS_BILLETES = [
    "Alta", "Aerolínea", "Localizador", "Nº billete", "Pasajero", "Nombre pasajero", "Apellido pasajero",
    "Vuelo", "Origen", "Destino", "Fecha vuelo", "Fecha emisión", "Importe", "Moneda", "PDF", "Estado",
    "Solicitud factura", "Intentos", "Factura", "Notas", "Id correo",
]
COLUMNAS_FACTURAS = [
    "Alta", "Aerolínea", "Nº factura", "Fecha factura", "Localizador", "Nº billete", "Cliente", "NIF cliente",
    "Base imponible", "IVA", "Total", "Moneda", "PDF", "Estado", "Enviada al gestor", "Notas", "Id correo",
]

ESTADO_PENDIENTE = "Factura pendiente"
ESTADO_SOLICITADA = "Factura solicitada"
ESTADO_ATRASADA = "Factura pendiente (atrasada)"
ESTADO_SOLICITADA_ATRASADA = "Factura solicitada (no llega)"
ESTADO_FACTURADO = "Facturado"
ESTADO_FACTURA_ERRONEA = "Factura con datos erróneos"
ESTADO_YA_FACTURADO = "Revisar: la aerolínea ya la había facturado"
ESTADO_NO_SE_PUDO = "Revisar: pedir la factura a mano"

MAX_INTENTOS = 5
# Air Europa no deja pedir la factura hasta 24-48 h después de emitir el billete.
DIAS_ESPERA = {"aireuropa": 2, "iberia": 0}

FACTURA_OK = "Correcta"
FACTURA_CIF_MAL = "Revisar: el CIF no es el de la empresa"
FACTURA_SIN_BILLETE = "Revisar: sin billete emparejado"

ETIQUETA_OK = "LegalSky/Procesado"
ETIQUETA_REVISAR = "LegalSky/Revisar"


@dataclass
class AdjuntoPdf:
    nombre: str
    contenido: bytes


@dataclass
class Correo:
    id: str
    asunto: str
    adjuntos: list[AdjuntoPdf]


class Buzon(Protocol):
    def correos_pendientes(self, busqueda: str) -> list[Correo]: ...
    def etiquetar(self, id_correo: str, etiqueta: str) -> None: ...


class Almacen(Protocol):
    def guardar_pdf(self, ruta_carpetas: list[str], nombre: str, contenido: bytes) -> str:
        """Guarda el PDF y devuelve su enlace."""
        ...


class Hoja(Protocol):
    def filas(self, pestana: str) -> list[dict[str, str]]:
        """Filas como diccionarios columna -> valor; incluyen '_fila' (número de fila en la hoja)."""
        ...
    def agregar(self, pestana: str, columnas: list[str], valores: dict[str, str]) -> None: ...
    def actualizar(self, pestana: str, fila: int, columnas: list[str], valores: dict[str, str]) -> None: ...


class Extractor(Protocol):
    def extraer(self, pdf: bytes, nombre_archivo: str, id_correo: str = "") -> DocumentoVuelo | None: ...


class Solicitador(Protocol):
    def solicitar(self, billete: Billete) -> Respuesta: ...


@dataclass
class Resumen:
    correos: int = 0
    billetes_nuevos: int = 0
    billetes_repetidos: int = 0
    facturas_nuevas: int = 0
    facturas_a_revisar: int = 0
    ignorados: int = 0
    errores: int = 0
    alertas_atraso: int = 0
    facturas_solicitadas: int = 0
    solicitudes_fallidas: int = 0


def normalizar_nif(nif: str | None) -> str:
    """'b-12.345.678' -> 'B12345678'; quita también el prefijo de país 'ES'."""
    limpio = re.sub(r"[^A-Za-z0-9]", "", nif or "").upper()
    return limpio[2:] if limpio.startswith("ES") and len(limpio) > 9 else limpio


def _solo_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor)


def _importe(valor: float | None) -> str:
    return "" if valor is None else f"{valor:.2f}".replace(".", ",")


def _carpetas_por_mes(tipo: str, fecha_iso: str | None, hoy: date) -> list[str]:
    try:
        fecha = date.fromisoformat(fecha_iso) if fecha_iso else hoy
    except ValueError:
        fecha = hoy
    return [tipo, f"{fecha.year}", f"{fecha.month:02d}"]


class Procesador:
    def __init__(self, buzon: Buzon, almacen: Almacen, hoja: Hoja, extractor: Extractor,
                 empresa_cif: str, dias_alerta: int = 7, hoy: date | None = None,
                 solicitador: Solicitador | None = None):
        self.buzon = buzon
        self.almacen = almacen
        self.hoja = hoja
        self.extractor = extractor
        self.solicitador = solicitador
        self.empresa_cif = normalizar_nif(empresa_cif)
        self.dias_alerta = dias_alerta
        self.hoy = hoy or date.today()

    def ejecutar(self, busqueda: str) -> Resumen:
        resumen = Resumen()
        for correo in self.buzon.correos_pendientes(busqueda):
            resumen.correos += 1
            revisar = False
            for adjunto in correo.adjuntos:
                try:
                    revisar |= self._procesar_adjunto(correo, adjunto, resumen)
                except Exception:
                    log.exception("Error procesando %s del correo %s", adjunto.nombre, correo.id)
                    resumen.errores += 1
                    revisar = True
            self.buzon.etiquetar(correo.id, ETIQUETA_REVISAR if revisar else ETIQUETA_OK)
        if self.solicitador is not None:
            self._solicitar_pendientes(resumen)
        resumen.alertas_atraso = self._marcar_atrasados()
        return resumen

    def _solicitar_pendientes(self, resumen: Resumen) -> None:
        """Bot 2: pide en la web la factura de cada billete que aún no la tiene."""
        for fila, billete in billetes_para_pedir(self.hoja, self.hoy):
            try:
                respuesta = self.solicitador.solicitar(billete)
            except Exception as e:
                log.exception("Error pidiendo la factura de %s", billete.numero_billete)
                respuesta = Respuesta(Resultado.REVISAR, f"Error inesperado: {e}"[:200])
            estado = anotar_respuesta(self.hoja, fila, respuesta, self.hoy)
            resumen.facturas_solicitadas += int(estado == ESTADO_SOLICITADA)
            resumen.solicitudes_fallidas += int(estado == ESTADO_NO_SE_PUDO)


    # Devuelve True si el adjunto necesita revisión humana.
    def _procesar_adjunto(self, correo: Correo, adjunto: AdjuntoPdf, resumen: Resumen) -> bool:
        doc = self.extractor.extraer(adjunto.contenido, adjunto.nombre, id_correo=correo.id)
        if doc is None:
            resumen.errores += 1
            return True
        if doc.tipo == "billete":
            return self._registrar_billete(correo, adjunto, doc, resumen)
        if doc.tipo == "factura":
            return self._registrar_factura(correo, adjunto, doc, resumen)
        resumen.ignorados += 1
        return False

    def _buscar_billete(self, filas: list[dict[str, str]], doc: DocumentoVuelo) -> dict[str, str] | None:
        numeros = {_solo_digitos(n) for n in doc.numeros_billete if _solo_digitos(n)}
        for fila in filas:
            de_la_fila = {_solo_digitos(n) for n in fila.get("Nº billete", "").split(",")}
            if numeros & de_la_fila:
                return fila
        if doc.localizador:
            localizador = doc.localizador.strip().upper()
            for fila in filas:
                if fila.get("Localizador", "").strip().upper() == localizador:
                    return fila
        return None

    def _registrar_billete(self, correo: Correo, adjunto: AdjuntoPdf, doc: DocumentoVuelo, resumen: Resumen) -> bool:
        if self._buscar_billete(self.hoja.filas(PESTANA_BILLETES), doc):
            resumen.billetes_repetidos += 1
            return False
        enlace = self.almacen.guardar_pdf(
            _carpetas_por_mes("Billetes", doc.fecha_emision, self.hoy), adjunto.nombre, adjunto.contenido)
        self.hoja.agregar(PESTANA_BILLETES, COLUMNAS_BILLETES, {
            "Alta": self.hoy.isoformat(),
            "Aerolínea": doc.aerolinea or "",
            "Localizador": doc.localizador or "",
            "Nº billete": ", ".join(doc.numeros_billete),
            "Pasajero": doc.pasajero or "",
            "Nombre pasajero": doc.pasajero_nombre or "",
            "Apellido pasajero": doc.pasajero_apellido or "",
            "Vuelo": doc.vuelo or "",
            "Origen": doc.origen or "",
            "Destino": doc.destino or "",
            "Fecha vuelo": doc.fecha_vuelo or "",
            "Fecha emisión": doc.fecha_emision or "",
            "Importe": _importe(doc.importe_total),
            "Moneda": doc.moneda or "",
            "PDF": enlace,
            "Estado": ESTADO_PENDIENTE,
            "Solicitud factura": "",
            "Intentos": "0",
            "Factura": "",
            "Notas": doc.notas or "",
            "Id correo": correo.id,
        })
        resumen.billetes_nuevos += 1
        self._emparejar_factura_previa(doc)
        return doc.confianza == "baja"

    def _emparejar_factura_previa(self, doc: DocumentoVuelo) -> None:
        """Si la factura de este billete llegó antes que el billete, se emparejan ahora."""
        numeros = {_solo_digitos(n) for n in doc.numeros_billete if _solo_digitos(n)}
        localizador = (doc.localizador or "").strip().upper()
        for factura in self.hoja.filas(PESTANA_FACTURAS):
            if factura.get("Estado") != FACTURA_SIN_BILLETE:
                continue
            de_factura = {_solo_digitos(n) for n in factura.get("Nº billete", "").split(",")}
            if not (numeros & de_factura or (localizador and factura.get("Localizador", "").strip().upper() == localizador)):
                continue
            billete = self._buscar_billete(self.hoja.filas(PESTANA_BILLETES), doc)
            self.hoja.actualizar(PESTANA_FACTURAS, int(factura["_fila"]), COLUMNAS_FACTURAS, {"Estado": FACTURA_OK})
            self.hoja.actualizar(PESTANA_BILLETES, int(billete["_fila"]), COLUMNAS_BILLETES, {
                "Estado": ESTADO_FACTURADO, "Factura": factura.get("Nº factura") or factura.get("PDF", ""),
            })
            return

    def _registrar_factura(self, correo: Correo, adjunto: AdjuntoPdf, doc: DocumentoVuelo, resumen: Resumen) -> bool:
        if doc.numero_factura and any(
            f.get("Nº factura") == doc.numero_factura for f in self.hoja.filas(PESTANA_FACTURAS)
        ):
            return False  # factura ya registrada (p. ej. reenviada dos veces)

        cif_ok = normalizar_nif(doc.nif_cliente) == self.empresa_cif
        billete = self._buscar_billete(self.hoja.filas(PESTANA_BILLETES), doc)
        if not cif_ok:
            estado = FACTURA_CIF_MAL
        elif billete is None:
            estado = FACTURA_SIN_BILLETE
        else:
            estado = FACTURA_OK

        enlace = self.almacen.guardar_pdf(
            _carpetas_por_mes("Facturas", doc.fecha_emision, self.hoy), adjunto.nombre, adjunto.contenido)
        self.hoja.agregar(PESTANA_FACTURAS, COLUMNAS_FACTURAS, {
            "Alta": self.hoy.isoformat(),
            "Aerolínea": doc.aerolinea or "",
            "Nº factura": doc.numero_factura or "",
            "Fecha factura": doc.fecha_emision or "",
            "Localizador": doc.localizador or "",
            "Nº billete": ", ".join(doc.numeros_billete),
            "Cliente": doc.razon_social_cliente or "",
            "NIF cliente": doc.nif_cliente or "",
            "Base imponible": _importe(doc.base_imponible),
            "IVA": _importe(doc.iva),
            "Total": _importe(doc.importe_total),
            "Moneda": doc.moneda or "",
            "PDF": enlace,
            "Estado": estado,
            "Enviada al gestor": "No",
            "Notas": doc.notas or "",
            "Id correo": correo.id,
        })
        if billete is not None:
            self.hoja.actualizar(PESTANA_BILLETES, int(billete["_fila"]), COLUMNAS_BILLETES, {
                "Estado": ESTADO_FACTURADO if cif_ok else ESTADO_FACTURA_ERRONEA,
                "Factura": doc.numero_factura or enlace,
            })
        resumen.facturas_nuevas += 1
        revisar = estado != FACTURA_OK or doc.confianza == "baja"
        resumen.facturas_a_revisar += int(revisar)
        return revisar

    def _marcar_atrasados(self) -> int:
        marcados = 0
        for fila in self.hoja.filas(PESTANA_BILLETES):
            if fila.get("Estado") not in (ESTADO_PENDIENTE, ESTADO_SOLICITADA):
                continue
            try:
                alta = datetime.strptime(fila.get("Alta", ""), "%Y-%m-%d").date()
            except ValueError:
                continue
            if (self.hoy - alta).days > self.dias_alerta:
                atrasado = ESTADO_ATRASADA if fila["Estado"] == ESTADO_PENDIENTE else ESTADO_SOLICITADA_ATRASADA
                self.hoja.actualizar(PESTANA_BILLETES, int(fila["_fila"]), COLUMNAS_BILLETES,
                                     {"Estado": atrasado})
                marcados += 1
        return marcados


# ---------- Bot 2: qué pedir y cómo anotarlo ----------
# Lo usan tanto el Procesador (navegador en la nube) como la tarea del PC (scripts/cola_pc.py).

def billetes_para_pedir(hoja: Hoja, hoy: date) -> list[tuple[int, Billete]]:
    """Billetes sin factura pedida, de Iberia o Air Europa, que la aerolínea ya deja pedir."""
    listos = []
    for fila in hoja.filas(PESTANA_BILLETES):
        if fila.get("Estado") not in (ESTADO_PENDIENTE, ESTADO_ATRASADA):
            continue
        receta = aerolinea_soportada(fila.get("Aerolínea", ""))
        if receta is None or int(fila.get("Intentos") or 0) >= MAX_INTENTOS or not _ya_se_puede(fila, receta, hoy):
            continue
        listos.append((int(fila["_fila"]), Billete(
            aerolinea=fila.get("Aerolínea", ""),
            nombre=fila.get("Nombre pasajero", ""),
            apellido=fila.get("Apellido pasajero", ""),
            numero_billete=fila.get("Nº billete", "").split(",")[0].strip(),
            localizador=fila.get("Localizador", ""),
            fecha_vuelo=fila.get("Fecha vuelo", ""),
        )))
    return listos


def anotar_respuesta(hoja: Hoja, fila: int, respuesta: Respuesta, hoy: date) -> str:
    """Escribe el resultado en la hoja y devuelve el estado nuevo ('' si no cambia)."""
    actual = next((f for f in hoja.filas(PESTANA_BILLETES) if int(f["_fila"]) == fila), None)
    if actual is None:
        raise ValueError(f"No existe la fila {fila} en la hoja de billetes")
    cambios = {"Solicitud factura": f"{hoy.isoformat()}: {respuesta.detalle}"}
    if respuesta.resultado == Resultado.SOLICITADA:
        cambios["Estado"] = ESTADO_SOLICITADA
    elif respuesta.resultado == Resultado.YA_FACTURADA:
        cambios["Estado"] = ESTADO_YA_FACTURADO
    else:
        intentos = int(actual.get("Intentos") or 0) + 1
        cambios["Intentos"] = str(intentos)
        if intentos >= MAX_INTENTOS:
            cambios["Estado"] = ESTADO_NO_SE_PUDO
    hoja.actualizar(PESTANA_BILLETES, fila, COLUMNAS_BILLETES, cambios)
    return cambios.get("Estado", "")


def _ya_se_puede(fila: dict[str, str], receta: str, hoy: date) -> bool:
    try:
        emision = date.fromisoformat(fila.get("Fecha emisión") or fila.get("Alta", ""))
    except ValueError:
        return True
    return hoy >= emision + timedelta(days=DIAS_ESPERA.get(receta, 0))
