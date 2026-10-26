"""Preparación inicial, una sola vez, con la cuenta de Google de compras.

1. Abre el navegador para que Federico autorice la app (Gmail, Drive, Sheets).
2. Guarda el token en token.json (NO subirlo a GitHub; va a Secret Manager).
3. Crea en Drive la carpeta "LegalSky - Billetes y facturas" y la hoja de control.

Uso:  python scripts/preparar.py ruta/a/client_secret.json
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

from legalsky_bots.google_servicios import ALCANCES, CARPETA_MIME  # noqa: E402
from legalsky_bots.procesador import (  # noqa: E402
    COLUMNAS_BILLETES, COLUMNAS_FACTURAS, PESTANA_BILLETES, PESTANA_FACTURAS,
)


def main(client_secret: str) -> None:
    creds = InstalledAppFlow.from_client_secrets_file(client_secret, ALCANCES).run_local_server(port=0)
    Path("token.json").write_text(creds.to_json(), encoding="utf-8")

    drive = build("drive", "v3", credentials=creds)
    carpeta = drive.files().create(
        body={"name": "LegalSky - Billetes y facturas", "mimeType": CARPETA_MIME}, fields="id").execute()

    sheets = build("sheets", "v4", credentials=creds).spreadsheets()
    hoja = sheets.create(body={
        "properties": {"title": "LegalSky - Control de billetes y facturas", "locale": "es_ES"},
        "sheets": [{"properties": {"title": PESTANA_BILLETES}}, {"properties": {"title": PESTANA_FACTURAS}}],
    }, fields="spreadsheetId").execute()
    sheets.values().batchUpdate(spreadsheetId=hoja["spreadsheetId"], body={
        "valueInputOption": "RAW",
        "data": [
            {"range": f"'{PESTANA_BILLETES}'!A1", "values": [COLUMNAS_BILLETES]},
            {"range": f"'{PESTANA_FACTURAS}'!A1", "values": [COLUMNAS_FACTURAS]},
        ],
    }).execute()
    drive.files().update(fileId=hoja["spreadsheetId"], addParents=carpeta["id"], fields="id").execute()

    print("Listo. Copia estos valores en Secret Manager / .env:")
    print(f"  DRIVE_CARPETA_RAIZ_ID={carpeta['id']}")
    print(f"  HOJA_CONTROL_ID={hoja['spreadsheetId']}")
    print("  GOOGLE_TOKEN_JSON=<contenido de token.json>")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
