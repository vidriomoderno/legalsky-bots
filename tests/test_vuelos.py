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
    lista = [vuelo(3 + i, 30 + i, destino=f"D{i}") for i in range(8)] + [vuelo(3, 25, destino="D0")]
    resultado = mejores(lista, busqueda())
    assert len(resultado) == 5
    assert resultado[0].precio == 25
    assert [v.destino for v in resultado].count("D0") == 1


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
