"""Inventario maestro: codigos de departamento y numeracion de documentos."""

import collections
import difflib
import itertools
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List

from ..comun.archivos import leer_csv, leer_texto
from ..comun.errores import CorpusError
from ..comun.esquema import TIPOS
from ..comun.texto import nfc, norm, sin_acentos
from .configuracion import EXT_RECONOCIDAS, PALABRAS_VACIAS_DEP

RE_CODIGO_DEP = re.compile(r"^[A-Z0-9]{3}$")


@dataclass
class Inventario:
    documentos: List[dict] = field(default_factory=list)   # filas de inventario_maestro.csv
    catalogo: List[dict] = field(default_factory=list)     # filas de catalogo.csv
    avisos: List[str] = field(default_factory=list)
    ignoradas: List[tuple] = field(default_factory=list)   # (ruta, motivo)
    departamentos: Dict[str, str] = field(default_factory=dict)
    rutas_validas: int = 0


def tipo_de_carpeta(nombre):
    n = norm(nombre)
    if n.startswith(("procedim", "proceso")):
        return "P"
    if n.startswith(("descrip", "perfil")):
        return "D"
    return None


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


def parsear_lista(path):
    """Rutas Tipo/Departamento/Archivo de lista.txt -> (filas validas, [(ruta, motivo) ignoradas])."""
    filas, ignoradas = [], []
    for linea in leer_texto(path).splitlines():
        l = linea.strip().strip('"').strip("'").strip()
        if not l:
            continue
        partes = [p for p in re.split(r"[\\/]+", l) if p]
        nombre = partes[-1] if partes else l
        if os.path.splitext(nombre)[1].lower() not in EXT_RECONOCIDAS:
            ignoradas.append((l, "no es PDF ni Word"))
            continue
        if len(partes) < 3:
            ignoradas.append((l, "la ruta no incluye Tipo/Departamento/Archivo"))
            continue
        tipo = tipo_de_carpeta(partes[-3])
        if not tipo:
            ignoradas.append((l, f"la carpeta '{partes[-3]}' no es 'Procedimiento' ni 'Descriptivo'"))
            continue
        filas.append({"tipo": tipo, "departamento": nfc(partes[-2]).strip(), "archivo": nfc(nombre).strip(),
                      "ruta": l})
    return filas, ignoradas


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


def _asignar_codigos(departamentos, fijados):
    codigos = dict(fijados)
    usados = set(codigos.values())
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


def construir_inventario(filas, ignoradas, codigos_fijados=None):
    inv = Inventario(ignoradas=ignoradas, rutas_validas=len(filas))
    deps = collections.OrderedDict()
    for f in sorted(filas, key=lambda f: norm(f["departamento"])):
        deps.setdefault(norm(f["departamento"]), f["departamento"])
    inv.departamentos = deps
    codigos = _asignar_codigos(deps, codigos_fijados or {})
    grupos = collections.defaultdict(list)
    for f in filas:
        grupos[(f["tipo"], norm(f["departamento"]))].append(f)
    for (tipo, kdep), lista_f in sorted(grupos.items(), key=lambda kv: (kv[0][0] != "D", codigos[kv[0][1]])):
        lista_f.sort(key=lambda f: (norm(os.path.splitext(f["archivo"])[0]), f["archivo"]))
        for n, c in collections.Counter(norm(f["archivo"]) for f in lista_f).items():
            if c > 1:
                inv.avisos.append(f"Archivo repetido en {TIPOS[tipo]}/{deps[kdep]}: {n}")
        ancho = ancho_numeracion(len(lista_f))
        for i, f in enumerate(lista_f, 1):
            obs = ""
            if f["archivo"].lower().endswith(".doc"):
                obs = "Formato .doc antiguo: guardarlo como .docx o PDF antes de convertir"
            inv.documentos.append({"codigo": f"{tipo}-{codigos[kdep]}-{i:0{ancho}d}", "tipo": TIPOS[tipo],
                                   "codigo_departamento": codigos[kdep], "departamento": deps[kdep],
                                   "archivo": f["archivo"], "ruta_original": f["ruta"], "observaciones": obs})
    for a, b in itertools.combinations(list(deps), 2):
        if difflib.SequenceMatcher(None, a, b).ratio() >= 0.85:
            inv.avisos.append(f"Nombres de departamento muy parecidos (¿son el mismo?): '{deps[a]}' y '{deps[b]}'")
    for k, nombre in deps.items():
        inv.catalogo.append({
            "departamento": nombre, "codigo": codigos[k],
            "descriptivos": sum(1 for f in filas if norm(f["departamento"]) == k and f["tipo"] == "D"),
            "procedimientos": sum(1 for f in filas if norm(f["departamento"]) == k and f["tipo"] == "P"),
        })
    inv.catalogo.sort(key=lambda r: r["codigo"])
    return inv


def inventario_provisional(entradas, tipo, codigo_dep, departamento):
    """Inventario con los archivos adjuntos de UN departamento (orden alfabetico), sin lista.txt."""
    docs = sorted((p for p in entradas if p.suffix.lower() in EXT_RECONOCIDAS),
                  key=lambda p: (norm(os.path.splitext(p.name)[0]), p.name))
    ancho = ancho_numeracion(len(docs))
    return [{"codigo": f"{tipo}-{codigo_dep}-{i:0{ancho}d}", "tipo": TIPOS[tipo], "codigo_departamento": codigo_dep,
             "departamento": departamento, "archivo": p.name} for i, p in enumerate(docs, 1)]
