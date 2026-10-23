"""Identidad de un documento (sin extension ni copias) y utilidades de tipo para ordenar y nombrar."""

import collections
import os

from ...comun.texto import nfc, norm
from ...comun.tipos import TIPOS_DOCUMENTO, tipo as tipo_documento
from ..configuracion import PREFERENCIA_EXT
from .modelo import RE_SUFIJO_COPIA


def clave_documento(nombre):
    """Identidad de un documento sin extension ni sufijo de copia: 'Compra (1).pdf' -> 'compra'."""
    return norm(RE_SUFIJO_COPIA.sub("", os.path.splitext(nfc(nombre))[0]))


def es_copia(nombre):
    return bool(RE_SUFIJO_COPIA.search(os.path.splitext(nombre)[0]))


def plural_de_tipo(codigo_tipo):
    t = tipo_documento(codigo_tipo)
    return t.plural if t else codigo_tipo


def nombre_de_tipo(codigo_tipo):
    t = tipo_documento(codigo_tipo)
    return t.nombre if t else codigo_tipo


ORDEN_DE_TIPOS = {t.codigo: i for i, t in enumerate(TIPOS_DOCUMENTO)}


def orden_de_tipo(codigo_tipo):
    return ORDEN_DE_TIPOS.get(codigo_tipo, len(ORDEN_DE_TIPOS))


def quitar_duplicados(filas, incluir=False):
    """Un mismo documento en .docx y .pdf, o una copia '(1)', se inventaria una sola vez.

    Se conserva el original (sin sufijo de copia) en el formato preferido (.docx). Con ``incluir``
    se conservan todos. Devuelve (filas, avisos).
    """
    grupos = collections.OrderedDict()
    for f in filas:
        grupos.setdefault((f["tipo"], norm(f["departamento"]), clave_documento(f["archivo"])), []).append(f)
    salida, avisos = [], []
    for (tipo, _dep, _doc), lista_f in grupos.items():
        if len(lista_f) == 1:
            salida += lista_f
            continue
        if incluir:
            salida += lista_f
            avisos.append("Posible duplicado conservado (--incluir-duplicados): "
                          + ", ".join(f["archivo"] for f in lista_f))
            continue
        lista_f.sort(key=lambda f: (es_copia(f["archivo"]),
                                    PREFERENCIA_EXT.get(os.path.splitext(f["archivo"])[1].lower(), 9), f["archivo"]))
        salida.append(lista_f[0])
        avisos.append(f"Duplicado en {plural_de_tipo(tipo)}/{lista_f[0]['departamento']}: se usa «{lista_f[0]['archivo']}» "
                      f"y se descarta {', '.join('«' + f['archivo'] + '»' for f in lista_f[1:])}")
    return salida, avisos
