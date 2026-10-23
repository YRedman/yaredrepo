"""Matriz organizacional en Excel: base de datos del corpus publicado para revisarla sin ejecutar codigo.

Hojas: Léeme, Resumen (formulas), Puestos, Funciones, Relaciones, Perfil y requisitos, Normativa citada,
Procedimientos, Políticas y protocolos, Documentos generales, Participación, Puestos x Procedimientos,
Indicadores y Revisión. Cada hoja se exporta tambien a un CSV (UTF-8, separador ';') en matriz/.
Todo sale del corpus publicado: lo que no esta en un documento no se completa.

- ``hojas``: las filas de cada hoja (una funcion por hoja).
- ``esquema``: columnas, anchos y descripciones.
- ``exportacion`` (CSV, solo biblioteca estandar) y ``excel`` (requiere openpyxl).
"""

from ...comun.estructura import CARPETA_PUBLICADA, rutas_publicadas
from .excel import escribir_excel, guardar_libro
from .exportacion import exportar_csv
from .hojas import datos_matriz
from .resumen import valores_resumen

ARCHIVO_MATRIZ = "matriz_organizacional.xlsx"

__all__ = ["ARCHIVO_MATRIZ", "datos_matriz", "escribir_matriz", "exportar_csv", "guardar_libro", "valores_resumen"]


def escribir_matriz(raiz, destino=None):
    """Escribe en <raiz>/copilot/fuente-corpus/matriz/ matriz_organizacional.xlsx (requiere openpyxl) y un CSV
    por hoja (solo biblioteca estandar). ``raiz`` es salida_corpus. Devuelve la ruta del Excel."""
    _, hojas = datos_matriz(raiz)
    carpeta = rutas_publicadas(raiz / CARPETA_PUBLICADA).matriz
    exportar_csv(hojas, raiz, carpeta)
    return escribir_excel(hojas, raiz, destino or carpeta / ARCHIVO_MATRIZ)
