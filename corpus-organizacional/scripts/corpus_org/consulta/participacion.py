"""Participacion de puestos en procedimientos: quien ejecuta, aprueba, revisa o es mencionado."""

import collections
import re
from dataclasses import dataclass, field
from typing import Dict, List

from ..comun.esquema import area_de
from ..comun.texto import oracion_con
from .puestos import DetectorPuestos
from .roles import es_columna_responsable, rol


def rol_sin_descriptivo(celda):
    """Texto de una celda de la columna Responsable que no coincide con ningun descriptivo.

    Toda celda de esa columna es un rol aunque no empiece con 'Jefe', 'Gerente'... ("comprador",
    "Comité de compras", "analistas").
    """
    t = celda.replace("[CELDA COMBINADA]", "").strip()
    return t if re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3}", t) and len(t.split()) <= 8 else ""


@dataclass
class FilaParticipacion:
    puesto: object               # Puesto
    procedimiento: str
    rol: str
    coincidencia: str
    seccion: str
    evidencia: str


@dataclass
class Participaciones:
    filas: List[FilaParticipacion] = field(default_factory=list)
    sin_descriptivo: Dict[str, set] = field(default_factory=collections.OrderedDict)   # rol -> {procedimientos}
    ambiguas: Dict[str, tuple] = field(default_factory=collections.OrderedDict)        # frase -> ({procs}, candidatos)

    def resumen_por_puesto(self):
        """[(Puesto, {procedimientos}, Counter de roles)] ordenado por cantidad de procedimientos distintos.

        Se calcula sobre todas las filas: es la tabla para contar quien concentra mas procedimientos.
        """
        res = collections.OrderedDict()
        for f in self.filas:
            r = res.setdefault(f.puesto.codigo, (f.puesto, set(), collections.Counter()))
            r[1].add(f.procedimiento)
            r[2][f.rol] += 1
        return sorted(res.values(), key=lambda r: (-len(r[1]), r[0].codigo))

    def puestos_con_participacion(self):
        return {f.puesto.codigo for f in self.filas}


def calcular_participacion(corpus, procedimientos, detector=None):
    detector = detector or DetectorPuestos.desde_corpus(corpus)
    p = Participaciones()
    vistos = set()
    for c in procedimientos:
        for sec, col, texto, linea in corpus.celdas(c):
            menciones = detector.detectar(texto, area_de(c))
            if not menciones and es_columna_responsable(col):
                rol_libre = rol_sin_descriptivo(texto)
                if rol_libre:
                    p.sin_descriptivo.setdefault(rol_libre, set()).add(c)
                continue
            for m in menciones:
                if m.tipo == "sin descriptivo":
                    p.sin_descriptivo.setdefault(m.frase, set()).add(c)
                    continue
                if m.tipo == "ambigua":
                    p.ambiguas.setdefault(m.frase, (set(), m.candidatos))[0].add(c)
                    continue
                r = rol(col, oracion_con(texto, m.frase), sec)
                if (m.puesto.codigo, c, r) in vistos:
                    continue
                vistos.add((m.puesto.codigo, c, r))
                p.filas.append(FilaParticipacion(m.puesto, c, r,
                                                 "exacta" if m.tipo == "exacta" else f"{m.etiqueta}: «{m.frase}»",
                                                 sec, linea))
    return p
