"""Datos del inventario maestro: el inventario que se construye y el anterior cuyos codigos se conservan."""

import collections
import re
from dataclasses import dataclass, field
from typing import Dict, List

RE_CODIGO_DEP = re.compile(r"^[A-Z0-9]{3}$")
RE_SUFIJO_COPIA = re.compile(r"\s*\(\d+\)$|\s*-\s*copia(\s*\(\d+\))?$|\s*copy$", re.I)


@dataclass
class Inventario:
    documentos: List[dict] = field(default_factory=list)   # filas de inventario_maestro.csv
    catalogo: List[dict] = field(default_factory=list)     # filas de catalogo.csv
    avisos: List[str] = field(default_factory=list)
    ignoradas: List[tuple] = field(default_factory=list)   # (ruta, motivo)
    equivalencias: List[tuple] = field(default_factory=list)   # (codigo anterior, codigo nuevo) de un cambio de area
    departamentos: Dict[str, str] = field(default_factory=dict)
    rutas_validas: int = 0


@dataclass
class InventarioBase:
    """Inventario anterior cuyos codigos se conservan (codigos estables entre construcciones)."""
    documentos: Dict[tuple, dict] = field(default_factory=dict)   # (tipo, depto, documento) -> fila
    departamentos: Dict[str, str] = field(default_factory=dict)   # depto normalizado -> codigo
    maximos: collections.Counter = field(default_factory=collections.Counter)   # (tipo, codigo_dep) -> mayor numero
    equivalencias: List[tuple] = field(default_factory=list)       # (codigo_anterior, codigo_nuevo) migrados
