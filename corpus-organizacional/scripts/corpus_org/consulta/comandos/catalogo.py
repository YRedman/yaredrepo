import collections

from ... import VERSION
from ...comun.esquema import tipo_desde_texto
from ...comun.tipos import TIPOS_AREA, tipo as tipo_documento
from ...comun.texto import norm
from .base import Comando


class Catalogo(Comando):
    nombre = "catalogo"
    ayuda = "Areas, codigos y numero de documentos."

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        esperado = collections.Counter()
        for f in cp.inventario:
            t = tipo_desde_texto(f.get("tipo")) or (f.get("codigo") or "").split("-")[0].upper()
            esperado[((f.get("codigo_departamento") or "").upper(), t)] += 1
        # tipos con algun documento o inventariado (DES y PRD siempre)
        tipos = [t for t in TIPOS_AREA if t in ("DES", "PRD") or any(a.codigos(t) for a in cp.areas.values())
                 or any(k[1] == t for k in esperado)]
        cab = ["Código", "Área"] + tipos
        if cp.inventario:
            cab += [f"{t} en inventario" for t in tipos]
        filas = []
        for cod, a in sorted(cp.areas.items(), key=lambda kv: norm(kv[1].nombre)):
            fila = [cod, a.nombre] + [len(a.codigos(t)) for t in tipos]
            if cp.inventario:
                fila += [esperado[(cod, t)] for t in tipos]
            filas.append(fila)
        s.linea(f"CATÁLOGO · corpus.py v{VERSION}")
        s.linea(f"Áreas: {len(cp.areas)} · " + " · ".join(
            f"{tipo_documento(t).plural} ({t}): {sum(len(a.codigos(t)) for a in cp.areas.values())}" for t in tipos))
        s.linea(f"Cobertura: {cp.cobertura()} · corpus completo: {'sí' if cp.completo else 'no'}")
        s.linea()
        s.tabla(cab, filas)
        ctx_docs = cp.contexto()
        if ctx_docs:
            s.linea()
            s.linea("Documentos generales (GEN): " + "; ".join(f"{c} {cp.docs[c].titulo}" for c in ctx_docs))
        alternos = {cod: sorted(x for x in v if norm(x) != norm(cp.areas[cod].nombre)) for cod, v in cp.alias.items()}
        alternos = {k: v for k, v in alternos.items() if v}
        if alternos:
            s.linea("Nombres alternos (del glosario): "
                    + "; ".join(f"{cod}: {', '.join(v)}" for cod, v in alternos.items()))
        if cp.kpis:
            s.linea(f"Indicadores (KPIs): {len(cp.kpis)} · consultar con: kpis")
        if cp.extra:
            s.linea("Áreas o entidades sin documentos propios: "
                    + "; ".join(f"{e.nombre} ({e.tipo})" for e in cp.extra))
        if cp.excluidos:
            s.linea(f"Documentos no vigentes excluidos: {len(cp.excluidos)} "
                    "(para incluirlos: CORPUS_INCLUIR_NO_VIGENTES=1).")
