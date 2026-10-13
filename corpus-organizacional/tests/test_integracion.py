"""Construye un corpus sintetico de punta a punta y consulta el resultado.

Necesita PyMuPDF, lxml, python-docx y reportlab; si falta alguno, la prueba se omite.
"""

import csv
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tests import ayuda  # noqa: F401

try:
    import docx  # noqa: F401
    import lxml  # noqa: F401
    import reportlab  # noqa: F401
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        import fitz  # noqa: F401
    from tests.fixtures_corpus import generar
    DEPENDENCIAS = True
except ImportError:
    DEPENDENCIAS = False

from corpus_org.consulta import cli as consulta_cli
from corpus_org.conversion import cli as conversion_cli


def construir(base, *extra):
    with redirect_stdout(io.StringIO()) as out:
        try:
            conversion_cli.main(["construir", "--entrada", str(base / "entrada"),
                                 "--contexto", str(base / "contexto"), "--sin-verificacion-cruzada",
                                 "--muestra-revision", "0", *extra])
            codigo = 0
        except SystemExit as e:
            codigo = e.code
    return codigo, out.getvalue()


def consultar(publicado, *argv, entorno=None):
    flujo = io.StringIO()
    env = {"CORPUS_DATOS": str(publicado), **(entorno or {})}
    with mock.patch.dict(os.environ, env):
        codigo = consulta_cli.main(list(argv), uso="uso", flujo=flujo)
    return codigo, flujo.getvalue()


@unittest.skipUnless(DEPENDENCIAS, "faltan dependencias de conversion o de las pruebas")
class IntegracionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.tmp.name)
        generar(cls.base)
        cls.codigo, cls.salida = construir(cls.base)
        cls.publicado = cls.base / "entrada" / "salida_corpus" / "publicado"
        with open(cls.publicado / ayuda.DATOS / "indice_corpus.csv", encoding="utf-8-sig") as f:
            cls.indice = {r["codigo"]: r for r in csv.DictReader(f, delimiter=";")}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_construccion_lista(self):
        self.assertEqual(self.codigo, 0, self.salida)
        self.assertIn("LISTO PARA PUBLICAR", self.salida)

    def test_metadatos_sin_falsos_positivos(self):
        self.assertEqual(self.indice["DES-ALM-01"]["estado_documental"], "")
        self.assertEqual(self.indice["PRD-COM-01"]["estado_documental"], "Vigente")
        self.assertEqual(self.indice["PRD-COM-01"]["propietario"], "Gerente de Compras")
        self.assertEqual(self.indice["PRD-COM-02"]["version"], "")
        self.assertEqual(self.indice["PRD-COM-02"]["estado_documental"], "Obsoleto")
        self.assertEqual(self.indice["PRD-COM-01"]["codigos_citados"], "PR-ALM-001")

    def test_pdf(self):
        r = self.indice["PRD-ALM-01"]
        self.assertEqual((r["codigo_interno"], r["version"], r["cobertura"]), ("PR-ALM-001", "1", "100.0 %"))

    def test_obsoleto_excluido_de_forma_coherente(self):
        _, catalogo = consultar(self.publicado, "catalogo")
        self.assertIn("Documentos no vigentes excluidos: 1", catalogo)
        self.assertNotIn("Responsable", catalogo)  # alias falso del glosario
        codigo, verif = consultar(self.publicado, "verificar")
        self.assertIn("Resultado: sin problemas", verif)
        _, busq = consultar(self.publicado, "buscar", "urgente")
        self.assertIn("Sin coincidencias", busq)
        codigo, doc = consultar(self.publicado, "doc", "PRD-COM-02")
        self.assertEqual(codigo, 2)
        _, todos = consultar(self.publicado, "doc", "PRD-COM-02", entorno={"CORPUS_INCLUIR_NO_VIGENTES": "1"})
        self.assertIn("Compra urgente", todos)

    def test_participacion_por_oracion(self):
        _, out = consultar(self.publicado, "participacion", "COM")
        fila = next(l for l in out.splitlines() if l.startswith("| Jefe de Almacén") and "Responsabilidades" in l)
        self.assertIn("Responsabilidad asignada", fila)

    def test_errores_de_area(self):
        codigo, out = consultar(self.publicado, "area", "xyz")
        self.assertEqual(codigo, 2)
        self.assertTrue(out.startswith("NO ENCONTRADO"))

    def test_reconstruir_no_deja_archivos_viejos(self):
        control = self.base / "entrada" / "salida_corpus" / "control"
        (control / "DIC_PRD_COM_01-01.csv").write_bytes((control / "DIC_PRD_COM.csv").read_bytes())
        codigo, salida = construir(self.base)
        self.assertEqual(codigo, 0, salida)
        self.assertFalse((control / "DIC_PRD_COM_01-01.csv").exists())


if __name__ == "__main__":
    unittest.main()
