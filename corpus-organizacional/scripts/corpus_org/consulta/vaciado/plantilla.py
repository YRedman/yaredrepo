"""Como esta organizada la plantilla metodologica: donde va el valor de cada rotulo y las columnas de cada tabla."""

import re

from ...comun.texto import norm
from .xlsx import columna_a_numero, numero_a_columna, partir_ref

FILA_ENCABEZADO_TABLA = 7
PRIMERA_FILA_TABLA = 8


def clave(texto):
    """Texto de un encabezado o rotulo comparable: sin acentos, mayusculas ni el asterisco de obligatorio."""
    return norm(re.sub(r"\*", "", str(texto or ""))).strip()


class Plantilla:
    """Consultas sobre el libro de la plantilla (solo lectura)."""

    def __init__(self, libro):
        self.libro = libro

    def valor_de_rotulo(self, hoja, rotulo, direccion):
        """Referencia de la celda donde se escribe el valor del rotulo: 'derecha' (Control) o 'abajo' (Perfil_Puesto)."""
        h = self.libro.hoja(hoja)
        buscado = clave(rotulo)
        for ref, c in h.celdas.items():
            if isinstance(c.valor, str) and clave(c.valor) == buscado:
                col, fila = partir_ref(ref)
                if direccion == "derecha":
                    return f"{numero_a_columna(columna_a_numero(col) + 1)}{fila}"
                return f"{col}{fila + 1}"
        return None

    def columnas_de_tabla(self, hoja):
        """{encabezado normalizado: letra de columna} de la fila de encabezados de la tabla."""
        h = self.libro.hoja(hoja)
        return {clave(c.valor): col for col, c in h.fila(FILA_ENCABEZADO_TABLA).items()
                if isinstance(c.valor, str) and c.valor.strip()}

    def estilo_de_entrada(self, hoja, columna):
        """Estilo de las celdas de entrada de una columna (el de su primera fila de datos)."""
        c = self.libro.hoja(hoja).celda(f"{columna}{PRIMERA_FILA_TABLA}")
        return c.estilo if c else None

    def catalogo(self, encabezado, hoja="Catálogos", fila_encabezado=6):
        """Opciones de una lista de la hoja de catalogos (columna cuyo encabezado, en la fila 6, es ``encabezado``); [] si no esta."""
        h = self.libro.hoja(hoja)
        if h is None:
            return []
        for col, c in h.fila(fila_encabezado).items():
            if isinstance(c.valor, str) and clave(c.valor) == clave(encabezado):
                opciones = []
                for n in range(fila_encabezado + 1, max(h.filas()) + 1):
                    v = h.valor(f"{col}{n}")
                    if isinstance(v, str) and v.strip():
                        opciones.append(v.strip())
                    elif opciones:
                        break
                return opciones
        return []

    def dias_por_mes(self, defecto):
        c = self.libro.hoja("Capacidad").celda("C11") if self.libro.hoja("Capacidad") else None
        return float(c.valor) if c is not None and isinstance(c.valor, (int, float)) else defecto
