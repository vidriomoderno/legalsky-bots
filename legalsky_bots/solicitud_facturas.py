"""Bot 2: pide la factura en la web de la aerolínea (Iberia y Air Europa).

Usa un navegador automático (Playwright + Chromium). Cada aerolínea tiene su
"receta": los pasos del formulario tal como estaban en octubre de 2026. Si una
web cambia, la receta devuelve REVISAR con el motivo y el billete queda para
que lo pida una persona.

REGLA GENERAL: la factura se pide siempre a nombre de la empresa española
(razón social, CIF y domicilio fiscal en España).
"""

import logging
import re
from dataclasses import dataclass
from datetime import date

from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .modelos import Billete, Respuesta, Resultado, aerolinea_soportada

log = logging.getLogger(__name__)

IBERIA_URL = "https://www.iberia.com/es/facturas/"
AIR_EUROPA_URL = "https://www.aireuropa.com/es/es/mytrips/invoice"

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
MESES_CORTOS = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]


@dataclass(frozen=True)
class DatosFiscales:
    razon_social: str
    cif: str
    domicilio: str
    ciudad: str
    codigo_postal: str
    provincia: str
    email: str


class SolicitadorWeb:
    """Abre un navegador por ejecución y lo reutiliza para todos los billetes.

    En el PC de Fede se usa su Google Chrome instalado (canal "chrome"), visible, con una
    carpeta de perfil propia del bot para que recuerde que ya se rechazaron las cookies.
    """

    def __init__(self, datos: DatosFiscales, enviar: bool = True, headless: bool = True,
                 canal: str | None = None, perfil: str | None = None):
        self.datos = datos
        self.enviar = enviar  # False = rellena todo pero no pulsa el botón final
        self.headless = headless
        self.canal = canal
        self.perfil = perfil
        self._pw = None
        self._contexto = None

    def __enter__(self):
        self._pw = sync_playwright().start()
        opciones = dict(headless=self.headless, channel=self.canal, locale="es-ES", timezone_id="Europe/Madrid")
        if self.perfil:
            self._contexto = self._pw.chromium.launch_persistent_context(self.perfil, **opciones)
        else:
            navegador = self._pw.chromium.launch(headless=self.headless, channel=self.canal)
            self._contexto = navegador.new_context(locale="es-ES", timezone_id="Europe/Madrid")
        return self

    def __exit__(self, *_):
        if self._contexto:
            self._contexto.close()
        if self._pw:
            self._pw.stop()

    def solicitar(self, billete: Billete) -> Respuesta:
        receta = aerolinea_soportada(billete.aerolinea)
        if receta is None:
            return Respuesta(Resultado.REVISAR, f"Aerolínea no soportada: {billete.aerolinea}")
        pagina = self._contexto.new_page()
        pagina.set_default_timeout(20_000)
        try:
            if receta == "iberia":
                return self._iberia(pagina, billete)
            return self._air_europa(pagina, billete)
        except PlaywrightTimeout as e:
            return Respuesta(Resultado.REVISAR, f"La web no respondió como se esperaba: {e.message[:200]}")
        finally:
            pagina.close()

    # ---------- Iberia ----------

    def _iberia(self, p: Page, b: Billete) -> Respuesta:
        digitos = re.sub(r"\D", "", b.numero_billete)
        if not (digitos.startswith("075") and len(digitos) == 13):
            return Respuesta(Resultado.REVISAR, f"Número de billete Iberia no válido: {b.numero_billete}")
        if not (b.nombre and b.apellido):
            return Respuesta(Resultado.REVISAR, "Falta nombre o apellido del pasajero")

        if (bloqueo := _bloqueado(p.goto(IBERIA_URL))):
            return bloqueo
        _rechazar_cookies(p, ["Configuración de cookies"], ["Rechazarlas todas", "Rechazar todas"])
        # El campo de billete ya trae "075-" y una máscara: se escriben solo los 10 dígitos restantes.
        p.fill("#inv-tk-name", b.nombre)
        p.fill("#inv-tk-surname", b.apellido)
        p.click("#inv-tk-ticket")
        p.keyboard.press("End")
        p.keyboard.type(digitos[3:], delay=40)
        if re.sub(r"\D", "", p.input_value("#inv-tk-ticket")) != digitos:
            return Respuesta(Resultado.REVISAR, "No se pudo escribir el número de billete en el formulario")
        p.get_by_role("button", name="Continuar").click()

        p.wait_for_selector("#companyNameIR, .ibe_form__error, [class*=error]", state="visible")
        if not p.locator("#companyNameIR").is_visible():
            return Respuesta(Resultado.REVISAR, "Iberia no encontró el billete: " + _texto_error(p))

        if p.get_by_role("button", name="Solicitar un duplicado").is_visible():
            return Respuesta(Resultado.YA_FACTURADA, "Iberia ya emitió la factura (solo ofrece duplicado)")

        p.check("#juridicalPerson")
        _rellenar_si_vacio(p, "#mailIR", self.datos.email)
        _rellenar_si_vacio(p, "#companyNameIR", self.datos.razon_social[:30])
        _rellenar_si_vacio(p, "#CIFIR", self.datos.cif)
        _rellenar_si_vacio(p, "#addressIR", self.datos.domicilio[:30])
        _rellenar_si_vacio(p, "#cityIR", self.datos.ciudad[:30])
        _rellenar_si_vacio(p, "#postCodeIR", self.datos.codigo_postal)

        boton = p.locator("main button").filter(has_text=re.compile(r"solicitar", re.I)).first
        if not self.enviar:
            return Respuesta(Resultado.REVISAR, "Modo prueba: formulario de Iberia listo, no enviado")
        boton.click()
        p.get_by_text("Tu factura está en camino").wait_for()
        return Respuesta(Resultado.SOLICITADA, "Iberia: factura en camino al correo indicado")

    # ---------- Air Europa ----------

    def _air_europa(self, p: Page, b: Billete) -> Respuesta:
        if not (b.localizador and b.fecha_vuelo):
            return Respuesta(Resultado.REVISAR, "Falta localizador o fecha de vuelo")
        fecha = date.fromisoformat(b.fecha_vuelo)

        if (bloqueo := _bloqueado(p.goto(AIR_EUROPA_URL))):
            return bloqueo
        _rechazar_cookies(p, [], ["Rechazar todas"])
        # Ventana de país e idioma: la empresa es española.
        aplicar = p.get_by_role("button", name="Aplicar")
        if aplicar.is_visible(timeout=5_000):
            p.get_by_role("combobox").first.click()
            p.get_by_role("option", name="España").click()
            aplicar.click()

        p.fill("#locator", b.localizador.upper())
        p.click("#date")
        objetivo = f"{MESES_CORTOS[fecha.month - 1]} {fecha.year}"
        for _ in range(36):
            periodo = p.locator(".mat-calendar-period-button").inner_text().strip().upper()
            if periodo == objetivo:
                break
            actual = _periodo_a_fecha(periodo)
            boton = ".mat-calendar-previous-button" if actual > (fecha.year, fecha.month) else ".mat-calendar-next-button"
            p.click(boton)
        p.get_by_role("button", name=f"{fecha.day} {MESES[fecha.month - 1]} {fecha.year}").click()
        p.get_by_role("button", name="Buscar").click()

        dialogo = p.get_by_text(re.compile(r"inténtalo de nuevo|contacta directamente", re.I))
        try:
            p.wait_for_url(re.compile(r"/passengers"), timeout=15_000)
        except PlaywrightTimeout:
            if dialogo.is_visible():
                return Respuesta(
                    Resultado.TODAVIA_NO,
                    "Air Europa rechazó la búsqueda (aún no han pasado 48 h, ya está facturada o los datos no coinciden)",
                )
            raise
        if dialogo.is_visible(timeout=3_000):
            return Respuesta(Resultado.TODAVIA_NO, "Air Europa rechazó la búsqueda")

        # Pantalla de pasajeros y datos fiscales. Pendiente de verificar con una reserva nueva:
        # se rellena por etiquetas visibles en lugar de ids fijos.
        for casilla in p.get_by_role("checkbox").all():
            if casilla.is_visible() and not casilla.is_checked():
                casilla.check()
        _rellenar_por_etiqueta(p, r"raz[oó]n social|nombre de la empresa|empresa", self.datos.razon_social)
        _rellenar_por_etiqueta(p, r"\bnif\b|\bcif\b|documento fiscal", self.datos.cif)
        _rellenar_por_etiqueta(p, r"direcci[oó]n|domicilio", self.datos.domicilio)
        _rellenar_por_etiqueta(p, r"c[oó]digo postal", self.datos.codigo_postal)
        _rellenar_por_etiqueta(p, r"ciudad|localidad|poblaci[oó]n", self.datos.ciudad)
        _rellenar_por_etiqueta(p, r"provincia", self.datos.provincia)
        _rellenar_por_etiqueta(p, r"e-?mail|correo", self.datos.email)

        boton = p.get_by_role("button", name=re.compile(r"solicitar|enviar|confirmar", re.I)).last
        if not self.enviar:
            return Respuesta(Resultado.REVISAR, "Modo prueba: formulario de Air Europa listo, no enviado")
        boton.click()
        p.get_by_text(re.compile(r"solicitud|recibir[aá]", re.I)).first.wait_for()
        return Respuesta(Resultado.SOLICITADA, "Air Europa: solicitud enviada")


