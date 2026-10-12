"""Clasificacion de verbos y roles. Son ayudas automaticas: se confirman con el texto original."""

import re

from ..comun.texto import norm

# (etiqueta, raices). Se buscan al inicio de palabra para no confundir 'confirma' con 'firma'.
VERBOS = [
    ("Aprueba o revisa", r"aprueb|autoriz|revis|valid|verific|liber|firm"),
    ("Solicita", r"solicit|requier|requer|pide|pedir"),
    ("Entrega o envía", r"entreg|envi|remit|traslad|deriv|suministr|proporcion|despach|transfier"),
    ("Recibe", r"recib|recepcion"),
    ("Notifica o informa", r"notific|inform|comunic|avis"),
    ("Reporta", r"report"),
    ("Coordina", r"coordin|acuerd"),
]
_RE_VERBOS = [(nombre, re.compile(r"\b(?:" + raices + r")")) for nombre, raices in VERBOS]
ROL_APRUEBA = re.compile(r"\b(?:aprueb|aprob|autoriz|firm|liber)")
ROL_REVISA = re.compile(r"\b(?:revis|valid|verific|supervis|inspeccion)")
COLUMNAS_RESPONSABLE = ("quien", "ejecuta", "rol")


def verbo(texto):
    n = norm(texto)
    for nombre, patron in _RE_VERBOS:
        if patron.search(n):
            return nombre
    return "Mención"


def rol(columna, oracion, seccion):
    """Rol de un puesto mencionado en un procedimiento.

    ``oracion`` es solo la oracion donde aparece el puesto (no toda la linea).
    """
    ncol = norm(columna)
    if ncol.startswith("responsab") or ncol in COLUMNAS_RESPONSABLE:
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
