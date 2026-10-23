"""Verificacion de que el Markdown conserva el texto del original."""

import collections
import re

from ..comun.esquema import RE_MARCAS
from ..comun.texto import numeros, tokens
from .analisis.bloques import texto_bloque
from .modelo import Verificacion


def _ubicar_faltantes(faltan, lineas_diag):
    """Cuenta las palabras faltantes por (pagina, zona) del original y guarda un ejemplo de cada zona."""
    origen, ejemplos = collections.Counter(), {}
    if not faltan:
        return origen, ejemplos
    pendientes = set(faltan)
    for pag, zona, txt in lineas_diag:
        tk = set(tokens(txt)) & pendientes
        if tk:
            origen[(pag, zona)] += sum(faltan[t] for t in tk)
            ejemplos.setdefault((pag, zona), txt[:90])
            pendientes -= tk
        if not pendientes:
            break
    if pendientes:
        origen[(0, "sin ubicar")] += sum(faltan[t] for t in pendientes)
    return origen, ejemplos


def _fragmentos(palabras, minimo=3):
    """Principios y finales (de ``minimo`` letras o mas) de las palabras: lo que queda de una palabra partida."""
    res = set()
    for w in palabras:
        for i in range(1, len(w) - minimo + 1):
            res.add(w[i:])
        for j in range(minimo, len(w)):
            res.add(w[:j])
    return res


def verificar(doc, bloques, analisis, cuerpo_md):
    """Compara el texto del original con el Markdown generado."""
    texto = re.sub(r"(?m)^#+\s", " ", RE_MARCAS.sub(" ", cuerpo_md))
    salida = collections.Counter(tokens(texto))
    esperado = doc.crudo.copy()
    esperado.subtract(doc.retirados)
    esperado.subtract(analisis.excluidos)
    esperado = +esperado
    faltan = esperado - salida
    total = sum(esperado.values())
    ocr = collections.Counter()
    for b in bloques:
        if b.get("ocr"):
            ocr.update(tokens(texto_bloque(b)))
    # el texto de una pagina escaneada viene del OCR: sus palabras no son "agregadas" aunque terminen
    # en una tabla o en un bloque que no lleva la marca de OCR
    crudo_set = set(doc.crudo) | doc.crudo_encabezado | doc.crudo_ocr
    agregadas = sorted(t for t in set(salida - ocr) - crudo_set
                       if not t.isdigit() and len(t) > 2 and not re.match(r"^[ivxlc]+$", t))
    cobertura = 100.0 if total == 0 else 100.0 * (total - sum(faltan.values())) / total
    origen, ejemplos = _ubicar_faltantes(faltan, doc.lineas_diag)
    cruz = []
    if doc.texto_cruzado is not None:
        base = set(doc.crudo) | doc.crudo_encabezado | set(analisis.excluidos)
        partes = _fragmentos(base)       # "atriz" de "M atriz": el segundo motor parte la palabra, no es otra palabra
        cruz = sorted(t for t in doc.texto_cruzado - base if len(t) > 2 and not t.isdigit() and t not in partes)
    numeros_faltan = +((doc.numeros - analisis.excluidos_numeros) - numeros(texto))
    return Verificacion(total=total, faltan=faltan, cobertura=cobertura, agregadas=agregadas, cruz=cruz,
                        origen=origen, ejemplos=ejemplos, numeros_faltan=numeros_faltan)
