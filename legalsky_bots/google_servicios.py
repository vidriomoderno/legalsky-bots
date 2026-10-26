"""Gmail, Drive y Sheets con la cuenta de Google de compras (OAuth de usuario).

Las tres APIs usan el mismo token: así todo (correos, PDF, hoja) queda en la
cuenta de Federico y no en una cuenta de servicio.
"""

import base64
import io
import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from .procesador import AdjuntoPdf, Correo

ALCANCES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

CARPETA_MIME = "application/vnd.google-apps.folder"


def credenciales(token_json: str) -> Credentials:
    creds = Credentials.from_authorized_user_info(json.loads(token_json), ALCANCES)
    if not creds.valid:
        creds.refresh(Request())
    return creds


def _columna(n: int) -> str:
    """1 -> A, 27 -> AA."""
    letras = ""
    while n:
        n, resto = divmod(n - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


class BuzonGmail:
    def __init__(self, creds: Credentials):
        self._api = build("gmail", "v1", credentials=creds, cache_discovery=False)
        self._etiquetas: dict[str, str] = {}

    def correos_pendientes(self, busqueda: str) -> list[Correo]:
        correos = []
        peticion = self._api.users().messages().list(userId="me", q=busqueda, maxResults=100)
        while peticion is not None:
            pagina = peticion.execute()
            for ref in pagina.get("messages", []):
                correos.append(self._leer(ref["id"]))
            peticion = self._api.users().messages().list_next(peticion, pagina)
        return correos

    def _leer(self, id_correo: str) -> Correo:
        mensaje = self._api.users().messages().get(userId="me", id=id_correo, format="full").execute()
        cabeceras = {c["name"].lower(): c["value"] for c in mensaje["payload"].get("headers", [])}
        adjuntos = []
        for parte in self._partes(mensaje["payload"]):
            nombre = parte.get("filename") or ""
            if not nombre.lower().endswith(".pdf"):
                continue
            cuerpo = parte.get("body", {})
            if "attachmentId" in cuerpo:
                cuerpo = self._api.users().messages().attachments().get(
                    userId="me", messageId=id_correo, id=cuerpo["attachmentId"]).execute()
            adjuntos.append(AdjuntoPdf(nombre=nombre, contenido=base64.urlsafe_b64decode(cuerpo["data"])))
        return Correo(id=id_correo, asunto=cabeceras.get("subject", ""), adjuntos=adjuntos)

    def _partes(self, parte: dict):
        yield parte
        for hija in parte.get("parts", []) or []:
            yield from self._partes(hija)

    def etiquetar(self, id_correo: str, etiqueta: str) -> None:
        self._api.users().messages().modify(
            userId="me", id=id_correo, body={"addLabelIds": [self._id_etiqueta(etiqueta)]}).execute()

    def _id_etiqueta(self, nombre: str) -> str:
        if not self._etiquetas:
            for e in self._api.users().labels().list(userId="me").execute().get("labels", []):
                self._etiquetas[e["name"]] = e["id"]
        if nombre not in self._etiquetas:
            nueva = self._api.users().labels().create(userId="me", body={"name": nombre}).execute()
            self._etiquetas[nombre] = nueva["id"]
        return self._etiquetas[nombre]


class AlmacenDrive:
    def __init__(self, creds: Credentials, carpeta_raiz_id: str):
        self._api = build("drive", "v3", credentials=creds, cache_discovery=False)
        self._raiz = carpeta_raiz_id
        self._cache: dict[tuple[str, str], str] = {}

    def _subcarpeta(self, padre: str, nombre: str) -> str:
        clave = (padre, nombre)
        if clave not in self._cache:
            nombre_q = nombre.replace("'", "\\'")
            encontradas = self._api.files().list(
                q=f"'{padre}' in parents and name = '{nombre_q}' and mimeType = '{CARPETA_MIME}' and trashed = false",
                fields="files(id)").execute().get("files", [])
            if encontradas:
                self._cache[clave] = encontradas[0]["id"]
            else:
                self._cache[clave] = self._api.files().create(
                    body={"name": nombre, "mimeType": CARPETA_MIME, "parents": [padre]}, fields="id").execute()["id"]
        return self._cache[clave]

    def guardar_pdf(self, ruta_carpetas: list[str], nombre: str, contenido: bytes) -> str:
        carpeta = self._raiz
        for nombre_carpeta in ruta_carpetas:
            carpeta = self._subcarpeta(carpeta, nombre_carpeta)
        archivo = self._api.files().create(
            body={"name": nombre, "parents": [carpeta]},
            media_body=MediaIoBaseUpload(io.BytesIO(contenido), mimetype="application/pdf"),
            fields="webViewLink").execute()
        return archivo["webViewLink"]


class HojaSheets:
    def __init__(self, creds: Credentials, hoja_id: str):
        self._api = build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()
        self._id = hoja_id

    def filas(self, pestana: str) -> list[dict[str, str]]:
        valores = self._api.values().get(spreadsheetId=self._id, range=f"'{pestana}'").execute().get("values", [])
        if not valores:
            return []
        cabecera, *datos = valores
        return [
            {"_fila": str(i), **{c: (fila[j] if j < len(fila) else "") for j, c in enumerate(cabecera)}}
            for i, fila in enumerate(datos, start=2)
        ]

    def agregar(self, pestana: str, columnas: list[str], valores: dict[str, str]) -> None:
        self._api.values().append(
            spreadsheetId=self._id, range=f"'{pestana}'!A1", valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS", body={"values": [[valores.get(c, "") for c in columnas]]}).execute()

    def actualizar(self, pestana: str, fila: int, columnas: list[str], valores: dict[str, str]) -> None:
        datos = [
            {"range": f"'{pestana}'!{_columna(columnas.index(c) + 1)}{fila}", "values": [[v]]}
            for c, v in valores.items()
        ]
        self._api.values().batchUpdate(
            spreadsheetId=self._id, body={"valueInputOption": "USER_ENTERED", "data": datos}).execute()
