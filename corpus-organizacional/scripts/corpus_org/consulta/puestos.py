"""Deteccion de puestos (con descriptivo) mencionados en un texto."""

import collections
import difflib
import re
from dataclasses import dataclass, field
from typing import List, Optional

from ..comun.esquema import area_de
from ..comun.texto import norm

PATRON_PUESTO = re.compile(
    r"\b((?:Gerente|Jefe|Jefa|Director|Directora|Coordinador|Coordinadora|Supervisor|Supervisora|Analista|"
    r"Encargado|Encargada|Auxiliar|Asistente|Técnico|Técnica|Especialista|Inspector|Inspectora|Responsable|"
    r"Comprador|Compradora|Recepcionista|Oficial|Ejecutivo|Ejecutiva|Representante|Operador|Operadora)"
    r"(?:\s+(?:de|del|la|las|los|el|y|en)?\s*[A-ZÁÉÍÓÚÑ][\wáéíóúñü]+){0,4})")
UMBRAL_PROBABLE = 0.85
MARGEN_EMPATE = 0.02
PALABRAS_VACIAS = {"de", "del", "la", "y"}


@dataclass(frozen=True)
class Puesto:
    codigo: str        # codigo del descriptivo (D-XXX-NN)
    nombre: str

    @property
    def area(self):
        return area_de(self.codigo)


@dataclass
class MencionPuesto:
    frase: str
    tipo: str                               # exacta | probable | ambigua | sin descriptivo
    puesto: Optional[Puesto] = None
    ratio: float = 1.0
    candidatos: List[Puesto] = field(default_factory=list)

    @property
    def asignada(self):
        return self.puesto is not None

    @property
    def etiqueta(self):
        return "exacta" if self.tipo == "exacta" else f"{self.tipo} ({self.ratio:.2f})"


def elegir(candidatos, area_origen=None):
    """El puesto si no hay duda; si varios, el del area del documento que menciona. None = ambiguo.

    Dos areas pueden tener un puesto con el mismo nombre ("Asistente Administrativo"): una mencion
    en un documento de Compras es el de Compras; en un documento de un tercer area no se sabe cual es.
    """
    distintos = {p.codigo: p for p in candidatos}
    if len(distintos) == 1:
        return next(iter(distintos.values()))
    misma_area = [p for p in distintos.values() if p.area == area_origen]
    return misma_area[0] if len(misma_area) == 1 else None


class DetectorPuestos:
    """Reconoce puestos por nombre exacto y, si no, por parecido.

    Una mencion que corresponde a varios puestos (mismo nombre en varias areas, o nombres parecidos con
    la misma puntuacion) solo se asigna si el area del documento la resuelve; si no, queda 'ambigua'.
    """

    def __init__(self, puestos):
        self.puestos = collections.defaultdict(list)    # nombre normalizado -> [Puesto]
        for p in puestos:
            self.puestos[norm(p.nombre)].append(p)
        claves = sorted(self.puestos, key=len, reverse=True)
        self._exacto = (re.compile(r"(?<!\w)(" + "|".join(re.escape(k) for k in claves) + r")(?!\w)")
                        if claves else None)

    @classmethod
    def desde_corpus(cls, corpus):
        puestos = []
        for c, f in sorted(corpus.meta.items()):
            if c.startswith("D-"):
                nombre = (f.get("nombre_puesto") or f.get("nombre") or "").strip()
                if nombre:
                    puestos.append(Puesto(c, nombre))
        return cls(puestos)

    @staticmethod
    def _puntuar(frase_norm, clave):
        r = difflib.SequenceMatcher(None, frase_norm, clave).ratio()
        palabras = frase_norm.split()
        cola = set(palabras) - PALABRAS_VACIAS
        if cola and cola <= set(clave.split()) and palabras[0] == clave.split()[0]:
            r = max(r, 0.86)
        return r

    @staticmethod
    def _resolver(frase, tipo, candidatos, ratio, area_origen):
        puesto = elegir(candidatos, area_origen)
        if puesto is None:
            unicos = list({p.codigo: p for p in candidatos}.values())
            return MencionPuesto(frase, "ambigua", ratio=ratio, candidatos=unicos)
        return MencionPuesto(frase, tipo, puesto, ratio)

    def _parecido(self, frase, area_origen):
        nf = norm(frase)
        puntos = sorted(((self._puntuar(nf, k), k) for k in self.puestos), reverse=True)
        if not puntos or puntos[0][0] < UMBRAL_PROBABLE:
            return MencionPuesto(frase, "sin descriptivo")
        mejor = puntos[0][0]
        candidatos = [p for r, k in puntos if mejor - r <= MARGEN_EMPATE for p in self.puestos[k]]
        return self._resolver(frase, "probable", candidatos, mejor, area_origen)

    def detectar(self, texto, area_origen=None):
        """Menciones de puestos en ``texto``: exactas primero y luego frases tipo 'Jefe de ...'.

        ``area_origen`` es el area del documento donde aparece el texto; resuelve los homonimos.
        """
        n = norm(texto)
        hallados, usados = [], set()
        if self._exacto is not None:
            for m in self._exacto.finditer(n):
                clave = m.group(1)
                if not any(clave in u for u in usados):
                    cands = self.puestos[clave]
                    hallados.append(self._resolver(cands[0].nombre, "exacta", cands, 1.0, area_origen))
                    usados.add(clave)
        for m in PATRON_PUESTO.finditer(texto):
            frase = m.group(1).strip()
            nf = norm(frase)
            if len(nf.split()) < 2 or any(nf in u or u in nf for u in usados):
                continue
            hallados.append(self._parecido(frase, area_origen))
            usados.add(nf)
        return hallados
