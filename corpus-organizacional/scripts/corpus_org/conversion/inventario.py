"""Inventario maestro: codigos de departamento y numeracion de documentos."""

import collections
import difflib
import hashlib
import itertools
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from ..comun.archivos import escribir_csv, leer_csv, leer_texto
from ..comun.errores import CorpusError
from ..comun.esquema import AREA_SIN_ASIGNAR, COLUMNAS_EQUIVALENCIAS, INVENTARIO_ACTIVO, INVENTARIO_RETIRADO
from ..comun.texto import nfc, norm, sin_acentos
from ..comun.tipos import (AREA_GENERAL, NOMBRE_AREA_GENERAL, TIPO_CONTEXTO_POR_DEFECTO, TIPOS_AREA,
                           TIPOS_DOCUMENTO, TIPOS_GENERALES, codigo_nuevo_desde_anterior, es_area_general,
                           tipo_de_carpeta, tipo_de_material, tipo_desde_texto, tipo_general_de,
                           tipos_candidatos, RE_CODIGO_ANTERIOR)
from ..comun.tipos import tipo as tipo_documento
from .configuracion import EXT_IMAGEN, EXT_RECONOCIDAS, PALABRAS_VACIAS_DEP, PREFERENCIA_EXT
from .entradas import es_archivo_ignorado, partes_ruta

RE_CODIGO_DEP = re.compile(r"^[A-Z0-9]{3}$")
RE_SUFIJO_COPIA = re.compile(r"\s*\(\d+\)$|\s*-\s*copia(\s*\(\d+\))?$|\s*copy$", re.I)


@dataclass
class Inventario:
    documentos: List[dict] = field(default_factory=list)   # filas de inventario_maestro.csv
    catalogo: List[dict] = field(default_factory=list)     # filas de catalogo.csv
    avisos: List[str] = field(default_factory=list)
    ignoradas: List[tuple] = field(default_factory=list)   # (ruta, motivo)
    equivalencias: List[tuple] = field(default_factory=list)   # (codigo anterior, codigo nuevo) de un cambio de area
    departamentos: Dict[str, str] = field(default_factory=dict)
    rutas_validas: int = 0


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


def parsear_lista(path, areas=None):
    """Rutas de lista.txt -> (filas validas, [(ruta, motivo) ignoradas]).

    La ruta normal es Tipo/Departamento/Archivo. Tambien se acepta Tipo/Archivo (sin carpeta de area):
    el area se toma de ``areas`` ({clave_documento: area}, el archivo areas.csv) y, si no esta, el
    documento queda en AREA_SIN_ASIGNAR con la marca ``sin_area``.
    """
    areas = areas or {}
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
        if len(partes) >= 2 and not (len(partes) >= 3 and tipo_de_carpeta(partes[-3])) \
                and tipo_de_carpeta(partes[-2]):
            area = areas.get(clave_documento(nombre), "")
            filas.append({"tipo": tipo_de_carpeta(partes[-2]), "departamento": area or AREA_SIN_ASIGNAR,
                          "archivo": nfc(nombre).strip(), "ruta": l, "sin_area": not area})
            continue
        if len(partes) < 3:
            ignoradas.append((l, "la ruta no incluye Tipo/Departamento/Archivo ni Tipo/Archivo"))
            continue
        tipo = tipo_de_carpeta(partes[-3])
        if not tipo:
            ignoradas.append((l, f"la carpeta '{partes[-3]}' no es de un tipo conocido "
                                 f"({', '.join(tipo_documento(t).plural for t in TIPOS_AREA)})"))
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
        avisos.append(f"Duplicado en {_plural(tipo)}/{lista_f[0]['departamento']}: se usa «{lista_f[0]['archivo']}» "
                      f"y se descarta {', '.join('«' + f['archivo'] + '»' for f in lista_f[1:])}")
    return salida, avisos


