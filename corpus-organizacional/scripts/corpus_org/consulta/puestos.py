"""Deteccion de puestos (con descriptivo) mencionados en un texto."""

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


class DetectorPuestos:
    """Reconoce puestos por nombre exacto y, si no, por parecido.

    Una mencion parecida a varios puestos con la misma puntuacion queda como 'ambigua' y no se
    asigna a ninguno (antes se asignaba al primero, lo que creaba relaciones falsas).
    """

    def __init__(self, puestos):
        self.puestos = {norm(p.nombre): p for p in puestos}
        claves = sorted(self.puestos, key=len, reverse=True)
        self._exacto = (re.compile(r"(?<!\w)(" + "|".join(re.escape(k) for k in claves) + r")(?!\w)")
                        if claves else None)

    @classmethod
    def desde_corpus(cls, corpus):
        puestos = []
        for c, f in corpus.meta.items():
            if c.startswith("D-"):
                nombre = (f.get("nombre_puesto") or f.get("nombre") or "").strip()
                if nombre:
                    puestos.append(Puesto(c, nombre))
        return cls(puestos)

    def _puntuar(self, frase_norm, clave):
        r = difflib.SequenceMatcher(None, frase_norm, clave).ratio()
        palabras = frase_norm.split()
        cola = set(palabras) - PALABRAS_VACIAS
        if cola and cola <= set(clave.split()) and palabras[0] == clave.split()[0]:
            r = max(r, 0.86)
        return r

    def _parecido(self, frase):
        nf = norm(frase)
        puntos = sorted(((self._puntuar(nf, k), k) for k in self.puestos), reverse=True)
        if not puntos or puntos[0][0] < UMBRAL_PROBABLE:
            return MencionPuesto(frase, "sin descriptivo")
        mejor = puntos[0][0]
        empatados = [self.puestos[k] for r, k in puntos if mejor - r <= MARGEN_EMPATE]
        if len(empatados) > 1:
            return MencionPuesto(frase, "ambigua", ratio=mejor, candidatos=empatados)
        return MencionPuesto(frase, "probable", self.puestos[puntos[0][1]], mejor)

    def detectar(self, texto):
        """Menciones de puestos en ``texto``: exactas primero y luego frases tipo 'Jefe de ...'."""
        n = norm(texto)
        hallados, usados = [], set()
        if self._exacto is not None:
            for m in self._exacto.finditer(n):
                clave = m.group(1)
                if not any(clave in u for u in usados):
                    hallados.append(MencionPuesto(self.puestos[clave].nombre, "exacta", self.puestos[clave]))
                    usados.add(clave)
        for m in PATRON_PUESTO.finditer(texto):
            frase = m.group(1).strip()
            nf = norm(frase)
            if len(nf.split()) < 2 or any(nf in u or u in nf for u in usados):
                continue
            hallados.append(self._parecido(frase))
            usados.add(nf)
        return hallados
