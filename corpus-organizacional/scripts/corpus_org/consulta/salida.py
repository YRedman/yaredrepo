"""Salida de texto de los comandos (inyectable para pruebas)."""

import sys

from ..comun.markdown import tabla


class Salida:
    def __init__(self, flujo=None):
        self.flujo = flujo or sys.stdout

    def linea(self, texto=""):
        self.flujo.write(f"{texto}\n")

    def tabla(self, cabecera, filas):
        self.linea(tabla(cabecera, filas))

    def lista(self, elementos, prefijo="- "):
        for e in elementos:
            self.linea(f"{prefijo}{e}")


def resumir_lista(codigos, n=30):
    codigos = list(codigos)
    return ", ".join(codigos[:n]) + (f" … y {len(codigos) - n} más" if len(codigos) > n else "")
