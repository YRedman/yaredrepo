import collections

from ...comun.texto import recortar_palabras
from ...comun.tipos import es_general
from ..extraccion import TIPOS_NORMATIVA, normativa
from .base import Comando

ORDEN_TIPOS = ["Ley", "Reglamento", "Norma", "Política", "Protocolo", "Procedimiento", "Manual", "Instructivo",
               "Código de documento"]
assert set(ORDEN_TIPOS) == {t for t, _ in TIPOS_NORMATIVA}
PALABRAS_CITA = 60


def citas_de(cp, codigos):
    """[(codigo, documento, tipo de referencia, cita literal, seccion)] de los documentos indicados."""
    res = []
    for c in codigos:
        for tipo, mencion, seccion in normativa(cp.doc(c)):
            res.append((c, cp.nombre(c), tipo, mencion, seccion))
    return res


def agrupar_por_tipo(citas):
    """{tipo de referencia: [cita]} en el orden de ORDEN_TIPOS (solo los tipos con citas)."""
    grupos = collections.OrderedDict((t, []) for t in ORDEN_TIPOS)
    for c in citas:
        grupos[c[2]].append(c)
    return collections.OrderedDict((t, v) for t, v in grupos.items() if v)


def codigos_con_texto(ctx, area=None):
    """Documentos de area (no generales) con texto, de un area o de todo el corpus."""
    return ctx.filtrar_area(sorted(c for c in ctx.corpus.docs if not es_general(c)), area)


class Normativa(Comando):
    nombre = "normativa"
    ayuda = "Citas de leyes, reglamentos, normas, politicas, protocolos y otros documentos (literales)."

    def configurar(self, parser):
        parser.add_argument("--area", default=None)

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        codigos = codigos_con_texto(ctx, args.area)
        citas = citas_de(cp, codigos)
        grupos = agrupar_por_tipo(citas)
        s.linea(f"NORMATIVA CITADA · {len(citas)} citas en {len({c[0] for c in citas})} de {len(codigos)} documentos"
                + (f" · área: {cp.areas[ctx.area(args.area)].nombre}" if args.area else ""))
        s.linea("Cada cita es el texto literal donde el documento menciona la referencia; no se interpreta si "
                "la referencia existe o aplica.")
        if not citas:
            s.linea("Sin citas de normativa en los documentos revisados.")
            return
        for tipo, lista in grupos.items():
            s.seccion(f"{tipo} ({len(lista)} citas en {len({c[0] for c in lista})} documentos)")
            s.tabla(["Código", "Documento", "Tipo de referencia", "Cita literal", "Sección"],
                    [[c, d, t, recortar_palabras(m, PALABRAS_CITA), sec] for c, d, t, m, sec in lista])
