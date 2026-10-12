"""Descriptivo PDF sintetico con la maquetacion de las plantillas reales de descriptivo de puesto.

Reproduce la estructura (no los datos) de los formatos que se usan en produccion:
- Tabla de encabezado con el titulo y las etiquetas sobre sus valores ("Código:" / "DP-FOR-001",
  "Vigencia:" o "Vigente a partir de:" / fecha, "Página:" / "1 de 2").
- Titulo numerado "1. <Puesto>." y "Función General/Objetivo del Puesto:".
- Objetivo en letra mas grande partido en renglones (uno termina en "a través de").
- Organigrama de dos cajas dibujadas a la izquierda del objetivo.
- Tabla "FUNCIONES ESPECÍFICAS | EVIDENCIA..." con celdas de varios renglones y bordes reales.
- Tabla "Áreas de Relacionamiento" (Área de Interacción | Tipo de Relación).
- Requisitos y firmas en la segunda pagina.

Requiere reportlab. Uso directo: python tests/fixtures_plantilla.py <archivo.pdf>
"""
import sys

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

ALTO = letter[1]
PUESTO = "Analista de Pruebas"
JEFE = "Coordinador de Pruebas"
SUBORDINADO = "Técnico de Pruebas"
OBJETIVO = ("Verificar la calidad de los productos de la empresa a través de",
            "la aplicación de pruebas de aceptación según los procedimientos",
            "establecidos por la organización.")
FUNCIONES = [
    (("Definir el plan de pruebas de cada entrega con base", "en los criterios establecidos."),
     ("• Plan de pruebas aprobado.",)),
    (("Ejecutar los casos de prueba de las diferentes líneas", "de producto y registrar los resultados",
      "en los formularios establecidos."),
     ("• Casos ejecutados.", "• Registro de resultados.")),
    (("Elaborar el informe mensual de hallazgos con", "gráficos de tendencia."),
     ("• Informe mensual de", "hallazgos.")),
]
RELACIONES = [("Gerente de Calidad Regional", "Subordinación Indirecta"),
              (JEFE, "Subordinación directa"),
              (SUBORDINADO, "Reporte Directo"),
              ("Gerentes de Producto", "Equipo Interdisciplinario")]


def _texto(c, x, top, texto, tam=11, negrita=False):
    c.setFont("Helvetica-Bold" if negrita else "Helvetica", tam)
    c.drawString(x, ALTO - top - tam, texto)


def _rect(c, x0, top0, x1, top1):
    c.rect(x0, ALTO - top1, x1 - x0, top1 - top0, stroke=1, fill=0)


def _tabla(c, xs, top, filas, tam=10, interlineado=14, negrita_primera=False):
    """Tabla con bordes completos; cada celda es una tupla de renglones. Devuelve el borde inferior."""
    c.setLineWidth(0.6)
    bordes = [top]
    for i, fila in enumerate(filas):
        alto = max(len(celda) for celda in fila) * interlineado + 6
        for j, celda in enumerate(fila):
            for k, renglon in enumerate(celda):
                _texto(c, xs[j] + 5, bordes[-1] + 4 + k * interlineado, renglon, tam, negrita_primera and i == 0)
        bordes.append(bordes[-1] + alto)
    for y in bordes:
        c.line(xs[0], ALTO - y, xs[-1], ALTO - y)
    for x in xs:
        c.line(x, ALTO - bordes[0], x, ALTO - bordes[-1])
    return bordes[-1]


