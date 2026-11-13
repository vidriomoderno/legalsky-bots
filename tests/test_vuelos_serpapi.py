import pytest

pytest.importorskip("httpx")
pytest.importorskip("starlette")

from datetime import datetime

import httpx

from legalsky_bots import vuelos_serpapi as serp
from legalsky_bots.vuelos import ZONA, Busqueda

AHORA = datetime(2026, 11, 13, 10, 0, tzinfo=ZONA)


def _tramo(salida, desde, hasta, aerolinea, llegada="2026-11-13 20:00"):
    return {"departure_airport": {"id": desde, "time": salida}, "arrival_airport": {"id": hasta, "time": llegada},
            "airline": aerolinea}


RESPUESTA = {
    "best_flights": [
        {"flights": [_tramo("2026-11-13 19:00", "MAD", "PMI", "Iberia Express")], "price": 26, "booking_token": "A"},
    ],
    "other_flights": [
        {"flights": [_tramo("2026-11-13 18:00", "MAD", "LHR", "Iberia"), _tramo("x", "LHR", "DUB", "Aer Lingus")],
         "price": 90, "booking_token": "B"},
        {"flights": [_tramo("2026-11-13 11:00", "MAD", "BCN", "Vueling")], "price": 10, "booking_token": "C"},  # < 2h30
        {"flights": [_tramo("2026-11-13 17:00", "MAD", "BCN", "Ryanair")], "price": 5, "booking_token": "D"},  # T1
        {"flights": [_tramo("2026-11-13 16:00", "MAD", "LGW", "British Airways")], "price": 40, "booking_token": "E"},
        {"price": 1},  # sin tramos: se ignora
    ],
}


def test_destinos_de_ciudad_se_piden_por_aeropuerto():
    destinos = serp.aeropuertos_destino("MAD", "internacional").split(",")
    assert {"LHR", "LGW", "CDG", "FCO", "MXP"} <= set(destinos)
    assert "LON" not in destinos and "PAR" not in destinos


def test_lee_vuelos_y_aplica_las_reglas_de_terminal_y_horario():
    b = Busqueda("MAD", "T4", "nacional", AHORA)
    elegidas = serp.mejores_opciones(serp.opciones_desde_respuesta(RESPUESTA), b)
    assert [(o.vuelo.aerolinea, o.vuelo.destino, o.vuelo.precio) for o in elegidas] == [
        ("Iberia Express", "PMI", 26), ("British Airways", "LON", 40), ("Iberia", "DUB", 90)]
    assert elegidas[0].booking_token == "A" and elegidas[2].vuelo.escalas == 1
    assert elegidas[0].vuelo.salida == datetime(2026, 11, 13, 19, 0, tzinfo=ZONA)


def test_una_consulta_por_dia_con_todos_los_destinos():
    pedidas = []

    def responder(request):
        pedidas.append(dict(request.url.params))
        return httpx.Response(200, json=RESPUESTA)

    b = Busqueda("MAD", "TODAS", "nacional", datetime(2026, 11, 13, 20, 0, tzinfo=ZONA))  # ventana pasa a mañana
    serp.buscar(b, "clave", httpx.Client(transport=httpx.MockTransport(responder)))
    assert [p["outbound_date"] for p in pedidas] == ["2026-11-13", "2026-11-14"]
    assert pedidas[0]["type"] == "2" and pedidas[0]["currency"] == "EUR" and "," in pedidas[0]["arrival_id"]


def test_sin_resultados_no_es_error():
    def responder(request):
        return httpx.Response(200, json={"error": "Google Flights hasn't returned any results for this query."})

    b = Busqueda("MAD", "T4", "nacional", AHORA)
    assert serp.buscar(b, "clave", httpx.Client(transport=httpx.MockTransport(responder))) == []


def test_elige_la_opcion_de_la_aerolinea_y_no_la_agencia():
    datos = {"booking_options": [
        {"together": {"book_with": "eDreams", "booking_request": {"url": "https://www.google.com/x", "post_data": "a"}}},
        {"together": {"book_with": "Iberia Express", "booking_request": {"url": "https://www.google.com/y", "post_data": "b"}}},
    ]}
    assert serp.opcion_de_la_aerolinea(datos, "Iberia Express")["booking_request"]["post_data"] == "b"
    assert serp.opcion_de_la_aerolinea(datos, "Vueling") is None


def test_resuelve_la_redireccion_de_google_a_la_aerolinea():
    def responder(request):
        assert request.method == "POST" and request.content == b"u=1"
        return httpx.Response(302, headers={"location": "https://booking.iberiaexpress.com/?from=MAD&to=PMI"})

    c = httpx.Client(transport=httpx.MockTransport(responder))
    enlace = serp.resolver_enlace({"url": "https://www.google.com/travel/clk/f", "post_data": "u=1"}, c)
    assert enlace == "https://booking.iberiaexpress.com/?from=MAD&to=PMI"
