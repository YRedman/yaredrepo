"""Publicacion del corpus: indice consolidado, copia limpia al skill y huellas."""

import collections
import datetime
import hashlib
import re
import shutil

from .. import VERSION
from ..comun.archivos import escribir_csv, leer_csv
from ..comun.esquema import (ARCHIVO_AREAS_EXTRA, ARCHIVO_EQUIVALENCIAS, ARCHIVO_HUELLAS, ARCHIVO_INDICE, ARCHIVO_INVENTARIO,
                             ARCHIVO_KPIS, COLUMNAS_INDICE, PREFIJO_DIC, PREFIJO_REPORTE, RE_DOC_MD)
from ..comun.estructura import BYTES_DIVIDIR_MD, NOMBRE_SKILL_MD, archivos_de_huellas, rutas_publicadas
from ..comun.tipos import POR_CODIGO, TIPOS_DOCUMENTO
from .huella import huella
from .skills import copiar_scripts

# Archivos que genera la conversion en control/ y que se regeneran en cada construccion
# (incluye los nombres de la codificacion anterior: P_*.md, D_*.md, contexto.md).
PATRONES_GENERADOS = tuple(f"{t.codigo}_*.md" for t in TIPOS_DOCUMENTO) + (
    "P_*.md", "D_*.md", "contexto.md", f"{PREFIJO_DIC}*.csv", f"{PREFIJO_REPORTE}*.md", ARCHIVO_KPIS,
    ARCHIVO_AREAS_EXTRA)
# Archivos de control/ que se publican tal cual (si existen) en fuente-corpus/indice/. El catalogo y el
# inventario del contexto son de la construccion: se quedan en control/.
PUBLICADOS_EN_INDICE = (ARCHIVO_INVENTARIO, ARCHIVO_EQUIVALENCIAS, ARCHIVO_AREAS_EXTRA)


def limpiar_generados(control):
    """Borra lo que genero una construccion anterior para que no se mezcle con la nueva.

    Sin esto, un DIC parcial de una corrida previa (p. ej. DIC_P_COM_01-05.csv) quedaba junto al
    completo y aparecian codigos duplicados que no existen.
    """
    borrados = []
    for patron in PATRONES_GENERADOS:
        for p in control.glob(patron):
            if p.is_file():
                p.unlink()
                borrados.append(p)
    return borrados


def consolidar_indices(control, carpeta_indice, relocalizado=None):
    """Une todos los DIC_*.csv en un indice maestro. Devuelve (ruta, codigos duplicados).

    ``relocalizado`` ({codigo: (archivo_md, linea_inicio, linea_fin)}) corrige la ubicacion de los
    documentos de un Markdown que se dividio en partes al publicarlo."""
    relocalizado = relocalizado or {}
    por_codigo = collections.OrderedDict()
    duplicados = []
    for p in sorted(control.glob(f"{PREFIJO_DIC}*.csv")):
        for f in leer_csv(p):
            c = (f.get("codigo") or "").strip().upper()
            if not c:
                continue
            if c in por_codigo:
                duplicados.append(c)
            fila = {k: f.get(k, "") for k in COLUMNAS_INDICE}
            if c in relocalizado:
                fila["archivo_md"], fila["linea_inicio"], fila["linea_fin"] = relocalizado[c]
            por_codigo[c] = fila
    indice = carpeta_indice / ARCHIVO_INDICE
    escribir_csv(indice, COLUMNAS_INDICE, list(por_codigo.values()))
    return indice, sorted(set(duplicados))


def _vaciar(carpeta):
    """Borra el contenido generado de una carpeta publicada. SKILL.md lo provee el equipo y no se toca.
    Devuelve los archivos que no se pudieron borrar (por ejemplo la matriz abierta en Excel)."""
    bloqueados = []
    if not carpeta.is_dir():
        return bloqueados
    for p in sorted(carpeta.rglob("*"), key=lambda q: len(q.parts), reverse=True):
        if p.name == NOMBRE_SKILL_MD and p.parent == carpeta:
            continue
        try:
            if p.is_dir():
                p.rmdir()
            else:
                p.unlink()
        except OSError:
            if p.is_file():
                bloqueados.append(p)
    return bloqueados


def tipo_de_archivo_md(nombre):
    """'DES' de 'DES_SEG.md' o 'DES_SEG_01-05.md' (grupo parcial); None si no es un Markdown de documentos."""
    t = nombre.split("_", 1)[0].upper()
    return t if t in POR_CODIGO and nombre.lower().endswith(".md") else None


RE_NUMERO_FINAL = re.compile(r"-(\d{2,3})$")
RE_SUFIJO_PARTE = re.compile(r"_\d{2,3}-\d{2,3}$")


