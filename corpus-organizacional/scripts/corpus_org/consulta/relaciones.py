"""Menciones explicitas entre areas (por nombre, sigla o puesto con descriptivo) y menciones no resueltas."""

import collections
import re
from dataclasses import dataclass

from ..comun.esquema import area_de
from ..comun.texto import norm
from .areas import patrones_area
from .entidades import quitar_exclusiones
from .puestos import DetectorPuestos
from .roles import verbo

# Unidades organizativas escritas en el texto ("Gerencia de Finanzas", "Comité de Compras").
RE_UNIDAD = re.compile(
    r"\b((?:Departamento|Gerencia|Direcci[oó]n|[ÁA]rea|Unidad|Coordinaci[oó]n|Jefatura|Comit[eé])\s+"
    r"(?:de\s+la\s+|de\s+los\s+|de\s+|del\s+)?[A-ZÁÉÍÓÚÑ][\wáéíóúñü]+"
    r"(?:\s+(?:y|e|de|del|la)?\s*[A-ZÁÉÍÓÚÑ][\wáéíóúñü]+){0,3})")
RE_PREFIJO_UNIDAD = re.compile(r"^(departamento|gerencia|direccion|area|unidad|coordinacion|jefatura|comite)\s+"
                               r"(de la|de los|de|del)?\s*")


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


class NoResueltas:
    """Menciones que no se pueden atribuir a un area del corpus: {(mencion, tipo): {codigos}}.

    No son relaciones; se informan para validarlas en la reunion.
    """

    def __init__(self):
        self.menciones = collections.OrderedDict()

    def agregar(self, frase, tipo, codigo):
        self.menciones.setdefault((frase, tipo), set()).add(codigo)

    def ordenadas(self):
        return sorted(self.menciones.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    def __bool__(self):
        return bool(self.menciones)


class AnalizadorRelaciones:
    def __init__(self, corpus, detector=None):
        self.corpus = corpus
        self.detector = detector or DetectorPuestos.desde_corpus(corpus)
        self.patrones = {cod: patrones_area(corpus.alias.get(cod, [])) for cod in corpus.areas}
        nombres_areas = {norm(a.nombre) for a in corpus.areas.values() if a.nombre}
        # entidades sin documentos (las internas con el nombre de un area del corpus ya son alias de esa area)
        self.extra = [(e, e.patrones()) for e in corpus.extra if norm(e.nombre) not in nombres_areas]
        self.nombres_conocidos = ({norm(n) for cod in corpus.areas for n in corpus.alias.get(cod, [])}
                                  | {norm(n) for e in corpus.extra for n in e.nombres})

    def _via_area(self, texto, destino):
        for p in self.patrones[destino]:
            m = p.search(texto)
            if m:
                return m.group(0)
        return None

    def menciones(self, origen, destinos, no_resueltas=None):
        """Menciones de las areas ``destinos`` en los documentos del area ``origen``.

        Si se pasa ``no_resueltas`` (NoResueltas), acumula ahi las menciones de entidades sin documentos,
        unidades organizativas desconocidas y puestos ambiguos.
        """
        res = []
        for c in self.corpus.areas[origen].codigos():
            for sec, l in self.corpus.cuerpo(c):
                texto = quitar_exclusiones(l, self.corpus.exclusiones)
                puestos = self.detector.detectar(l, origen)
                asignados = [m for m in puestos if m.asignada]
                for d in destinos:
                    if d == origen:
                        continue
                    via, frase = None, None
                    frase_area = self._via_area(texto, d)
                    if frase_area:
                        via, frase = "área", frase_area
                    else:
                        m = next((m for m in asignados if m.puesto.area == d), None)
                        if m:
                            via, frase = f"puesto {m.puesto.nombre} ({m.puesto.codigo}, {m.etiqueta})", m.frase
                    if via:
                        res.append(Mencion(c, d, sec, via, verbo(l, frase), l))
                if no_resueltas is not None:
                    self._no_resueltas(c, l, texto, puestos, no_resueltas)
        return res

    def _no_resueltas(self, codigo, linea, texto, puestos, no_resueltas):
        """``linea`` es el texto original (para citar las unidades tal como estan escritas) y ``texto``
        la version sin acentos ni frases excluidas."""
        for e, pats in self.extra:
            if any(p.search(texto) for p in pats):
                no_resueltas.agregar(e.nombre, f"sin documentos ({e.tipo})", codigo)
        for m in RE_UNIDAD.finditer(linea):
            frase = m.group(1).strip()
            nf = norm(frase)
            if any(x in nf for x in self.corpus.exclusiones):
                continue
            corto = RE_PREFIJO_UNIDAD.sub("", nf)
            if nf in self.nombres_conocidos or corto in self.nombres_conocidos:
                continue
            if corto and any(corto in x for x in self.nombres_conocidos):
                continue
            no_resueltas.agregar(frase, "unidad no identificada", codigo)
        for m in puestos:
            if m.tipo == "ambigua":
                no_resueltas.agregar(m.frase, "puesto ambiguo: " + ", ".join(p.codigo for p in m.candidatos), codigo)
