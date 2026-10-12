"""Menciones explicitas entre areas (por nombre, sigla o puesto con descriptivo)."""

from dataclasses import dataclass

from ..comun.esquema import area_de
from ..comun.texto import sin_acentos
from .areas import patrones_area
from .puestos import DetectorPuestos
from .roles import verbo


@dataclass
class Mencion:
    codigo: str          # documento donde aparece la mencion
    destino: str         # area mencionada
    seccion: str
    via: str             # "área" o "puesto <nombre> (<codigo>, <tipo>)"
    verbo: str
    linea: str

    @property
    def area_origen(self):
        return area_de(self.codigo)


class AnalizadorRelaciones:
    def __init__(self, corpus, detector=None):
        self.corpus = corpus
        self.detector = detector or DetectorPuestos.desde_corpus(corpus)
        self.patrones = {cod: patrones_area(corpus.alias.get(cod, [])) for cod in corpus.areas}

    def _via_area(self, texto, destino):
        for p in self.patrones[destino]:
            m = p.search(texto)
            if m:
                return m.group(0)
        return None

    def menciones(self, origen, destinos):
        """Menciones de las areas ``destinos`` en los documentos del area ``origen``."""
        res = []
        for c in self.corpus.areas[origen].codigos():
            for sec, l in self.corpus.cuerpo(c):
                texto = sin_acentos(l)
                puestos = None
                for d in destinos:
                    if d == origen:
                        continue
                    via, frase = None, None
                    frase_area = self._via_area(texto, d)
                    if frase_area:
                        via, frase = "área", frase_area
                    else:
                        if puestos is None:
                            puestos = [m for m in self.detector.detectar(l, origen) if m.asignada]
                        m = next((m for m in puestos if m.puesto.area == d), None)
                        if m:
                            via, frase = f"puesto {m.puesto.nombre} ({m.puesto.codigo}, {m.etiqueta})", m.frase
                    if via:
                        res.append(Mencion(c, d, sec, via, verbo(l, frase), l))
        return res
