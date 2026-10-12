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
from ..comun.esquema import INVENTARIO_ACTIVO, INVENTARIO_RETIRADO, TIPOS
from ..comun.texto import nfc, norm, sin_acentos
from .configuracion import EXT_RECONOCIDAS, PALABRAS_VACIAS_DEP, PREFERENCIA_EXT
from .entradas import es_archivo_ignorado, partes_ruta

RE_CODIGO_DEP = re.compile(r"^[A-Z0-9]{3}$")
RE_SUFIJO_COPIA = re.compile(r"\s*\(\d+\)$|\s*-\s*copia(\s*\(\d+\))?$|\s*copy$", re.I)


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
        partes = partes_ruta(l)
        nombre = partes[-1] if partes else l
        if es_archivo_ignorado(nombre):
            ignoradas.append((l, "archivo temporal o del sistema"))
            continue
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


def clave_documento(nombre):
    """Identidad de un documento sin extension ni sufijo de copia: 'Compra (1).pdf' -> 'compra'."""
    return norm(RE_SUFIJO_COPIA.sub("", os.path.splitext(nfc(nombre))[0]))


def _es_copia(nombre):
    return bool(RE_SUFIJO_COPIA.search(os.path.splitext(nombre)[0]))


def quitar_duplicados(filas, incluir=False):
    """Un mismo documento en .docx y .pdf, o una copia '(1)', se inventaria una sola vez.

    Se conserva el original (sin sufijo de copia) en el formato preferido (.docx). Con ``incluir``
    se conservan todos. Devuelve (filas, avisos).
    """
    grupos = collections.OrderedDict()
    for f in filas:
        grupos.setdefault((f["tipo"], norm(f["departamento"]), clave_documento(f["archivo"])), []).append(f)
    salida, avisos = [], []
    for (tipo, _dep, _doc), lista_f in grupos.items():
        if len(lista_f) == 1:
            salida += lista_f
            continue
        if incluir:
            salida += lista_f
            avisos.append("Posible duplicado conservado (--incluir-duplicados): "
                          + ", ".join(f["archivo"] for f in lista_f))
            continue
        lista_f.sort(key=lambda f: (_es_copia(f["archivo"]),
                                    PREFERENCIA_EXT.get(os.path.splitext(f["archivo"])[1].lower(), 9), f["archivo"]))
        salida.append(lista_f[0])
        avisos.append(f"Duplicado en {TIPOS[tipo]}/{lista_f[0]['departamento']}: se usa «{lista_f[0]['archivo']}» "
                      f"y se descarta {', '.join('«' + f['archivo'] + '»' for f in lista_f[1:])}")
    return salida, avisos


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


def _asignar_codigos(departamentos, fijados, reservados=()):
    codigos = dict(fijados)
    usados = set(codigos.values()) | set(reservados)
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


@dataclass
class InventarioBase:
    """Inventario anterior cuyos codigos se conservan (codigos estables entre construcciones)."""
    documentos: Dict[tuple, dict] = field(default_factory=dict)   # (tipo, depto, documento) -> fila
    departamentos: Dict[str, str] = field(default_factory=dict)   # depto normalizado -> codigo
    maximos: collections.Counter = field(default_factory=collections.Counter)   # (tipo, codigo_dep) -> mayor numero


def _tipo_inventario(fila):
    return "P" if (fila.get("tipo") or "").lower().startswith("p") else "D"


def leer_base(path):
    base = InventarioBase()
    for f in leer_csv(path):
        t = _tipo_inventario(f)
        dep = (f.get("departamento") or "").strip()
        cod_dep = (f.get("codigo_departamento") or "").strip().upper()
        if dep and cod_dep:
            base.departamentos.setdefault(norm(dep), cod_dep)
        try:
            n = int(f["codigo"].rsplit("-", 1)[1])
        except (KeyError, ValueError, IndexError):
            continue
        base.maximos[(t, cod_dep)] = max(base.maximos[(t, cod_dep)], n)
        base.documentos[(t, norm(dep), clave_documento(f.get("archivo", "")))] = f
    return base


def _fila(codigo, tipo, cod_dep, departamento, f, obs):
    return {"codigo": codigo, "tipo": TIPOS[tipo], "codigo_departamento": cod_dep, "departamento": departamento,
            "archivo": f["archivo"], "ruta_original": f["ruta"], "observaciones": obs,
            "estado_inventario": INVENTARIO_ACTIVO}


