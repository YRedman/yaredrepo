"""Analisis de un documento extraido: secciones, campos clave, actividades y codigos citados."""

import re

from ..comun.esquema import MARCA_COMBINADA
from ..comun.texto import norm, tokens
from .configuracion import (BLOQUES_INICIALES_METADATOS, CAMPOS_CLAVE, COLUMNAS_ACTIVIDAD, ETIQUETAS_D,
                            SECCIONES_POR_TIPO)
from .metadatos import extraer_metadatos
from .modelo import Analisis
from .secciones import buscar_alias, clave_titulo, es_excluida

# Codigos de otros documentos: al menos dos guiones (PR-ALM-001, NOM-035-STPS-2018).
# Asi no se confunden con normas o nombres como ISO-9001 o COVID-19.
RE_CODIGO_DOC = re.compile(r"\b[A-Z]{1,6}-[A-Z0-9]{2,6}-(?:[A-Z0-9]{1,6}-)?\d{1,4}\b")


def texto_bloque(b):
    if b["k"] == "tabla":
        return " ".join(" ".join(c.replace(MARCA_COMBINADA, "") for c in f) for f in b["filas"])
    return b.get("texto", "")


def analizar(doc, tipo):
    """Devuelve ``(bloques_publicables, Analisis)`` sin modificar ``doc``."""
    a = Analisis()
    bloques, secciones = _separar_secciones(doc.bloques, tipo, a)
    a.campos = _campos_de_secciones(secciones)
    if tipo == "D":
        _campos_por_etiqueta(bloques, a.campos)
    a.subprocedimientos = [b["texto"] for _t, campo, bs in secciones if campo == "desarrollo"
                           for b in bs if b["k"] == "h"]
    a.titulos = [s[0] for s in secciones]
    a.faltantes = [nombre for campo, nombre in CAMPOS_CLAVE.get(tipo, []) if not a.campos.get(campo, "").strip()]
    # En materiales de contexto (glosarios, organigramas) las tablas "Etiqueta | Valor" son contenido,
    # no metadatos del documento: ahi solo se lee el encabezado.
    iniciales = [] if tipo == "C" else bloques[:BLOQUES_INICIALES_METADATOS]
    a.metadatos = extraer_metadatos(doc.encabezado, iniciales)
    a.actividades = _actividades(secciones) if tipo == "P" else []
    a.codigos_citados = _codigos_citados(doc.encabezado, bloques, a.metadatos.codigo_interno)
    return bloques, a


def _separar_secciones(bloques, tipo, a):
    """Quita las secciones excluidas y agrupa los bloques por seccion de primer nivel."""
    tabla_secciones = SECCIONES_POR_TIPO.get(tipo, [])
    nivel_base = min((b["nivel"] for b in bloques if b["k"] == "h"), default=1)
    resultado, secciones = [], []   # secciones: [titulo, campo, [bloques]]
    actual = None
    excluyendo = False
    for b in bloques:
        if b["k"] == "h" and b["nivel"] <= nivel_base:
            clave = clave_titulo(b["texto"])
            if es_excluida(clave):
                excluyendo = True
                a.secciones_excluidas.append(b["texto"])
                a.excluidos.update(tokens(b["texto"]))
                continue
            excluyendo = False
            actual = [b["texto"], buscar_alias(clave, tabla_secciones) if tabla_secciones else None, []]
            secciones.append(actual)
            resultado.append(b)
            continue
        if excluyendo:
            a.excluidos.update(tokens(texto_bloque(b)))
            continue
        resultado.append(b)
        if actual is not None:
            actual[2].append(b)
    return resultado, secciones


def _campos_de_secciones(secciones):
    campos = {}
    for _titulo, campo, bloques in secciones:
        if not campo or campo in campos:
            continue
        texto = " ".join(texto_bloque(b) for b in bloques if b["k"] != "h").strip()
        if texto:
            campos[campo] = texto
        elif any(b["k"] == "h" for b in bloques):
            campos[campo] = " ".join(texto_bloque(b) for b in bloques)
    return campos


def _campos_por_etiqueta(bloques, campos):
    """Datos del puesto en tablas 'Etiqueta | Valor' o lineas 'Etiqueta: valor' (descriptivos)."""
    for b in bloques:
        if b["k"] == "tabla":
            for f in b["filas"]:
                for j in range(len(f) - 1):
                    clave = clave_titulo(f[j])
                    c = buscar_alias(clave, ETIQUETAS_D)
                    if c and len(clave.split()) <= 4 and f[j + 1].strip() and c not in campos:
                        campos[c] = f[j + 1].replace(MARCA_COMBINADA, "").strip()
        elif b["k"] in ("p", "li"):
            m = re.match(r"^([^:]{2,40}):\s*(\S.*)$", b["texto"])
            if m:
                c = buscar_alias(clave_titulo(m.group(1)), ETIQUETAS_D)
                if c and c not in campos:
                    campos[c] = m.group(2).strip()


def _actividades(secciones):
    """Actividades documentadas: items de lista y celdas de la columna 'Actividad' en el desarrollo.

    Las vinetas de otras secciones (alcance, politicas, referencias...) no son actividades.
    """
    actividades = []
    for _titulo, campo, bloques in secciones:
        if campo != "desarrollo":
            continue
        for b in bloques:
            if b["k"] == "li" and b.get("texto", "").strip():
                actividades.append(b["texto"].strip())
            elif b["k"] == "tabla" and b["filas"]:
                cols = [j for j, c in enumerate(b["filas"][0]) if norm(c).startswith(COLUMNAS_ACTIVIDAD)]
                for f in b["filas"][1:]:
                    for j in cols:
                        valor = f[j].replace(MARCA_COMBINADA, "").strip() if j < len(f) else ""
                        if valor and not f[j].endswith(MARCA_COMBINADA):
                            actividades.append(valor)
    return actividades


def _codigos_citados(encabezado, bloques, codigo_interno):
    todo = " ".join(encabezado) + " " + " ".join(texto_bloque(b) for b in bloques)
    return sorted(set(RE_CODIGO_DOC.findall(todo)) - ({codigo_interno} if codigo_interno else set()))
