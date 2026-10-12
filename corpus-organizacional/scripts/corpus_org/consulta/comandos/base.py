"""Contrato de los comandos de consulta y contexto compartido."""

import difflib
from abc import ABC, abstractmethod

from ...comun.errores import CorpusError
from ...comun.esquema import RE_CODIGO, area_de
from ..areas import ResolutorAreas


class Contexto:
    """Lo que necesita un comando para ejecutarse: el corpus y donde escribir."""

    def __init__(self, corpus, salida):
        self.corpus = corpus
        self.salida = salida
        self._resolutor = ResolutorAreas(corpus.areas, corpus.alias)

    def area(self, texto):
        """Codigo del area; avisa si se eligio por parecido para que no pase inadvertido."""
        cod, interpretado = self._resolutor.resolver(texto)
        if interpretado:
            self.salida.linea(f"AVISO: '{texto}' se interpretó como el área {self.corpus.areas[cod].nombre} ({cod}).")
        return cod

    def exigir_documento(self, codigo):
        c = codigo.strip().upper()
        if c in self.corpus.docs:
            return c
        if c in self.corpus.excluidos:
            raise CorpusError(f"{c} está excluido por su estado documental "
                              f"('{self.corpus.excluidos[c]}'). Para consultarlo usa CORPUS_INCLUIR_NO_VIGENTES=1.", 2)
        cerca = difflib.get_close_matches(c, list(self.corpus.docs), n=5, cutoff=0.6)
        raise CorpusError(f"No existe el documento {c}." + (f" ¿Quisiste decir: {', '.join(cerca)}?" if cerca else ""), 2)

    def codigos_objetivo(self, texto, tipo=None):
        """Codigos con texto de un documento (si ``texto`` es un codigo) o de un area."""
        if RE_CODIGO.match(texto.strip()):
            return [self.exigir_documento(texto)]
        a = self.corpus.areas[self.area(texto)]
        return [c for c in a.codigos(tipo) if c in self.corpus.docs]

    def filtrar_area(self, codigos, texto_area):
        if not texto_area:
            return list(codigos)
        cod = self.area(texto_area)
        return [c for c in codigos if not c.startswith("C-") and area_de(c) == cod]


class Comando(ABC):
    """Un subcomando de ``corpus.py``. Para agregar uno nuevo: subclase + registro en ``comandos``."""

    nombre = ""
    ayuda = ""

    def configurar(self, parser):
        """Declara los argumentos del comando."""

    @abstractmethod
    def ejecutar(self, ctx, args):
        """Escribe el resultado en ``ctx.salida``."""
