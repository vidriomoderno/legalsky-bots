from datetime import date

import pytest

from legalsky_bots.modelos import DocumentoVuelo, Respuesta, Resultado
from legalsky_bots.procesador import (
    ESTADO_ATRASADA, ESTADO_FACTURA_ERRONEA, ESTADO_FACTURADO, ESTADO_NO_SE_PUDO, ESTADO_PENDIENTE,
    ESTADO_SOLICITADA, ESTADO_SOLICITADA_ATRASADA, ESTADO_YA_FACTURADO, ETIQUETA_OK, ETIQUETA_REVISAR,
    FACTURA_CIF_MAL, FACTURA_OK, FACTURA_SIN_BILLETE, MAX_INTENTOS, PESTANA_BILLETES, PESTANA_FACTURAS,
    AdjuntoPdf, Correo, Procesador, normalizar_nif,
)

CIF = "B12345678"
HOY = date(2026, 10, 26)


class BuzonFalso:
    def __init__(self, correos):
        self.correos = correos
        self.etiquetas = {}

    def correos_pendientes(self, busqueda):
        return self.correos

    def etiquetar(self, id_correo, etiqueta):
        self.etiquetas[id_correo] = etiqueta


class AlmacenFalso:
    def __init__(self):
        self.guardados = []

    def guardar_pdf(self, ruta_carpetas, nombre, contenido):
        self.guardados.append("/".join([*ruta_carpetas, nombre]))
        return f"https://drive/{len(self.guardados)}"


class HojaFalsa:
    def __init__(self):
        self.datos = {PESTANA_BILLETES: [], PESTANA_FACTURAS: []}

    def filas(self, pestana):
        return [{"_fila": str(i), **f} for i, f in enumerate(self.datos[pestana], start=2)]

    def agregar(self, pestana, columnas, valores):
        self.datos[pestana].append({c: valores.get(c, "") for c in columnas})

    def actualizar(self, pestana, fila, columnas, valores):
        self.datos[pestana][fila - 2].update(valores)


class ExtractorFalso:
    """Devuelve el documento asociado al nombre del archivo."""

    def __init__(self, por_nombre):
        self.por_nombre = por_nombre

    def extraer(self, pdf, nombre_archivo, id_correo=""):
        resultado = self.por_nombre[nombre_archivo]
        if isinstance(resultado, Exception):
            raise resultado
        return resultado


def doc(**campos):
    base = dict(
        tipo="billete", aerolinea="Iberia", localizador="H3ZPH", numeros_billete=["075-2537889485"],
        pasajero="GARCIA/DIEGO", pasajero_nombre="DIEGO", pasajero_apellido="GARCIA", vuelo="IB0643", origen="MAD", destino="BCN", fecha_vuelo="2026-07-28",
        fecha_emision="2026-07-28", importe_total=56.0, moneda="EUR", numero_factura=None, nif_cliente=None,
        razon_social_cliente=None, base_imponible=None, iva=None, confianza="alta", notas=None,
    )
    base.update(campos)
    return DocumentoVuelo(**base)


def factura(**campos):
    base = dict(tipo="factura", numero_factura="F-001", nif_cliente="ES-B12.345.678",
                razon_social_cliente="LegalSky SL", base_imponible=50.91, iva=5.09, fecha_emision="2026-07-30")
    base.update(campos)
    return doc(**base)


def correo(id_, *nombres):
    return Correo(id=id_, asunto="", adjuntos=[AdjuntoPdf(n, b"%PDF") for n in nombres])


class SolicitadorFalso:
    def __init__(self, resultado=Resultado.SOLICITADA):
        self.resultado = resultado
        self.pedidos = []

    def solicitar(self, billete):
        self.pedidos.append(billete)
        if isinstance(self.resultado, Exception):
            raise self.resultado
        return Respuesta(self.resultado, "detalle")


def montar(correos, por_nombre, hoja=None, hoy=HOY, solicitador=None):
    buzon, almacen, hoja = BuzonFalso(correos), AlmacenFalso(), hoja or HojaFalsa()
    p = Procesador(buzon, almacen, hoja, ExtractorFalso(por_nombre), empresa_cif=CIF, hoy=hoy,
                   solicitador=solicitador)
    return p, buzon, almacen, hoja


def test_billete_nuevo_se_guarda_y_queda_pendiente():
    p, buzon, almacen, hoja = montar(
        [correo("m1", "ET.pdf", "Condiciones.pdf")],
        {"ET.pdf": doc(), "Condiciones.pdf": doc(tipo="otro")},
    )
    r = p.ejecutar("")
    assert (r.billetes_nuevos, r.ignorados, r.errores) == (1, 1, 0)
    fila = hoja.datos[PESTANA_BILLETES][0]
    assert fila["Estado"] == ESTADO_PENDIENTE
    assert fila["Importe"] == "56,00"
    assert almacen.guardados == ["Billetes/2026/07/ET.pdf"]
    assert buzon.etiquetas == {"m1": ETIQUETA_OK}


