from legalsky_bots import config


def test_cargar_env_lee_env_y_token_sin_pisar_variables(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("# comentario\nEMPRESA_CIF=B88315387\nHOJA_CONTROL_ID=desde_env\n", encoding="utf-8")
    (tmp_path / "token.json").write_text('{"token": "x"}', encoding="utf-8")
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    monkeypatch.setenv("HOJA_CONTROL_ID", "ya_puesta")
    monkeypatch.delenv("EMPRESA_CIF", raising=False)
    monkeypatch.delenv("GOOGLE_TOKEN_JSON", raising=False)

    config.cargar_env()

    import os
    assert os.environ["EMPRESA_CIF"] == "B88315387"
    assert os.environ["HOJA_CONTROL_ID"] == "ya_puesta"
    assert os.environ["GOOGLE_TOKEN_JSON"] == '{"token": "x"}'