def leer_areas(path):
    """areas.csv (columnas archivo;area) -> {clave_documento: area}. Las filas sin area se ignoran."""
    areas = {}
    for r in leer_csv(path):
        archivo = (r.get("archivo") or "").strip()
        area = (r.get("area") or r.get("área") or "").strip()
        if archivo and area:
            areas[clave_documento(archivo)] = nfc(area)
    return areas


def actualizar_plantilla_areas(path, filas):
    """Agrega a areas.csv los archivos sin carpeta de area que todavia no estan, con el area vacia.

    Un documento y sus copias ("archivo (1).pdf") ocupan una sola fila: la del original, o la que ya
    tiene el area escrita. Conserva las areas ya escritas. Devuelve cuantos archivos se agregaron.
    """
    existentes = leer_csv(path) if path.is_file() else []
    por_clave = collections.OrderedDict()
    for r in existentes:
        fila = {"archivo": (r.get("archivo") or "").strip(), "area": (r.get("area") or r.get("área") or "").strip()}
        k = clave_documento(fila["archivo"])
        previa = por_clave.get(k)
        if previa is None or (not previa["area"] and (fila["area"] or _es_copia(previa["archivo"]))):
            por_clave[k] = dict(fila, area=fila["area"] or (previa or {}).get("area", ""))
    agregados = 0
    for f in sorted(filas, key=lambda f: (_es_copia(f["archivo"]), f["archivo"])):
        k = clave_documento(f["archivo"])
        if f.get("sin_area") and k not in por_clave:
            por_clave[k] = {"archivo": f["archivo"], "area": ""}
            agregados += 1
    if agregados or not path.is_file() or len(por_clave) != len(existentes):
        escribir_csv(path, ["archivo", "area"], sorted(por_clave.values(), key=lambda r: norm(r["archivo"])))
    return agregados


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


def _plural(codigo_tipo):
    t = tipo_documento(codigo_tipo)
    return t.plural if t else codigo_tipo


def _nombre(codigo_tipo):
    t = tipo_documento(codigo_tipo)
    return t.nombre if t else codigo_tipo


_ORDEN_TIPOS = {t.codigo: i for i, t in enumerate(TIPOS_DOCUMENTO)}


def _orden_tipo(codigo_tipo):
    return _ORDEN_TIPOS.get(codigo_tipo, len(_ORDEN_TIPOS))


def nombre_departamento(nombre):
    """El area que significa 'toda la empresa' (General, Corporativo...) se unifica como 'General' (GEN)."""
    return NOMBRE_AREA_GENERAL if es_area_general(nombre) else nombre


def _asignar_codigos(departamentos, fijados, reservados=()):
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


@dataclass
class InventarioBase:
    """Inventario anterior cuyos codigos se conservan (codigos estables entre construcciones)."""
    documentos: Dict[tuple, dict] = field(default_factory=dict)   # (tipo, depto, documento) -> fila
    departamentos: Dict[str, str] = field(default_factory=dict)   # depto normalizado -> codigo
    maximos: collections.Counter = field(default_factory=collections.Counter)   # (tipo, codigo_dep) -> mayor numero
    equivalencias: List[tuple] = field(default_factory=list)       # (codigo_anterior, codigo_nuevo) migrados


def tipo_de_fila(fila):
    """Codigo de tipo de una fila de inventario o indice: 'DES', o desde 'Descriptivo'/'D' (formato anterior)."""
    t = tipo_desde_texto(fila.get("tipo"))
    if t:
        return t
    return (fila.get("codigo") or "").split("-")[0].upper() or "PRD"


def migrar_fila(f, equivalencias=None):
    """Fila del inventario con el codigo anterior (D-/P-) pasada a la codificacion TTT-AAA-NN."""
    anterior = (f.get("codigo") or "").strip().upper()
    nuevo = codigo_nuevo_desde_anterior(anterior) if RE_CODIGO_ANTERIOR.match(anterior) else None
    t = tipo_de_fila(f)
    f = dict(f, tipo=tipo_documento(t).nombre if tipo_documento(t) else f.get("tipo", ""))
    if nuevo:
        f["codigo"] = nuevo
        if equivalencias is not None:
            equivalencias.append((anterior, nuevo))
    return f


