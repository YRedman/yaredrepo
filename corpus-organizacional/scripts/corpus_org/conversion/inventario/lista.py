"""Entrada del inventario: la lista de archivos (lista.txt) y las areas de los documentos sueltos (areas.csv)."""

import collections
import os
from pathlib import Path

from ...comun.archivos import escribir_csv, leer_csv, leer_csv_opcional, leer_texto
from ...comun.esquema import ARCHIVO_AREAS_DOCUMENTOS, AREA_SIN_ASIGNAR
from ...comun.texto import nfc, norm
from ...comun.tipos import TIPOS_AREA, tipo_de_carpeta, tipo as tipo_documento
from ..configuracion import EXT_RECONOCIDAS
from ..entradas import es_archivo_ignorado, localizar, partes_ruta
from .claves import clave_documento, es_copia


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


def leer_areas(path):
    """areas.csv (columnas archivo;area) -> {clave_documento: area}. Las filas sin area se ignoran."""
    areas = {}
    for r in leer_csv(path):
        archivo = (r.get("archivo") or "").strip()
        area = (r.get("area") or r.get("área") or "").strip()
        if archivo and area:
            areas[clave_documento(archivo)] = nfc(area)
    return areas


def localizar_areas(entrada):
    """(ruta de areas.csv, areas leidas o None si el archivo no existe) de la carpeta de entrada."""
    ruta = localizar(ARCHIVO_AREAS_DOCUMENTOS, entrada) or Path(entrada) / ARCHIVO_AREAS_DOCUMENTOS
    return ruta, (leer_areas(ruta) if Path(ruta).is_file() else None)


def actualizar_plantilla_areas(path, filas):
    """Agrega a areas.csv los archivos sin carpeta de area que todavia no estan, con el area vacia.

    Un documento y sus copias ("archivo (1).pdf") ocupan una sola fila: la del original, o la que ya
    tiene el area escrita. Conserva las areas ya escritas. Devuelve cuantos archivos se agregaron.
    """
    existentes = leer_csv_opcional(path)
    por_clave = collections.OrderedDict()
    for r in existentes:
        fila = {"archivo": (r.get("archivo") or "").strip(), "area": (r.get("area") or r.get("área") or "").strip()}
        k = clave_documento(fila["archivo"])
        previa = por_clave.get(k)
        if previa is None or (not previa["area"] and (fila["area"] or es_copia(previa["archivo"]))):
            por_clave[k] = dict(fila, area=fila["area"] or (previa or {}).get("area", ""))
    agregados = 0
    for f in sorted(filas, key=lambda f: (es_copia(f["archivo"]), f["archivo"])):
        k = clave_documento(f["archivo"])
        if f.get("sin_area") and k not in por_clave:
            por_clave[k] = {"archivo": f["archivo"], "area": ""}
            agregados += 1
    if agregados or not path.is_file() or len(por_clave) != len(existentes):
        escribir_csv(path, ["archivo", "area"], sorted(por_clave.values(), key=lambda r: norm(r["archivo"])))
    return agregados
