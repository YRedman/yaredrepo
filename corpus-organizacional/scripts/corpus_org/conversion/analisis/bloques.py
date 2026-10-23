"""Texto de un bloque del documento y registro del texto que se omite a proposito."""

from ...comun.esquema import MARCA_COMBINADA
from ...comun.texto import numeros, tokens


def texto_bloque(b):
    if b["k"] == "tabla":
        return " ".join(" ".join(c.replace(MARCA_COMBINADA, "") for c in f) for f in b["filas"])
    return b.get("texto", "")


def excluir_bloque(a, b):
    """Registra el texto de un bloque que se omite a proposito (no cuenta como faltante en la verificacion)."""
    texto = texto_bloque(b)
    a.excluidos.update(tokens(texto))
    a.excluidos_numeros.update(numeros(texto))
