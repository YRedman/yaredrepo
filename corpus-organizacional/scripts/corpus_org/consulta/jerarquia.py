"""Estructura de un area: subordinados directos y nivel jerarquico de cada puesto (segun los descriptivos)."""

from ..comun.tipos import tipo_de_codigo


def _puestos_en(detector, texto, cod_area, excepto):
    """Codigos de puestos del area mencionados en ``texto`` (asignados, distintos de ``excepto``)."""
    res = []
    for m in detector.detectar(texto or "", cod_area):
        if m.asignada and m.puesto.area == cod_area and m.puesto.codigo != excepto \
                and m.puesto.codigo not in res:
            res.append(m.puesto.codigo)
    return res


def estructura_area(corpus, cod_area, detector):
    """[(codigo, jefe en el area o '', subordinados directos [codigos], nivel)] de los puestos del area.

    - Jefe: el puesto del area que menciona «Reporta a» o, si no, el que lo lista en «Supervisa a». Sin jefe
      en el area (reporta fuera de ella, o no se indica) el puesto es de nivel 1.
    - Subordinados directos: los puestos del area cuyo «Reporta a» es este puesto, mas los que este puesto
      menciona en «Supervisa a».
    """
    puestos = [c for c in corpus.areas[cod_area].codigos("DES") if c in corpus.meta]
    jefe = {}
    for c in puestos:
        en_area = _puestos_en(detector, corpus.meta[c].get("reporta_a"), cod_area, c)
        jefe[c] = en_area[0] if en_area else ""
    subordinados = {c: [] for c in puestos}
    for c in puestos:
        if jefe[c] in subordinados and c not in subordinados[jefe[c]]:
            subordinados[jefe[c]].append(c)
        for otro in _puestos_en(detector, corpus.meta[c].get("supervisa_a"), cod_area, c):
            if otro in subordinados[c] or otro not in subordinados:
                continue
            subordinados[c].append(otro)

    for c in puestos:        # sin jefe en «Reporta a», lo es quien lo lista en «Supervisa a»
        if not jefe[c]:
            jefe[c] = next((p for p in sorted(puestos) if c in subordinados[p]), "")

    def nivel(c):
        n, visto = 1, {c}
        while jefe.get(c) and jefe[c] not in visto:
            c = jefe[c]
            visto.add(c)
            n += 1
        return n
    return [(c, jefe[c], sorted(subordinados[c]), nivel(c)) for c in puestos if tipo_de_codigo(c) == "DES"]
