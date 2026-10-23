"""Avisos de estructura: indicios de que la conversion pudo alterar el orden o repetir contenido."""

import collections
import re

from ...comun.esquema import MARCA_COMBINADA
from ...comun.texto import norm, tokens
from .bloques import texto_bloque


def _pagina(b):
    p = b.get("pagina")
    return f"p.{p + 1}" if isinstance(p, int) else "documento"


CERCA_REPETIDO = 3      # bloques: un parrafo repetido tan cerca de su copia es casi seguro un duplicado


def es_subtitulo(texto):
    """Linea corta sin punto final («Jurídicos», «Personas Físicas»): rotula la lista que sigue."""
    t = texto.strip()
    return 0 < len(t.split()) <= 6 and not t.endswith((".", ";", ","))


RE_FIN_DE_FLUJO = re.compile(r"^\s*fin\b(?:\s+\w+){0,3}\s*\.?\s*$", re.I)      # «Fin del proceso»: fila propia de un flujo


def _hay_separador(bloques, i, j):
    """True si entre dos bloques hay un titulo, un subtitulo o una frase que introduce una lista («Director Comercial:»): la misma
    funcion repetida para dos puestos es contenido del original, no un duplicado de la conversion."""
    return any(b["k"] == "h" or (b["k"] == "p" and (b.get("texto", "").rstrip().endswith(":") or es_subtitulo(b["texto"])))
               for b in bloques[i + 1:j])


def _repetidos_por_conversion(bloques):
    """Parrafos largos que aparecen dos veces como si la conversion los hubiera duplicado: en la misma pagina o a
    pocos bloques de distancia. Una frase que vuelve en otra pagina (el pie de cada diapositiva, una clausula que
    el documento repite en dos secciones) es contenido del original, no un duplicado de la conversion."""
    posiciones = collections.defaultdict(list)
    for i, b in enumerate(bloques):
        if b["k"] in ("p", "li") and len(b.get("texto", "")) >= 40 and not b["texto"].rstrip().endswith(":"):
            pag = b.get("pagina")
            posiciones[norm(b["texto"])].append((i, pag if isinstance(pag, int) else None))
    repetidos = []
    for t, apariciones in posiciones.items():
        if any((a[1] is None or b[1] is None or a[1] == b[1] or b[0] - a[0] <= CERCA_REPETIDO)
               and not _hay_separador(bloques, a[0], b[0])
               for k, a in enumerate(apariciones) for b in apariciones[k + 1:]):
            repetidos.append(t)
    return repetidos


def avisos_de_estructura(bloques, imagenes_grandes, hoja_de_calculo=False):
    """Senales de que la estructura pudo leerse mal aunque el texto este completo.

    - tabla con filas sin primera celda (fila partida que quedo como fila nueva);
    - parrafos largos repetidos (contenido duplicado por la conversion);
    - documento cuyo contenido esta sobre todo en imagenes (hay que transcribirlo a mano).
    """
    avisos = []
    for b in bloques:
        if b["k"] == "tabla" and len(b["filas"]) >= 4 and not hoja_de_calculo:
            datos = b["filas"][1:]
            if sum(1 for f in datos if f and f[0].strip()) >= 0.8 * len(datos):
                huerfanas = [f for f in datos if f and not f[0].strip()
                             and any(c.strip() and not c.endswith(MARCA_COMBINADA) for c in f[1:])]
                huerfanas = [f for f in huerfanas if not RE_FIN_DE_FLUJO.match(" ".join(c for c in f if c.strip()))]
                if huerfanas:
                    avisos.append(f"{_pagina(b)}: {len(huerfanas)} filas de tabla sin primera celda "
                                  "(posible fila partida)")
    repetidos = _repetidos_por_conversion(bloques)
    if repetidos:
        avisos.append(f"{len(repetidos)} párrafos repetidos (posible duplicado de conversión): «{repetidos[0][:60]}…»")
    palabras = sum(len(tokens(texto_bloque(b))) for b in bloques if b["k"] != "marca")
    if imagenes_grandes >= 3 and palabras < 40 * imagenes_grandes:
        avisos.append(f"el contenido está sobre todo en imágenes ({imagenes_grandes} imágenes, {palabras} palabras): "
                      "transcribirlo a mano (.md o .csv) si es relevante")
    return avisos