# ---------- utilidades ----------

def _bloqueado(respuesta) -> Respuesta | None:
    """Iberia y Air Europa devuelven 403 a los navegadores automáticos (protección antibots).
    No se intenta saltar esa protección: el billete queda para pedirlo a mano."""
    if respuesta is not None and respuesta.status == 403:
        return Respuesta(Resultado.REVISAR, "La web de la aerolínea bloquea navegadores automáticos (403)")
    return None

def _rechazar_cookies(p: Page, abrir: list[str], rechazar: list[str]) -> None:
    """Rechaza cookies no esenciales si aparece el aviso (nunca las acepta)."""
    for nombre in abrir:
        boton = p.get_by_role("button", name=nombre)
        if boton.is_visible(timeout=3_000):
            boton.click()
            break
    for nombre in rechazar:
        boton = p.get_by_role("button", name=nombre)
        if boton.is_visible(timeout=3_000):
            boton.click()
            return


def _rellenar_si_vacio(p: Page, selector: str, valor: str) -> None:
    campo = p.locator(selector)
    if campo.is_visible() and campo.is_editable() and not campo.input_value().strip():
        campo.fill(valor)


def _rellenar_por_etiqueta(p: Page, patron: str, valor: str) -> None:
    campo = p.get_by_label(re.compile(patron, re.I)).first
    try:
        if campo.is_visible(timeout=1_000) and campo.is_editable() and not campo.input_value().strip():
            campo.fill(valor)
    except PlaywrightTimeout:
        log.info("Campo no encontrado: %s", patron)


def _texto_error(p: Page) -> str:
    textos = p.locator(".ibe_form__error, [class*=error]").all_inner_texts()
    return " ".join(t.strip() for t in textos if t.strip())[:200] or "sin detalle"


def _periodo_a_fecha(periodo: str) -> tuple[int, int]:
    mes, anio = periodo.split()
    return int(anio), MESES_CORTOS.index(mes[:3]) + 1