def test_billete_repetido_no_se_duplica():
    p, _, almacen, hoja = montar(
        [correo("m1", "a.pdf"), correo("m2", "b.pdf")],
        {"a.pdf": doc(), "b.pdf": doc(numeros_billete=["0752537889485"])},
    )
    r = p.ejecutar("")
    assert (r.billetes_nuevos, r.billetes_repetidos) == (1, 1)
    assert len(hoja.datos[PESTANA_BILLETES]) == 1
    assert len(almacen.guardados) == 1


def test_factura_correcta_marca_billete_facturado():
    p, buzon, almacen, hoja = montar(
        [correo("m1", "billete.pdf"), correo("m2", "factura.pdf")],
        {"billete.pdf": doc(), "factura.pdf": factura()},
    )
    r = p.ejecutar("")
    assert (r.facturas_nuevas, r.facturas_a_revisar) == (1, 0)
    assert hoja.datos[PESTANA_FACTURAS][0]["Estado"] == FACTURA_OK
    assert hoja.datos[PESTANA_FACTURAS][0]["Enviada al gestor"] == "No"
    assert hoja.datos[PESTANA_BILLETES][0]["Estado"] == ESTADO_FACTURADO
    assert hoja.datos[PESTANA_BILLETES][0]["Factura"] == "F-001"
    assert "Facturas/2026/07/factura.pdf" in almacen.guardados
    assert buzon.etiquetas["m2"] == ETIQUETA_OK


def test_factura_empareja_por_localizador_si_no_trae_numero_de_billete():
    p, _, _, hoja = montar(
        [correo("m1", "billete.pdf"), correo("m2", "factura.pdf")],
        {"billete.pdf": doc(), "factura.pdf": factura(numeros_billete=[], localizador="h3zph")},
    )
    p.ejecutar("")
    assert hoja.datos[PESTANA_BILLETES][0]["Estado"] == ESTADO_FACTURADO


def test_factura_con_cif_ajeno_se_marca_para_revisar():
    p, buzon, _, hoja = montar(
        [correo("m1", "billete.pdf"), correo("m2", "factura.pdf")],
        {"billete.pdf": doc(), "factura.pdf": factura(nif_cliente="12345678Z")},
    )
    r = p.ejecutar("")
    assert r.facturas_a_revisar == 1
    assert hoja.datos[PESTANA_FACTURAS][0]["Estado"] == FACTURA_CIF_MAL
    assert hoja.datos[PESTANA_BILLETES][0]["Estado"] == ESTADO_FACTURA_ERRONEA
    assert buzon.etiquetas["m2"] == ETIQUETA_REVISAR


def test_factura_sin_billete_se_guarda_y_se_marca():
    p, buzon, _, hoja = montar([correo("m1", "factura.pdf")], {"factura.pdf": factura()})
    p.ejecutar("")
    assert hoja.datos[PESTANA_FACTURAS][0]["Estado"] == FACTURA_SIN_BILLETE
    assert buzon.etiquetas["m1"] == ETIQUETA_REVISAR


def test_factura_repetida_no_se_duplica():
    p, _, _, hoja = montar(
        [correo("m1", "f1.pdf"), correo("m2", "f2.pdf")],
        {"f1.pdf": factura(), "f2.pdf": factura()},
    )
    p.ejecutar("")
    assert len(hoja.datos[PESTANA_FACTURAS]) == 1


def test_error_o_pdf_ilegible_manda_el_correo_a_revisar():
    p, buzon, _, _ = montar(
        [correo("m1", "roto.pdf"), correo("m2", "ilegible.pdf")],
        {"roto.pdf": RuntimeError("API caída"), "ilegible.pdf": None},
    )
    r = p.ejecutar("")
    assert r.errores == 2
    assert buzon.etiquetas == {"m1": ETIQUETA_REVISAR, "m2": ETIQUETA_REVISAR}


def test_billete_sin_factura_mas_de_7_dias_se_marca_atrasado():
    hoja = HojaFalsa()
    hoja.datos[PESTANA_BILLETES] = [
        {"Alta": "2026-10-10", "Estado": ESTADO_PENDIENTE, "Nº billete": "1"},
        {"Alta": "2026-10-24", "Estado": ESTADO_PENDIENTE, "Nº billete": "2"},
        {"Alta": "2026-10-01", "Estado": ESTADO_FACTURADO, "Nº billete": "3"},
    ]
    p, _, _, hoja = montar([], {}, hoja=hoja)
    r = p.ejecutar("")
    assert r.alertas_atraso == 1
    assert [f["Estado"] for f in hoja.datos[PESTANA_BILLETES]] == [ESTADO_ATRASADA, ESTADO_PENDIENTE, ESTADO_FACTURADO]


