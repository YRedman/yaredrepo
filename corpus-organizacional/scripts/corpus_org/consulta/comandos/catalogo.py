import collections

from ... import VERSION
from ...comun.esquema import tipo_desde_texto
from ...comun.texto import norm
from .base import Comando


class Catalogo(Comando):
    nombre = "catalogo"
    ayuda = "Areas, codigos y numero de documentos."

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        esperado = collections.Counter()
        for f in cp.inventario:
            t = tipo_desde_texto(f.get("tipo")) or "P"
            esperado[((f.get("codigo_departamento") or "").upper(), t)] += 1
        cab = ["Código", "Área", "Descriptivos", "Procedimientos"]
        if cp.inventario:
            cab += ["Descriptivos en inventario", "Procedimientos en inventario"]
        filas = []
        for cod, a in sorted(cp.areas.items(), key=lambda kv: norm(kv[1].nombre)):
            fila = [cod, a.nombre, len(a.descriptivos), len(a.procedimientos)]
            if cp.inventario:
                fila += [esperado[(cod, "D")], esperado[(cod, "P")]]
            filas.append(fila)
        s.linea(f"CATÁLOGO · corpus.py v{VERSION}")
        s.linea(f"Áreas: {len(cp.areas)} · Descriptivos: {sum(len(a.descriptivos) for a in cp.areas.values())} · "
                f"Procedimientos: {sum(len(a.procedimientos) for a in cp.areas.values())}")
        s.linea()
        s.tabla(cab, filas)
        ctx_docs = cp.contexto()
        if ctx_docs:
            s.linea()
            s.linea("Materiales de contexto: " + "; ".join(f"{c} {cp.docs[c].titulo}" for c in ctx_docs))
        alternos = {cod: sorted(x for x in v if norm(x) != norm(cp.areas[cod].nombre)) for cod, v in cp.alias.items()}
        alternos = {k: v for k, v in alternos.items() if v}
        if alternos:
            s.linea("Nombres alternos (del glosario): "
                    + "; ".join(f"{cod}: {', '.join(v)}" for cod, v in alternos.items()))
        if cp.excluidos:
            s.linea(f"Documentos no vigentes excluidos: {len(cp.excluidos)} "
                    "(para incluirlos: CORPUS_INCLUIR_NO_VIGENTES=1).")
