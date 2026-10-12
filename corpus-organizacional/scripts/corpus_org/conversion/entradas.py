"""Ubicacion de los archivos de entrada (adjuntos del chat o carpeta local)."""

import os
import re
from pathlib import Path

from ..comun.texto import nfc, norm
from .configuracion import ARCHIVOS_IGNORADOS, EXT_RECONOCIDAS

CARPETAS_ADJUNTOS = ("/mnt/data", "/mnt/user-data/uploads")
EXT_ENTRADA = EXT_RECONOCIDAS | {".csv", ".txt"}
RE_IGNORADOS = re.compile(ARCHIVOS_IGNORADOS, re.I)


def es_archivo_ignorado(nombre):
    """Archivos temporales o del sistema (~$doc.docx, Thumbs.db...) que nunca son documentos."""
    return bool(RE_IGNORADOS.search(nombre))


def entrada_por_defecto():
    """Carpeta donde estan los adjuntos: /mnt/data en Copilot; si no, la carpeta actual."""
    for c in (CARPETAS_ADJUNTOS[0], os.getcwd(), CARPETAS_ADJUNTOS[1]):
        if os.path.isdir(c):
            try:
                if any(os.path.splitext(n)[1].lower() in EXT_ENTRADA for n in os.listdir(c)):
                    return c
            except OSError:
                continue
    return os.getcwd()


def partes_ruta(ruta):
    """Partes de una ruta escrita con / o con \\ (las de lista.txt vienen de Windows)."""
    return [p for p in re.split(r"[\\/]+", str(ruta or "")) if p]


def clave_ruta(partes):
    """(tipo, departamento, archivo) comparables a partir de las tres ultimas partes de una ruta."""
    if len(partes) < 3:
        return None
    return norm(partes[-3])[:5], norm(partes[-2]), norm(nfc(partes[-1]))


def clave_archivo(nombre):
    """Nombre comparable: sin acentos ni mayusculas y sin el sufijo ' (1)' de las copias."""
    base, ext = os.path.splitext(nfc(nombre))
    base = re.sub(r"\s*\(\d+\)$", "", base)
    return norm(base) + ext.lower()


def buscar_entradas(entrada, salida, extensiones=EXT_RECONOCIDAS):
    """Documentos dentro de ``entrada`` (recursivo), sin la carpeta de salida ni archivos temporales."""
    archivos = []
    salida = Path(salida).resolve()
    for raiz, dirs, nombres in os.walk(entrada):
        r = Path(raiz)
        dirs[:] = [x for x in dirs if not x.startswith(".") and x not in ("node_modules", "__pycache__")
                   and (r / x).resolve() != salida]
        for n in nombres:
            if os.path.splitext(n)[1].lower() in extensiones and not es_archivo_ignorado(n):
                archivos.append(r / n)
    return archivos


def localizar(nombre, entrada):
    """Busca un archivo por ruta, por nombre en las carpetas habituales o por nombre comparable."""
    if not nombre:
        return None
    p = Path(nombre)
    if p.is_file():
        return p
    for base in (Path(entrada), Path(os.getcwd()), Path(CARPETAS_ADJUNTOS[0])):
        q = base / p.name
        if q.is_file():
            return q
    objetivo = clave_archivo(p.name)
    for raiz, _, nombres in os.walk(entrada):
        for n in nombres:
            if clave_archivo(n) == objetivo:
                return Path(raiz) / n
    return None
