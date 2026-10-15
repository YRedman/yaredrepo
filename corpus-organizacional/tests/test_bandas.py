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


def _banda(c, y_arriba, titulo, filas, x0=72, x1=561, alto=29, interior=False):
    """Dibuja una banda de color con el titulo y filas de texto separadas por una linea fina. Devuelve la y final.

    ``alto`` 13 reproduce la plantilla de bandas delgadas; ``interior`` agrega el rectangulo interior que dibuja
    esa plantilla alrededor del titulo."""
    c.setFillColorRGB(*AZUL)
    c.rect(x0, y_arriba - alto, x1 - x0, alto, stroke=0, fill=1)
    if interior:
        c.rect(x0 + 5, y_arriba - alto, x1 - x0 - 10, alto - 2, stroke=0, fill=1)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString((x0 + x1) / 2, y_arriba - alto + (alto - 10) / 2 + 1, titulo)
    y = y_arriba - alto
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

    def test_fila_suelta_al_inicio_continua_la_caja_anterior_y_otra_caja_no(self):
        """La fila con borde que abre la pagina 2 sigue a la caja de la pagina 1; «Firma» es otra caja."""
        def pagina1(c):
            _banda(c, 300, "Caracteristicas Especiales", ["Disponibilidad para viajar"])

        def pagina2(c):
            c.setFont("Helvetica", 10)
            c.drawString(78, 760, "Disponibilidad para movilizarse")
            c.setStrokeColorRGB(*CLARO)
            c.line(72, 755, 561, 755)
            _banda(c, 700, "Firma de Aprobacion", ["Director del area"])
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "continua.pdf"
            _pdf(ruta, [pagina1, pagina2])
            d, _ = _extraer(ruta)
        tablas = [b["filas"] for b in d.bloques if b["k"] == "tabla"]
        self.assertIn([["Caracteristicas Especiales"], ["Disponibilidad para viajar"],
                       ["Disponibilidad para movilizarse"]], tablas)
        self.assertIn([["Firma de Aprobacion"], ["Director del area"]], tablas)
        self.assertFalse(any("tabla partida" in a for a in d.avisos), d.avisos)

    def test_bandas_delgadas_con_rectangulo_interior_son_una_sola_caja(self):
        def pagina(c):
            c.setFont("Helvetica", 10)
            c.drawString(72, 740, "Texto de apertura del documento.")
            y = _banda(c, 600, "Accesos a Sistemas", ["Office 365", "Licencia SAP"], alto=13, interior=True)
            _banda(c, y - 24, "Herramientas de Trabajo", ["Laptop", "Flota"], alto=13, interior=True)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "delgadas.pdf"
            _pdf(ruta, [pagina])
            d, _ = _extraer(ruta)
        tablas = [b["filas"] for b in d.bloques if b["k"] == "tabla"]
        self.assertIn([["Accesos a Sistemas"], ["Office 365"], ["Licencia SAP"]], tablas)
        self.assertIn([["Herramientas de Trabajo"], ["Laptop"], ["Flota"]], tablas)
        self.assertFalse(d.avisos, d.avisos)

    def test_encabezado_con_valor_bajo_su_etiqueta_no_se_cuela_entre_tablas_partidas(self):
        """La fecha y el «2 de 3» bajo «Vigencia:» y «Pagina:» son encabezado aunque no tengan letras."""
        def con_encabezado(n, cuerpo):
            def pagina(c):
                c.setFont("Helvetica-Bold", 14)
                c.drawString(200, 760, "Descripcion de Puesto y Perfil por Competencias")
                c.setFont("Helvetica", 9)
                c.drawString(450, 745, "Codigo: GGH-FOR-040")
                c.drawString(450, 730, "Vigencia:")
                c.drawString(450, 715, "23/10/2023")
                c.drawString(520, 730, "Pagina:")
                c.drawString(522, 715, f"{n} de 3")
                cuerpo(c)
            return pagina

        def p1(c):
            _banda(c, 300, "Caracteristicas Especiales", ["Disponibilidad para viajar"], alto=13, interior=True)

        def p2(c):
            c.setFont("Helvetica", 10)
            c.drawString(78, 695, "Disponibilidad para movilizarse")
            c.setStrokeColorRGB(*CLARO)
            c.line(72, 690, 561, 690)
            _banda(c, 650, "Firma de Aprobacion", ["Director del area"], alto=13, interior=True)

        def p3(c):
            c.setFont("Helvetica", 10)
            c.drawString(72, 600, "Texto final del documento.")
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "encabezado.pdf"
            _pdf(ruta, [con_encabezado(1, p1), con_encabezado(2, p2), con_encabezado(3, p3)])
            d, _ = _extraer(ruta)
        tablas = [b["filas"] for b in d.bloques if b["k"] == "tabla"]
        self.assertIn([["Caracteristicas Especiales"], ["Disponibilidad para viajar"],
                       ["Disponibilidad para movilizarse"]], tablas)
        self.assertIn([["Firma de Aprobacion"], ["Director del area"]], tablas)
        self.assertFalse(d.avisos, d.avisos)

    def test_parrafo_con_letra_mayor_al_cuerpo_no_se_vuelve_titulo(self):
        def pagina(c):
            c.setFont("Helvetica", 10)
            for k in range(12):
                c.drawString(72, 740 - 14 * k, f"Linea de cuerpo numero {k} con texto corriente del documento.")
            c.setFont("Helvetica", 11.5)
            for k, l in enumerate(["Garantizar el seguimiento eficiente del proceso de compras",
                                   "de bienes y servicios, asegurando la gestion de facturacion",
                                   "de proveedores y el registro contable de las mismas."]):
                c.drawString(72, 500 - 15 * k, l)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "letra.pdf"
            _pdf(ruta, [pagina])
            d, _ = _extraer(ruta)
        titulos = [b["texto"] for b in d.bloques if b["k"] == "h"]
        self.assertFalse(any("Garantizar" in t for t in titulos), titulos)


