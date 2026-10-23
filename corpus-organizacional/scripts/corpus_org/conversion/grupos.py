"""Un grupo de documentos a convertir (un tipo de un departamento) y el resultado de convertirlo."""

from dataclasses import dataclass
from typing import Dict, List

from ..comun.tipos import familia, tipo as tipo_documento
from .modelo import DocumentoConvertido


@dataclass
class Grupo:
    tipo: str                      # codigo de tipo: DES, PRD, PRO, POL u ORG, KPI... (generales)
    codigo_dep: str
    departamento: str
    filas: List[dict]              # filas del inventario a procesar
    archivos: Dict[str, object]    # codigo -> Path del archivo adjunto
    nombre_base: str               # PRD_COM, DES_ALM_01-05, ORG_GEN...
    completo: bool = True

    @property
    def es_contexto(self):
        return familia(self.tipo) == "C"

    @property
    def familia(self):
        """'D', 'P' o 'C': como se analiza el documento (ver comun/tipos.py)."""
        return familia(self.tipo)

    @property
    def titulo(self):
        td = tipo_documento(self.tipo)
        plural = td.plural if td else self.tipo
        if self.es_contexto:
            return f"{plural} · General ({self.codigo_dep})"
        return f"{plural} · {self.departamento} ({self.codigo_dep})"


@dataclass
class ResultadoGrupo:
    grupo: Grupo
    documentos: List[DocumentoConvertido]
    archivos_generados: list

    @property
    def convertidos(self):
        return [r for r in self.documentos if r.ok]