def test_solicitada_que_no_llega_no_se_vuelve_a_pedir():
    hoja = HojaFalsa()
    hoja.datos[PESTANA_BILLETES] = [
        {"Alta": "2026-10-10", "Estado": ESTADO_SOLICITADA, "Aerolínea": "Iberia", "Nº billete": "1"},
    ]
    solicitador = SolicitadorFalso()
    p, _, _, hoja = montar([], {}, hoja=hoja, solicitador=solicitador)
    p.ejecutar("")
    assert solicitador.pedidos == []
    assert hoja.datos[PESTANA_BILLETES][0]["Estado"] == ESTADO_SOLICITADA_ATRASADA


# ---------- Bot 2: solicitud de facturas ----------

def test_billete_nuevo_de_iberia_se_pide_en_la_misma_pasada():
    solicitador = SolicitadorFalso()
    p, _, _, hoja = montar([correo("m1", "ET.pdf")], {"ET.pdf": doc()}, solicitador=solicitador)
    r = p.ejecutar("")
    assert r.facturas_solicitadas == 1
    pedido = solicitador.pedidos[0]
    assert (pedido.nombre, pedido.apellido, pedido.numero_billete) == ("DIEGO", "GARCIA", "075-2537889485")
    fila = hoja.datos[PESTANA_BILLETES][0]
    assert fila["Estado"] == ESTADO_SOLICITADA
    assert fila["Solicitud factura"].startswith("2026-10-26")


def test_air_europa_espera_48_horas_desde_la_emision():
    billete_ae = doc(aerolinea="Air Europa", localizador="9RU3AI", numeros_billete=["996 2426800452"],
                     fecha_emision="2026-10-25", fecha_vuelo="2026-10-30")
    solicitador = SolicitadorFalso()
    p, _, _, hoja = montar([correo("m1", "ae.pdf")], {"ae.pdf": billete_ae}, solicitador=solicitador)
    p.ejecutar("")
    assert solicitador.pedidos == []
    assert hoja.datos[PESTANA_BILLETES][0]["Estado"] == ESTADO_PENDIENTE

    p.hoy = date(2026, 10, 27)
    p.ejecutar("")
    assert solicitador.pedidos[0].localizador == "9RU3AI"
    assert hoja.datos[PESTANA_BILLETES][0]["Estado"] == ESTADO_SOLICITADA


def test_aerolinea_no_soportada_no_se_pide():
    solicitador = SolicitadorFalso()
    p, _, _, hoja = montar([correo("m1", "x.pdf")], {"x.pdf": doc(aerolinea="Vueling")}, solicitador=solicitador)
    p.ejecutar("")
    assert solicitador.pedidos == []
    assert hoja.datos[PESTANA_BILLETES][0]["Estado"] == ESTADO_PENDIENTE


def test_ya_facturado_queda_para_revisar_sin_reintentos():
    solicitador = SolicitadorFalso(Resultado.YA_FACTURADA)
    p, _, _, hoja = montar([correo("m1", "ET.pdf")], {"ET.pdf": doc()}, solicitador=solicitador)
    p.ejecutar("")
    p.ejecutar("")
    assert len(solicitador.pedidos) == 1
    assert hoja.datos[PESTANA_BILLETES][0]["Estado"] == ESTADO_YA_FACTURADO


@pytest.mark.parametrize("fallo", [Resultado.REVISAR, Resultado.TODAVIA_NO, RuntimeError("web caída")])
def test_fallos_se_reintentan_hasta_el_maximo_y_luego_a_mano(fallo):
    solicitador = SolicitadorFalso(fallo)
    p, _, _, hoja = montar([correo("m1", "ET.pdf")], {"ET.pdf": doc()}, solicitador=solicitador)
    for _ in range(MAX_INTENTOS + 2):
        p.ejecutar("")
    assert len(solicitador.pedidos) == MAX_INTENTOS
    fila = hoja.datos[PESTANA_BILLETES][0]
    assert fila["Estado"] == ESTADO_NO_SE_PUDO
    assert fila["Intentos"] == str(MAX_INTENTOS)


def test_factura_que_llega_marca_facturado_un_billete_solicitado():
    solicitador = SolicitadorFalso()
    p, _, _, hoja = montar([correo("m1", "billete.pdf")], {"billete.pdf": doc(), "factura.pdf": factura()},
                           solicitador=solicitador)
    p.ejecutar("")
    assert hoja.datos[PESTANA_BILLETES][0]["Estado"] == ESTADO_SOLICITADA
    p.buzon.correos = [correo("m2", "factura.pdf")]
    p.ejecutar("")
    assert hoja.datos[PESTANA_BILLETES][0]["Estado"] == ESTADO_FACTURADO
    assert len(solicitador.pedidos) == 1


@pytest.mark.parametrize("entrada,esperado", [
    ("B-12.345.678", "B12345678"), ("ES B12345678", "B12345678"), ("esb12345678", "B12345678"), (None, ""),
])
def test_normalizar_nif(entrada, esperado):
    assert normalizar_nif(entrada) == esperado
