"""Datos que Claude extrae de cada PDF, y tipos compartidos entre los bots."""

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Resultado(str, Enum):
    SOLICITADA = "solicitada"
    YA_FACTURADA = "ya_facturada"
    TODAVIA_NO = "todavia_no"  # la aerolínea aún no deja pedirla (p. ej. < 48 h)
    REVISAR = "revisar"


@dataclass(frozen=True)
class Billete:
    aerolinea: str
    nombre: str
    apellido: str
    numero_billete: str
    localizador: str
    fecha_vuelo: str  # AAAA-MM-DD


@dataclass(frozen=True)
class Respuesta:
    resultado: Resultado
    detalle: str = ""


def aerolinea_soportada(aerolinea: str) -> str | None:
    texto = (aerolinea or "").lower().replace(" ", "")
    if "iberia" in texto:
        return "iberia"
    if "aireuropa" in texto:
        return "aireuropa"
    return None


class DocumentoVuelo(BaseModel):
    tipo: Literal["billete", "factura", "otro"] = Field(
        description="billete = recibo/confirmación de compra; factura = factura fiscal; otro = cualquier otra cosa"
    )
    aerolinea: str | None = Field(description="Nombre comercial, p. ej. 'Iberia', 'Air Europa'")
    localizador: str | None = Field(description="Código de reserva, sin prefijo de aerolínea (p. ej. '7PGSYM')")
    numeros_billete: list[str] = Field(description="Números de billete tal como aparecen, p. ej. '075-2537889485'")
    pasajero: str | None = Field(description="Nombre del pasajero tal como aparece")
    pasajero_nombre: str | None = Field(
        description="Solo el nombre de pila tal como aparece en el billete (Iberia 'APELLIDO/NOMBRE' -> NOMBRE)")
    pasajero_apellido: str | None = Field(
        description="Solo el primer apellido tal como aparece en el billete (Iberia 'APELLIDO/NOMBRE' -> APELLIDO)")
    vuelo: str | None = Field(description="Número de vuelo, p. ej. 'IB0643'")
    origen: str | None = Field(description="Ciudad o código IATA de origen")
    destino: str | None = Field(description="Ciudad o código IATA de destino")
    fecha_vuelo: str | None = Field(description="Fecha del vuelo en formato AAAA-MM-DD")
    fecha_emision: str | None = Field(description="Fecha de emisión del billete o de la factura, AAAA-MM-DD")
    importe_total: float | None = Field(description="Importe total pagado")
    moneda: str | None = Field(description="Código ISO, p. ej. 'EUR'")
    numero_factura: str | None = Field(description="Solo facturas: número de factura")
    nif_cliente: str | None = Field(description="Solo facturas: NIF/CIF del cliente al que va dirigida")
    razon_social_cliente: str | None = Field(description="Solo facturas: nombre o razón social del cliente")
    base_imponible: float | None = Field(description="Solo facturas: base imponible")
    iva: float | None = Field(description="Solo facturas: cuota de IVA")
    confianza: Literal["alta", "media", "baja"] = Field(
        description="baja si el documento es ilegible, ambiguo o faltan datos clave"
    )
    notas: str | None = Field(description="Algo que una persona deba revisar; null si nada")
