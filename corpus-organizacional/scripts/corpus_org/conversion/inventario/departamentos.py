"""Codigos de departamento: los propuestos, los fijados en catalogo.csv y la numeracion de los documentos."""

import collections
import itertools
import re

from ...comun.archivos import leer_csv
from ...comun.errores import CorpusError
from ...comun.texto import norm, sin_acentos
from ...comun.tipos import AREA_GENERAL, NOMBRE_AREA_GENERAL, es_area_general
from ..configuracion import PALABRAS_VACIAS_DEP
from .modelo import RE_CODIGO_DEP


def candidatos_codigo(nombre):
    """Codigos de 3 letras propuestos para un departamento, del mas al menos legible."""
    palabras = [w for w in re.findall(r"[A-Z0-9]+", sin_acentos(nombre).upper()) if w not in PALABRAS_VACIAS_DEP]
    if not palabras:
        palabras = ["DEP"]
    cands = []
    if len(palabras) == 1:
        w = palabras[0]
        cons = [c for c in w[1:] if c not in "AEIOU"]
        cands += [w[:3], w[0] + "".join(cons[:2]), w[0] + w[2:4]]
    elif len(palabras) == 2:
        a, b = palabras
        cands += [a[0] + b[:2], a[:2] + b[0], a[0] + b[0] + (b[1:2] or a[1:2])]
    else:
        cands += ["".join(w[0] for w in palabras[:3]), palabras[0][0] + palabras[1][0] + palabras[-1][0]]
    letras = "".join(palabras)
    combinaciones = list(itertools.combinations(range(len(letras)), 3))
    cands += ["".join(letras[i] for i in comb) for comb in combinaciones if comb[0] == 0]
    cands += ["".join(letras[i] for i in comb) for comb in combinaciones]
    vistos = []
    for c in cands:
        c = (c + "XXX")[:3]
        if RE_CODIGO_DEP.match(c) and c not in vistos:
            vistos.append(c)
    return vistos


def leer_catalogo_codigos(path):
    """Codigos de departamento fijados por el usuario en catalogo.csv: {departamento normalizado: codigo}."""
    codigos = {}
    for r in leer_csv(path):
        dep = r.get("departamento") or r.get("Departamento")
        cod = (r.get("codigo") or r.get("Codigo") or r.get("código") or "").strip().upper()
        if dep and cod:
            if not RE_CODIGO_DEP.match(cod):
                raise CorpusError(f"El código '{cod}' de '{dep}' no tiene 3 letras o números.")
            codigos[norm(dep)] = cod
    repetidos = [c for c, n in collections.Counter(codigos.values()).items() if n > 1]
    if repetidos:
        raise CorpusError("Códigos repetidos en el catálogo: " + ", ".join(repetidos))
    return codigos


def nombre_departamento(nombre):
    """El area que significa 'toda la empresa' (General, Corporativo...) se unifica como 'General' (GEN)."""
    return NOMBRE_AREA_GENERAL if es_area_general(nombre) else nombre


def asignar_codigos(departamentos, fijados, reservados=()):
    """Codigo de 3 letras por departamento. GEN queda reservado para el area general."""
    codigos = dict(fijados)
    for k in departamentos:
        if k == norm(NOMBRE_AREA_GENERAL):
            codigos[k] = AREA_GENERAL
    usados = set(codigos.values()) | set(reservados) | {AREA_GENERAL}
    for k, nombre in departamentos.items():
        if k in codigos:
            continue
        for c in candidatos_codigo(nombre):
            if c not in usados:
                codigos[k] = c
                usados.add(c)
                break
    return codigos


def ancho_numeracion(cantidad):
    return 3 if cantidad > 99 else 2