def leer_base(path):
    base = InventarioBase()
    for f in leer_csv(path):
        f = migrar_fila(f, base.equivalencias)
        t = tipo_de_fila(f)
        dep = (f.get("departamento") or "").strip()
        cod_dep = (f.get("codigo_departamento") or "").strip().upper()
        if norm(dep) == norm(AREA_SIN_ASIGNAR):
            continue   # codigos provisionales: cambian cuando se asigna el area
        if dep and cod_dep:
            base.departamentos.setdefault(norm(dep), cod_dep)
        try:
            n = int(f["codigo"].rsplit("-", 1)[1])
        except (KeyError, ValueError, IndexError):
            continue
        base.maximos[(t, cod_dep)] = max(base.maximos[(t, cod_dep)], n)
        base.documentos[(t, norm(dep), clave_documento(f.get("archivo", "")))] = f
    return base


def _fila(codigo, codigo_tipo, cod_dep, departamento, f, obs):
    return {"codigo": codigo, "tipo": tipo_documento(codigo_tipo).nombre, "codigo_departamento": cod_dep, "departamento": departamento,
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
    filas = [dict(f, departamento=nombre_departamento(f["departamento"])) for f in filas]
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
    nuevos, vistos, por_documento = [], set(), {}
    for (tipo, kdep), lista_f in sorted(grupos.items(), key=lambda kv: (_orden_tipo(kv[0][0]), codigos[kv[0][1]])):
        lista_f.sort(key=lambda f: (norm(os.path.splitext(f["archivo"])[0]), f["archivo"]))
        for n, c in collections.Counter(norm(f["archivo"]) for f in lista_f).items():
            if c > 1:
                inv.avisos.append(f"Archivo repetido en {_plural(tipo)}/{deps[kdep]}: {n}")
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
            por_documento[(tipo, clave_documento(f["archivo"]))] = codigo
    retirados = []
    for clave, f in base.documentos.items():
        if clave not in vistos:
            nuevo = por_documento.get((clave[0], clave[2]))
            if nuevo and nuevo != f["codigo"]:       # el mismo documento cambio de area: tiene otro codigo
                inv.equivalencias.append((f["codigo"], nuevo))
                motivo = f"RETIRADO: el documento pasó a {nuevo} (cambió de área); el código queda reservado"
            else:
                retirados.append(f["codigo"])
                motivo = "RETIRADO: no está en la lista actual; el código queda reservado"
            inv.documentos.append(dict(f, estado_inventario=INVENTARIO_RETIRADO, observaciones=motivo))
    if nuevos:
        inv.avisos.append(f"Documentos nuevos (códigos agregados al final): {', '.join(nuevos)}")
    if retirados:
        inv.avisos.append(f"Documentos del inventario base que ya no están (códigos reservados): {', '.join(retirados)}")
    if inv.equivalencias:
        inv.avisos.append(f"Documentos que cambiaron de área ({len(inv.equivalencias)}): su código anterior queda "
                          "reservado y la equivalencia en equivalencias_codigos.csv")
    inv.documentos.sort(key=lambda f: (_orden_tipo(f["codigo"].split("-")[0]), f["codigo"]))
    for a, b in itertools.combinations(list(deps), 2):
        if difflib.SequenceMatcher(None, a, b).ratio() >= 0.85:
            inv.avisos.append(f"Nombres de departamento muy parecidos (¿son el mismo?): '{deps[a]}' y '{deps[b]}'")
    for k, nombre in deps.items():
        fila_cat = {"departamento": nombre, "codigo": codigos[k]}
        for t in TIPOS_AREA:
            fila_cat[t] = sum(1 for f in filas if norm(f["departamento"]) == k and f["tipo"] == t)
        inv.catalogo.append(fila_cat)
    inv.catalogo.sort(key=lambda r: r["codigo"])
    return inv


def inventario_provisional(entradas, tipo, codigo_dep, departamento):
    """Inventario con los archivos adjuntos de UN departamento (orden alfabetico), sin lista.txt."""
    filas = [{"tipo": tipo, "departamento": departamento, "archivo": p.name, "path": p}
             for p in entradas if p.suffix.lower() in EXT_RECONOCIDAS]
    filas, _avisos = quitar_duplicados(filas)
    docs = sorted((f["path"] for f in filas), key=lambda p: (norm(os.path.splitext(p.name)[0]), p.name))
    ancho = ancho_numeracion(len(docs))
    return [{"codigo": f"{tipo}-{codigo_dep}-{i:0{ancho}d}", "tipo": _nombre(tipo), "codigo_departamento": codigo_dep,
             "departamento": departamento, "archivo": p.name} for i, p in enumerate(docs, 1)]


# ---------------------------------------------------------------------------
# Documentos generales de contexto (ORG-GEN-01, KPI-GEN-01...)
# ---------------------------------------------------------------------------

def clasificar_material(path, carpeta_contexto=None):
    """(tipo, area) de un archivo de la carpeta de contexto.

    El tipo sale de la subcarpeta mas cercana que lo indique (Procedimientos\\, Políticas\\, Normativas\\,
    Organigramas\\...) o, si ninguna lo indica, del nombre del archivo (ficha de proceso, procedimiento,
    politica, organigrama, kpi...). Para un documento de area (DES, PRD, PRO, POL) el area es la subcarpeta
    que sigue a la del tipo (Procedimientos\\Calidad\\x.pdf) o, si el archivo esta directamente en la carpeta del tipo,
    la carpeta que la contiene (Calidad\\Procedimiento\\x.pdf); '' si no hay ninguna. Solo PDF y Word pueden
    ser documentos de area; lo demas es un documento general (CTX si no se reconoce)."""
    partes = []
    if carpeta_contexto is not None:
        try:
            partes = list(Path(path).relative_to(carpeta_contexto).parts[:-1])
        except ValueError:
            partes = []
    nombre = os.path.splitext(Path(path).name)[0]
    t, area = None, ""
    for i in range(len(partes) - 1, -1, -1):
        candidatos = tipos_candidatos(partes[i])
        if not candidatos:
            continue
        if len(candidatos) == 1:
            t = candidatos[0]
        else:
            # carpeta con varios tipos («Políticas y procedimientos», «Estructura organizacional y descriptivos»):
            # decide el nombre del archivo; si no dice nada, el tipo general de la carpeta o, si no hay, el primero
            por_nombre = tipo_de_material(nombre)
            generales = [c for c in candidatos if c in TIPOS_GENERALES]
            t = por_nombre or (generales[0] if generales else candidatos[0])
        area = partes[i + 1] if i + 1 < len(partes) else ""
        if not area and i >= 1 and not tipos_candidatos(partes[i - 1]):
            area = partes[i - 1]    # Gestión Comercial\Ventas\Procedimiento\x.docx: el area es la carpeta que contiene la del tipo
        break
    if not t:
        t = tipo_de_material(nombre)
    if t in TIPOS_AREA and Path(path).suffix.lower() not in EXT_RECONOCIDAS:
        t = tipo_general_de(os.path.splitext(Path(path).name)[0])
    general_por_nombre = tipo_de_material(os.path.splitext(Path(path).name)[0])
    if t in TIPOS_AREA and general_por_nombre in TIPOS_GENERALES:
        t = general_por_nombre      # «Mapa de procesos» o «Organigrama» en la carpeta Procedimientos: es general
    if t is None or t in TIPOS_AREA:
        return (t or TIPO_CONTEXTO_POR_DEFECTO), (nfc(area).strip() if t in TIPOS_AREA else "")
    return t, ""


def tipo_de_contexto(path, carpeta_contexto=None):
    """Tipo general (ORG, KPI, GLO, MPR o CTX) de un material de contexto que no es documento de area."""
    t, _ = clasificar_material(path, carpeta_contexto)
    return TIPO_CONTEXTO_POR_DEFECTO if t in TIPOS_AREA else t


def documentos_de_area_en_contexto(archivos, carpeta_contexto, areas=None):
    """Filas de lista (como las de ``parsear_lista``) de los procedimientos, politicas, protocolos y
    descriptivos que estan en la carpeta de contexto: se inventarian y convierten como los de la entrada.

    El area es la subcarpeta de area, la de areas.csv o, si no hay ninguna, General (GEN): un material
    de contexto sin area se toma como de toda la empresa."""
    areas = areas or {}
    filas = []
    for p in archivos:
        t, area = clasificar_material(p, carpeta_contexto)
        if t not in TIPOS_AREA:
            continue
        explicita = areas.get(clave_documento(p.name), "") or area      # lo que escribio el usuario en areas.csv manda
        filas.append({"tipo": t, "departamento": explicita or NOMBRE_AREA_GENERAL, "archivo": nfc(p.name).strip(),
                      "ruta": str(p), "desde_contexto": True, "area_por_defecto": not explicita})
    return filas


def quitar_copias_contexto(archivos, carpeta=None):
    """Un mismo material repetido en el contexto ('X (1).csv' junto a 'X.csv', o 'X.docx' y 'X.pdf') se numera una sola
    vez: se conserva el original (sin sufijo de copia) en el formato preferido. Un .csv y un .md del mismo nombre no son
    el mismo material. Devuelve (archivos, avisos)."""
    grupos = collections.OrderedDict()
    for p in archivos:
        ext = p.suffix.lower()
        familia = "documento" if ext in PREFERENCIA_EXT else ext
        # las capturas «cafeImageExport (1).png», «(2).png»... son imagenes distintas, no copias: solo se unen las identicas
        clave = (_huella_archivo(p),) if ext in EXT_IMAGEN else (clave_documento(p.name),)
        grupos.setdefault(clave + (familia,), []).append(p)
    salida, avisos = [], []
    for lista_p in grupos.values():
        if len(lista_p) == 1:
            salida += lista_p
            continue
        lista_p.sort(key=lambda p: (_es_copia(p.name), PREFERENCIA_EXT.get(p.suffix.lower(), 9), norm(p.name)))
        usado, descartados = lista_p[0], lista_p[1:]
        salida.append(usado)
        distintos = [q for q in descartados if _huella_archivo(q) != _huella_archivo(usado)]
        aviso = f"Duplicado en el contexto: se usa «{_mostrar(usado, carpeta)}» y se descarta " + ", ".join(
            f"«{_mostrar(q, carpeta)}»" for q in descartados)
        if distintos:
            aviso += " (el contenido de " + ", ".join(f"«{_mostrar(q, carpeta)}»" for q in distintos) + \
                " es distinto: confirme cuál es el vigente)"
        avisos.append(aviso)
    return salida, avisos


def _mostrar(p, carpeta):
    """Nombre del archivo con su carpeta (relativa al contexto) para distinguir los que se llaman igual."""
    try:
        return Path(p).relative_to(carpeta).as_posix() if carpeta is not None else Path(p).name
    except ValueError:
        return Path(p).name


def _huella_archivo(p):
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    except OSError:
        return None


def inventario_contexto(archivos, carpeta_contexto=None, base=(), anteriores=None):
    """Filas de inventario de los materiales de contexto, numerados por tipo dentro de GEN.

    ``base`` son las filas del inventario de contexto anterior: cada material conserva su codigo, los
    nuevos van al final de su tipo y los que ya no estan quedan RETIRADOS (codigo reservado).
    ``anteriores`` es {clave_documento: codigo C-CTX-NN} de una construccion con la codificacion anterior:
    esos materiales se numeran primero, en su orden anterior. Devuelve (filas, [(anterior, nuevo)]).
    """
    anteriores = anteriores or {}
    previos, maximos = {}, collections.Counter()
    for f in base:
        t = tipo_de_fila(f)
        try:
            maximos[t] = max(maximos[t], int(f["codigo"].rsplit("-", 1)[1]))
        except (KeyError, ValueError, IndexError):
            continue
        previos[(t, clave_documento(f.get("archivo", "")))] = f
    por_tipo = collections.defaultdict(list)
    for p in archivos:
        por_tipo[tipo_de_contexto(p, carpeta_contexto)].append(p)
    filas, equivalencias, vistos = [], [], set()
    for t in sorted(por_tipo, key=_orden_tipo):
        def orden(p):
            ant = anteriores.get(clave_documento(p.name), "")
            return (0, ant) if ant else (1, norm(p.name))
        lista_p = sorted(por_tipo[t], key=orden)
        siguiente = maximos[t]
        ancho = ancho_numeracion(max(len(lista_p), siguiente))
        for p in lista_p:
            clave = (t, clave_documento(p.name))
            ruta = str(p.relative_to(carpeta_contexto)) if carpeta_contexto is not None else p.name
            if clave in previos:
                codigo = previos[clave]["codigo"]
                vistos.add(clave)
            else:
                siguiente += 1
                codigo = f"{t}-{AREA_GENERAL}-{siguiente:0{ancho}d}"
            ant = anteriores.get(clave_documento(p.name))
            if ant:
                equivalencias.append((ant, codigo))
            filas.append({"codigo": codigo, "tipo": _nombre(t), "codigo_departamento": AREA_GENERAL,
                          "departamento": NOMBRE_AREA_GENERAL, "archivo": p.name, "ruta_original": ruta,
                          "observaciones": "", "estado_inventario": INVENTARIO_ACTIVO, "path": p})
    for clave, f in previos.items():
        if clave not in vistos and (f.get("estado_inventario") or INVENTARIO_ACTIVO) != INVENTARIO_RETIRADO:
            filas.append(dict(f, estado_inventario=INVENTARIO_RETIRADO,
                              observaciones="RETIRADO: ya no es un documento general del contexto; el código queda reservado"))
        elif clave not in vistos:
            filas.append(f)
    filas.sort(key=lambda f: (_orden_tipo(f["codigo"].split("-")[0]), f["codigo"]))
    return filas, equivalencias


def escribir_equivalencias(path, nuevas):
    """Agrega a equivalencias_codigos.csv (codigo_anterior;codigo_nuevo) las equivalencias nuevas, sin repetir."""
    existentes = leer_csv(path) if path.is_file() else []
    vistos = {(r.get("codigo_anterior", ""), r.get("codigo_nuevo", "")) for r in existentes}
    filas = [{"codigo_anterior": r.get("codigo_anterior", ""), "codigo_nuevo": r.get("codigo_nuevo", "")}
             for r in existentes]
    for ant, nuevo in nuevas:
        if (ant, nuevo) not in vistos and ant != nuevo:
            vistos.add((ant, nuevo))
            filas.append({"codigo_anterior": ant, "codigo_nuevo": nuevo})
    if filas:
        escribir_csv(path, COLUMNAS_EQUIVALENCIAS, filas)
    return filas


def leer_equivalencias(path):
    """{codigo_anterior: codigo_nuevo} de equivalencias_codigos.csv."""
    return {(r.get("codigo_anterior") or "").strip().upper(): (r.get("codigo_nuevo") or "").strip().upper()
            for r in (leer_csv(path) if path.is_file() else []) if r.get("codigo_anterior")}
