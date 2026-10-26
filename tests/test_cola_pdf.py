from scripts.cola_pdf import BuzonDeLote, ExtractorDesdeArchivo, normalizar
from tests.test_procesador import (
    CIF, AlmacenFalso, BuzonFalso, HojaFalsa, correo, doc, factura,
)
from legalsky_bots.procesador import (
    ESTADO_FACTURADO, ETIQUETA_OK, ETIQUETA_REVISAR, FACTURA_OK, PESTANA_BILLETES, PESTANA_FACTURAS, Procesador,
)


class BuzonConLeer(BuzonFalso):
    def leer(self, id_correo):
        return next(c for c in self.correos if c.id == id_correo)


def fila(id_correo, archivo, d):
    return {"id_correo": id_correo, "archivo": archivo, "datos": None if d is None else d.model_dump()}


def test_normalizar_completa_campos_que_falten():
    d = normalizar({"tipo": "billete", "aerolinea": "Iberia", "numeros_billete": ["075-1"], "campo_raro": 1})
    assert d.tipo == "billete" and d.localizador is None and d.confianza == "media"
    assert normalizar({"tipo": "otra cosa"}) is None
    assert normalizar(None) is None


def test_registrar_lote_solo_toca_los_correos_leidos():
    buzon = BuzonConLeer([correo("m1", "ET.pdf"), correo("m2", "otro.pdf")])
    hoja = HojaFalsa()
    extractor = ExtractorDesdeArchivo([fila("m1", "ET.pdf", doc())])
    p = Procesador(BuzonDeLote(buzon, ["m1"]), AlmacenFalso(), hoja, extractor, empresa_cif=CIF)
    r = p.ejecutar("")
    assert r.billetes_nuevos == 1
    assert buzon.etiquetas == {"m1": ETIQUETA_OK}  # m2 queda para el siguiente lote


def test_pdf_que_claude_no_pudo_leer_va_a_revisar():
    buzon = BuzonConLeer([correo("m1", "roto.pdf")])
    p = Procesador(BuzonDeLote(buzon, ["m1"]), AlmacenFalso(), HojaFalsa(),
                   ExtractorDesdeArchivo([fila("m1", "roto.pdf", None)]), empresa_cif=CIF)
    p.ejecutar("")
    assert buzon.etiquetas == {"m1": ETIQUETA_REVISAR}


def test_factura_que_llega_antes_que_el_billete_se_empareja_despues():
    hoja = HojaFalsa()
    buzon = BuzonConLeer([correo("m1", "factura.pdf"), correo("m2", "ET.pdf")])
    extractor = ExtractorDesdeArchivo([fila("m1", "factura.pdf", factura()), fila("m2", "ET.pdf", doc())])
    Procesador(BuzonDeLote(buzon, ["m1"]), AlmacenFalso(), hoja, extractor, empresa_cif=CIF).ejecutar("")
    Procesador(BuzonDeLote(buzon, ["m2"]), AlmacenFalso(), hoja, extractor, empresa_cif=CIF).ejecutar("")
    assert hoja.datos[PESTANA_FACTURAS][0]["Estado"] == FACTURA_OK
    assert hoja.datos[PESTANA_BILLETES][0]["Estado"] == ESTADO_FACTURADO
    assert hoja.datos[PESTANA_BILLETES][0]["Factura"] == "F-001"
