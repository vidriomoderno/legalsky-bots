"""Punto de entrada: una pasada de los bots 1, 2 y 3.

En Cloud Run corre como Job; Cloud Scheduler lo lanza cada 15 minutos, así que
cada billete nuevo que llega al Gmail tiene su factura pedida en menos de 15 min
(o en cuanto la aerolínea lo permita).
"""

import contextlib
import logging
import sys

from . import config
from .extractor import Extractor
from .google_servicios import AlmacenDrive, BuzonGmail, HojaSheets, credenciales
from .procesador import Procesador


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = config.cargar()
    creds = credenciales(cfg.google_token_json)

    with contextlib.ExitStack() as pila:
        solicitador = None
        if cfg.solicitar_facturas:
            from .solicitud_facturas import DatosFiscales, SolicitadorWeb

            solicitador = pila.enter_context(SolicitadorWeb(
                DatosFiscales(
                    razon_social=cfg.empresa_razon_social, cif=cfg.empresa_cif,
                    domicilio=cfg.empresa_domicilio, ciudad=cfg.empresa_ciudad,
                    codigo_postal=cfg.empresa_codigo_postal, provincia=cfg.empresa_provincia,
                    email=cfg.email_facturas,
                ),
                enviar=cfg.enviar_solicitudes,
            ))
        procesador = Procesador(
            buzon=BuzonGmail(creds),
            almacen=AlmacenDrive(creds, cfg.drive_carpeta_raiz_id),
            hoja=HojaSheets(creds, cfg.hoja_control_id),
            extractor=Extractor(),
            empresa_cif=cfg.empresa_cif,
            dias_alerta=cfg.dias_alerta_sin_factura,
            solicitador=solicitador,
        )
        resumen = procesador.ejecutar(cfg.gmail_busqueda)
    logging.info("Resumen: %s", resumen)
    return 1 if resumen.errores else 0


if __name__ == "__main__":
    sys.exit(main())
