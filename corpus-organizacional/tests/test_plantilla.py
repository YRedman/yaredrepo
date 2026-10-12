"""Lectura de descriptivos PDF con la maquetacion de las plantillas reales (v3.4).

Los PDF se generan con datos ficticios (tests/fixtures_plantilla.py); ningun documento real entra al repositorio.
"""

import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tests import ayuda  # noqa: F401
from corpus_org.conversion import cli as conversion_cli
from corpus_org.conversion.extractores.maquetacion import nivel_titulo

try:
    import reportlab  # noqa: F401
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        import fitz  # noqa: F401
    from tests import fixtures_plantilla
    DEPENDENCIAS = True
except ImportError:
    DEPENDENCIAS = False


def _fila(texto, tam=12.0, bold=False):
    return {"texto": texto, "tam": tam, "bold": bold, "vineta": None, "marcador": None}


class TituloTest(unittest.TestCase):
    """Un renglon destacado (negrita o mas grande) que esta a mitad de frase no es un titulo."""

    def test_termina_en_palabra_de_enlace(self):
        self.assertEqual(nivel_titulo(_fila("Conocer la satisfacción de los clientes a través de"), 11.0, [12.0]), 0)

    def test_empieza_en_minuscula(self):
        self.assertEqual(nivel_titulo(_fila("la aplicación de encuestas según los procedimientos"), 11.0, [12.0]), 0)

    def test_titulo_destacado(self):
        self.assertTrue(nivel_titulo(_fila("Requisitos del Puesto", bold=True), 11.0, [12.0]))


def _convertir(etiqueta_vigencia):
    with tempfile.TemporaryDirectory() as tmp:
        entrada, salida = Path(tmp) / "entrada", Path(tmp) / "salida"
        entrada.mkdir()
        fixtures_plantilla.generar(entrada / "Analista de Pruebas.pdf", etiqueta_vigencia)
        with redirect_stdout(io.StringIO()):
            conversion_cli.main(["convertir", "--entrada", str(entrada), "--salida", str(salida),
                                 "--departamento", "Pruebas", "--tipo", "D", "--dep", "PRU",
                                 "--sin-verificacion-cruzada"])
        md = (salida / "D_PRU.md").read_text(encoding="utf-8")
        with open(salida / "DIC_D_PRU.csv", encoding="utf-8-sig", newline="") as f:
            fila = next(csv.DictReader(f, delimiter=";"))
    return md, fila


@unittest.skipUnless(DEPENDENCIAS, "faltan reportlab o PyMuPDF")
class PlantillaRealTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.md, cls.fila = _convertir("Vigencia:")
        cls.cuerpo = cls.md[cls.md.index("### [D-PRU-01]"):cls.md.index("Datos de encabezado y pie")]

    def test_campos_clave(self):
        f = self.fila
        self.assertEqual(f["nombre_puesto"], fixtures_plantilla.PUESTO)
        self.assertEqual(f["reporta_a"], fixtures_plantilla.JEFE)
        self.assertEqual(f["supervisa_a"], fixtures_plantilla.SUBORDINADO)
        self.assertEqual(f["campos_no_especificados"], "")
        self.assertEqual(f["cobertura"], "100.0 %")

    def test_encabezado_con_valores_bajo_la_etiqueta(self):
        self.assertEqual((self.fila["codigo_interno"], self.fila["version"], self.fila["fecha_vigencia"]),
                         ("DP-FOR-001", "04", "15/03/2024"))
        self.assertNotIn("15/03/2024", self.cuerpo)
        self.assertNotIn("1 de 2", self.cuerpo)

    def test_objetivo_completo_en_un_parrafo(self):
        objetivo = " ".join(fixtures_plantilla.OBJETIVO)
        self.assertEqual(self.fila["proposito_literal"], objetivo)
        self.assertIn("\n" + objetivo + "\n", self.cuerpo)
        self.assertNotIn("### [D-PRU-01] la aplicación", self.cuerpo)

    def test_organigrama_una_sola_vez(self):
        self.assertEqual(self.cuerpo.count("[ORGANIGRAMA"), 1)
        self.assertIn(f"{fixtures_plantilla.JEFE} → {fixtures_plantilla.PUESTO}", self.cuerpo)

    def test_funciones_una_fila_por_celda(self):
        self.assertIn("| Ejecutar los casos de prueba de las diferentes líneas de producto y registrar los "
                      "resultados en los formularios establecidos. | • Casos ejecutados. • Registro de resultados. |",
                      self.cuerpo)
        self.assertIn("| Elaborar el informe mensual de hallazgos con gráficos de tendencia. | "
                      "• Informe mensual de hallazgos. |", self.cuerpo)

    def test_relacionamiento_y_firmas(self):
        self.assertIn("| Técnico de Pruebas | Reporte Directo |", self.cuerpo)
        self.assertIn("Secciones no incluidas: Firma de Aprobación, Firma del Colaborador", self.md)
        self.assertNotIn("Nombre: ____", self.cuerpo)


@unittest.skipUnless(DEPENDENCIAS, "faltan reportlab o PyMuPDF")
class VigenteAPartirDeTest(unittest.TestCase):
    def test_etiqueta_alternativa(self):
        _, fila = _convertir("Vigente a partir de:")
        self.assertEqual(fila["fecha_vigencia"], "15/03/2024")


if __name__ == "__main__":
    unittest.main()
