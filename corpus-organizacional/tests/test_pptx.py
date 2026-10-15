"""Lectura de presentaciones de PowerPoint (.pptx).

Las presentaciones se generan con datos ficticios; ningun documento real entra al repositorio.
"""

import tempfile
import unittest
from pathlib import Path

from tests import ayuda  # noqa: F401

try:
    from pptx import Presentation
    from pptx.util import Inches
    from PIL import Image, ImageDraw, ImageFont
    from corpus_org.conversion.extractores import extractor_para, formato_real
    from corpus_org.conversion.extractores.ocr import idioma_ocr
    DEPENDENCIAS = True
except ImportError:
    DEPENDENCIAS = False

OCR = DEPENDENCIAS and idioma_ocr() is not None
FUENTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _extraer(ruta):
    return extractor_para(ruta).extraer(ruta)


def _textos(d):
    return [b.get("texto", "") for b in d.bloques]


@unittest.skipUnless(DEPENDENCIAS, "faltan python-pptx o Pillow")
class PptxTest(unittest.TestCase):
    def _presentacion(self, ruta, construir):
        prs = Presentation()
        construir(prs)
        prs.save(ruta)

    def test_titulo_lista_con_niveles_y_notas(self):
        def construir(prs):
            s = prs.slides.add_slide(prs.slide_layouts[1])
            s.shapes.title.text = "Plan de gestión del cambio"
            tf = s.placeholders[1].text_frame
            tf.text = "Comunicar el alcance"
            p = tf.add_paragraph()
            p.text = "Champions por área"
            p.level = 1
            s.notes_slide.notes_text_frame.text = "Mencionar el calendario"
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "plan.pptx"
            self._presentacion(ruta, construir)
            d = _extraer(ruta)
        titulos = [b["texto"] for b in d.bloques if b["k"] == "h"]
        self.assertEqual(titulos, ["Diapositiva 1: Plan de gestión del cambio"])
        listas = [(b["texto"], b["nivel"]) for b in d.bloques if b["k"] == "li"]
        self.assertEqual(listas, [("Comunicar el alcance", 0), ("Champions por área", 1)])
        self.assertIn("Notas del orador: Mencionar el calendario", _textos(d))
        self.assertEqual(d.paginas, 1)

    def test_tabla_y_diapositiva_oculta(self):
        def construir(prs):
            s = prs.slides.add_slide(prs.slide_layouts[5])
            s.shapes.title.text = "Responsables"
            t = s.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(6), Inches(1)).table
            for i, fila in enumerate([["Área", "Responsable"], ["Compras", "Gerente"]]):
                for j, v in enumerate(fila):
                    t.cell(i, j).text = v
            o = prs.slides.add_slide(prs.slide_layouts[5])
            o.shapes.title.text = "Borrador oculto"
            o._element.set("show", "0")
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "tabla.pptx"
            self._presentacion(ruta, construir)
            d = _extraer(ruta)
        self.assertEqual([b["filas"] for b in d.bloques if b["k"] == "tabla"],
                         [[["Área", "Responsable"], ["Compras", "Gerente"]]])
        self.assertNotIn("Borrador oculto", " ".join(_textos(d)))
        self.assertTrue(any("ocultas" in n for n in d.notas), d.notas)
        self.assertEqual(d.tablas, 1)

    def test_orden_de_lectura_por_posicion_y_pie_omitido(self):
        def construir(prs):
            s = prs.slides.add_slide(prs.slide_layouts[6])
            derecha = s.shapes.add_textbox(Inches(5), Inches(1), Inches(3), Inches(1))
            derecha.text_frame.text = "Columna derecha"
            izquierda = s.shapes.add_textbox(Inches(0.5), Inches(1), Inches(3), Inches(1))
            izquierda.text_frame.text = "Columna izquierda"
            abajo = s.shapes.add_textbox(Inches(0.5), Inches(4), Inches(3), Inches(1))
            abajo.text_frame.text = "Texto de abajo"
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "orden.pptx"
            self._presentacion(ruta, construir)
            d = _extraer(ruta)
        textos = [t for t in _textos(d) if not t.startswith("Diapositiva")]
        self.assertEqual(textos, ["Columna izquierda", "Columna derecha", "Texto de abajo"])

    def test_un_pptx_con_extension_pdf_o_csv_se_lee_como_pptx(self):
        def construir(prs):
            s = prs.slides.add_slide(prs.slide_layouts[5])
            s.shapes.title.text = "Hola"
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "a.pptx"
            self._presentacion(real, construir)
            falso = Path(tmp) / "a.csv"
            falso.write_bytes(real.read_bytes())
            self.assertEqual(formato_real(falso), ".pptx")
            d = _extraer(falso)
        self.assertEqual([b["texto"] for b in d.bloques if b["k"] == "h"], ["Diapositiva 1: Hola"])
        self.assertTrue(any("presentación de PowerPoint" in n for n in d.notas), d.notas)

    def test_el_texto_leido_es_el_texto_del_original(self):
        """crudo (palabras esperadas) y texto emitido coinciden: la verificacion no marca palabras agregadas."""
        def construir(prs):
            s = prs.slides.add_slide(prs.slide_layouts[1])
            s.shapes.title.text = "Objetivos estratégicos"
            s.placeholders[1].text_frame.text = "Reducir la rotación voluntaria"
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "objetivos.pptx"
            self._presentacion(ruta, construir)
            d = _extraer(ruta)
        for palabra in ("objetivos", "estratégicos", "reducir", "rotación", "diapositiva"):
            self.assertIn(palabra, d.crudo)


@unittest.skipUnless(OCR, "faltan Tesseract (spa), pytesseract o Pillow")
class ImagenEnDiapositivaTest(unittest.TestCase):
    def test_una_captura_en_la_diapositiva_se_lee_con_ocr_y_un_icono_no(self):
        img = Image.new("RGB", (800, 500), "white")
        dib = ImageDraw.Draw(img)
        f = ImageFont.truetype(FUENTE, 24)
        for k, t in enumerate(["Gerencia de Operaciones Regional", "Coordinador de Almacen Central",
                               "Analista de Inventarios Senior", "Supervisor de Despacho Nacional",
                               "Asistente de Logistica Inversa"]):
            dib.text((30, 40 + 70 * k), t, fill="black", font=f)
        with tempfile.TemporaryDirectory() as tmp:
            png, icono = Path(tmp) / "captura.png", Path(tmp) / "icono.png"
            img.save(png)
            Image.new("RGB", (64, 64), "red").save(icono)
            prs = Presentation()
            s = prs.slides.add_slide(prs.slide_layouts[5])
            s.shapes.title.text = "Organigrama"
            s.shapes.add_picture(str(png), Inches(0.5), Inches(1.5), width=Inches(8))
            s.shapes.add_picture(str(icono), Inches(0.1), Inches(0.1), width=Inches(0.4))
            ruta = Path(tmp) / "con_imagen.pptx"
            prs.save(ruta)
            d = _extraer(ruta)
        texto = " ".join(_textos(d))
        self.assertIn("Coordinador de Almacen", texto)
        self.assertEqual(sum(1 for b in d.bloques if b["k"] == "marca"), 1)
        self.assertEqual(d.paginas_ocr, [1])


if __name__ == "__main__":
    unittest.main()
