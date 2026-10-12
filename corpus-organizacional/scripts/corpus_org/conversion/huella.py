"""Huella del codigo que genero una salida (para trazabilidad en reportes)."""

import functools
from pathlib import Path

from ..comun.archivos import huella_codigo


@functools.lru_cache(maxsize=1)
def huella():
    return huella_codigo(Path(__file__).resolve().parent.parent)