@unittest.skipUnless(DEPENDENCIAS, "faltan reportlab o PyMuPDF")
class IndiceTest(unittest.TestCase):
    def test_filas_de_indice_con_titulos_conocidos_conservan_su_numero(self):
        """'2. Objetivo 7' y '3. Alcance 7' no se funden en un titulo y no pierden el '3.'."""
        def pagina(c):
            c.setFont("Helvetica", 10)
            filas = [("1.", "Carta del Presidente", "4"), ("2.", "Objetivo", "7"), ("3.", "Alcance", "7"),
                     ("4.", "Declaracion de Principios", "7"), ("5.", "Definiciones", "8")]
            for k, (n, t, pg) in enumerate(filas):
                y = 700 - 15 * k
                c.drawString(45, y, n)
                c.drawString(81, y, t)
                c.drawString(426, y, pg)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "indice.pdf"
            _pdf(ruta, [pagina])
            d, _ = _extraer(ruta)
        texto = "\n".join((b.get("marcador", "") + " " + b.get("texto", "")) for b in d.bloques)
        for n in ("2.", "3.", "4.", "5."):
            self.assertIn(n, texto)
        self.assertEqual(sum(1 for b in d.bloques if b["k"] == "h" and "Alcance" in b["texto"]
                             and "Objetivo" in b["texto"]), 0)


class CeldasRepetidasTest(unittest.TestCase):
    def test_la_celda_interior_que_repite_a_la_grande_se_vacia_y_las_columnas_se_unen(self):
        from corpus_org.conversion.extractores.pdf import _quitar_celdas_repetidas, _quitar_vacias
        largo = "Administrar el control estadistico del proceso de levantamiento"
        filas = [["FUNCIONES", "", "EVIDENCIA"], [largo, largo, "Informe"], ["", "Coordinar la evaluacion de puestos", "Escala"],
                 ]
        r = _quitar_vacias(_quitar_celdas_repetidas(filas), 3)
        self.assertEqual(r[1], [largo, "Informe"])
        self.assertEqual(r[2], ["Coordinar la evaluacion de puestos", "Escala"])
        self.assertEqual(_quitar_celdas_repetidas([["N/A", "N/A", "N/A"]]), [["N/A", "N/A", "N/A"]])   # datos reales


class CeldaSinBordeTest(unittest.TestCase):
    def test_celda_sin_borde_toma_el_ancho_de_su_columna_y_el_alto_de_su_fila(self):
        from corpus_org.conversion.extractores.pdf import _celda_sin_borde
        filas = [[(75, 0, 332, 20), (337, 0, 554, 20)], [None, (337, 20, 554, 60)]]
        self.assertEqual(_celda_sin_borde(filas, 1, 0), (75, 20, 332, 60))

    def test_celda_combinada_no_se_inventa(self):
        from corpus_org.conversion.extractores.pdf import _celda_sin_borde
        horizontal = [[(75, 0, 332, 20), (337, 0, 554, 20)], [(75, 20, 554, 40), None]]
        self.assertIsNone(_celda_sin_borde(horizontal, 1, 1))
        vertical = [[(75, 0, 332, 20), (337, 0, 554, 80)], [(75, 20, 332, 40), None]]
        self.assertIsNone(_celda_sin_borde(vertical, 1, 1))


if __name__ == "__main__":
    unittest.main()
