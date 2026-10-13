"""Lectura de paginas escaneadas: lineas de tablas en la imagen, celdas, duplicados y lectura completa."""

import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tests import ayuda  # noqa: F401

try:
    import numpy as np
    from corpus_org.conversion.extractores import ocr_pagina as O
    NUMPY = True
except ImportError:
    NUMPY = False


def _pagina(alto=1000, ancho=1600):
    return np.full((alto, ancho), 255, dtype=np.uint8)


def _h(g, y, x0, x1, gris=120, grosor=3):
    g[y:y + grosor, x0:x1] = gris


def _v(g, x, y0, y1, gris=120, grosor=3):
    g[y0:y1, x:x + grosor] = gris


def _tablas(g, palabras=()):
    return O.tablas_imagen(*O.lineas_imagen(g), g, list(palabras))


@unittest.skipUnless(NUMPY, "falta numpy")
class LineasImagenTest(unittest.TestCase):
    def test_cuadricula_de_dos_por_dos(self):
        g = _pagina()
        for y in (100, 200, 300):
            _h(g, y, 100, 1500)
        for x in (100, 800, 1497):
            _v(g, x, 100, 303)
        tablas = _tablas(g)
        self.assertEqual(len(tablas), 1)
        self.assertEqual([len(f) for f in tablas[0].filas], [2, 2])

    def test_linea_algo_inclinada_sigue_siendo_linea(self):
        g = _pagina()
        for x in range(100, 1500):
            y = 400 + (x - 100) * 8 // 1400          # baja 8 px de punta a punta (como el escaneo real)
            g[y:y + 3, x] = 30
        horizontales, _ = O.lineas_imagen(g)
        self.assertTrue(any(h.fin - h.ini > 1300 for h in horizontales))

    def test_fila_con_relleno_y_letras_claras(self):
        """Los bordes de las letras blancas sobre el relleno no son columnas: se usan las de las otras filas."""
        g = _pagina()
        g[100:160, 100:1500] = 90                    # cabecera con relleno oscuro
        for x in range(150, 1400, 60):               # "letras" claras dentro del relleno
            g[115:150, x:x + 6] = 250
        for y in (160, 260):
            _h(g, y, 100, 1500)
        for x in (100, 800, 1497):
            _v(g, x, 160, 263)
        tablas = _tablas(g)
        self.assertEqual([len(f) for f in tablas[0].filas], [2, 2])

    def test_linea_corta_dentro_de_una_celda_no_corta_la_tabla(self):
        g = _pagina()
        for y in (100, 200, 400):
            _h(g, y, 100, 1500)
        for x in (100, 800, 1497):
            _v(g, x, 100, 403)
        _h(g, 300, 200, 420)                          # subrayado dentro de la segunda fila
        tablas = _tablas(g)
        self.assertEqual(len(tablas), 1)
        self.assertEqual(len(tablas[0].filas), 2)

    def test_titulo_de_ancho_completo_no_se_parte(self):
        g = _pagina()
        g[100:160, 100:1500] = 90
        for y in (160, 260):
            _h(g, y, 100, 1500)
        for x in (100, 800, 1497):
            _v(g, x, 160, 263)
        titulo = ("Requisitos", 700, 115, 900, 145, 95.0, (1, 1, 1))   # cruza la columna en x=800
        tablas = _tablas(g, [titulo])
        self.assertEqual([len(f) for f in tablas[0].filas], [1, 2])


@unittest.skipUnless(NUMPY, "falta numpy")
class PalabrasTest(unittest.TestCase):
    def test_fragmentos_repetidos_y_vinetas(self):
        c = O.Celda(0, 0, 1000, 100)
        c.palabras = [("Educación", 100, 10, 300, 40, 90.0, 1), ("ión", 240, 12, 300, 40, 50.0, 1),
                      ("e", 320, 10, 330, 40, 70.0, 1), ("100%", 340, 10, 420, 40, 95.0, 1)]
        self.assertEqual(O.texto_celda(c), "Educación • 100%")

    def test_bordes_y_manchas_no_son_palabras(self):
        datos = {"text": ["|", "Hola", "p", "5"], "conf": [90, 95, 30, 40], "left": [0, 10, 50, 60],
                 "top": [0] * 4, "width": [5] * 4, "height": [10] * 4, "block_num": [1] * 4,
                 "par_num": [1] * 4, "line_num": [1] * 4}
        self.assertEqual([p[0] for p in O.palabras_tesseract(datos)], ["Hola", "5"])


def _ocr_disponible():
    try:
        from corpus_org.conversion.extractores.ocr import idioma_ocr
        import reportlab  # noqa: F401
        return NUMPY and idioma_ocr() == "spa"
    except ImportError:
        return False


@unittest.skipUnless(_ocr_disponible(), "faltan Tesseract con español, numpy o reportlab")
class DescriptivoEscaneadoTest(unittest.TestCase):
    """La plantilla real convertida en imagen: tablas, organigrama y encabezado salen igual que en digital."""

    @classmethod
    def setUpClass(cls):
        import pymupdf
        from corpus_org.conversion import cli as conversion_cli
        from tests import fixtures_plantilla
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        entrada, salida = base / "entrada", base / "salida"
        entrada.mkdir()
        fixtures_plantilla.generar(base / "digital.pdf")
        origen, escaneado = pymupdf.open(base / "digital.pdf"), pymupdf.open()
        for pg in origen:
            nueva = escaneado.new_page(width=pg.rect.width, height=pg.rect.height)
            nueva.insert_image(nueva.rect, pixmap=pg.get_pixmap(dpi=200))
        escaneado.save(entrada / "Analista de Pruebas.pdf")
        with redirect_stdout(io.StringIO()):
            conversion_cli.main(["convertir", "--entrada", str(entrada), "--salida", str(salida),
                                 "--departamento", "Pruebas", "--tipo", "DES", "--dep", "PRU",
                                 "--sin-verificacion-cruzada"])
        cls.md = (salida / "DES_PRU.md").read_text(encoding="utf-8")
        with open(salida / "DIC_DES_PRU.csv", encoding="utf-8-sig", newline="") as f:
            cls.fila = next(csv.DictReader(f, delimiter=";"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_campos_clave_y_encabezado(self):
        f = self.fila
        self.assertEqual((f["nombre_puesto"], f["reporta_a"], f["supervisa_a"]),
                         ("Analista de Pruebas", "Coordinador de Pruebas", "Técnico de Pruebas"))
        self.assertEqual((f["codigo_interno"], f["version"], f["fecha_vigencia"]), ("DP-FOR-001", "04", "15/03/2024"))
        self.assertEqual(f["campos_no_especificados"], "")
        self.assertEqual(f["paginas_ocr"], "1, 2")
        self.assertGreater(float(f["confianza_ocr"]), 85)

    def test_tablas_y_organigrama(self):
        self.assertIn("| Gerentes de Producto | Equipo Interdisciplinario |", self.md)
        self.assertIn("| Elaborar el informe mensual de hallazgos con gráficos de tendencia. |", self.md)
        self.assertIn("Coordinador de Pruebas → Analista de Pruebas", self.md)

    def test_confianza_alta_no_pide_revision(self):
        self.assertNotIn("OCR en páginas", self.fila["detalle_avisos"])


if __name__ == "__main__":
    unittest.main()
