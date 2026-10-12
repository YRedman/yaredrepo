"""Asignacion de los archivos adjuntos a las filas del inventario y armado de grupos de conversion."""

import collections
from dataclasses import dataclass, field
from typing import Dict, List

from pathlib import Path

from ..comun.texto import nfc
from .entradas import clave_archivo, clave_ruta, partes_ruta
from .lote import Grupo


@dataclass
class Asignacion:
    grupos: Dict[tuple, List[dict]]                 # (tipo, dep) -> filas del inventario
    asignados: Dict[tuple, Dict[str, object]]       # (tipo, dep) -> {codigo: Path}
    ambiguos: List[str] = field(default_factory=list)

    @property
    def usados(self):
        return {str(p) for m in self.asignados.values() for p in m.values()}


def _tipo_fila(fila):
    return "P" if fila["tipo"].lower().startswith("p") else "D"


def _indice_por_ruta(entradas, raiz):
    """{(tipo, departamento, archivo): Path} para los archivos ordenados en carpetas Tipo/Departamento/."""
    por_ruta = {}
    for p in entradas:
        try:
            partes = Path(p).resolve().relative_to(Path(raiz).resolve()).parts
        except ValueError:
            partes = Path(p).parts
        clave = clave_ruta(partes)
        if clave:
            por_ruta[clave] = p
    return por_ruta


def _mismo_nombre(candidatos, archivo):
    """Entre un archivo y sus copias ('x.pdf', 'x (1).pdf'), el que se llama igual que la fila del inventario."""
    objetivo = nfc(archivo).strip().lower()
    for p in candidatos:
        if nfc(p.name).strip().lower() == objetivo:
            return p
    return candidatos[0]


def asignar_archivos(inventario, entradas, tipo_filtro=None, dep_filtro=None, raiz=None):
    """Relaciona cada fila del inventario con su archivo adjunto.

    Primero por ruta Tipo/Departamento/Archivo (la de lista.txt), asi dos areas pueden tener un archivo
    con el mismo nombre. Si los adjuntos llegan sin carpetas, por nombre comparable; en ese caso un
    archivo que coincide con varios grupos no se asigna a ninguno salvo que se filtre por tipo y
    departamento: asi no se publica en el area equivocada.
    """
    por_clave = collections.defaultdict(list)
    for p in entradas:
        por_clave[clave_archivo(p.name)].append(p)
    por_ruta = _indice_por_ruta(entradas, raiz) if raiz else {}
    por_nombre = set()
    grupos = collections.OrderedDict()
    for f in inventario:
        grupos.setdefault((_tipo_fila(f), f["codigo_departamento"]), []).append(f)
    asignados = {}
    for (t, dep), filas in grupos.items():
        if (tipo_filtro and t != tipo_filtro) or (dep_filtro and dep != dep_filtro):
            continue
        for f in filas:
            kr = clave_ruta(partes_ruta(f.get("ruta_original")))
            if kr in por_ruta:
                asignados.setdefault((t, dep), {})[f["codigo"]] = por_ruta[kr]
                continue
            k = clave_archivo(f["archivo"])
            if k in por_clave:
                p = _mismo_nombre(por_clave[k], f["archivo"])
                asignados.setdefault((t, dep), {})[f["codigo"]] = p
                por_nombre.add(str(p))
    cuenta = collections.Counter(str(p) for m in asignados.values() for p in m.values() if str(p) in por_nombre)
    ambiguos = [p for p, n in cuenta.items() if n > 1]
    if ambiguos and not (tipo_filtro and dep_filtro):
        for clave in list(asignados):
            asignados[clave] = {c: p for c, p in asignados[clave].items() if str(p) not in ambiguos}
            if not asignados[clave]:
                del asignados[clave]
    return Asignacion(grupos, asignados, ambiguos)


def _numero(codigo):
    return int(codigo.rsplit("-", 1)[1])


def grupos_a_convertir(asignacion):
    """Un ``Grupo`` por tipo y departamento con archivos; parcial si no estan todos sus documentos."""
    grupos = []
    for (t, dep), mapa in asignacion.asignados.items():
        filas = sorted(asignacion.grupos[(t, dep)], key=lambda f: f["codigo"])
        completo = len(mapa) == len(filas)
        if completo:
            nombre_base, filas_proc = f"{t}_{dep}", filas
        else:
            nums = [_numero(f["codigo"]) for f in filas if f["codigo"] in mapa]
            lo, hi = min(nums), max(nums)
            nombre_base = f"{t}_{dep}_{lo:02d}-{hi:02d}"
            filas_proc = [f for f in filas if lo <= _numero(f["codigo"]) <= hi]
        grupos.append(Grupo(t, dep, filas[0]["departamento"], filas_proc, mapa, nombre_base, completo))
    return grupos
