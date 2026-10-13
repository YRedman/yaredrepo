"""Utilidades de las pruebas: hace importable el paquete ``corpus_org``."""

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# Estructura publicada en dos skills (salida_corpus/publicado/...)
DATOS = Path("corpus-contexto") / "datos"
DOCUMENTOS = Path("corpus-documentos")
