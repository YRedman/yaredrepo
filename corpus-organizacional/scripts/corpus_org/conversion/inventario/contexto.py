"""Materiales de la carpeta de contexto: su tipo, los que son documentos de area y su inventario (codigos GEN)."""

import collections
import hashlib
import os
from pathlib import Path

from ...comun.esquema import INVENTARIO_ACTIVO, INVENTARIO_RETIRADO, tipo_de_fila
from ...comun.texto import nfc, norm
from ...comun.tipos import (AREA_GENERAL, NOMBRE_AREA_GENERAL, TIPO_CONTEXTO_POR_DEFECTO, TIPOS_AREA, TIPOS_GENERALES,
                            tipo_de_material, tipo_general_de, tipos_candidatos)
from ..configuracion import EXT_IMAGEN, EXT_RECONOCIDAS, PREFERENCIA_EXT
from .claves import clave_documento, es_copia, nombre_de_tipo, orden_de_tipo
from .departamentos import ancho_numeracion

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
        lista_p.sort(key=lambda p: (es_copia(p.name), PREFERENCIA_EXT.get(p.suffix.lower(), 9), norm(p.name)))
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


class _BaseDeContexto:
    """El inventario de contexto anterior, indexado de las tres formas en que un material puede reconocerse."""

    def __init__(self, base):
        self.maximos = collections.Counter()               # tipo -> mayor numero usado
        self.por_codigo = {}
        self.por_clave = collections.defaultdict(list)     # (tipo, documento sin copia) -> filas
        self.por_nombre = {}                               # (tipo, nombre normalizado) -> fila
        for f in base:
            t = tipo_de_fila(f)
            try:
                self.maximos[t] = max(self.maximos[t], int(f["codigo"].rsplit("-", 1)[1]))
            except (KeyError, ValueError, IndexError):
                continue
            if f["codigo"] in self.por_codigo:
                continue                    # un codigo repetido en el inventario anterior (error de una corrida): solo cuenta el primero
            self.por_codigo[f["codigo"]] = f
            self.por_clave[(t, clave_documento(f.get("archivo", "")))].append(f)
            self.por_nombre.setdefault((t, norm(f.get("archivo", ""))), f)


def _codigos_conservados(base, tipo, archivos, asignados):
    """{archivo: codigo} de los materiales que ya tenian codigo: 1) el mismo nombre de archivo; 2) el mismo documento
    con otro sufijo de copia («x (2).png» frente a «x (1).png»). Dos archivos nunca comparten codigo."""
    codigos = {}
    for p in archivos:
        f = base.por_nombre.get((tipo, norm(p.name)))
        if f is not None and f["codigo"] not in asignados:
            codigos[p] = f["codigo"]
            asignados.add(f["codigo"])
    for p in archivos:
        if p in codigos:
            continue
        for f in base.por_clave.get((tipo, clave_documento(p.name)), ()):
            if f["codigo"] not in asignados:
                codigos[p] = f["codigo"]
                asignados.add(f["codigo"])
                break
    return codigos


def _fila_de_material(codigo, tipo, p, carpeta_contexto):
    ruta = str(p.relative_to(carpeta_contexto)) if carpeta_contexto is not None else p.name
    return {"codigo": codigo, "tipo": nombre_de_tipo(tipo), "codigo_departamento": AREA_GENERAL,
            "departamento": NOMBRE_AREA_GENERAL, "archivo": p.name, "ruta_original": ruta, "observaciones": "",
            "estado_inventario": INVENTARIO_ACTIVO, "path": p}


def _retirar_materiales(base, asignados):
    """Los materiales del inventario anterior que ya no estan quedan RETIRADOS: su codigo se reserva."""
    filas = []
    for codigo, f in base.por_codigo.items():
        if codigo in asignados:
            continue
        if (f.get("estado_inventario") or INVENTARIO_ACTIVO) != INVENTARIO_RETIRADO:
            filas.append(dict(f, estado_inventario=INVENTARIO_RETIRADO,
                              observaciones="RETIRADO: ya no es un documento general del contexto; el código queda reservado"))
        else:
            filas.append(f)
    return filas


def inventario_contexto(archivos, carpeta_contexto=None, base=(), anteriores=None):
    """Filas de inventario de los materiales de contexto, numerados por tipo dentro de GEN.

    ``base`` son las filas del inventario de contexto anterior: cada material conserva su codigo, los
    nuevos van al final de su tipo y los que ya no estan quedan RETIRADOS (codigo reservado).
    ``anteriores`` es {clave_documento: codigo C-CTX-NN} de una construccion con la codificacion anterior:
    esos materiales se numeran primero, en su orden anterior. Devuelve (filas, [(anterior, nuevo)]).
    """
    anteriores = anteriores or {}
    base = _BaseDeContexto(base)
    por_tipo = collections.defaultdict(list)
    for p in archivos:
        por_tipo[tipo_de_contexto(p, carpeta_contexto)].append(p)

    def orden(p):
        ant = anteriores.get(clave_documento(p.name), "")
        return (0, ant) if ant else (1, norm(p.name))

    filas, equivalencias, asignados = [], [], set()
    for t in sorted(por_tipo, key=orden_de_tipo):
        lista_p = sorted(por_tipo[t], key=orden)
        siguiente = base.maximos[t]
        ancho = ancho_numeracion(max(len(lista_p), siguiente))
        codigos = _codigos_conservados(base, t, lista_p, asignados)
        for p in lista_p:
            if p not in codigos:
                siguiente += 1
                codigos[p] = f"{t}-{AREA_GENERAL}-{siguiente:0{ancho}d}"
                asignados.add(codigos[p])
            if anteriores.get(clave_documento(p.name)):
                equivalencias.append((anteriores[clave_documento(p.name)], codigos[p]))
            filas.append(_fila_de_material(codigos[p], t, p, carpeta_contexto))
    filas += _retirar_materiales(base, asignados)
    filas.sort(key=lambda f: (orden_de_tipo(f["codigo"].split("-")[0]), f["codigo"]))
    return filas, equivalencias
