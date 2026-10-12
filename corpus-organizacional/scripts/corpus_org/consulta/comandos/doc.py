from ...comun.esquema import RE_SECCION
from ...comun.texto import norm
from .base import Comando


class Documento(Comando):
    nombre = "doc"
    ayuda = "Texto completo y literal de un documento (o de una seccion)."

    def configurar(self, parser):
        parser.add_argument("codigo")
        parser.add_argument("--seccion", default=None)

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        c = ctx.exigir_documento(args.codigo)
        d = cp.docs[c]
        if not args.seccion:
            s.linea(f"[{d.archivo} · líneas {d.inicio + 1}-{d.inicio + len(d.lineas)}]")
            s.linea("\n".join(d.lineas))
            return
        objetivo = norm(args.seccion)
        imprimir, nivel, hallado = False, 0, False
        for l in d.lineas:
            m = RE_SECCION.match(l)
            if m:
                n = len(m.group(1))
                if imprimir and n <= nivel:
                    imprimir = False
                if not imprimir and objetivo in norm(m.group(2)):
                    imprimir, nivel, hallado = True, n, True
            if imprimir:
                s.linea(l)
        if not hallado:
            s.linea(f"NO ENCONTRADO: {c} no tiene una sección que contenga '{args.seccion}'. Secciones:")
            s.lista(t for t, _ in cp.secciones(c))
