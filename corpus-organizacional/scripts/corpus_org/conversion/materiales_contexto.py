"""La carpeta de contexto: que archivos son documentos de area, que son datos y cuales no se pueden leer."""

import collections
import os
import shutil
from pathlib import Path

from ..comun.archivos import escribir_csv, leer_csv, leer_csv_opcional, unir_csv
from ..comun.esquema import (ARCHIVO_AREAS_EXTRA, ARCHIVO_INDICE, ARCHIVO_INVENTARIO, ARCHIVO_INVENTARIO_CONTEXTO,
                             ARCHIVO_KPIS, PREFIJO_DIC, inventario_activo)
from ..comun.texto import norm
from ..comun.tipos import RE_CODIGO_ANTERIOR
from .configuracion import EXT_RECONOCIDAS, EXT_TEXTO
from .entradas import buscar_entradas, es_archivo_ignorado
from .inventario import actualizar_plantilla_areas, clave_documento, documentos_de_area_en_contexto, localizar_areas

# Archivos de control que pueden estar junto al contexto y no son material de contexto.
ARCHIVOS_NO_CONTEXTO = ("lista", "inventario_maestro", "catalogo")
ARCHIVO_NO_LEIDOS = "archivos_no_leidos.csv"
AVISOS_OMITIDOS_MOSTRADOS = 8


def es_material_de_contexto(ruta):
    """False para los archivos de control (lista, inventario, catalogo) que pueden estar junto al contexto."""
    return not norm(Path(ruta).name).startswith(ARCHIVOS_NO_CONTEXTO)


def documentos_de_area_del_contexto(contexto, entrada, raiz_salida):
    """Filas de inventario de los documentos de area (PRD, POL, PRO, DES) de la carpeta de contexto, y los
    nombres de los que se omiten por estar ya en la entrada."""
    archivos = [p for p in buscar_entradas(contexto, raiz_salida) if es_material_de_contexto(p)]
    ruta_areas, areas = localizar_areas(entrada)
    # un documento que ya esta en la entrada (mismo nombre) no se repite desde el contexto, sea cual sea su tipo
    en_entrada = {clave_documento(p.name) for p in buscar_entradas(entrada, raiz_salida)
                  if Path(contexto) not in Path(p).parents}
    omitidos = [p for p in archivos if clave_documento(p.name) in en_entrada]
    if omitidos:
        print(f"AVISO: {len(omitidos)} archivos de la carpeta de contexto ya están en la entrada (mismo nombre) y "
              "no se repiten: " + "; ".join(p.name for p in omitidos[:AVISOS_OMITIDOS_MOSTRADOS])
              + (" …" if len(omitidos) > AVISOS_OMITIDOS_MOSTRADOS else ""))
    filas = documentos_de_area_en_contexto([p for p in archivos if p not in omitidos], contexto, areas)
    _avisar_documentos_sin_area(filas, ruta_areas)
    return filas, [p.name for p in omitidos]


def _avisar_documentos_sin_area(filas, ruta_areas):
    """Los que quedaron en General por no tener area se agregan a areas.csv (area vacia) para que se asignen."""
    por_defecto = [{"archivo": f["archivo"], "sin_area": True} for f in filas if f.get("area_por_defecto")]
    if not por_defecto:
        return
    agregados = actualizar_plantilla_areas(Path(ruta_areas), por_defecto)
    print(f"AVISO: {len(por_defecto)} documentos de área de la carpeta de contexto quedan en «General» (GEN) "
          "porque no tienen área: escriba la suya en la columna 'area' de " + str(ruta_areas)
          + (f" (se agregaron {agregados})." if agregados else "."))


def archivos_no_leidos(contexto, control):
    """Archivos de la carpeta de contexto que el script no puede leer (.pptx, .xlsx, .zip...). Los lista en
    control/archivos_no_leidos.csv y devuelve un aviso (o None si no hay)."""
    no_leidos = []
    for raiz, dirs, nombres in os.walk(contexto):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for n in nombres:
            ext = os.path.splitext(n)[1].lower()
            if not es_archivo_ignorado(n) and ext not in EXT_RECONOCIDAS | EXT_TEXTO:
                no_leidos.append({"archivo": os.path.relpath(os.path.join(raiz, n), contexto), "extension": ext})
    if not no_leidos:
        return None
    escribir_csv(control / ARCHIVO_NO_LEIDOS, ["archivo", "extension"], no_leidos)
    conteo = collections.Counter(f["extension"] or "(sin extensión)" for f in no_leidos)
    zips = " Un .zip no se abre: descomprímalo dentro de la carpeta de contexto." if ".zip" in conteo else ""
    return (f"{len(no_leidos)} archivos de la carpeta de contexto no se leen ("
            + ", ".join(f"{e} ×{n}" for e, n in conteo.most_common()) + "): guárdelos como PDF o Word." + zips
            + f" Lista en {control / ARCHIVO_NO_LEIDOS}")


def equivalencias_de_contexto(control, de_area, anteriores):
    """(codigo anterior, codigo nuevo) de los materiales de contexto que ahora son documentos de area: su
    C-CTX-NN de la codificacion anterior o su codigo general (CTX-GEN-NN...) de una construccion previa."""
    rutas = {f["ruta"] for f in de_area}
    nuevos = {clave_documento(f["archivo"]): f["codigo"] for f in leer_csv(control / ARCHIVO_INVENTARIO)
              if f.get("ruta_original") in rutas}
    generales = {clave_documento(f.get("archivo", "")): f["codigo"]
                 for f in inventario_activo(leer_csv_opcional(control / ARCHIVO_INVENTARIO_CONTEXTO))}
    pares = []
    for clave, nuevo in nuevos.items():
        for viejo in (anteriores.get(clave), generales.get(clave)):
            if viejo and viejo != nuevo:
                pares.append((viejo, nuevo))
    return pares


def contexto_anterior(control, raiz_salida):
    """{clave_documento(archivo): C-CTX-NN} de una construccion con la codificacion anterior, para numerar
    primero esos materiales y registrar su equivalencia. Vacio si no la hay."""
    fuentes = [control / f"{PREFIJO_DIC}contexto.csv", raiz_salida / "publicado" / ARCHIVO_INDICE]
    anteriores = {}
    for p in fuentes:
        for f in leer_csv_opcional(p):
            c = (f.get("codigo") or "").strip().upper()
            if RE_CODIGO_ANTERIOR.match(c) and c.startswith("C-") and f.get("archivo_origen"):
                anteriores.setdefault(clave_documento(f["archivo_origen"]), c)
    return anteriores


def copiar_datos_de_contexto(contexto, control):
    """Copia a control/ los datos estructurados del contexto: kpi*.csv (unidos en kpis.csv) y areas_extra.csv.

    Devuelve los nombres de archivo que no son documentos de contexto: los indicadores se quedan en kpis.csv
    (no se crea un Markdown de indicadores).
    """
    kpis = sorted(p for p in contexto.iterdir() if p.suffix.lower() == ".csv" and norm(p.name).startswith("kpi"))
    if kpis:
        unir_csv(kpis, control / ARCHIVO_KPIS)
    extra = [p for p in contexto.iterdir() if norm(p.name) == ARCHIVO_AREAS_EXTRA]
    if extra:
        shutil.copy2(extra[0], control / ARCHIVO_AREAS_EXTRA)
    return [p.name for p in kpis + extra]
