"""Genera docs/Instrucciones_Fede.pdf: guía corta para usar pedir_facturas.bat.

    python docs/generar_instrucciones_pdf.py
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SALIDA = Path(__file__).with_name("Instrucciones_Fede.pdf")

AZUL = colors.HexColor("#1F4E79")
AZUL_CLARO = colors.HexColor("#E7F1FB")
VERDE_CLARO = colors.HexColor("#E5F4E4")
AMARILLO_CLARO = colors.HexColor("#FFF4D6")
ROJO_CLARO = colors.HexColor("#FBEBEB")
GRIS = colors.HexColor("#555555")

titulo = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=AZUL, alignment=TA_CENTER)
subtitulo = ParagraphStyle("subtitulo", fontName="Helvetica", fontSize=12, leading=16, textColor=GRIS, alignment=TA_CENTER)
h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=AZUL, spaceBefore=10, spaceAfter=6)
texto = ParagraphStyle("texto", fontName="Helvetica", fontSize=12, leading=16)
texto_negrita = ParagraphStyle("texto_negrita", parent=texto, fontName="Helvetica-Bold")
numero = ParagraphStyle("numero", fontName="Helvetica-Bold", fontSize=18, leading=20, textColor=colors.white, alignment=TA_CENTER)
pie = ParagraphStyle("pie", fontName="Helvetica", fontSize=9, leading=12, textColor=GRIS, alignment=TA_CENTER)

ANCHO = A4[0] - 36 * mm


def caja(contenido, fondo):
    t = Table([[contenido]], colWidths=[ANCHO])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fondo),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#BBBBBB")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


class Casilla(Flowable):
    """Cuadrado vacío para marcar con el dedo o un bolígrafo."""

    lado = 4.5 * mm

    def wrap(self, aw, ah):
        return self.lado, self.lado

    def draw(self):
        self.canv.setStrokeColor(AZUL)
        self.canv.setLineWidth(1.2)
        self.canv.rect(0, 0, self.lado, self.lado)


def lista_casillas(items, fondo):
    filas = [[Casilla(), Paragraph(i, texto)] for i in items]
    t = Table(filas, colWidths=[10 * mm, ANCHO - 10 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fondo),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (1, 0), (1, -1), 4),
    ]))
    return t


def pasos(items):
    filas = []
    for n, (principal, detalle) in enumerate(items, start=1):
        cuerpo = [Paragraph(principal, texto_negrita)]
        if detalle:
            cuerpo.append(Paragraph(detalle, texto))
        filas.append([Paragraph(str(n), numero), cuerpo])
    t = Table(filas, colWidths=[12 * mm, ANCHO - 12 * mm])
    estilo = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (1, 0), (1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#DDDDDD")),
    ]
    for i in range(len(items)):
        estilo.append(("BACKGROUND", (0, i), (0, i), AZUL))
    t.setStyle(TableStyle(estilo))
    return t


def tabla(cabecera, filas, fondo_cabecera=AZUL):
    datos = [[Paragraph(f"<font color='white'><b>{c}</b></font>", texto) for c in cabecera]]
    datos += [[Paragraph(c, texto) for c in fila] for fila in filas]
    t = Table(datos, colWidths=[ANCHO * 0.42, ANCHO * 0.58], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), fondo_cabecera),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F6F6")]),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def contenido():
    s = []
    s += [Paragraph("Bot de facturas LegalSky", titulo), Spacer(1, 4),
          Paragraph("Instrucciones para Fede", subtitulo), Spacer(1, 10)]
    s.append(caja(Paragraph(
        "<b>¿Qué hace?</b> Pide solo las facturas de los billetes de Iberia y Air Europa "
        "que llegan a <b>legalskybarcelona@gmail.com</b> y las apunta en la hoja de control. "
        "Tú solo haces <b>doble clic</b>.", texto), AZUL_CLARO))

    s.append(Paragraph("1. Lo que necesitas", h1))
    s.append(lista_casillas([
        "Una <b>cuenta de Claude</b> con plan <b>Pro o Max</b> (el plan gratis no sirve).",
        "Un <b>PC con Windows 10 u 11</b> y conexión a internet.",
        "<b>Google Chrome</b> instalado, con la sesión de <b>legalskybarcelona@gmail.com</b>.",
        "Tres archivos que te manda Juan Fernando: <b>pedir_facturas.bat</b>, <b>.env</b> y "
        "<b>token.json</b>. Los dos últimos son secretos: no los compartas.",
    ], VERDE_CLARO))
    s.append(Spacer(1, 4))
    s.append(caja(Paragraph(
        "<b>Lo demás lo instala el programa solo</b> la primera vez: Python, Claude Code, la carpeta "
        "«bot legal sky» en Documentos y un acceso directo en el Escritorio.", texto), AZUL_CLARO))

    s.append(KeepTogether([
        Paragraph("La primera vez", h1),
        pasos([
            ("Guarda los 3 archivos juntos en la misma carpeta.", "Por ejemplo, en Descargas."),
            ("Haz doble clic en «pedir_facturas.bat».", "Espera mientras instala. Tarda unos minutos."),
            ("Si se abre la página de Claude, entra con tu cuenta.", "Después vuelve a la ventana negra."),
            ("Si se abre la extensión «Claude in Chrome», pulsa «Añadir a Chrome».",
             "Entra con tu misma cuenta de Claude, vuelve a la ventana negra y pulsa una tecla."),
            ("Listo.", "Desde ahora usa el acceso directo <b>«Pedir facturas LegalSky»</b> del Escritorio."),
        ]),
    ]))

    s.append(KeepTogether([
        Paragraph("2. Antes de hacer doble clic (cada vez)", h1),
        lista_casillas([
            "<b>Google Chrome está abierto.</b>",
            "En ese Chrome está abierta la sesión de <b>legalskybarcelona@gmail.com</b>.",
            "La extensión <b>Claude in Chrome</b> está conectada.",
            "Hay <b>internet</b>.",
        ], AMARILLO_CLARO),
    ]))

    s.append(KeepTogether([
        Paragraph("3. Cómo usarlo (todas las veces)", h1),
        pasos([
            ("Abre Google Chrome.", ""),
            ("Doble clic en «Pedir facturas LegalSky» del Escritorio.",
             "Se abre una ventana negra. <b>No la cierres.</b>"),
            ("Espera.", "Chrome abre pestañas solo y rellena las páginas de Iberia y Air Europa. "
                        "<b>No toques esas pestañas.</b> Puede tardar unos minutos."),
            ("Lee el resumen.", "Al final la ventana negra dice cuántas facturas pidió."),
            ("Pulsa cualquier tecla.", "La ventana se cierra. ¡Listo!"),
        ]),
    ]))
    s.append(Spacer(1, 6))
    s.append(caja(Paragraph(
        "<b>¿Cada cuánto?</b> Cuando quieras. Lo normal: <b>una vez por semana</b>. "
        "Las facturas de Air Europa solo se pueden pedir 2 días después de comprar el billete; "
        "si aún no toca, el bot lo intenta la próxima vez.", texto), AZUL_CLARO))

    s.append(KeepTogether([
        Paragraph("4. Qué significa la hoja de control", h1),
        tabla(["Si dice…", "Quiere decir…"], [
            ["Factura pendiente", "El billete está apuntado. La factura se pedirá en el próximo doble clic."],
            ["Factura solicitada", "Ya se pidió. Llegará al Gmail en 1 a 3 días."],
            ["Facturado", "La factura ya llegó y está guardada. No hay que hacer nada."],
            ["Revisar: …", "El bot no pudo. Mira el motivo en la columna «Solicitud factura»."],
        ]),
    ]))

    s.append(KeepTogether([
        Paragraph("5. Si algo sale mal", h1),
        tabla(["Problema", "Qué hacer"], [
            ["Chrome no estaba abierto", "Abre Chrome y vuelve a hacer doble clic."],
            ["La extensión pregunta si permite iberia.com o aireuropa.com",
             "Pulsa <b>Permitir siempre</b>."],
            ["«No se pudo instalar…» o «No se pudo descargar…»",
             "Revisa internet y vuelve a hacer doble clic. Si sigue, llama a Juan Fernando."],
            ["«Faltan los archivos secretos»",
             "Pon .env y token.json junto al archivo y vuelve a hacer doble clic."],
            ["Un billete dice «Revisar: pedir la factura a mano»",
             "Pide esa factura tú en la web: iberia.com/es/facturas o aireuropa.com (Facturas). "
             "Los datos están en la hoja."],
        ], fondo_cabecera=colors.HexColor("#A33A3A")),
    ]))

    s.append(Spacer(1, 10))
    s.append(caja(Paragraph(
        "<b>Recuerda:</b> las facturas siempre van a nombre de la empresa en España "
        "(LegalSky Reclamaciones Aereas · CIF B88315387). Nunca pagues nada ni aceptes nada "
        "que te pida el bot por otro sitio.", texto), ROJO_CLARO))
    return s


def numerar(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(GRIS)
    canvas.drawCentredString(A4[0] / 2, 10 * mm, f"LegalSky · Bot de facturas · página {doc.page}")
    canvas.restoreState()


if __name__ == "__main__":
    doc = SimpleDocTemplate(str(SALIDA), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm,
                            title="Bot de facturas LegalSky - Instrucciones para Fede", author="LegalSky")
    doc.build(contenido(), onFirstPage=numerar, onLaterPages=numerar)
    print(SALIDA)
