"""Indicadores (KPIs) transcritos en kpis.csv y su relacion por terminos con los documentos.

Columnas reconocidas (las que falten quedan vacias): id, grupo, gestion, indicador, meta, medicion, unidad,
estado_segun_leyenda, periodo, observaciones, terminos_busqueda (terminos separados por '|').
"""

from ..comun.texto import norm, patron_termino


def terminos(kpi):
    return [t.strip() for t in (kpi.get("terminos_busqueda") or "").split("|") if t.strip()]


def sin_medicion(kpi):
    """Una medicion vacia es 'sin medicion', nunca cero."""
    return not (kpi.get("medicion") or "").strip()


def kpis_relacionados(corpus, codigos, kpis=None):
    """[(kpi, {codigos})] de los documentos que mencionan algun termino de busqueda de cada indicador.

    Es coincidencia de terminos, no una relacion documentada: se presenta como [Inferido].
    """
    res = []
    lineas = {c: [norm(l) for _, l in corpus.cuerpo(c)] for c in codigos}
    for k in (corpus.kpis if kpis is None else kpis):
        pats = [patron_termino(t) for t in terminos(k)]
        if not pats:
            continue
        cods = {c for c, ls in lineas.items() if any(p.search(l) for l in ls for p in pats)}
        if cods:
            res.append((k, cods))
    return res
