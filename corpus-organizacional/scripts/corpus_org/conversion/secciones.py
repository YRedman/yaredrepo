"""Reconocimiento de titulos de seccion (comun a PDF, Word y analisis)."""

import re

from ..comun.texto import norm
from .configuracion import SECCIONES_D, SECCIONES_EXCLUIDAS, SECCIONES_P


def clave_titulo(s):
    """Titulo de seccion normalizado y sin numeracion: '6.1 Políticas:' -> 'politicas'."""
    s = norm(s)
    s = re.sub(r"^(?:\d{1,3}(?:\.\d{1,3})*\.?|[ivxlc]{1,6}\.|[a-z][\.\)])\s*", "", s)
    s = re.sub(r"[\s:\.\-–—]+$", "", s)
    s = re.sub(r"[^\w\s/]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def buscar_alias(clave, tabla):
    for alias, campo in tabla:
        if clave == alias or clave.startswith(alias + " ") or clave.startswith(alias + "/"):
            return campo
    return None


def etiqueta_exacta(texto, tabla, max_palabras=5):
    """Campo si el texto ES una etiqueta de ``tabla`` (igual tras normalizar, con o sin ':')."""
    c = clave_titulo(texto or "")
    if not c or len(c.split()) > max_palabras:
        return None
    return next((campo for alias, campo in tabla if c == alias), None)


def es_excluida(clave):
    return any(clave == a or clave.startswith(a + " ") for a in SECCIONES_EXCLUIDAS)


def es_seccion_conocida(clave):
    return bool(buscar_alias(clave, SECCIONES_P) or buscar_alias(clave, SECCIONES_D) or es_excluida(clave))


def profundidad_numeracion(texto):
    """'3.2 Alcance' -> 2; sin numeracion -> None."""
    m = re.match(r"^\s*(\d{1,3}(?:\.\d{1,3})*)\.?\s+\S", texto)
    return len(m.group(1).split(".")) if m else None


def es_titulo_corto(texto):
    return len(texto) <= 120 and len(texto.split()) <= 16
