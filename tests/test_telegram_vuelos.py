import pytest

pytest.importorskip("httpx")
pytest.importorskip("starlette")

import asyncio
from datetime import datetime

from starlette.testclient import TestClient

from legalsky_bots import telegram_vuelos as tg
from legalsky_bots import vuelos_serpapi as serp
from legalsky_bots.vuelos import ZONA, Vuelo


@pytest.fixture
def enviados(monkeypatch):
    lista = []

    async def falso(metodo, **datos):
        lista.append((metodo, datos))
        return {"ok": True}

    monkeypatch.setattr(tg, "telegram", falso)
    monkeypatch.setenv("USUARIOS_PERMITIDOS", "111, 222")
    monkeypatch.setenv("SERPAPI_KEY", "k")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://bot.onrender.com")
    tg._busquedas.clear()
    tg._redirecciones.clear()
    return lista


def _boton(usuario, dato):
    return {"callback_query": {"id": "q", "from": {"id": usuario}, "data": dato,
                               "message": {"chat": {"id": 5}, "message_id": 9}}}


def _correr(aviso):
    asyncio.run(tg.atender(aviso))


def test_desconocido_recibe_su_numero_y_no_puede_buscar(enviados):
    tg._solicitudes_avisadas.clear()
    persona = {"id": 999, "first_name": "Ana", "username": "ana_ls"}
    _correr({"message": {"from": persona, "chat": {"id": 5}, "text": "/vuelos"}})
    assert "999" in enviados[0][1]["text"]
    aviso = enviados[1][1]
    assert aviso["chat_id"] == 111 and "Ana (@ana_ls)" in aviso["text"] and "999" in aviso["text"]
    _correr({"message": {"from": persona, "chat": {"id": 5}, "text": "hola"}})
    assert sum(1 for m, d in enviados if d.get("chat_id") == 111) == 1  # solo se avisa una vez
    _correr(_boton(999, "x|MAD|T4|nacional"))
    assert enviados[-1] == ("answerCallbackQuery", {"callback_query_id": "q", "text": "No tienes acceso."})


def test_flujo_completo_hasta_el_enlace(enviados, monkeypatch):
    vuelo = Vuelo("Iberia Express", "PMI", datetime(2026, 11, 13, 19, 0, tzinfo=ZONA), 26)
    monkeypatch.setattr(serp, "buscar", lambda b, clave: [serp.Opcion(vuelo, "TOKEN")])
    monkeypatch.setattr(serp, "enlace_aerolinea",
                        lambda b, o, clave: ("https://booking.iberiaexpress.com/?to=PMI", {"url": "u"}))

    _correr({"message": {"from": {"id": 111}, "chat": {"id": 5}, "text": "/vuelos"}})
    assert enviados[-1][1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "a|MAD"
    _correr(_boton(111, "a|MAD"))
    assert [b["text"] for b in enviados[-1][1]["reply_markup"]["inline_keyboard"][0]] == ["T1", "T2", "T4"]
    _correr(_boton(111, "t|MAD|T4"))
    _correr(_boton(111, "x|MAD|T4|nacional"))
    resultado = enviados[-1][1]
    assert "26 €" in resultado["text"] and "Iberia Express" in resultado["text"]
    dato = resultado["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert dato.startswith("e|")

    _correr(_boton(111, dato))
    boton = enviados[-1][1]["reply_markup"]["inline_keyboard"][0][0]
    assert boton == {"text": "Abrir en booking.iberiaexpress.com", "url": "https://booking.iberiaexpress.com/?to=PMI"}


def test_si_no_se_resuelve_el_enlace_usa_la_pagina_puente(enviados, monkeypatch):
    vuelo = Vuelo("Vueling", "BCN", datetime(2026, 11, 13, 19, 0, tzinfo=ZONA), 30)
    monkeypatch.setattr(serp, "buscar", lambda b, clave: [serp.Opcion(vuelo, "TOKEN")])
    peticion = {"url": "https://www.google.com/travel/clk/f", "post_data": "u=abc&x=1"}
    monkeypatch.setattr(serp, "enlace_aerolinea", lambda b, o, clave: ("", peticion))
    _correr(_boton(111, "x|MAD|T4|nacional"))
    _correr(_boton(111, enviados[-1][1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]))
    url = enviados[-1][1]["reply_markup"]["inline_keyboard"][0][0]["url"]
    assert url.startswith("https://bot.onrender.com/ir/")

    pagina = TestClient(tg.app).get("/ir/" + url.rsplit("/", 1)[1]).text
    assert 'action="https://www.google.com/travel/clk/f"' in pagina and 'name="u" value="abc"' in pagina


def test_busqueda_caducada(enviados):
    _correr(_boton(111, "e|noexiste|1"))
    assert "caducado" in enviados[-1][1]["text"]


def test_webhook_exige_el_secreto(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRETO", "s3cr3t")
    c = TestClient(tg.app)
    assert c.post("/telegram", json={}).status_code == 403
    assert c.post("/telegram", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": "malo"}).status_code == 403
    assert tg.secreto_telegram().isalnum() and tg.secreto_telegram() != "s3cr3t"
    monkeypatch.setattr(tg, "_atender_seguro", lambda aviso: None)
    ok = c.post("/telegram", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": tg.secreto_telegram()})
    assert ok.status_code == 200
    monkeypatch.setenv("WEBHOOK_SECRETO", "")
    assert c.post("/telegram", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": ""}).status_code == 403
