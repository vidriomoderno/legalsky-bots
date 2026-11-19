import base64

from scripts import pruebas_retraso as pr

# JPEG real de 2x1 píxeles.
JPEG_2x1 = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAx"
    "NDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
    "MjIyMjIyMjL/wAARCAABAAIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUF"
    "BAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVW"
    "V1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi"
    "4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAEC"
    "AxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVm"
    "Z2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq"
    "8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDi6KKK+ZP3E//Z")


def test_vuelo_a_buscar():
    directo = pr.vuelo_a_buscar("FR7958")
    assert directo == {"tramos": [{"aerolinea": "FR", "numero": "7958"}], "con_escala": False}
    assert pr.vuelo_a_buscar("W67022")["tramos"][0]["aerolinea"] == "W6"
    escala = pr.vuelo_a_buscar("IB1048-563")
    assert escala["con_escala"] and [t["numero"] for t in escala["tramos"]] == ["1048", "563"]
    assert [t["numero"] for t in pr.vuelo_a_buscar("UX198-7703")["tramos"]] == ["198", "7703"]
    assert pr.vuelo_a_buscar("AZ78")["tramos"][0]["numero"] == "78"
    for raro in ("CONEXIONES", "IB258/256", "", "1234"):
        assert pr.vuelo_a_buscar(raro) is None


def test_nombre_pdf():
    assert pr.nombre_pdf("FR7958", "2026-11-16", "ORK-BCN") == "FR7958_2026-11-16_ORK-BCN.pdf"
    assert pr.nombre_pdf("ib 1048/563", "2026-11-17", "scq-agp") == "IB1048563_2026-11-17_SCQ-AGP.pdf"


def test_crear_pdf(tmp_path):
    img = tmp_path / "c.jpg"
    img.write_bytes(JPEG_2x1)
    pdf = pr.crear_pdf([{"imagen": img, "titulo": "FR7958 - VUELO RETRASADO", "url": "https://x/y"}],
                       tmp_path / "x" / "p.pdf")
    datos = pdf.read_bytes()
    assert datos.startswith(b"%PDF") and b"/Width 2 /Height 1" in datos and datos.rstrip().endswith(b"%%EOF")
    assert b"/Count 1" in datos and b"(DOCUMENTO 3)" in datos and b"/MediaBox [0 0 595.28 841.89]" in datos
    assert b"/URI (https://x/y)" in datos and b"(https://x/y) Tj" in datos
    assert pr.medidas_jpeg(JPEG_2x1) == (2, 1)


def test_pdf_con_escala_como_la_asesora(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pr, "CARPETA_PDF", tmp_path)
    img = tmp_path / "c.jpg"
    img.write_bytes(JPEG_2x1)
    pr.main(["pdf", str(img), str(img), "--vuelo", "IB1048-563", "--fecha", "2026-11-17", "--ruta", "SCQ-AGP",
             "--url", "u1", "--url", "u2"])
    datos = (tmp_path / "IB1048-563_2026-11-17_SCQ-AGP.pdf").read_bytes()
    # Los dos tramos en la misma página, con los títulos de la asesora.
    assert b"/Count 1" in datos and b"(IB1048 - VUELO RETRASADO)" in datos
    assert "(IB563 - CONEXIÓN PERDIDA)".encode("cp1252") in datos and b"/URI (u2)" in datos
    assert pr.titulos_por_defecto("W67022", 1) == ["W67022 - VUELO RETRASADO"]
    import pytest
    with pytest.raises(SystemExit):
        pr.main(["pdf", str(img), str(img), "--vuelo", "X", "--fecha", "d", "--ruta", "r", "--url", "u1"])


def test_anotar_hechos_y_resumen(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pr, "TRABAJO", tmp_path)
    monkeypatch.setattr(pr, "REGISTRO", tmp_path / "r.json")
    pr.anotar("48571", "FR7958", "subida", "retraso 3 h 39 min")
    pr.anotar("1", "VY1", "revisar", "ruta distinta")
    pr.main(["hechos"])
    assert '["48571"]' in capsys.readouterr().out
    texto = pr.resumen()
    assert "subida: 1" in texto and "VY1: ruta distinta" in texto


def test_rehacer(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.setattr(pr, "REHACER", tmp_path / "rehacer.json")
    monkeypatch.setattr(pr, "REGISTRO", tmp_path / "reg.json")
    monkeypatch.setattr(pr, "TRABAJO", tmp_path)
    (tmp_path / "rehacer.json").write_text(_json.dumps([{"id": "1", "codigo": "IB1195"}, {"id": "2", "codigo": "W67022"}]), encoding="utf-8")
    assert [v["id"] for v in pr.por_rehacer()] == ["1", "2"]
    pr.anotar("1", "IB1195", "rehecha", "")
    assert [v["id"] for v in pr.por_rehacer()] == ["2"]
    assert pr.es_pdf_del_bot("ib1195_2026-11-17_mad-tls-1795092861.pdf", "IB1195")
    assert pr.es_pdf_del_bot("ib1048-563_2026-11-17_scq-agp-1795.pdf", "IB1048-563")
    assert not pr.es_pdf_del_bot("ib1195_2026-11-17_mad-tls-1795092861.pdf", "IB119")
    assert not pr.es_pdf_del_bot("Pantallazo IB1195.pdf", "IB1195")
