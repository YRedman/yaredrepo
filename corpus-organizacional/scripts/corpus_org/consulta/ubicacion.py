"""Ubicacion de la carpeta del corpus publicado."""

import os
from pathlib import Path

VARIABLE_DATOS = "CORPUS_DATOS"
VARIABLE_NO_VIGENTES = "CORPUS_INCLUIR_NO_VIGENTES"


def resolver_carpeta_datos(raiz_skill, entorno=None):
    """Primero ``CORPUS_DATOS``, luego salida_corpus/publicado, publicado/ y la estructura historica datos/."""
    entorno = os.environ if entorno is None else entorno
    env = entorno.get(VARIABLE_DATOS)
    opciones = [Path(env).expanduser() if env else None, raiz_skill / "salida_corpus" / "publicado",
                raiz_skill / "publicado", raiz_skill / "datos"]
    for q in opciones:
        if q and q.is_dir():
            return q.resolve()
    return (raiz_skill / "datos").resolve()


def incluir_no_vigentes(entorno=None):
    entorno = os.environ if entorno is None else entorno
    return entorno.get(VARIABLE_NO_VIGENTES, "").strip().lower() in ("1", "true", "si", "sí")
