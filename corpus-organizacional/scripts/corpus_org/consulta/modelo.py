"""Modelo de lectura del corpus publicado."""

from dataclasses import dataclass, field
from typing import List

from ..comun.esquema import area_de


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
        return self.codigo[0]

    @property
    def area(self):
        return area_de(self.codigo)

    @property
    def ubicacion(self):
        return f"{self.archivo}:{self.inicio + 1}-{self.fin}"


@dataclass
class Area:
    codigo: str
    nombre: str = ""
    descriptivos: List[str] = field(default_factory=list)
    procedimientos: List[str] = field(default_factory=list)

    def codigos(self, tipo=None):
        return ((self.descriptivos if tipo in (None, "D") else [])
                + (self.procedimientos if tipo in (None, "P") else []))

    def agregar(self, codigo):
        (self.descriptivos if codigo.startswith("D-") else self.procedimientos).append(codigo)
