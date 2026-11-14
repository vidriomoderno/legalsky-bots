from datetime import datetime, timedelta

import pytest

from legalsky_bots.vuelos import (
    ZONA, Busqueda, Vuelo, consultas, en_horario_ideal, mejores, sale_de_terminal, vuelo_desde_dict,
    dominio, enlace_de_aerolinea,
)

AHORA = datetime(2026, 11, 4, 10, 0, tzinfo=ZONA)


def busqueda(aeropuerto="MAD", terminal="TODAS", tipo="nacional"):
    return Busqueda(aeropuerto, terminal, tipo, AHORA)


def vuelo(horas, precio, aerolinea="Iberia", destino="BCN"):
    return Vuelo(aerolinea, destino, AHORA + timedelta(hours=horas), precio)


def test_nunca_un_vuelo_que_sale_en_menos_de_2h30():
    b = busqueda()
    lista = [vuelo(2.49, 10), vuelo(2.5, 50), vuelo(0, 5)]
    assert [v.precio for v in mejores(lista, b)] == [50]


def test_vuelo_ya_salido_o_a_mas_de_12_horas_no_entra():
    assert mejores([vuelo(-1, 5), vuelo(12.1, 5)], busqueda()) == []
    assert [v.precio for v in mejores([vuelo(12, 5)], busqueda())] == [5]


def test_manda_el_precio_aunque_este_fuera_del_horario_ideal():
    resultado = mejores([vuelo(10, 80), vuelo(3, 40)], busqueda())
    assert [v.precio for v in resultado] == [40, 80]


def test_a_igual_precio_gana_el_horario_ideal():
    resultado = mejores([vuelo(3, 40, destino="AGP"), vuelo(10, 40, destino="SVQ")], busqueda())
    assert [v.destino for v in resultado] == ["SVQ", "AGP"]


def test_maximo_5_opciones_y_sin_repetidos():
    destinos = ["BCN", "AGP", "SVQ", "PMI", "VLC", "BIO", "ALC", "LPA"]
    lista = [vuelo(3 + i, 30 + i, destino=d) for i, d in enumerate(destinos)] + [vuelo(3, 25, destino="BCN")]
    resultado = mejores(lista, busqueda())
    assert len(resultado) == 5
    assert resultado[0].precio == 25
    assert [v.destino for v in resultado].count("BCN") == 1


@pytest.mark.parametrize("aerolinea,aeropuerto,terminal,esperado", [
    ("Ryanair", "MAD", "T1", True), ("Ryanair", "MAD", "T4", False), ("Ryanair", "BCN", "T2", True),
    ("Vueling", "MAD", "T4", True), ("Vueling", "BCN", "T1", True), ("Vueling", "BCN", "T2", False),
    ("Iberia Express", "MAD", "T4", True), ("Iberojet", "MAD", "T4", False), ("Iberojet", "MAD", "T1", True),
    ("Air Europa", "MAD", "T1", True), ("Air Europa", "MAD", "T2", True), ("KLM", "MAD", "T2", True),
    ("easyJet", "BCN", "T2", True), ("Marca Rara", "MAD", "T1", False), ("Marca Rara", "MAD", "TODAS", True),
])
def test_terminal_por_aerolinea(aerolinea, aeropuerto, terminal, esperado):
    assert sale_de_terminal(aerolinea, aeropuerto, terminal) is esperado


def test_filtra_por_terminal_elegida():
    b = busqueda(terminal="T1")
    resultado = mejores([vuelo(5, 20, "Iberia"), vuelo(5, 60, "Ryanair")], b)
    assert [v.aerolinea for v in resultado] == ["Ryanair"]


def test_terminal_que_no_existe_en_ese_aeropuerto():
    with pytest.raises(ValueError):
        busqueda("BCN", "T4")


def test_consultas_cubren_los_dias_de_la_ventana():
    c = consultas(busqueda("BCN", tipo="internacional"))
    assert {x["dia"] for x in c} == {"2026-11-04"}
    assert "curr=EUR" in c[0]["url"] and "BCN" in c[0]["url"]

    noche = Busqueda("MAD", "T1", "nacional", AHORA.replace(hour=20))
    assert {x["dia"] for x in consultas(noche)} == {"2026-11-04", "2026-11-05"}


def test_horario_ideal_de_8_a_12_horas():
    b = busqueda()
    assert en_horario_ideal(vuelo(8, 1), b) and en_horario_ideal(vuelo(12, 1), b)
    assert not en_horario_ideal(vuelo(7.9, 1), b) and not en_horario_ideal(vuelo(12.1, 1), b)


