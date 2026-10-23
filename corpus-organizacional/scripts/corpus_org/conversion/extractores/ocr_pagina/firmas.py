"""Campos de firma manuscrita: su lectura es ruido, no texto, y se quitan del resultado."""

import collections
import difflib
import re

from ....comun.texto import norm
from .texto import texto_celda


# Etiqueta de un campo de firma: a su lado hay un trazo manuscrito que el OCR lee como letras sueltas sin sentido.
RE_ETIQUETA_FIRMA = re.compile(r"\b(firma|firmas|firmado|rubrica|sello|(elaborado|revisado|aprobado|autorizado) por|"
                               r"gerente del area|director\s*/?\s*gerente)\b")
CONF_FIRMA_MIN = 75            # en un campo de firma solo se conservan las palabras leidas con al menos esta confianza


def es_etiqueta_de_firma(texto):
    return bool(RE_ETIQUETA_FIRMA.search(norm(texto)))


ROTULOS_DE_FIRMA = ("Firma de Aprobación", "Firma del Colaborador", "Firmas de Aprobación")


def rotulo_de_firma(texto):
    """El rotulo canonico («Firma de Aprobación») si ``texto`` es ese rotulo leido con ruido del OCR («de Firma de
    Aprobación», «Firma de Aj»); si no, el mismo texto."""
    n = norm(texto)
    if "firma" not in n or len(n) > 40:
        return texto
    cerca = difflib.get_close_matches(n, [norm(r) for r in ROTULOS_DE_FIRMA], n=1, cutoff=0.6)
    return next((r for r in ROTULOS_DE_FIRMA if norm(r) == cerca[0]), texto) if cerca else texto


def quitar_firmas(tablas):
    """Vacia las celdas que acompanan a una etiqueta de firma («Director / Gerente Sr. / Gerente del area:», «Firma de
    Aprobacion») cuando solo traen lecturas de baja confianza: son el trazo de la firma, no texto. Un nombre escrito a
    maquina junto a la firma (confianza alta) se conserva. Devuelve cuantos campos de firma se ignoraron."""
    ignoradas = 0
    for t in tablas:
        for fila in t.filas:
            etiquetas = [j for j, c in enumerate(fila) if es_etiqueta_de_firma(texto_celda(c))]
            if not etiquetas:
                continue
            for j, c in enumerate(fila):
                if j in etiquetas or not c.palabras:
                    continue
                firmes = [p for p in c.palabras if p[5] >= CONF_FIRMA_MIN]
                if sum(1 for p in firmes if len(re.findall(r"[^\W\d_]", p[0])) >= 3) < 2:
                    c.palabras, ignoradas = [], ignoradas + 1
                elif len(firmes) < len(c.palabras):
                    c.palabras = firmes
    return ignoradas


def quitar_firmas_en_lineas(palabras):
    """(palabras sin el trazo de firma, campos ignorados): en una linea que trae una etiqueta de firma se descartan las
    palabras de baja confianza (el trazo a su lado)."""
    lineas = collections.defaultdict(list)
    for p in palabras:
        lineas[p[6]].append(p)
    quitar, ignoradas = set(), 0
    for ps in lineas.values():
        if es_etiqueta_de_firma(" ".join(p[0] for p in sorted(ps, key=lambda q: q[1]))):
            malas = [id(p) for p in ps if p[5] < CONF_FIRMA_MIN]
            if malas:
                quitar.update(malas)
                ignoradas += 1
    return [p for p in palabras if id(p) not in quitar], ignoradas
