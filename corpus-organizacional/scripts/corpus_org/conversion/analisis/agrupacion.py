"""Agrupa los bloques por seccion y quita las secciones excluidas."""

from ..configuracion import SECCIONES_POR_TIPO
from ..secciones import buscar_alias, clave_titulo, es_excluida
from .bloques import excluir_bloque


def separar_secciones(bloques, tipo, a):
    """Quita las secciones excluidas y agrupa los bloques por seccion de primer nivel."""
    tabla_secciones = SECCIONES_POR_TIPO.get(tipo, [])
    nivel_base = min((b["nivel"] for b in bloques if b["k"] == "h"), default=1)
    resultado, secciones = [], []   # secciones: [titulo, campo, [bloques]]
    actual = None
    excluyendo = False
    for b in bloques:
        campo_titulo = _campo_de_titulo(b, tabla_secciones)
        if campo_titulo and actual is not None and actual[1] is None and not excluyendo:
            # un subtitulo o una tabla cuyo encabezado es una seccion conocida ("Función General/Objetivo
            # del Puesto:" bajo el titulo del puesto, "FUNCIONES ESPECÍFICAS" como cabecera de tabla)
            # abre una seccion logica aunque no sea un titulo de primer nivel
            actual = [_texto_titulo(b), campo_titulo, [] if b["k"] == "h" else [b]]
            secciones.append(actual)
            resultado.append(b)
            continue
        if b["k"] == "tabla" and campo_titulo and actual is not None and actual[1] != campo_titulo and not excluyendo:
            actual = [_texto_titulo(b), campo_titulo, [b]]
            secciones.append(actual)
            resultado.append(b)
            continue
        if b["k"] == "h" and b["nivel"] <= nivel_base:
            clave = clave_titulo(b["texto"])
            if es_excluida(clave):
                excluyendo = True
                a.secciones_excluidas.append(b["texto"])
                excluir_bloque(a, b)
                continue
            excluyendo = False
            actual = [b["texto"], buscar_alias(clave, tabla_secciones) if tabla_secciones else None, []]
            secciones.append(actual)
            resultado.append(b)
            continue
        if excluyendo:
            excluir_bloque(a, b)
            continue
        resultado.append(b)
        if actual is not None:
            actual[2].append(b)
    return resultado, secciones


def _texto_titulo(b):
    if b["k"] == "h":
        return b["texto"]
    return next((c for c in b["filas"][0] if c.strip()), "")


def _campo_de_titulo(b, tabla_secciones):
    """Campo de un subtitulo o de una tabla cuya primera celda con texto es el titulo de una seccion."""
    if not tabla_secciones:
        return None
    if b["k"] == "h":
        texto = b["texto"]
    elif b["k"] == "tabla" and b["filas"]:
        texto = _texto_titulo(b)
    else:
        return None
    clave = clave_titulo(texto)
    if not clave or len(clave.split()) > 8 or es_excluida(clave):
        return None
    return buscar_alias(clave, tabla_secciones)
