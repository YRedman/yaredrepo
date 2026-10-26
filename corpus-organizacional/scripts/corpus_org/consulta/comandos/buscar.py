import collections
import re

from ...comun.errores import CorpusError
from ...comun.esquema import area_de
from ...comun.tipos import FILTROS_TIPO, cumple_tipo
from ...comun.texto import norm, patron_termino, recortar_palabras as recortar
from .base import Comando, argumento_tipo

MAX_COINCIDENCIAS_POR_DOC = 4
MAX_FILAS = 80


def fragmento(linea, pats, ancho=110):
    """Ventana de ``ancho`` caracteres alrededor del primer termino hallado, alineada a palabras completas."""
    texto = re.sub(r"\s+", " ", linea.strip().strip("|").replace("|", "·"))
    nl = norm(texto)
    pos, fin_termino = min(((m.start(), m.end()) for p in pats for m in [p.search(nl)] if m), default=(0, 0))
    pos, fin_termino = min(pos, len(texto)), min(fin_termino, len(texto))
    ini = max(0, pos - ancho // 2)
    fin = max(ini + ancho, fin_termino)
    while 0 < ini < pos and not texto[ini - 1].isspace():       # no empezar en medio de una palabra
        ini += 1
    while len(texto) > fin > fin_termino and not texto[fin].isspace():   # ni terminar en medio de una palabra
        fin -= 1
    return ("…" if ini > 0 else "") + texto[ini:fin].strip() + ("…" if fin < len(texto) else "")


class Buscar(Comando):
    nombre = "buscar"
    ayuda = "Busqueda literal (sin distinguir mayusculas ni acentos)."

    def configurar(self, parser):
        parser.add_argument("terminos", metavar="termino1|termino2")
        parser.add_argument("--area", default=None)
        parser.add_argument("--tipo", type=argumento_tipo, default=None, help="|".join(FILTROS_TIPO))

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        terminos = [t.strip() for t in args.terminos.split("|") if t.strip()]
        if not terminos:
            raise CorpusError("Indica al menos un término.")
        cods = self._documentos(ctx, args)
        pats = [patron_termino(t) for t in terminos]
        resultados = _coincidencias(cp, cods, pats)
        s.linea(f"BÚSQUEDA · términos: {', '.join(terminos)}" + (f" · área: {args.area}" if args.area else "")
                + (f" · tipo: {args.tipo}" if args.tipo else ""))
        s.linea(f"Documentos revisados: {len(cods)} · con coincidencias: {len(resultados)} · "
                f"coincidencias totales: {sum(len(v) for v in resultados.values())}")
        if not resultados:
            s.linea("Sin coincidencias literales. Prueba con sinónimos o variantes (separados con |).")
            return
        filas = _filas(cp, resultados, pats)
        s.linea()
        s.linea("Todos los documentos con coincidencias: " + ", ".join(f"{c} ({len(v)})" for c, v in resultados.items()))
        s.linea()
        s.tabla(["Código", "Documento", "Área", "Sección", "Fragmento"], filas[:MAX_FILAS])
        if len(filas) > MAX_FILAS:
            s.linea(f"Se muestran {MAX_FILAS} de {len(filas)} filas. Para ver el resto, acota con --area o --tipo, "
                    "o lee cada documento con doc <CÓDIGO>.")

    @staticmethod
    def _documentos(ctx, args):
        """Los documentos donde se busca: todos, o los de un area y/o un tipo."""
        cods = sorted(ctx.corpus.docs)
        if args.area:
            cod = ctx.area(args.area)
            cods = [c for c in cods if area_de(c) == cod]
        if args.tipo:
            cods = [c for c in cods if cumple_tipo(c, args.tipo)]
        return cods


def _coincidencias(cp, cods, pats):
    """{codigo: [(seccion, linea)]} de las lineas (o el titulo) donde aparece algun termino."""
    resultados = collections.OrderedDict()
    for c in cods:
        for sec, l in cp.cuerpo(c):
            nl = norm(l)
            if any(p.search(nl) for p in pats):
                resultados.setdefault(c, []).append((sec, l))
        titulo = cp.docs[c].titulo
        if c not in resultados and any(p.search(norm(titulo)) for p in pats):
            resultados[c] = [("(título)", titulo)]
    return resultados


def _filas(cp, resultados, pats):
    filas = []
    for c, lista in resultados.items():
        f = cp.meta.get(c, {})
        for sec, l in lista[:MAX_COINCIDENCIAS_POR_DOC]:
            filas.append([c, cp.nombre(c), f.get("departamento", ""), recortar(sec, 8), fragmento(l, pats)])
        if len(lista) > MAX_COINCIDENCIAS_POR_DOC:
            filas.append([c, "", "", "", f"… y {len(lista) - MAX_COINCIDENCIAS_POR_DOC} coincidencias más (ver doc {c})"])
    return filas
