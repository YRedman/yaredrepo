import collections

from ...comun.esquema import area_de
from ..cadena import calcular_enlaces, faltantes, tipo_de_codigo_cliente, vecinos
from ..salida import resumir_lista
from .base import Comando

MAX_FALTANTES = 40


class Cadena(Comando):
    nombre = "cadena"
    ayuda = "Cadena documental: que documento cita a cual (códigos internos resueltos contra el corpus)."

    def configurar(self, parser):
        parser.add_argument("codigo", nargs="?", default=None, help="Documento del que se quiere la cadena.")
        parser.add_argument("--profundidad", type=int, default=2, help="Saltos hacia delante y hacia atrás (2 por defecto).")
        parser.add_argument("--area", default=None)

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        enlaces = calcular_enlaces(cp.meta)
        if args.codigo:
            return self._de_documento(ctx, enlaces, ctx.exigir_documento(args.codigo), max(1, args.profundidad))
        if args.area:
            codigos = set(ctx.filtrar_area(sorted(cp.meta), args.area))
            enlaces = [e for e in enlaces if e.origen in codigos or e.destino in codigos]
        resueltos = [e for e in enlaces if e.resuelto]
        s.linea(f"CADENA DOCUMENTAL · {len(resueltos)} citas entre documentos del corpus · "
                f"{len({e.citado for e in enlaces if not e.resuelto})} códigos citados sin documento en el corpus")
        s.linea("Un código citado se une con el código interno de un documento del corpus si es igual o es su final "
                "(sin el prefijo de gerencia); no se interpreta qué relación hay entre ellos.")
        por_area = collections.Counter((area_de(e.origen), area_de(e.destino)) for e in resueltos
                                       if area_de(e.origen) != area_de(e.destino))
        if por_area:
            s.linea()
            s.linea("## Citas entre áreas")
            s.tabla(["Área que cita", "Área citada", "Citas"],
                    [[cp.areas[a].nombre if a in cp.areas else a, cp.areas[b].nombre if b in cp.areas else b, n]
                     for (a, b), n in por_area.most_common()])
        entradas = collections.Counter(e.destino for e in resueltos)
        if entradas:
            s.linea()
            s.linea("## Documentos más citados")
            s.tabla(["Código", "Documento", "Citado por"],
                    [[c, cp.nombre(c), n] for c, n in entradas.most_common(15)])
        falta = faltantes(enlaces)
        if falta:
            s.linea()
            s.linea(f"## Documentos citados que faltan en el corpus ({len(falta)})")
            s.linea("Son oportunidades: documentos que otros mencionan y todavía no se han entregado.")
            s.tabla(["Código citado", "Tipo", "Citado por"],
                    [[c, tipo_de_codigo_cliente(c), resumir_lista(sorted(o), 6)]
                     for c, o in list(falta.items())[:MAX_FALTANTES]])
            if len(falta) > MAX_FALTANTES:
                s.linea(f"… y {len(falta) - MAX_FALTANTES} más (hoja «Cadena documental» de la matriz).")
        if not enlaces:
            s.linea("Sin citas entre documentos.")

    def _de_documento(self, ctx, enlaces, codigo, profundidad):
        cp, s = ctx.corpus, ctx.salida
        s.linea(f"CADENA DE {codigo} · {cp.nombre(codigo)}")
        for titulo, sentido in (("Cita a (hacia delante)", "sale"), ("Citado por (hacia atrás)", "entra")):
            v = vecinos(enlaces, codigo, sentido, profundidad)
            s.linea()
            s.linea(f"## {titulo}: {len(v)} documentos")
            if v:
                s.tabla(["Código", "Documento", "Saltos"], [[c, cp.nombre(c), d] for c, d in sorted(v.items(), key=lambda kv: (kv[1], kv[0]))])
        propios = [e for e in enlaces if e.origen == codigo and not e.resuelto]
        if propios:
            s.linea()
            s.linea(f"## Citados que no están en el corpus ({len(propios)})")
            s.tabla(["Código citado", "Tipo"], [[e.citado, tipo_de_codigo_cliente(e.citado)] for e in propios])
