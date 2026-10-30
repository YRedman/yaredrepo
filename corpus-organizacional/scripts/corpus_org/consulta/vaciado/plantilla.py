"""Como esta organizada la plantilla metodologica: donde va el valor de cada rotulo y las columnas de cada tabla."""

import re

from ...comun.texto import norm
from .xlsx import columna_a_numero, numero_a_columna, partir_ref

FILA_ENCABEZADO_TABLA = 7
PRIMERA_FILA_TABLA = 8
ESTILO_ENTRADA_FILAS_NUEVAS = None        # lo decide quien escribe (se copia el de la fila de encabezado de entrada)


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

    def capacidad_de_filas(self, hoja, parte_de_tabla_ref):
        """Ultima fila de la tabla (de su ref 'B7:K18')."""
        return int(re.search(r"(\d+)$", parte_de_tabla_ref).group(1))

    def dias_por_mes(self, defecto):
        c = self.libro.hoja("Capacidad").celda("C11") if self.libro.hoja("Capacidad") else None
        return float(c.valor) if c is not None and isinstance(c.valor, (int, float)) else defecto
