"""Integridad del corpus publicado: compara cada archivo con su SHA-256 de la conversion (huellas.sha256)."""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from ..comun.esquema import ARCHIVO_HUELLAS
from ..comun.estructura import CARPETA_INDICE, SKILL_CORPUS


@dataclass
class ResultadoHuellas:
    existe: bool
    modificados: List[str] = field(default_factory=list)
    faltantes: List[str] = field(default_factory=list)

    @property
    def correcto(self):
        return self.existe and not self.modificados and not self.faltantes


def _ruta(nombre, skill):
    """Archivo de una linea de huellas: '<skill>/<ruta>' (``fuente-corpus/...``)."""
    nombre_skill, _, resto = nombre.partition("/")
    return skill / resto if nombre_skill == SKILL_CORPUS and resto else skill / nombre


def verificar_huellas(skill):
    """Compara los archivos con indice/huellas.sha256 del skill."""
    skill = Path(skill)
    p = skill / CARPETA_INDICE / ARCHIVO_HUELLAS
    if not p.is_file():
        return ResultadoHuellas(existe=False)
    r = ResultadoHuellas(existe=True)
    for linea in p.read_text(encoding="utf-8").splitlines():
        if not linea.strip() or linea.startswith("#"):
            continue
        esperado, nombre = linea.split(None, 1)
        nombre = nombre.strip()
        archivo = _ruta(nombre, skill)
        if not archivo.is_file():
            r.faltantes.append(nombre)
        elif hashlib.sha256(archivo.read_bytes()).hexdigest() != esperado:
            r.modificados.append(nombre)
    return r
