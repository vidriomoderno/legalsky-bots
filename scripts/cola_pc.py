"""Puente entre la hoja de control y la tarea programada del PC (bot 2 en navegador real).

    python scripts/cola_pc.py pendientes
        -> JSON con los billetes cuya factura hay que pedir hoy, y los datos fiscales.
    python scripts/cola_pc.py anotar FILA RESULTADO "DETALLE"
        RESULTADO: solicitada | ya_facturada | todavia_no | revisar
    python scripts/cola_pc.py resumen
        -> cuántos billetes hay en cada estado y cuántos se pueden pedir hoy.

Lee GOOGLE_TOKEN_JSON (o token.json) y HOJA_CONTROL_ID del entorno o del .env de la raíz.
"""

import json
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from legalsky_bots.config import cargar_env  # noqa: E402
from legalsky_bots.google_servicios import HojaSheets, credenciales  # noqa: E402
from legalsky_bots.modelos import Respuesta, Resultado  # noqa: E402
from legalsky_bots.procesador import PESTANA_BILLETES, anotar_respuesta, billetes_para_pedir  # noqa: E402

DATOS_FISCALES = {  # REGLA GENERAL: empresa en España.
    "razon_social": "EMPRESA_RAZON_SOCIAL",
    "cif": "EMPRESA_CIF",
    "domicilio": "EMPRESA_DOMICILIO",
    "ciudad": "EMPRESA_CIUDAD",
    "codigo_postal": "EMPRESA_CODIGO_POSTAL",
    "provincia": "EMPRESA_PROVINCIA",
    "email": "EMAIL_FACTURAS",
}


def _hoja() -> HojaSheets:
    faltan = [v for v in ("GOOGLE_TOKEN_JSON", "HOJA_CONTROL_ID") if not os.environ.get(v)]
    if faltan:
        sys.exit(f"Falta configuración: {', '.join(faltan)}. Crea .env y token.json "
                 "siguiendo el README (Puesta en marcha).")
    return HojaSheets(credenciales(os.environ["GOOGLE_TOKEN_JSON"]), os.environ["HOJA_CONTROL_ID"])


def pendientes() -> dict:
    lista = []
    for fila, b in billetes_para_pedir(_hoja(), date.today()):
        item = {"fila": fila, **b.__dict__}
        if "europa" in b.aerolinea.lower() and b.localizador and b.fecha_vuelo:
            # Air Europa admite entrar directo a la reserva y saltarse el calendario.
            item["url"] = f"https://www.aireuropa.com/es/es/mytrips/invoice/{b.localizador.upper()}/{b.fecha_vuelo}/passengers"
        else:
            item["url"] = "https://www.iberia.com/es/facturas/"
        lista.append(item)
    return {
        "datos_fiscales": {campo: os.environ.get(var, "") for campo, var in DATOS_FISCALES.items()},
        "billetes": lista,
    }


def resumen() -> dict:
    """Cuántos billetes hay en cada estado y cuántos se pueden pedir hoy."""
    hoja = _hoja()
    estados = Counter(f.get("Estado", "") or "(sin estado)" for f in hoja.filas(PESTANA_BILLETES))
    return {"por_estado": dict(estados.most_common()), "para_pedir_hoy": len(billetes_para_pedir(hoja, date.today()))}


def anotar(fila: int, resultado: str, detalle: str) -> str:
    estado = anotar_respuesta(_hoja(), fila, Respuesta(Resultado(resultado), detalle[:200]), date.today())
    return estado or "sin cambio de estado (se reintentará)"


def main(argv: list[str]) -> None:
    cargar_env()
    if argv[:1] == ["pendientes"]:
        print(json.dumps(pendientes(), ensure_ascii=False, indent=2))
    elif argv[:1] == ["resumen"]:
        print(json.dumps(resumen(), ensure_ascii=False, indent=2))
    elif len(argv) == 4 and argv[0] == "anotar":
        print(anotar(int(argv[1]), argv[2], argv[3]))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
