"""El log de la consola convertido a HTML."""

import re

from ...comun.markdown import celdas
from .elementos import alerta, esc

RE_SEPARADOR_MARKDOWN = re.compile(r"^\|[\s\-|:]+\|$")
RE_TITULO_DE_FASE = re.compile(r"^[A-ZÁÉÍÓÚÑ ]{5,} ·")
INICIOS_DE_ERROR = ("ERROR", "- PROBLEMA", "PROBLEMA")
INICIOS_DE_AVISO = ("AVISO", "REVISIÓN VISUAL", "Revisar en", "AVISOS")


def _tabla_markdown(lineas):
    """Tabla HTML de las lineas de una tabla markdown; vacia si solo tenian el separador."""
    filas = [celdas(l) for l in lineas if not RE_SEPARADOR_MARKDOWN.match(l.strip())]
    if not filas:
        return ""
    cabecera = "".join(f"<th>{esc(c)}</th>" for c in filas[0])
    cuerpo = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in f) + "</tr>" for f in filas[1:])
    return f'<div class="tabla-caja"><table><thead><tr>{cabecera}</tr></thead><tbody>{cuerpo}</tbody></table></div>'


def _linea(linea):
    if RE_TITULO_DE_FASE.match(linea) or linea.startswith("CONSTRUIR CORPUS"):
        return f"<h3>{esc(linea)}</h3>"
    if linea.startswith(INICIOS_DE_ERROR):
        return alerta("error", esc(linea))
    if linea.startswith(INICIOS_DE_AVISO):
        return alerta("aviso", esc(linea))
    return f'<div class="mono">{esc(linea)}</div>'


def log_a_html(texto):
    """El log de la consola con color: ERROR en rojo, AVISO / REVISIÓN en ambar y las tablas markdown como tablas."""
    salida, tabla = [], []
    for linea in (texto or "").splitlines():
        if linea.startswith("|"):
            tabla.append(linea)
            continue
        if tabla:
            salida.append(_tabla_markdown(tabla))
            tabla = []
        if linea.strip():
            salida.append(_linea(linea))
    if tabla:
        salida.append(_tabla_markdown(tabla))
    return "".join(salida)
