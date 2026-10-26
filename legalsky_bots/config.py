"""Configuración leída de variables de entorno (en Cloud Run vienen de Secret Manager).

REGLA GENERAL DEL PROYECTO: LegalSky es una empresa en ESPAÑA.
Facturas con CIF y domicilio fiscal españoles, IVA español, euros.
"""

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parents[1]


def cargar_env() -> None:
    """En un PC: lee el archivo .env de la carpeta del proyecto (sin pisar variables ya puestas)
    y, si no hay GOOGLE_TOKEN_JSON, usa token.json."""
    archivo = RAIZ / ".env"
    if archivo.exists():
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                clave, valor = linea.split("=", 1)
                os.environ.setdefault(clave.strip(), valor.strip())
    token = RAIZ / "token.json"
    if not os.environ.get("GOOGLE_TOKEN_JSON") and token.exists():
        os.environ["GOOGLE_TOKEN_JSON"] = token.read_text(encoding="utf-8")


@dataclass(frozen=True)
class Config:
    empresa_razon_social: str
    empresa_cif: str
    drive_carpeta_raiz_id: str
    hoja_control_id: str
    google_token_json: str
    gmail_busqueda: str
    dias_alerta_sin_factura: int
    empresa_domicilio: str
    empresa_ciudad: str
    empresa_codigo_postal: str
    empresa_provincia: str
    email_facturas: str
    solicitar_facturas: bool
    enviar_solicitudes: bool


def _obligatoria(nombre: str) -> str:
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        raise RuntimeError(f"Falta la variable de entorno {nombre}")
    return valor


# El bot solo lee correos recibidos a partir de esta fecha (00:00 hora de España).
FECHA_INICIO = "2026-10-15"


def busqueda_gmail(desde: str) -> str:
    """Búsqueda de Gmail con los correos con PDF aún no procesados desde `desde` (AAAA-MM-DD).
    Se usa un instante exacto (segundos) porque "after:AAAA/MM/DD" de Gmail va en hora del Pacífico."""
    inicio = datetime.fromisoformat(desde).replace(tzinfo=ZoneInfo("Europe/Madrid"))
    return ("has:attachment filename:pdf -label:LegalSky/Procesado -label:LegalSky/Revisar "
            f"after:{int(inicio.timestamp())}")


def cargar() -> Config:
    cargar_env()
    return Config(
        empresa_razon_social=_obligatoria("EMPRESA_RAZON_SOCIAL"),
        empresa_cif=_obligatoria("EMPRESA_CIF"),
        drive_carpeta_raiz_id=_obligatoria("DRIVE_CARPETA_RAIZ_ID"),
        hoja_control_id=_obligatoria("HOJA_CONTROL_ID"),
        google_token_json=_obligatoria("GOOGLE_TOKEN_JSON"),
        gmail_busqueda=os.environ.get("GMAIL_BUSQUEDA") or busqueda_gmail(os.environ.get("GMAIL_DESDE", FECHA_INICIO)),
        dias_alerta_sin_factura=int(os.environ.get("DIAS_ALERTA_SIN_FACTURA", "7")),
        empresa_domicilio=os.environ.get("EMPRESA_DOMICILIO", "Plaza Mayor Ciudad Pegaso 11"),
        empresa_ciudad=os.environ.get("EMPRESA_CIUDAD", "Madrid"),
        empresa_codigo_postal=os.environ.get("EMPRESA_CODIGO_POSTAL", "28022"),
        empresa_provincia=os.environ.get("EMPRESA_PROVINCIA", "Madrid"),
        email_facturas=os.environ.get("EMAIL_FACTURAS", "legalskybarcelona@gmail.com"),
        # Apagado por defecto: Iberia y Air Europa bloquean (403) los navegadores automáticos
        # desde servidores. Ver README, "Bot 2".
        solicitar_facturas=_si_no("SOLICITAR_FACTURAS", False),
        # False = el bot rellena los formularios pero no pulsa el botón final (para probar).
        enviar_solicitudes=_si_no("ENVIAR_SOLICITUDES", True),
    )


def _si_no(nombre: str, por_defecto: bool) -> bool:
    valor = os.environ.get(nombre, "").strip().lower()
    return por_defecto if not valor else valor in ("1", "si", "sí", "true", "yes")
