"""Texto dentro de imagenes de paginas digitales (graficos, organigramas como imagen) y mejora de la lectura OCR.

Las imagenes se generan con texto ficticio; ningun documento real entra al repositorio.
"""

import io
import tempfile
import unittest
from pathlib import Path

from tests import ayuda  # noqa: F401

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    import pymupdf  # noqa: F401
    from corpus_org.conversion.extractores import extractor_para
    from corpus_org.conversion.extractores import ocr_pagina as O
    from corpus_org.conversion.extractores.ocr import idioma_ocr
    DEPENDENCIAS = True
except ImportError:
    DEPENDENCIAS = False

OCR = DEPENDENCIAS and idioma_ocr() is not None
FUENTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _imagen_con_texto(lineas, tam=(1200, 700), px=44):
    img = Image.new("L", tam, 255)
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype(FUENTE, px)
    except OSError:
        f = ImageFont.load_default()
    for k, t in enumerate(lineas):
        d.text((60, 60 + 80 * k), t, fill=0, font=f)
    return img


def _pdf_con_imagen(ruta, img):
    c = canvas.Canvas(str(ruta))
    c.setFont("Helvetica", 11)
    c.drawString(72, 760, "Texto digital de la pagina que acompana al grafico.")
    b = io.BytesIO()
    img.convert("RGB").save(b, "PNG")
    b.seek(0)
    c.drawImage(ImageReader(b), 72, 250, width=450, height=263)
    c.showPage()
    c.save()


@unittest.skipUnless(OCR, "faltan Tesseract (spa), pytesseract, Pillow o numpy")
class TextoEnImagenTest(unittest.TestCase):
    def test_el_texto_de_una_imagen_grande_se_lee_con_ocr(self):
        img = _imagen_con_texto(["Gerencia de Operaciones", "Coordinador de Almacen", "Analista de Inventarios",
                                 "Supervisor de Despacho"])
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "grafico.pdf"
            _pdf_con_imagen(ruta, img)
            d = extractor_para(ruta, False).extraer(ruta)
        textos = " ".join(b.get("texto", "") for b in d.bloques)
        self.assertIn("Coordinador de Almacen", textos)
        self.assertTrue(any("texto leído de la imagen con OCR" in b.get("texto", "") for b in d.bloques), textos)
        self.assertFalse(d.avisos, d.avisos)

    def test_una_imagen_sin_texto_queda_como_imagen(self):
        img = Image.new("L", (800, 500), 140)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "foto.pdf"
            _pdf_con_imagen(ruta, img)
            d = extractor_para(ruta, False).extraer(ruta)
        marcas = [b["texto"] for b in d.bloques if b["k"] == "marca"]
        self.assertEqual(marcas, ["[DIAGRAMA O IMAGEN: ver página 1 del documento original]"])


@unittest.skipUnless(OCR, "faltan Tesseract (spa), pytesseract, Pillow o numpy")
class MejoraDeLecturaTest(unittest.TestCase):
    def test_una_pagina_con_sombra_se_relee_hasta_pasar_del_80(self):
        """Con una sombra lateral la lectura normal solo saca unas palabras; con mas contraste y nitidez se recupera."""
        import pymupdf
        base = Image.new("L", (1700, 2200), 255)
        dibujo = ImageDraw.Draw(base)
        try:
            fuente = ImageFont.truetype(FUENTE, 30)
        except OSError:
            fuente = ImageFont.load_default()
        frases = ["Procedimiento de compras de bienes y servicios", "El area de compras recibe la solicitud aprobada y",
                  "emite la orden de compra al proveedor seleccionado", "segun la politica vigente de la organizacion."]
        for k, t in enumerate(frases * 5):
            dibujo.text((120, 200 + 62 * k), t, fill=0, font=fuente)
        sombra = np.asarray(base).astype(float) * np.linspace(0.25, 1.0, 1700)[None, :] * 0.8 + 20
        img = Image.fromarray(np.clip(sombra, 0, 255).astype("uint8"))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        doc = pymupdf.open()
        pagina = doc.new_page(width=612, height=792)
        pagina.insert_image(pagina.rect, stream=buf.getvalue())
        from corpus_org.conversion.extractores.ocr import configurar_pytesseract
        normal = O._leer_pagina_con(pagina, idioma_ocr(), configurar_pytesseract(), O.DPI_OCR, None, 0)
        mejor = O.leer_pagina(pagina, idioma_ocr(), configurar_pytesseract())
        self.assertLess(normal.confianza, O.CONFIANZA_OBJETIVO)
        self.assertGreaterEqual(mejor.confianza, O.CONFIANZA_OBJETIVO)
        self.assertGreater(len(mejor.confianzas), 3 * len(normal.confianzas))
        self.assertNotEqual(mejor.mejora, "original")


@unittest.skipUnless(DEPENDENCIAS, "faltan dependencias de imagen")
class RecetasTest(unittest.TestCase):
    def test_las_recetas_conservan_el_tamano_de_la_pagina(self):
        img = _imagen_con_texto(["Prueba de recetas"], tam=(400, 200))
        for nombre, receta in O.RECETAS:
            if receta is not None:
                self.assertEqual(receta(img).size, img.size, nombre)

    def test_blanco_y_negro_solo_tiene_dos_valores(self):
        img = _imagen_con_texto(["Prueba"], tam=(300, 150))
        valores = set(np.asarray(O._receta_binarizada(img)).ravel().tolist())
        self.assertLessEqual(valores, {0, 255})

    def test_elegir_prefiere_la_lectura_buena_que_recupera_mas_texto(self):
        poca = (O.PaginaOCR(lineas=[], confianzas=[92.0] * 20), "blanco y negro", None)
        mucha = (O.PaginaOCR(lineas=[], confianzas=[85.0] * 130), "contraste y nitidez", None)
        mala = (O.PaginaOCR(lineas=[], confianzas=[50.0] * 15), "original", None)
        self.assertIs(O._elegir([mala, poca, mucha]), mucha)
        self.assertIsNone(O._elegir([mala], solo_buenas=True))
        self.assertIs(O._elegir([mala]), mala)

    def test_mejor_lectura_exige_mas_confianza_sin_perder_texto(self):
        base = O.PaginaOCR(lineas=[], confianzas=[60.0] * 100)
        self.assertTrue(O._mejor_lectura(O.PaginaOCR(lineas=[], confianzas=[85.0] * 100), base))
        self.assertFalse(O._mejor_lectura(O.PaginaOCR(lineas=[], confianzas=[95.0] * 40), base))   # perdio texto
        self.assertFalse(O._mejor_lectura(O.PaginaOCR(lineas=[], confianzas=[60.2] * 100), base))   # mejora trivial


if __name__ == "__main__":
    unittest.main()