def _encabezado(c, pagina, total, etiqueta_vigencia):
    """Tabla de encabezado: titulo a la izquierda y cada etiqueta sobre su valor en su propia celda.

    Con "Vigente a partir de:" usa la segunda variante de la plantilla (tres columnas de celdas con
    "Próxima revisión" y "Sustituye a" junto a la vigencia).
    """
    c.setLineWidth(0.6)
    if etiqueta_vigencia == "Vigencia:":
        cols, tam = (135, 433, 504, 573), 11
        celdas = ((0, "Código:", "DP-FOR-001"), (1, "Versión:", "04"),
                  (0, etiqueta_vigencia, "15/03/2024"), (1, "Página:", f"{pagina} de {total}"))
    else:
        cols, tam = (95, 300, 420, 505, 590), 9
        celdas = ((0, "Código:", "DP-FOR-001"), (1, "Versión:", "04"), (2, "Página:", f"{pagina} de {total}"),
                  (0, etiqueta_vigencia, "15/03/2024"), (1, "Próxima revisión:", "N/A"),
                  (2, "Sustituye a:", "Versión 03"))
    _rect(c, 40, 35, cols[-1], 107)
    for x in cols[1:-1]:
        c.line(x, ALTO - 35, x, ALTO - 107)
    c.line(cols[1], ALTO - 71, cols[-1], ALTO - 71)
    _texto(c, cols[0] + 5, 43, "Descripción de Puesto y", 16, True)
    _texto(c, cols[0] + 5, 68, "Perfil por Competencias", 16, True)
    ncel = len(cols) - 2
    for k, (j, etiqueta, valor) in enumerate(celdas):
        top = 40 if k < ncel else 76
        _texto(c, cols[1 + j] + 5, top, etiqueta, tam, True)
        _texto(c, cols[1 + j] + 5, top + tam + 3, valor, tam)


def generar(path, etiqueta_vigencia="Vigencia:"):
    c = canvas.Canvas(str(path), pagesize=letter)
    _encabezado(c, 1, 2, etiqueta_vigencia)
    _texto(c, 72, 148, f"1. {PUESTO}.", 11, True)
    _texto(c, 72, 169, "Función General/Objetivo del Puesto:", 11, True)
    for k, renglon in enumerate(OBJETIVO):
        _texto(c, 167, 189 + k * 15, renglon, 12)
    # organigrama: dos cajas dibujadas, una sobre otra, a la izquierda del objetivo
    c.setLineWidth(0.8)
    for top, renglones in ((188, ("Coordinador de", "Pruebas")), (234, ("Analista de", "Pruebas"))):
        _rect(c, 80, top, 152, top + 30)
        for k, renglon in enumerate(renglones):
            _texto(c, 88, top + 4 + k * 10, renglon, 9, True)
    c.line(116, ALTO - 218, 116, ALTO - 234)
    fondo = _tabla(c, (72, 337, 554), 280,
                   [(("FUNCIONES ESPECÍFICAS",), ("EVIDENCIA DE CUMPLIMENTO / ENTREGABLES",))] + FUNCIONES,
                   negrita_primera=True)
    _texto(c, 72, fondo + 20, "Áreas de Relacionamiento:", 11, True)
    _tabla(c, (72, 278, 554), fondo + 40, [(("Área de Interacción",), ("Tipo de Relación",))]
           + [((a,), (t,)) for a, t in RELACIONES], negrita_primera=True)
    c.showPage()
    _encabezado(c, 2, 2, etiqueta_vigencia)
    fondo = _tabla(c, (72, 250, 554), 130,
                   [(("Requisitos del Puesto",), ("",)),
                    (("Nivel de Educación Formal",), ("Título universitario en ingeniería o carreras afines.",)),
                    (("Experiencia",), ("Dos años en puestos similares.",))], negrita_primera=True)
    _texto(c, 72, fondo + 40, "Firma de Aprobación", 11, True)
    _texto(c, 72, fondo + 60, "Nombre: ____________________   Fecha: ____________", 10)
    _texto(c, 72, fondo + 90, "Firma del Colaborador", 11, True)
    _texto(c, 72, fondo + 110, "Nombre: ____________________   Fecha: ____________", 10)
    c.showPage()
    c.save()
    return path


if __name__ == "__main__":
    generar(sys.argv[1])
