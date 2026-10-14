"""Clasificacion de verbos y roles. Son ayudas automaticas: se confirman con el texto original."""

import re

from ..comun.texto import norm, oracion_con

# (etiqueta, raices). Se buscan al inicio de palabra para no confundir 'confirma' con 'firma'.
# 'firm' y 'liber' no indican aprobacion ("registrar la firma", "preparar la liberacion").
VERBOS = [
    ("Aprueba o revisa", r"aprob|aprueb|autoriz|revis|valid|verific|inspeccion|supervis"),
    ("Solicita", r"solicit|requier|requer|pide|pedir"),
    ("Entrega", r"entreg|envi|remit|traslad|deriv|suministr|proporcion|despach|transfier"),
    ("Recibe", r"recib|recepcion"),
    ("Notifica", r"notific|inform|comunic|avis"),
    ("Reporta", r"report"),
    ("Coordina", r"coordin|acuerd"),
]
RE_VERBO = re.compile(r"\b(?:" + "|".join(f"(?P<v{i}>{raices})" for i, (_, raices) in enumerate(VERBOS)) + r")")
ROL_APRUEBA = re.compile(r"\b(?:aprob|aprueb|autoriz)")
ROL_REVISA = re.compile(r"\b(?:revis|valid|verific|supervis|inspeccion)")
COLUMNAS_RESPONSABLE = ("quien", "ejecuta", "rol")


def es_columna_responsable(columna):
    ncol = norm(columna)
    return ncol.startswith("responsab") or ncol in COLUMNAS_RESPONSABLE


def _verbo_cercano(texto, fragmento):
    """Verbo de la oracion donde aparece ``fragmento``; si hay varios, el mas cercano a la mencion."""
    oracion = oracion_con(texto, fragmento) if fragmento else norm(texto)
    f = norm(fragmento or "")
    pos = oracion.find(f) if f else -1
    candidatos = []
    for m in RE_VERBO.finditer(oracion):
        nombre = next(VERBOS[i][0] for i in range(len(VERBOS)) if m.group(f"v{i}"))
        candidatos.append((abs(m.start() - pos) if pos >= 0 else m.start(), nombre))
    return min(candidatos)[1] if candidatos else "Mención"


def verbo(texto, fragmento=None):
    """Verbo con el que se menciona ``fragmento`` en ``texto``.

    En una fila de tabla se busca primero en la celda de la mencion: en "| Entregar la mercancía a Almacén |
    coordinadores de logística |" el verbo de Almacén es 'Entregar', no el sustantivo 'coordinadores'.
    Si esa celda no tiene verbo se usa la fila completa.
    """
    if texto.lstrip().startswith("|") and fragmento:
        f = norm(fragmento)
        celda = next((c for c in texto.strip().strip("|").split("|") if f in norm(c)), None)
        if celda is not None:
            v = _verbo_cercano(celda, fragmento)
            if v != "Mención":
                return v
    return _verbo_cercano(texto, fragmento)


def rol(columna, oracion, seccion):
    """Rol de un puesto mencionado en un procedimiento.

    ``oracion`` es solo la oracion donde aparece el puesto (no toda la linea).
    """
    if es_columna_responsable(columna):
        return "Ejecuta (responsable del paso)"
    n = norm(oracion)
    if ROL_APRUEBA.search(n):
        return "Aprueba"
    if ROL_REVISA.search(n):
        return "Revisa o verifica"
    if "responsab" in norm(seccion):
        return "Responsabilidad asignada"
    if columna:
        return f"Mencionado en la columna «{columna}»"
    return "Mencionado"