def dividir_markdown(texto, nombre, max_bytes):
    """Divide el Markdown de un grupo en partes de a lo sumo ``max_bytes``, cortando entre documentos.

    Devuelve [(nombre, texto, {codigo: (linea_inicio, linea_fin)})]. Las partes se llaman
    ``PRD_SEG_01-20.md`` y ``PRD_SEG_21-40.md`` (numero del primer y del ultimo documento). Si cabe en un
    archivo, devuelve el mismo texto con su nombre."""
    lineas = texto.split("\n")
    inicios = [i for i, l in enumerate(lineas) if RE_DOC_MD.match(l)]
    if not inicios or len(texto.encode("utf-8")) <= max_bytes:
        return [(nombre, texto, {})]
    cabecera = lineas[:inicios[0]]
    bloques = []
    for k, i in enumerate(inicios):
        fin = inicios[k + 1] if k + 1 < len(inicios) else len(lineas)
        bloques.append((RE_DOC_MD.match(lineas[i]).group(1), lineas[i:fin]))
    partes, actual, tam = [], [], 0
    for b in bloques:
        t = sum(len(l.encode("utf-8")) + 1 for l in b[1])
        if actual and tam + t > max_bytes:
            partes.append(actual)
            actual, tam = [], 0
        actual.append(b)
        tam += t
    partes.append(actual)
    if len(partes) == 1:           # un solo documento mas grande que el limite: no hay donde cortar
        return [(nombre, texto, {})]
    base = RE_SUFIJO_PARTE.sub("", nombre[:-3])
    salida = []
    for parte in partes:
        ubic, cuerpo = {}, list(cabecera)
        for codigo, ls in parte:
            ubic[codigo] = (len(cuerpo) + 1, len(cuerpo) + len(ls))
            cuerpo += ls
        cab = [re.sub(r"(Documentos[^:]*: )\d+", rf"\g<1>{len(parte)}", l) for l in cabecera]
        cuerpo[:len(cabecera)] = cab
        lo, hi = (RE_NUMERO_FINAL.search(parte[0][0]), RE_NUMERO_FINAL.search(parte[-1][0]))
        nombre_parte = f"{base}_{lo.group(1)}-{hi.group(1)}.md"
        salida.append((nombre_parte, "\n".join(cuerpo).rstrip() + "\n", ubic))
    return salida


def publicar_corpus(control, publicado, avisos=None, max_md_bytes=BYTES_DIVIDIR_MD):
    """Publica el skill fuente-corpus, listo para comprimir (``publicado`` = salida_corpus/copilot):

    - documentos/: un .md por tipo y area en DES/, PRD/, PRO/ y POL/.
    - contexto/ (documentos generales y kpis.csv), indice/ (indice, inventario, areas_extra, equivalencias),
      matriz/ (la escribe la matriz) y scripts/ (corpus.py y corpus_org/).

    Reportes y DIC parciales quedan en control/. Un Markdown de mas de ``max_md_bytes`` se divide en partes.
    SKILL.md no se borra al vaciar (``construir`` lo copia del repositorio despues de publicar).
    Devuelve (archivos publicados, codigos duplicados)."""
    rutas = rutas_publicadas(publicado)
    publicado.mkdir(parents=True, exist_ok=True)
    bloqueados = _vaciar(rutas.skill)
    if bloqueados and avisos is not None:
        avisos.append("No se pudieron reemplazar (¿abiertos en otro programa?): "
                      + ", ".join(str(p.relative_to(publicado)) for p in bloqueados))
    for d in (rutas.contexto, rutas.indice, rutas.documentos):
        d.mkdir(parents=True, exist_ok=True)
    copiados, relocalizado = [], {}
    for p in sorted(control.glob("*.md")):
        t = tipo_de_archivo_md(p.name)
        if p.name.upper().startswith(PREFIJO_REPORTE) or t is None:
            continue
        destino = rutas.contexto if POR_CODIGO[t].general else rutas.documentos / t
        destino.mkdir(parents=True, exist_ok=True)
        for nombre, texto, ubic in dividir_markdown(p.read_text(encoding="utf-8"), p.name, max_md_bytes):
            (destino / nombre).write_text(texto, encoding="utf-8")
            copiados.append(destino / nombre)
            relocalizado.update({c: (nombre, i, f) for c, (i, f) in ubic.items()})
    if (control / ARCHIVO_KPIS).is_file():
        copiados.append(shutil.copy2(control / ARCHIVO_KPIS, rutas.contexto / ARCHIVO_KPIS))
    for nombre in PUBLICADOS_EN_INDICE:
        if (control / nombre).is_file():
            copiados.append(shutil.copy2(control / nombre, rutas.indice / nombre))
    indice, duplicados = consolidar_indices(control, rutas.indice, relocalizado)
    copiados.append(indice)
    copiados += copiar_scripts(rutas.scripts)
    return copiados, duplicados


def escribir_huellas(publicado):
    """SHA-256 de cada archivo de las dos carpetas (rutas '<skill>/<ruta>'), en
    fuente-corpus/indice/huellas.sha256; ``corpus.py verificar`` los recalcula para detectar cambios.
    Se escribe al final de la construccion, cuando ya no cambia ningun otro archivo."""
    rutas = rutas_publicadas(publicado)
    rutas.indice.mkdir(parents=True, exist_ok=True)
    lineas = [f"# convertir.py v{VERSION} · huella del código {huella()} · {datetime.datetime.now():%Y-%m-%d %H:%M}"]
    for p in archivos_de_huellas(publicado):
        try:
            lineas.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(publicado).as_posix()}")
        except OSError:                 # bloqueado por otro programa (p. ej. Excel con la matriz abierta)
            print(f"AVISO: no pude leer {p.name} para la huella; cierra el programa que lo usa y ejecuta "
                  f"'convertir.py matriz'.")
    (rutas.indice / ARCHIVO_HUELLAS).write_text("\n".join(lineas) + "\n", encoding="utf-8")