def test_lee_hora_local_de_espana():
    v = vuelo_desde_dict({"aerolinea": "Vueling", "destino": "BCN", "salida": "2026-11-05T10:10", "precio": "136"})
    assert v.salida.tzinfo is ZONA and v.precio == 136


@pytest.mark.parametrize("url, esperado", [
    ("https://www.iberia.com/es/vuelos/?x=1", "https://www.iberia.com/es/vuelos/?x=1"),
    ("https://www.google.com/travel/clk?u=abc", ""),
    ("https://www.google.es/flights", ""),
    ("http://www.vueling.com/", ""),
    ("javascript:alert(1)", ""),
    ("", ""),
])
def test_solo_enlaces_web_fuera_de_google(url, esperado):
    assert enlace_de_aerolinea(url) == esperado


def test_dominio_sin_www():
    assert dominio("https://www.aireuropa.com/es/vuelos") == "aireuropa.com"


# ---------------------------------------------------------------- nacional / internacional por el primer vuelo
from legalsky_bots.vuelos import AEROLINEAS_POR_TERMINAL, TERMINALES, tipo_de_ruta_valido  # noqa: E402


@pytest.mark.parametrize("tipo, escalas_en, destino, esperado", [
    ("internacional", "", "LIS", True),
    ("internacional", "MAD", "LIS", False),       # Barcelona-Lisboa por Madrid: el primer vuelo es nacional
    ("internacional", "LIS", "CMN", True),
    ("internacional", "", "MAD", False),
    ("nacional", "", "PMI", True),
    ("nacional", "MAD", "LPA", True),
    ("nacional", "LIS", "PMI", False),            # sale de España para volver: no es nacional
    ("nacional", "", "LIS", False),
    ("internacional", "LIS", "PMI", False),       # acaba en España: confunde, no se muestra
])
def test_tipo_por_el_primer_vuelo(tipo, escalas_en, destino, esperado):
    assert tipo_de_ruta_valido(tipo, escalas_en, destino) is esperado


COMBINACIONES = [(a, t, tipo) for a in TERMINALES for t in TERMINALES[a] + ["TODAS"]
                 for tipo in ("nacional", "internacional")]


@pytest.mark.parametrize("aeropuerto, terminal, tipo", COMBINACIONES)
def test_ninguna_opcion_mezcla_nacional_e_internacional(aeropuerto, terminal, tipo):
    b = Busqueda(aeropuerto, terminal, tipo, AHORA)
    otro = "MAD" if aeropuerto == "BCN" else "BCN"
    terminal_real = terminal if terminal != "TODAS" else TERMINALES[aeropuerto][0]
    aerolinea = AEROLINEAS_POR_TERMINAL[(aeropuerto, terminal_real)].split("|")[0].strip()
    salida = AHORA + timedelta(hours=5)
    vuelos = [
        Vuelo(aerolinea, "PMI", salida, 10),                               # nacional directo
        Vuelo(aerolinea, "LIS", salida, 11),                               # internacional directo
        Vuelo(aerolinea, "LIS", salida, 12, escalas=1, escalas_en=otro),   # internacional con escala en España
        Vuelo(aerolinea, "PMI", salida, 13, escalas=1, escalas_en="LIS"),  # vuelve a España por fuera: nunca
        Vuelo(aerolinea, "CMN", salida, 14, escalas=1, escalas_en="LIS"),  # internacional con escala fuera
        Vuelo(aerolinea, "LPA", salida, 15, escalas=1, escalas_en=otro),   # nacional con escala en España
        Vuelo(aerolinea, "DUB", salida, 1, escalas=1),                     # escala desconocida: nunca
    ]
    destinos = sorted(v.destino for v in mejores(vuelos, b))
    # Internacional: solo directos. Nacional: directos o con escala dentro de España.
    assert destinos == (["LPA", "PMI"] if tipo == "nacional" else ["LIS"])


def test_todos_los_destinos_tienen_nombre_y_bandera_correcta():
    from legalsky_bots.vuelos import AEROPUERTOS_ESPANA, DESTINOS, NOMBRES, nombre_lugar
    for (aeropuerto, tipo), destinos in DESTINOS.items():
        for d in destinos:
            assert d in NOMBRES, d
            es_espana = nombre_lugar(d).startswith("🇪🇸")
            assert es_espana == (tipo == "nacional"), (aeropuerto, tipo, d)
    for codigo, (nombre, bandera) in NOMBRES.items():
        assert (bandera == "🇪🇸") == (codigo in AEROPUERTOS_ESPANA), codigo
