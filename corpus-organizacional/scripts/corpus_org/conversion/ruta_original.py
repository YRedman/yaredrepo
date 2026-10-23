"""Donde esta el archivo original de un documento, para revisarlo."""

import re
from pathlib import Path


def ruta_original(fila, grupo, opciones=None, path=None):
    """Donde esta el archivo para revisarlo: 'entrada/<ruta>' o 'contexto/<ruta>', relativa a esa carpeta.

    Se parte del archivo realmente leido (``path``): un documento de area que vino de la carpeta de contexto
    (procedimientos, politicas...) se muestra como 'contexto/...' aunque su fila del inventario base traiga otra
    ruta. Sin archivo (no adjunto) se usa la ruta del inventario; si no cuelga de ninguna carpeta, sus tres
    ultimas partes (Tipo/Departamento/Archivo)."""
    raices = ((getattr(opciones, "raiz_contexto", None), "contexto"), (getattr(opciones, "raiz_entrada", None), "entrada"))
    candidatos = [str(path)] if path is not None else []
    candidatos.append((fila.get("ruta_original") or fila.get("archivo") or "").strip())
    for ruta in candidatos:
        for raiz, etiqueta in raices:
            if raiz is None:
                continue
            try:
                return f"{etiqueta}/" + Path(ruta).resolve().relative_to(Path(raiz).resolve()).as_posix()
            except (ValueError, OSError):
                continue
    partes = [x for x in re.split(r"[\\/]+", candidatos[-1]) if x]
    if grupo.es_contexto or fila.get("desde_contexto"):
        return "contexto/" + "/".join(partes)
    return "entrada/" + "/".join(partes[-3:] if len(partes) > 3 else partes)
