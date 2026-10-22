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


def _pagina_de_texto(giro=0, espejo=False):
    """Pagina PyMuPDF con una imagen de texto (como un escaneo) puesta al reves, de lado o reflejada."""
    import pymupdf
    base = _imagen_con_texto(["Procedimiento de compras de bienes y servicios", "El area de compras recibe la solicitud aprobada y",
                              "emite la orden de compra al proveedor seleccionado", "segun la politica vigente de la organizacion."] * 6,
                             tam=(1700, 2200), px=34)
    img = O.orientar(base, giro, espejo)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    doc = pymupdf.open()
    ancho, alto = (612, 792) if img.width < img.height else (792, 612)
    pagina = doc.new_page(width=ancho, height=alto)
    pagina.insert_image(pagina.rect, stream=buf.getvalue())
    return doc, pagina


@unittest.skipUnless(OCR, "faltan Tesseract (spa), pytesseract, Pillow o numpy")
class OrientacionTest(unittest.TestCase):
    def test_una_pagina_reflejada_se_detecta_y_se_lee_bien(self):
        from corpus_org.conversion.extractores.ocr import configurar_pytesseract
        _doc, pagina = _pagina_de_texto(espejo=True)
        res = O.leer_pagina(pagina, idioma_ocr(), configurar_pytesseract())
        self.assertTrue(res.espejo)
        self.assertGreaterEqual(res.confianza, O.CONFIANZA_OBJETIVO)
        self.assertIn("reflejada", res.mejora)
        self.assertIn("Procedimiento de compras", " ".join(l["texto"] for l in res.lineas))

    def test_una_pagina_al_reves_se_endereza(self):
        from corpus_org.conversion.extractores.ocr import configurar_pytesseract
        _doc, pagina = _pagina_de_texto(giro=180)
        res = O.leer_pagina(pagina, idioma_ocr(), configurar_pytesseract())
        self.assertEqual((res.orientacion, res.espejo), (180, False))
        self.assertGreaterEqual(res.confianza, O.CONFIANZA_OBJETIVO)

    def test_una_pagina_derecha_no_prueba_orientaciones(self):
        from corpus_org.conversion.extractores.ocr import configurar_pytesseract
        _doc, pagina = _pagina_de_texto()
        with unittest.mock.patch.object(O, "orientacion_por_prueba", side_effect=AssertionError("no debia probarse")):
            res = O.leer_pagina(pagina, idioma_ocr(), configurar_pytesseract())
        self.assertEqual((res.orientacion, res.espejo), (0, False))

    def test_una_imagen_reflejada_de_un_excel_se_lee_con_su_orientacion(self):
        from corpus_org.conversion.extractores.ocr import configurar_pytesseract
        base = _imagen_con_texto(["Procedimiento de compras de bienes y servicios", "El area de compras recibe la solicitud aprobada y",
                                  "emite la orden de compra al proveedor seleccionado", "segun la politica vigente de la organizacion."] * 4,
                                 tam=(1500, 1500), px=34)
        res = O.leer_imagen(O.orientar(base, 0, True), idioma_ocr(), configurar_pytesseract())
        self.assertTrue(res.espejo)
        self.assertGreaterEqual(res.confianza, O.CONFIANZA_OBJETIVO)

    def test_orientar_gira_y_refleja(self):
        img = Image.new("L", (4, 2), 255)
        img.putpixel((0, 0), 0)
        self.assertEqual(O.orientar(img, 0, True).getpixel((3, 0)), 0)          # reflejo horizontal
        self.assertEqual(O.orientar(img, 180).getpixel((3, 1)), 0)              # medio giro
        self.assertEqual(O.orientar(img, 90).size, (2, 4))


@unittest.skipUnless(DEPENDENCIAS, "faltan dependencias de imagen")
class FirmasTest(unittest.TestCase):
    def test_el_trazo_de_una_firma_se_ignora_pero_un_nombre_escrito_a_maquina_se_conserva(self):
        celda = lambda palabras: O.Celda(  # noqa: E731
            0, 0, 500, 10, [(t, 50 * k, 0, 50 * k + 40, 10, c) for k, (t, c) in enumerate(palabras)])

        class T:
            def __init__(self, filas):
                self.filas = filas
        etiqueta = [("Director", 95), ("Gerente", 95), ("del", 95), ("área:", 95)]
        trazo = [("a", 40), ("ZZ", 35), ("o", 50)]
        nombre = [("Carlos", 92), ("Pérez", 94), ("~", 30)]
        tablas = [T([[celda(etiqueta), celda(trazo)], [celda(etiqueta), celda(nombre)]]),
                  T([[celda([("Función", 95)]), celda([("Planificar", 90), ("tareas", 41)])]])]
        self.assertEqual(O._quitar_firmas(tablas), 1)
        self.assertEqual(tablas[0].filas[0][1].palabras, [])
        self.assertEqual([p[0] for p in tablas[0].filas[1][1].palabras], ["Carlos", "Pérez"])
        self.assertEqual(len(tablas[1].filas[0][1].palabras), 2)           # una fila sin etiqueta de firma no se toca

    def test_en_una_linea_con_etiqueta_de_firma_se_descartan_las_palabras_de_baja_confianza(self):
        clave = (1, 1, 1)
        palabras = [("Firma:", 0, 0, 5, 5, 96, clave), ("xx", 6, 0, 9, 5, 30, clave), ("Texto", 0, 10, 5, 15, 40, (1, 1, 2))]
        limpias, n = O._quitar_firmas_en_lineas(palabras)
        self.assertEqual(([p[0] for p in limpias], n), (["Firma:", "Texto"], 1))

    def test_rotulos_de_firma_leidos_con_ruido_se_normalizan(self):
        self.assertEqual(O.rotulo_de_firma("de Firma de Aprobación"), "Firma de Aprobación")
        self.assertEqual(O.rotulo_de_firma("Firma de Aj"), "Firma de Aprobación")
        self.assertEqual(O.rotulo_de_firma("Firmado por la gerencia de compras en la fecha indicada abajo"),
                         "Firmado por la gerencia de compras en la fecha indicada abajo")

    def test_una_imagen_junto_a_una_etiqueta_de_firma_en_un_pdf_digital_se_ignora(self):
        import pymupdf
        from corpus_org.conversion.extractores import extractor_para
        firma = Image.new("L", (500, 200), 255)
        ImageDraw.Draw(firma).line([(20, 150), (120, 40), (220, 160), (320, 50), (480, 140)], fill=0, width=5)
        buf = io.BytesIO()
        firma.convert("RGB").save(buf, "PNG")
        doc = pymupdf.open()
        pagina = doc.new_page(width=612, height=792)
        pagina.insert_text((72, 100), "Objetivo del puesto: coordinar las compras de la region.", fontsize=11)
        pagina.insert_text((72, 300), "Firma del Colaborador", fontsize=11)
        pagina.insert_image(pymupdf.Rect(72, 310, 320, 410), stream=buf.getvalue())
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "p.pdf"
            doc.save(str(ruta))
            d = extractor_para(ruta).extraer(ruta)
        textos = " ".join(b.get("texto", "") for b in d.bloques)
        self.assertNotIn("IMAGEN", textos)
        self.assertEqual(d.diagramas, [])
        self.assertTrue(any("firma manuscrita" in n for n in d.notas), d.notas)
