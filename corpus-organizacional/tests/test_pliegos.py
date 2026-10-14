"""PDF en pliegos (dos paginas de libro por pagina del PDF) y texto de Word con cambios controlados.

Los PDF se generan con datos ficticios; ningun documento real entra al repositorio.
"""

import tempfile
import unittest
from pathlib import Path

from tests import ayuda  # noqa: F401

try:
    from reportlab.pdfgen import canvas
    import pymupdf  # noqa: F401
    DEPENDENCIAS = True
except ImportError:
    try:
        from reportlab.pdfgen import canvas
        import fitz  # noqa: F401
        DEPENDENCIAS = True
    except ImportError:
        DEPENDENCIAS = False

from corpus_org.conversion.extractores import extractor_para
from corpus_org.conversion.extractores.word import _crudo_docx_xml

ANCHO, ALTO = 936, 576


def _texto(d):
    return "\n".join(b.get("texto", "") for b in d.bloques if b["k"] != "tabla")


def _pliego(c, n):
    """Pagina apaisada: texto de la pagina izquierda (x=60) y de la derecha (x=540) a las mismas alturas."""
    c.setFont("Helvetica", 10)
    for k in range(6):
        c.drawString(60, 480 - 14 * k, f"Izquierda{n} linea{k} de un parrafo que sigue")
        c.drawString(540, 480 - 14 * k, f"Derecha{n} linea{k} de otro parrafo que sigue")
    c.drawString(60, 30, "Codigo MAN-001 pie de pagina")      # el pie solo esta en la pagina izquierda
    c.showPage()


@unittest.skipUnless(DEPENDENCIAS, "faltan reportlab o PyMuPDF")
class PliegosTest(unittest.TestCase):
    def _crear(self, ruta, pliegos):
        c = canvas.Canvas(str(ruta), pagesize=(468, ALTO))
        c.setFont("Helvetica-Bold", 20)
        c.drawString(100, 300, "PORTADA DEL FOLLETO")
        c.showPage()
        c.setPageSize((ANCHO, ALTO))
        for n in range(1, pliegos + 1):
            _pliego(c, n)
        c.save()

    def test_cada_mitad_se_lee_por_separado(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "folleto.pdf"
            self._crear(ruta, 4)
            d = extractor_para(ruta, False).extraer(ruta)
        t = _texto(d)
        self.assertEqual(d.paginas, 1 + 4 * 2)
        for n in range(1, 5):
            self.assertLess(t.index(f"Izquierda{n} linea5"), t.index(f"Derecha{n} linea0"))
        self.assertLess(t.index("Derecha1 linea5"), t.index("Izquierda2 linea0"))
        self.assertTrue(any("pliegos" in n for n in d.notas), d.notas)

    def test_documento_apaisado_sin_pliegos_no_se_parte(self):
        """Una pagina apaisada con un titulo que cruza el centro no es un pliego."""
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "ancho.pdf"
            c = canvas.Canvas(str(ruta), pagesize=(ANCHO, ALTO))
            for n in range(4):
                c.setFont("Helvetica", 14)
                c.drawString(200, 500, "Un titulo largo que cruza el centro de la pagina completa de lado a lado")
                c.drawString(60, 400, f"Texto de la pagina {n}")
                c.showPage()
            c.save()
            d = extractor_para(ruta, False).extraer(ruta)
        self.assertEqual(d.paginas, 4)


class WordCambiosControladosTest(unittest.TestCase):
    def test_marca_de_parrafo_borrado_no_oculta_el_texto_vivo(self):
        xml = ('<w:p><w:pPr><w:rPr><w:del w:id="1" w:author="x"/></w:rPr></w:pPr>'
               '<w:r><w:t>Comunicación al colaborador</w:t></w:r>'
               '<w:del w:id="2"><w:r><w:delText>texto borrado</w:delText></w:r></w:del>'
               '<w:r><w:t>sigue</w:t></w:r></w:p>').encode("utf-8")
        crudo = _crudo_docx_xml(xml)
        self.assertIn("colaborador", crudo)
        self.assertIn("sigue", crudo)
        self.assertNotIn("borrado", crudo)


if __name__ == "__main__":
    unittest.main()