def construir_inventario(filas, ignoradas, codigos_fijados=None, incluir_duplicados=False, base=None):
    """Inventario maestro a partir de las rutas de lista.txt.

    Con ``base`` (el inventario anterior) los codigos no cambian: cada documento conserva el suyo, los
    nuevos se numeran despues del mayor codigo de su grupo y los que ya no estan quedan RETIRADOS
    (su codigo queda reservado y no se reutiliza). Sin ``base`` se numera en orden alfabetico.
    """
    base = base or InventarioBase()
    inv = Inventario(ignoradas=ignoradas, rutas_validas=len(filas))
    filas, inv.avisos = quitar_duplicados(filas, incluir_duplicados)
    deps = collections.OrderedDict()
    for f in sorted(filas, key=lambda f: norm(f["departamento"])):
        deps.setdefault(norm(f["departamento"]), f["departamento"])
    inv.departamentos = deps
    fijados = dict(codigos_fijados or {})
    for k, cod in base.departamentos.items():
        if k in deps and k not in fijados:
            fijados[k] = cod
    codigos = _asignar_codigos(deps, fijados, reservados=set(base.departamentos.values()))
    grupos = collections.defaultdict(list)
    for f in filas:
        grupos[(f["tipo"], norm(f["departamento"]))].append(f)
    nuevos, vistos = [], set()
    for (tipo, kdep), lista_f in sorted(grupos.items(), key=lambda kv: (kv[0][0] != "D", codigos[kv[0][1]])):
        lista_f.sort(key=lambda f: (norm(os.path.splitext(f["archivo"])[0]), f["archivo"]))
        for n, c in collections.Counter(norm(f["archivo"]) for f in lista_f).items():
            if c > 1:
                inv.avisos.append(f"Archivo repetido en {TIPOS[tipo]}/{deps[kdep]}: {n}")
        cod_dep = codigos[kdep]
        siguiente = base.maximos[(tipo, cod_dep)]
        ancho = ancho_numeracion(max(len(lista_f), siguiente))
        for f in lista_f:
            obs = "Formato .doc antiguo: guardarlo como .docx o PDF antes de convertir" \
                if f["archivo"].lower().endswith(".doc") else ""
            clave = (tipo, kdep, clave_documento(f["archivo"]))
            if clave in base.documentos:
                codigo = base.documentos[clave]["codigo"]
                vistos.add(clave)
            else:
                siguiente += 1
                codigo = f"{tipo}-{cod_dep}-{siguiente:0{ancho}d}"
                if base.documentos:
                    nuevos.append(codigo)
                    obs = (obs + "; " if obs else "") + "NUEVO respecto del inventario base"
            inv.documentos.append(_fila(codigo, tipo, cod_dep, deps[kdep], f, obs))
    retirados = []
    for clave, f in base.documentos.items():
        if clave not in vistos:
            retirados.append(f["codigo"])
            inv.documentos.append(dict(f, estado_inventario=INVENTARIO_RETIRADO,
                                       observaciones="RETIRADO: no está en la lista actual; el código queda reservado"))
    if nuevos:
        inv.avisos.append(f"Documentos nuevos (códigos agregados al final): {', '.join(nuevos)}")
    if retirados:
        inv.avisos.append(f"Documentos del inventario base que ya no están (códigos reservados): {', '.join(retirados)}")
    inv.documentos.sort(key=lambda f: (f["codigo"][0] != "D", f["codigo"]))
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
    filas = [{"tipo": tipo, "departamento": departamento, "archivo": p.name, "path": p}
             for p in entradas if p.suffix.lower() in EXT_RECONOCIDAS]
    filas, _avisos = quitar_duplicados(filas)
    docs = sorted((f["path"] for f in filas), key=lambda p: (norm(os.path.splitext(p.name)[0]), p.name))
    ancho = ancho_numeracion(len(docs))
    return [{"codigo": f"{tipo}-{codigo_dep}-{i:0{ancho}d}", "tipo": TIPOS[tipo], "codigo_departamento": codigo_dep,
             "departamento": departamento, "archivo": p.name} for i, p in enumerate(docs, 1)]
