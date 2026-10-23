"""Las palabras leidas por OCR no son "agregadas" aunque terminen en una tabla."""

import collections
import unittest

from tests import ayuda  # noqa: F401
from corpus_org.conversion.extractores.pdf.lineas import palabras_ocr
from corpus_org.conversion.modelo import DocumentoExtraido
from corpus_org.conversion.verificacion import verificar


class _Analisis:
    excluidos = collections.Counter()
    excluidos_numeros = collections.Counter()


class VerificacionOcrTest(unittest.TestCase):
    def test_tabla_armada_con_texto_ocr(self):
        doc = DocumentoExtraido()
        doc.crudo_ocr = palabras_ocr(["Cumplir la normativa ambien-", "tal aplicable", "Gestionar activos fijos"])
        tabla = {"k": "tabla", "filas": [["Cumplir la normativa ambiental aplicable", "Gestionar activos fijos"]]}
        md = "| Cumplir la normativa ambiental aplicable | Gestionar activos fijos |\n"
        v = verificar(doc, [tabla], _Analisis(), md)
        self.assertEqual(v.agregadas, [])

    def test_texto_que_no_viene_de_ningun_lado_sigue_detectandose(self):
        doc = DocumentoExtraido()
        doc.crudo.update(["gestionar", "activos"])
        v = verificar(doc, [], _Analisis(), "Gestionar activos inventados\n")
        self.assertEqual(v.agregadas, ["inventados"])


if __name__ == "__main__":
    unittest.main()
