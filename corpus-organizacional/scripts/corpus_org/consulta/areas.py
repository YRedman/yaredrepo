"""Nombres alternos de las areas y resolucion del area que escribe el usuario."""

import collections
import difflib
import re

from ..comun.errores import AreaAmbigua, AreaNoEncontrada
from ..comun.markdown import celdas
from ..comun.texto import norm, patron_frase, sin_acentos

RE_PREFIJO_AREA = re.compile(r"^(departamento|gerencia|direccion|area|unidad)\s+(de|del)\s+")
# Un alias tomado del glosario debe parecer una sigla: 'RRHH', 'TI', 'R.H.', 'SST'.
# Asi una fila como "| Responsable | Compras |" no convierte 'Responsable' en nombre del area.
RE_SIGLA = re.compile(r"^[A-ZÁÉÍÓÚÑ0-9][A-ZÁÉÍÓÚÑ0-9&./-]{1,9}$")


def construir_alias(areas, documentos_contexto):
    """{codigo: {nombres}}: nombre oficial, nombre sin 'Departamento de' y siglas del glosario."""
    alias = collections.defaultdict(set)
    nombres = {norm(a.nombre): cod for cod, a in areas.items() if a.nombre}
    for cod, a in areas.items():
        if a.nombre:
            alias[cod].add(a.nombre)
            corto = RE_PREFIJO_AREA.sub("", norm(a.nombre))
            if corto != norm(a.nombre):
                alias[cod].add(corto)
    for d in documentos_contexto:
        for l in d.lineas:
            if not l.startswith("|") or l.startswith("|---"):
                continue
            cel = celdas(l)
            if len(cel) < 2:
                continue
            for sigla, nombre in ((cel[0], cel[1]), (cel[1], cel[0])):
                if norm(nombre) in nombres and RE_SIGLA.match(sigla) and norm(sigla) != norm(nombre):
                    alias[nombres[norm(nombre)]].add(sigla)
    return alias


def patrones_area(alias_area):
    """Expresiones que reconocen una mencion explicita del area en un texto sin acentos.

    Un nombre de una sola palabra debe aparecer con mayuscula inicial ('Compras', no 'compras')
    y una sigla tal como esta escrita ('ALM'); los nombres compuestos no distinguen mayusculas.
    """
    pats = []
    for nombre in alias_area:
        base = sin_acentos(nombre).strip()
        if len(base.split()) == 1:
            if len(base) < 2:
                continue
            pats.append(patron_frase(base[0].upper() + base[1:]))
        else:
            pats.append(patron_frase(base, re.I))
    return pats


class ResolutorAreas:
    """Traduce lo que escribe el usuario (codigo, nombre, alias o parecido) al codigo del area."""

    def __init__(self, areas, alias):
        self.areas = areas
        self.alias = alias

    def _disponibles(self, codigos=None):
        return [(cod, self.areas[cod].nombre) for cod in (codigos or self.areas)]

    def resolver(self, texto):
        """Devuelve ``(codigo, interpretado)``; ``interpretado`` es True si se eligio por parecido."""
        t = norm(texto)
        if t.upper() in self.areas:
            return t.upper(), False
        for cod, a in self.areas.items():
            if norm(a.nombre) == t:
                return cod, False
        for cod, nombres in self.alias.items():
            if any(norm(x) == t for x in nombres):
                return cod, False
        parcial = [cod for cod, a in self.areas.items()
                   if t and a.nombre and (t in norm(a.nombre) or norm(a.nombre) in t)]
        if len(parcial) == 1:
            return parcial[0], True
        if parcial:
            raise AreaAmbigua(texto, self._disponibles(parcial))
        cerca = difflib.get_close_matches(t, [norm(a.nombre) for a in self.areas.values()], n=5, cutoff=0.6)
        candidatos = [cod for cod, a in self.areas.items() if norm(a.nombre) in cerca]
        if len(candidatos) == 1:
            return candidatos[0], True
        if candidatos:
            raise AreaAmbigua(texto, self._disponibles(candidatos))
        raise AreaNoEncontrada(texto, self._disponibles())
