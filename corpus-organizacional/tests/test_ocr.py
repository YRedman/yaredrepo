"""Localizacion de Tesseract (OCR) y diagnostico."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import ayuda  # noqa: F401
from corpus_org.conversion.extractores import ocr


class TesseractTest(unittest.TestCase):
    def test_variable_tesseract_cmd_y_carpeta_de_instalacion(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "Tesseract-OCR" / "tesseract.exe"
            exe.parent.mkdir()
            exe.write_bytes(b"")
            # sin PATH: se encuentra en la carpeta de instalacion de Windows (ProgramFiles)
            with mock.patch.dict(os.environ, {"ProgramFiles": tmp}, clear=False), \
                    mock.patch.object(ocr.shutil, "which", return_value=None):
                os.environ.pop("TESSERACT_CMD", None)
                self.assertEqual(ocr.ejecutable_tesseract(), str(exe))
            # TESSERACT_CMD tiene prioridad
            otro = Path(tmp) / "otro.exe"
            otro.write_bytes(b"")
            with mock.patch.dict(os.environ, {"TESSERACT_CMD": str(otro)}):
                self.assertEqual(ocr.ejecutable_tesseract(), str(otro))

    def test_diagnostico_sin_tesseract(self):
        with mock.patch.object(ocr, "ejecutable_tesseract", return_value=None):
            lineas = ocr.diagnostico()
        self.assertFalse(lineas[-1][0])
        self.assertIn("TESSERACT_CMD", lineas[-1][1])


if __name__ == "__main__":
    unittest.main()
