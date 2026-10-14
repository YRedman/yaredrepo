"""Cajas de una columna (banda de color con titulo y filas con borde fino) en PDF y tablas partidas entre paginas.

Los PDF se generan con datos ficticios; ningun documento real entra al repositorio.
"""

import tempfile
import unittest
from pathlib import Path

from tests import ayuda  # noqa: F401

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    import pymupdf  # noqa: F401
    DEPENDENCIAS = True
except ImportError:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        import fitz  # noqa: F401
        DEPENDENCIAS = True
    except ImportError:
        DEPENDENCIAS = False

from corpus_org.conversion.extractores import extractor_para

AZUL, CLARO = (0.584, 0.702, 0.843), (0.706, 0.776, 0.906)


def _banda(c, y_arriba, titulo, filas, x0=72, x1=561):
    """Dibuja una banda de color con el titulo y filas de texto separadas por una linea fina. Devuelve la y final."""
    c.setFillColorRGB(*AZUL)
    c.rect(x0, y_arriba - 29, x1 - x0, 29, stroke=0, fill=1)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString((x0 + x1) / 2, y_arriba - 19, titulo)
    y = y_arriba - 29
    for texto in filas:
        c.setFont("Helvetica", 10)
        c.drawString(x0 + 6, y - 12, texto)
        y -= 17
        c.setStrokeColorRGB(*CLARO)
        c.setLineWidth(1)
        c.line(x0, y, x1, y)
    return y


def _pdf(ruta, paginas):
    c = canvas.Canvas(str(ruta), pagesize=letter)
    for dibujar in paginas:
        dibujar(c)
        c.showPage()
    c.save()


def _extraer(ruta):
    d = extractor_para(ruta, False).extraer(ruta)
    return d, "\n".join("|".join(map(str, f)) if b["k"] == "tabla" else b.get("texto", "")
                        for b in d.bloques for f in (b["filas"] if b["k"] == "tabla" else [[]]))


@unittest.skipUnless(DEPENDENCIAS, "faltan reportlab o PyMuPDF")
class BandasTest(unittest.TestCase):
    def test_banda_con_filas_es_una_tabla_y_no_un_diagrama(self):
        def pagina(c):
            c.setFont("Helvetica", 10)
            c.drawString(72, 740, "Texto de apertura del documento.")
            y = _banda(c, 600, "Accesos a Sistemas", ["Licencia SAP", "Office 365"])
            y = _banda(c, y - 24, "Herramientas de Trabajo", ["Laptop", "Flota", "Tarjeta de Combustible"])
            _banda(c, y - 24, "Otra seccion", ["Una fila"])
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "bandas.pdf"
            _pdf(ruta, [pagina])
            d, _ = _extraer(ruta)
        tablas = [b["filas"] for b in d.bloques if b["k"] == "tabla"]
        self.assertIn([["Accesos a Sistemas"], ["Licencia SAP"], ["Office 365"]], tablas)
        self.assertIn([["Herramientas de Trabajo"], ["Laptop"], ["Flota"], ["Tarjeta de Combustible"]], tablas)
        self.assertFalse(any("diagrama vectorial" in a for a in d.avisos), d.avisos)

    def test_parrafo_bajo_una_banda_no_se_parte_en_filas(self):
        def pagina(c):
            c.setFillColorRGB(*AZUL)
            c.rect(72, 600, 489, 29, stroke=0, fill=1)
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(316, 610, "Titulo en banda")
            c.setFont("Helvetica", 10)
            for k, l in enumerate(["Primera linea de un parrafo que continua", "en la segunda linea del parrafo",
                                   "y termina en la tercera linea."]):
                c.drawString(78, 586 - 13 * k, l)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "parrafo.pdf"
            _pdf(ruta, [pagina])
            d, _ = _extraer(ruta)
        self.assertEqual([b for b in d.bloques if b["k"] == "tabla"], [])

    def test_titulo_en_negrita_entre_paginas_separa_las_tablas(self):
        """La tabla del final de la pagina 1 y la que abre la pagina 2 son distintas si entre ellas hay un titulo."""
        def pagina1(c):
            _banda(c, 600, "Herramientas de Trabajo", ["Laptop", "Flota"])
            c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(316, 60, "Caracteristicas Especiales del Puesto")

        def pagina2(c):
            _banda(c, 700, "Firma de Aprobacion", ["Director / Gerente del area:"])
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "partida.pdf"
            _pdf(ruta, [pagina1, pagina2])
            d, _ = _extraer(ruta)
        tablas = [b["filas"] for b in d.bloques if b["k"] == "tabla"]
        self.assertIn([["Herramientas de Trabajo"], ["Laptop"], ["Flota"]], tablas)
        self.assertIn([["Firma de Aprobacion"], ["Director / Gerente del area:"]], tablas)
        self.assertFalse(any("tabla partida" in a for a in d.avisos), d.avisos)


if __name__ == "__main__":
    unittest.main()
