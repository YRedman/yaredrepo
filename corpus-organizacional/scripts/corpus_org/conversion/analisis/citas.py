"""Codigos de otros documentos que el documento cita."""

import re

from .bloques import texto_bloque


# Codigos de otros documentos: al menos dos guiones (PR-ALM-001, NOM-035-STPS-2018).
# Asi no se confunden con normas o nombres como ISO-9001 o COVID-19.
CODIGO_DOC = r"[A-Z]{1,6}-[A-Z0-9]{2,6}-(?:[A-Z0-9]{1,6}-){0,2}\d{1,4}"     # hasta 5 segmentos: XYZ-ALMA-RD-PRO-011
RE_CODIGO_PROPIO = re.compile(r"C[oó]digo\s*:?\s*(" + CODIGO_DOC + r")\b")
RE_CODIGO_DOC = re.compile(r"\b" + CODIGO_DOC + r"\b")


def codigos_citados(encabezado, bloques, codigo_interno):
    todo = " ".join(encabezado) + " " + " ".join(texto_bloque(b) for b in bloques)
    # los codigos que el encabezado escribe tras «Código:» son del propio documento (a veces con el de una version
    # anterior): no son citas
    propios = set(RE_CODIGO_PROPIO.findall(" ".join(encabezado)))
    return sorted(set(RE_CODIGO_DOC.findall(todo)) - propios - ({codigo_interno} if codigo_interno else set()))
