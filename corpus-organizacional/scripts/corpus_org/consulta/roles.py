"""Clasificacion de verbos y roles. Son ayudas automaticas: se confirman con el texto original."""

import re

from ..comun.texto import norm, oracion_con

# (etiqueta, raices). Se buscan al inicio de palabra para no confundir 'confirma' con 'firma'.
# 'firm' y 'liber' no indican aprobacion ("registrar la firma", "preparar la liberacion").
VERBOS = [
    ("Aprueba", r"aprob|aprueb|autoriz"),
    ("Revisa o verifica", r"revis|valid|verific|inspeccion|supervis"),
    ("Solicita", r"solicit|requier|requer|pide|pedir"),
    ("Entrega o envía", r"entreg|envi|remit|traslad|deriv|suministr|proporcion|despach|transfier"),
    ("Recibe", r"recib|recepcion"),
    ("Notifica o informa", r"notific|inform|comunic|avis"),
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


def verbo(texto, fragmento=None):
    """Verbo de la oracion donde aparece ``fragmento``; si hay varios, el mas cercano a la mencion.

    En "Compras solicita el material y lo envía a Almacén" el verbo de Almacén es 'envía', no 'solicita'.
    """
    oracion = oracion_con(texto, fragmento) if fragmento else norm(texto)
    f = norm(fragmento or "")
    pos = oracion.find(f) if f else -1
    candidatos = []
    for m in RE_VERBO.finditer(oracion):
        nombre = next(VERBOS[i][0] for i in range(len(VERBOS)) if m.group(f"v{i}"))
        distancia = abs(m.start() - pos) if pos >= 0 else m.start()
        candidatos.append((distancia, nombre))
    return min(candidatos)[1] if candidatos else "Mención"


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
