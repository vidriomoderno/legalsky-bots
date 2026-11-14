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
    lista = type('Lista', (list,), {})()

    async def falso(metodo, **datos):
        lista.append((metodo, datos))
        if metodo == "getChat":
            return {"ok": True, "result": fijado.get("mensaje") and {"pinned_message": fijado["mensaje"]} or {}}
        return {"ok": True, "result": {"message_id": 77}}

    fijado = {}
    lista.fijado = fijado

    monkeypatch.setattr(tg, "telegram", falso)
    monkeypatch.setenv("USUARIOS_PERMITIDOS", "111, 222")
    monkeypatch.setenv("SERPAPI_KEY", "k")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://bot.onrender.com")
    tg._busquedas.clear()
    tg._redirecciones.clear()
    tg._aprobados.clear()
    tg._solicitudes_avisadas.clear()
    tg._lista.update(cargada=False, chat=None, mensaje=None)
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
    mensajes = [d for m, d in enviados if m == "sendMessage"]
    assert "999" in mensajes[0]["text"]
    aviso = mensajes[1]
    assert aviso["chat_id"] == 111 and "Ana (@ana_ls)" in aviso["text"] and "999" in aviso["text"]
    _correr({"message": {"from": persona, "chat": {"id": 5}, "text": "hola"}})
    assert sum(1 for m, d in enviados if m == "sendMessage" and d.get("chat_id") == 111) == 1  # solo se avisa una vez
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


def test_dar_acceso_con_el_boton_y_guardarlo_fijado(enviados):
    _correr({"message": {"from": {"id": 555, "first_name": "Fede"}, "chat": {"id": 555}, "text": "hola"}})
    aviso = next(d for m, d in enviados if m == "sendMessage" and d.get("chat_id") == 111)
    assert [b["callback_data"] for b in aviso["reply_markup"]["inline_keyboard"][0]] == ["ok|555", "no|555"]

    _correr(_boton(222, "ok|555"))  # 222 tiene acceso pero no es administrador
    assert enviados[-1][1]["text"] == "Solo el administrador."
    assert 555 not in tg.usuarios_permitidos()

    boton = _boton(111, "ok|555")
    boton["callback_query"]["message"]["text"] = aviso["text"]
    _correr(boton)
    assert 555 in tg.usuarios_permitidos()
    metodos = [m for m, d in enviados]
    assert "pinChatMessage" in metodos
    lista = next(d["text"] for m, d in enviados if d.get("text", "").startswith(tg.CABECERA_LISTA))
    assert "• Fede — id 555" in lista
    assert any(d.get("chat_id") == 555 and "Ya tienes acceso" in d["text"] for m, d in enviados)


def test_al_reiniciar_lee_la_lista_fijada(enviados):
    enviados.fijado["mensaje"] = {"message_id": 9, "text": tg.CABECERA_LISTA + "\n• Fede (@fede) — id 555"}
    _correr({"message": {"from": {"id": 555}, "chat": {"id": 555}, "text": "/vuelos"}})
    assert enviados[-1][1]["text"].startswith("Hola")
    assert tg._lista["mensaje"] == 9

    _correr(_boton(111, "qt|555"))
    assert 555 not in tg.usuarios_permitidos()
    assert any(m == "editMessageText" and d.get("message_id") == 9 and "nadie" in d["text"] for m, d in enviados)


def test_comando_dar_solo_para_el_administrador(enviados):
    _correr({"message": {"from": {"id": 222}, "chat": {"id": 222}, "text": "/dar 777 Intruso"}})
    assert 777 not in tg.usuarios_permitidos()
    _correr({"message": {"from": {"id": 111}, "chat": {"id": 111}, "text": "/dar 777 Fede Lopez"}})
    assert tg._aprobados[777] == "Fede Lopez"


def test_ignora_el_aviso_de_mensaje_fijado(enviados):
    _correr({"message": {"from": {"id": 9180987645, "is_bot": True, "first_name": "LegalSky Vuelos"},
                         "chat": {"id": 111}, "pinned_message": {"message_id": 77}}})
    assert not [d for m, d in enviados if m == "sendMessage"]


def test_el_mensaje_muestra_ciudades_y_tipo():
    from legalsky_bots.vuelos import Busqueda as B
    b = B("MAD", "T1", "internacional", datetime(2026, 11, 14, 17, 33, tzinfo=ZONA))
    v = Vuelo("Ryanair", "LON", datetime(2026, 11, 14, 20, 20, tzinfo=ZONA), 100)
    w = Vuelo("TAP", "OPO", datetime(2026, 11, 14, 21, 0, tzinfo=ZONA), 120, escalas=1, escalas_en="LIS")
    texto = tg.texto_resultado(b, [serp.Opcion(v, ""), serp.Opcion(w, "")])
    assert "🌍 INTERNACIONAL" in texto and "🇬🇧 Londres" in texto and "escala en 🇵🇹 Lisboa" in texto
    assert "LON" not in texto
