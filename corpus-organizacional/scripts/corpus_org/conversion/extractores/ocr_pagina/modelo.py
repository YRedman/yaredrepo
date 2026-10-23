"""Resultados del OCR de una pagina: lineas, celdas y tablas detectadas."""

import re
from dataclasses import dataclass, field
from typing import List

from .texto import texto_celda


@dataclass
class Segmento:
    pos: float      # y (horizontal) o x (vertical), en px
    ini: float      # x0 (horizontal) o y0 (vertical)
    fin: float


@dataclass
class Celda:
    x0: float
    y0: float
    x1: float
    y1: float
    palabras: list = field(default_factory=list)   # (texto, x0, y0, x1, y1, conf)

    def contiene(self, cx, cy):
        return self.x0 - 2 <= cx <= self.x1 + 2 and self.y0 - 2 <= cy <= self.y1 + 2


@dataclass
class TablaImagen:
    filas: List[List[Celda]]

    @property
    def x0(self):
        return min(c.x0 for f in self.filas for c in f)

    @property
    def x1(self):
        return max(c.x1 for f in self.filas for c in f)

    @property
    def y0(self):
        return self.filas[0][0].y0

    @property
    def y1(self):
        return self.filas[-1][0].y1

    def textos(self):
        return [[texto_celda(c) for c in f] for f in self.filas]


@dataclass
class PaginaOCR:
    lineas: list                                    # lineas fuera de tablas (formato de _lineas_pagina, en pt)
    tablas: list = field(default_factory=list)      # (y0, x0, y1, x1 en pt, filas de texto, xs en pt)
    cajas: list = field(default_factory=list)       # (y0, x0, textos) de un organigrama
    encabezado: list = field(default_factory=list)  # textos de las celdas del encabezado del formato
    confianzas: list = field(default_factory=list)  # confianza de cada palabra leida
    mejora: str = ""                                # tratamiento de imagen con que se obtuvo la lectura
    dpi: int = 0
    orientacion: int = 0                            # grados que se giro la pagina (0, 90, 180, 270)
    espejo: bool = False                            # la pagina estaba reflejada y se leyo ya corregida
    firmas: int = 0                                 # campos de firma manuscrita ignorados (su OCR es ruido)
    disperso: bool = False                          # texto suelto de un diagrama (etiquetas), no parrafos
    descartadas: int = 0                            # palabras leidas con menos de CONF_PALABRA_MIN: ruido de graficos
    etiquetas: list = field(default_factory=list)   # en un diagrama: texto de cada caja, decision o flecha

    @property
    def confianza(self):
        return sum(self.confianzas) / len(self.confianzas) if self.confianzas else 0.0

    @property
    def textos(self):
        """Todos los textos leidos: lineas, celdas de tablas, cajas y encabezado."""
        return ([l["texto"] for l in self.lineas] + [c for t in self.tablas for f in t[4] for c in f]
                + [c[2] for c in self.cajas] + list(self.encabezado))

    @property
    def palabras_utiles(self):
        """Palabras de 4 o mas letras: una pagina con menos de MIN_PALABRAS_TEXTO es una foto, no texto."""
        return sum(1 for t in self.textos for _ in re.findall(r"[^\W\d_]{4,}", t))
