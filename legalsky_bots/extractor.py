"""Lee un PDF (billete o factura de aerolínea) con Claude y devuelve sus datos."""

import base64
import logging

import anthropic

from .modelos import DocumentoVuelo

log = logging.getLogger(__name__)

MODELO = "claude-opus-5-5"

INSTRUCCIONES = """Eres el asistente administrativo de una empresa española.
La empresa compra billetes de avión para que sus comerciales entren a las zonas
restringidas de los aeropuertos. Te pasan un PDF que llegó al correo de compras.

Clasifícalo:
- "billete": recibo de billete, confirmación de compra o itinerario. NO es una factura.
- "factura": factura fiscal emitida por la aerolínea (tiene número de factura y datos fiscales del cliente).
- "otro": condiciones de transporte, publicidad o cualquier otra cosa.

Formatos conocidos:
- Iberia, factura ("Factura de billete de transporte de pasaje"): el número de
  factura es el mismo número de billete (075-...). La base puede venir como
  "Base sujeta" y "Base no sujeta": base_imponible = Base sujeta.
- Air Europa, factura (número "SS/..."): el número de billete aparece en la
  segunda página como "Documento Asociado" o "Billete / Ticket"; puede llevar
  IVA al 10 % y al 21 %: iva = suma de las cuotas.

Extrae los campos tal como aparecen en el documento. No inventes: si un dato no
está, devuélvelo como null (o lista vacía). Fechas en AAAA-MM-DD; si el año no
aparece junto a la fecha del vuelo, tómalo de la fecha de emisión. Importes como
número con punto decimal."""


class Extractor:
    def __init__(self, cliente: anthropic.Anthropic | None = None):
        self._cliente = cliente or anthropic.Anthropic()

    def extraer(self, pdf: bytes, nombre_archivo: str) -> DocumentoVuelo | None:
        """Devuelve None si Claude no pudo procesar el documento (para revisión manual)."""
        respuesta = self._cliente.beta.messages.parse(
            model=MODELO,
            max_tokens=16000,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=INSTRUCCIONES,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": base64.standard_b64encode(pdf).decode("ascii"),
                            },
                        },
                        {"type": "text", "text": f"Archivo: {nombre_archivo}"},
                    ],
                }
            ],
            output_format=DocumentoVuelo,
        )
        if respuesta.stop_reason != "end_turn" or respuesta.parsed_output is None:
            log.warning("No se pudo extraer %s (stop_reason=%s)", nombre_archivo, respuesta.stop_reason)
            return None
        return respuesta.parsed_output
