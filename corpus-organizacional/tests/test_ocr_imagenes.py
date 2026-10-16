"""Texto dentro de imagenes de paginas digitales (graficos, organigramas como imagen) y mejora de la lectura OCR.

Las imagenes se generan con texto ficticio; ningun documento real entra al repositorio.
"""

import io
import unittest.mock
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


@unittest.skipUnless(DEPENDENCIAS, "faltan dependencias de imagen")
class EtiquetasDeDiagramaTest(unittest.TestCase):
    def test_las_palabras_de_una_caja_se_unen_y_las_cajas_vecinas_no(self):
        def pal(t, x0, y0, x1, y1):
            return (t, x0, y0, x1, y1, 90.0, None)
        palabras = [pal("Recibir", 100, 100, 190, 130), pal("pedido", 200, 100, 280, 130),            # una linea
                    pal("Enviar", 100, 300, 175, 330), pal("notificacion", 100, 336, 240, 366),       # dos lineas
                    pal("Cobro", 600, 100, 670, 130)]
        self.assertEqual([e[0] for e in O.agrupar_etiquetas(palabras)],
                         ["Recibir pedido", "Cobro", "Enviar notificacion"])

    def test_las_etiquetas_se_corrigen_con_el_texto_del_libro_y_se_quitan_los_fragmentos(self):
        from corpus_org.conversion.extractores.imagenes import depurar_etiquetas
        referencia = ["Ejecución del Pedido", "Cotización"]
        etiquetas, corregidas, quitadas = depurar_etiquetas(
            ["Ejecucion del pedido", "Ejecuciom del Pedido", "ión", "USO", "do Cotización", "SI", "Si", "Cobro de Pedido"],
            referencia)
        self.assertEqual(etiquetas, ["Ejecución del Pedido", "Cotización", "SI", "Cobro de Pedido"])
        self.assertEqual((corregidas, quitadas), (2, 2))


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
class ImagenSueltaTest(unittest.TestCase):
    def test_un_png_de_contexto_se_lee_con_ocr(self):
        if not OCR:
            self.skipTest("falta Tesseract (spa)")
        img = _imagen_con_texto(["Reunion de seguimiento semanal del proyecto", "Responsable: Gerencia de Operaciones",
                                 "Entregable: informe de avance mensual", "Fecha limite: fin de mes"], tam=(1000, 500))
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "captura.png"
            img.save(ruta)
            d = extractor_para(ruta).extraer(ruta)
        texto = " ".join(b.get("texto", "") for b in d.bloques)
        self.assertIn("Gerencia de Operaciones", texto)
        self.assertEqual(d.paginas_ocr, [1])

    def test_una_imagen_que_el_ocr_lee_con_menos_de_60_no_aporta_su_texto(self):
        from unittest import mock
        from corpus_org.conversion.extractores.imagenes import texto_de_imagen
        from corpus_org.conversion.modelo import DocumentoExtraido
        ruido = O.PaginaOCR(lineas=[{"texto": "xqzv wklp rtmn bhjc vfgd ssdd", "x0": 0, "y0": 0, "x1": 10, "y1": 5,
                                     "tam": 0.0, "bold": False, "font": "ocr", "spans": [], "chars": 20, "ocr": True}],
                            confianzas=[26.0] * 6)
        d, bloques = DocumentoExtraido(), []
        with mock.patch("corpus_org.conversion.extractores.ocr.idioma_ocr", return_value="spa"), \
                mock.patch("corpus_org.conversion.extractores.ocr_pagina.leer_imagen", return_value=ruido):
            texto_de_imagen(d, bloques, "LA HOJA «Diagrama»", 1, _png_bytes())
        self.assertEqual([b["k"] for b in bloques], ["marca"])
        self.assertIn("ilegible", bloques[0]["texto"])
        self.assertEqual(d.paginas_ocr, [])
        self.assertTrue(any("no se pudo leer" in a for a in d.avisos), d.avisos)


def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), "white").save(buf, "PNG")
    return buf.getvalue()


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


@unittest.skipUnless(OCR, "faltan Tesseract (spa), pytesseract, Pillow o numpy")
class FotoTest(unittest.TestCase):
    def test_una_foto_sin_texto_se_lee_dos_veces_y_no_en_todas_las_mejoras(self):
        import pymupdf
        from corpus_org.conversion.extractores.ocr import configurar_pytesseract
        rng = np.random.RandomState(3)
        base = np.kron(rng.randint(40, 220, (22, 17)), np.ones((100, 100)))        # manchas de tonos medios, sin texto
        img = Image.fromarray(np.clip(base + rng.normal(0, 12, base.shape), 0, 255).astype("uint8"))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        doc = pymupdf.open()
        pagina = doc.new_page(width=612, height=792)
        pagina.insert_image(pagina.rect, stream=buf.getvalue())
        llamadas = []
        original = O._leer_pagina_con

        def contar(*a, **k):
            llamadas.append(1)
            return original(*a, **k)
        with unittest.mock.patch.object(O, "_leer_pagina_con", contar):
            res = O.leer_pagina(pagina, idioma_ocr(), configurar_pytesseract())
        self.assertLess(res.palabras_utiles, O.MIN_PALABRAS_TEXTO)
        self.assertEqual(len(llamadas), 2)          # antes eran 5 o 6 lecturas completas por foto

    def test_pixmap_a_gris_conserva_la_imagen_sin_pasar_por_png(self):
        import pymupdf
        doc = pymupdf.open()
        pagina = doc.new_page(width=200, height=100)
        pagina.draw_rect(pymupdf.Rect(20, 20, 100, 60), fill=(0, 0, 0))
        img = O._imagen_pagina(pagina, 72)
        self.assertEqual((img.mode, img.size), ("L", (200, 100)))
        self.assertEqual((img.getpixel((50, 40)), img.getpixel((150, 80))), (0, 255))
