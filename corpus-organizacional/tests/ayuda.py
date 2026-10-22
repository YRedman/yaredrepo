"""Utilidades de las pruebas: hace importable el paquete ``corpus_org``."""

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# Estructura publicada (salida_corpus/copilot/...)
PUBLICADA = "copilot"
DOCUMENTOS = Path("fuente-corpus") / "documentos"
INDICE = Path("fuente-corpus") / "indice"
CONTEXTO = Path("fuente-corpus") / "contexto"
MATRIZ = Path("fuente-corpus") / "matriz"
