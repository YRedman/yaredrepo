"""Lectura y escritura de archivos de texto y CSV del corpus."""

import csv
import hashlib
import io
import re
from pathlib import Path


def leer_texto(path):
    """Lee un archivo detectando UTF-8 (con o sin BOM), UTF-16 con BOM o, en ultimo caso, cp1252."""
    datos = Path(path).read_bytes()
    if datos[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return datos.decode("utf-16")
    try:
        return datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        return datos.decode("cp1252", errors="replace")


def detectar_delimitador(primera_linea):
    return ";" if primera_linea.count(";") >= primera_linea.count(",") else ","


def leer_csv(path, columnas_si_no_hay_encabezado=None):
    """Lee un CSV separado por ';' o ','.

    Si se indican ``columnas_si_no_hay_encabezado`` y la primera fila no contiene la
    columna ``codigo``, el archivo se interpreta como datos sin encabezado.
    """
    txt = leer_texto(path)
    lineas = txt.splitlines()
    if not lineas:
        return []
    delim = detectar_delimitador(lineas[0])
    cabecera = [c.strip().lower() for c in next(csv.reader([lineas[0]], delimiter=delim))]
    if columnas_si_no_hay_encabezado and "codigo" not in cabecera:
        return list(csv.DictReader(io.StringIO(txt), fieldnames=columnas_si_no_hay_encabezado, delimiter=delim))
    return list(csv.DictReader(io.StringIO(txt), delimiter=delim))


def campo_csv(s):
    """Valor en una sola linea; ';' se cambia por ',' para que el CSV se lea bien en Excel."""
    s = (s or "").replace(";", ",").replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", s).strip()


def escribir_csv(path, columnas, filas):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        w.writerow(columnas)
        for fila in filas:
            w.writerow([campo_csv("" if fila.get(c) is None else str(fila.get(c))) for c in columnas])


def huella_codigo(raiz):
    """Huella corta del codigo fuente (todos los .py del paquete) para trazar que version genero la salida."""
    h = hashlib.sha256()
    try:
        for p in sorted(Path(raiz).rglob("*.py")):
            h.update(p.read_bytes())
    except OSError:
        return "no disponible"
    return h.hexdigest()[:16]
