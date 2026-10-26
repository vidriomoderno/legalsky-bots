from datetime import date

from legalsky_bots.modelos import Respuesta, Resultado
from legalsky_bots.procesador import (
    ESTADO_NO_SE_PUDO, ESTADO_PENDIENTE, ESTADO_SOLICITADA, MAX_INTENTOS, PESTANA_BILLETES,
    anotar_respuesta, billetes_para_pedir,
)
from tests.test_procesador import HojaFalsa

HOY = date(2026, 10, 26)


def hoja_con(*filas):
    hoja = HojaFalsa()
    hoja.datos[PESTANA_BILLETES] = [dict(f) for f in filas]
    return hoja


IBERIA = {"Aerolínea": "Iberia", "Estado": ESTADO_PENDIENTE, "Nombre pasajero": "STEWART",
          "Apellido pasajero": "AGUDELO", "Nº billete": "075-2535525435", "Fecha emisión": "2026-10-26"}
AIR_EUROPA = {"Aerolínea": "Air Europa", "Estado": ESTADO_PENDIENTE, "Localizador": "9RU3AI",
              "Fecha vuelo": "2026-10-30", "Nº billete": "996 2426800452", "Fecha emisión": "2026-10-25"}


def test_pendientes_respeta_espera_de_air_europa_y_estado():
    hoja = hoja_con(IBERIA, AIR_EUROPA, {**IBERIA, "Estado": ESTADO_SOLICITADA})
    listos = billetes_para_pedir(hoja, HOY)
    assert [(f, b.aerolinea) for f, b in listos] == [(2, "Iberia")]
    assert [b.aerolinea for _, b in billetes_para_pedir(hoja, date(2026, 10, 27))] == ["Iberia", "Air Europa"]


def test_anotar_solicitada_y_reintentos_hasta_mano():
    hoja = hoja_con(IBERIA, AIR_EUROPA)
    assert anotar_respuesta(hoja, 2, Respuesta(Resultado.SOLICITADA, "en camino"), HOY) == ESTADO_SOLICITADA
    assert hoja.datos[PESTANA_BILLETES][0]["Solicitud factura"] == "2026-10-26: en camino"

    for _ in range(MAX_INTENTOS - 1):
        assert anotar_respuesta(hoja, 3, Respuesta(Resultado.TODAVIA_NO, "x"), HOY) == ""
    assert anotar_respuesta(hoja, 3, Respuesta(Resultado.REVISAR, "captcha"), HOY) == ESTADO_NO_SE_PUDO
    assert billetes_para_pedir(hoja, date(2026, 11, 1)) == []
