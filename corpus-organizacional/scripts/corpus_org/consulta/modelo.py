"""Modelo de lectura del corpus publicado."""

from dataclasses import dataclass, field
from typing import Dict, List

from ..comun.esquema import area_de
from ..comun.tipos import TIPOS_AREA, familia, tipo_de_codigo


@dataclass
class DocumentoCorpus:
    codigo: str
    archivo: str
    inicio: int            # indice (base 0) de la linea "## [CODIGO]" en el archivo
    fin: int               # indice exclusivo
    titulo: str
    lineas: List[str] = field(default_factory=list)

    @property
    def tipo(self):
        return tipo_de_codigo(self.codigo)

    @property
    def area(self):
        return area_de(self.codigo)

    @property
    def ubicacion(self):
        return f"{self.archivo}:{self.inicio + 1}-{self.fin}"


@dataclass
class Area:
    """Documentos de un area, por tipo (DES, PRD, PRO, POL)."""
    codigo: str
    nombre: str = ""
    por_tipo: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def descriptivos(self):
        return self.por_tipo.get("DES", [])

    @property
    def procedimientos(self):
        return self.por_tipo.get("PRD", [])

    def codigos(self, tipo=None):
        """Codigos del area. ``tipo``: None (todos), un codigo (DES, PRD, PRO, POL) o la familia de analisis
        'D' (descriptivos) o 'P' (procedimientos, protocolos y politicas: documentos con actividades)."""
        orden = list(TIPOS_AREA) + sorted(set(self.por_tipo) - set(TIPOS_AREA))
        return [c for t in orden for c in self.por_tipo.get(t, [])
                if tipo is None or t == tipo or (tipo in ("D", "P") and familia(t) == tipo)]

    def agregar(self, codigo):
        self.por_tipo.setdefault(tipo_de_codigo(codigo), []).append(codigo)
