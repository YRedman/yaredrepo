import collections

from ... import VERSION
from ...comun.esquema import tipo_de_fila
from ...comun.tipos import TIPOS_AREA, tipo as tipo_documento
from ...comun.texto import norm
from .base import Comando


def _inventariados_por_area_y_tipo(cp):
    esperado = collections.Counter()
    for f in cp.inventario:
        esperado[((f.get("codigo_departamento") or "").upper(), tipo_de_fila(f, ""))] += 1
    return esperado


def _tipos_presentes(cp, esperado):
    """Tipos con algun documento o inventariado (DES y PRD siempre)."""
    return [t for t in TIPOS_AREA if t in ("DES", "PRD") or any(a.codigos(t) for a in cp.areas.values())
            or any(k[1] == t for k in esperado)]


def _tabla_de_areas(cp, tipos, esperado):
    cabecera = ["Código", "Área"] + tipos
    if cp.inventario:
        cabecera += [f"{t} en inventario" for t in tipos]
    filas = []
    for cod, a in sorted(cp.areas.items(), key=lambda kv: norm(kv[1].nombre)):
        fila = [cod, a.nombre] + [len(a.codigos(t)) for t in tipos]
        if cp.inventario:
            fila += [esperado[(cod, t)] for t in tipos]
        filas.append(fila)
    return cabecera, filas


def _notas(s, cp):
    ctx_docs = cp.contexto()
    if ctx_docs:
        s.linea()
        s.linea("Documentos generales (GEN): " + "; ".join(f"{c} {cp.docs[c].titulo}" for c in ctx_docs))
    alternos = {cod: sorted(x for x in v if norm(x) != norm(cp.areas[cod].nombre)) for cod, v in cp.alias.items()}
    alternos = {k: v for k, v in alternos.items() if v}
    if alternos:
        s.linea("Nombres alternos (del glosario): " + "; ".join(f"{cod}: {', '.join(v)}" for cod, v in alternos.items()))
    if cp.kpis:
        s.linea(f"Indicadores (KPIs): {len(cp.kpis)} · consultar con: kpis")
    if cp.extra:
        s.linea("Áreas o entidades sin documentos propios: " + "; ".join(f"{e.nombre} ({e.tipo})" for e in cp.extra))
    if cp.excluidos:
        s.linea(f"Documentos no vigentes excluidos: {len(cp.excluidos)} (para incluirlos: CORPUS_INCLUIR_NO_VIGENTES=1).")


class Catalogo(Comando):
    nombre = "catalogo"
    ayuda = "Areas, codigos y numero de documentos."

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        esperado = _inventariados_por_area_y_tipo(cp)
        tipos = _tipos_presentes(cp, esperado)
        cabecera, filas = _tabla_de_areas(cp, tipos, esperado)
        s.linea(f"CATÁLOGO · corpus.py v{VERSION}")
        s.linea(f"Áreas: {len(cp.areas)} · " + " · ".join(
            f"{tipo_documento(t).plural} ({t}): {sum(len(a.codigos(t)) for a in cp.areas.values())}" for t in tipos))
        s.linea(f"Cobertura: {cp.cobertura()} · corpus completo: {'sí' if cp.completo else 'no'}")
        s.linea()
        s.tabla(cabecera, filas)
        _notas(s, cp)
