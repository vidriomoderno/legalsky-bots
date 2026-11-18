from PIL import Image

from scripts import pruebas_retraso as pr


def test_vuelo_a_buscar():
    assert pr.vuelo_a_buscar("FR7958") == {"aerolinea": "FR", "numero": "7958", "con_escala": False, "tramos": 1}
    assert pr.vuelo_a_buscar("W67022")["aerolinea"] == "W6"
    assert pr.vuelo_a_buscar("IB1048-563") == {"aerolinea": "IB", "numero": "563", "con_escala": True, "tramos": 2}
    assert pr.vuelo_a_buscar("UX198-7703")["numero"] == "7703"
    assert pr.vuelo_a_buscar("AZ78")["numero"] == "78"
    for raro in ("CONEXIONES", "IB258/256", "", "1234"):
        assert pr.vuelo_a_buscar(raro) is None


def test_nombre_pdf():
    assert pr.nombre_pdf("FR7958", "2026-11-16", "ORK-BCN") == "FR7958_2026-11-16_ORK-BCN.pdf"
    assert pr.nombre_pdf("ib 1048/563", "2026-11-17", "scq-agp") == "IB1048563_2026-11-17_SCQ-AGP.pdf"


def test_crear_pdf(tmp_path):
    img = tmp_path / "c.png"
    Image.new("RGB", (300, 200), "navy").save(img)
    pdf = pr.crear_pdf(img, tmp_path / "x" / "p.pdf", ["Vuelo FR7958", "Fuente: FlightStats"])
    assert pdf.read_bytes().startswith(b"%PDF")


def test_anotar_hechos_y_resumen(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pr, "TRABAJO", tmp_path)
    monkeypatch.setattr(pr, "REGISTRO", tmp_path / "r.json")
    pr.anotar("48571", "FR7958", "subida", "retraso 3 h 39 min")
    pr.anotar("1", "VY1", "revisar", "ruta distinta")
    pr.main(["hechos"])
    assert '["48571"]' in capsys.readouterr().out
    texto = pr.resumen()
    assert "subida: 1" in texto and "VY1: ruta distinta" in texto
