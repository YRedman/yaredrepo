"""Un CSV por hoja de la matriz (solo biblioteca estandar), para consultarla sin Excel."""

import datetime
import re

from ... import VERSION
from ...comun.archivos import escribir_csv_filas, leer_texto
from ...comun.esquema import ARCHIVO_RESUMEN
from .esquema import COLUMNAS_RESUMEN, DESCRIPCIONES, cabecera_y_filas, nombre_csv
from .resumen import valores_resumen


def estado_construccion(raiz):
    p = raiz / ARCHIVO_RESUMEN
    m = re.search(r"Resultado:\s*\**([^*\n]+)", leer_texto(p)) if p.is_file() else None
    return m.group(1).strip() if m else "desconocido"


def exportar_csv(hojas, raiz, carpeta):
    """Un CSV por hoja de la matriz (UTF-8, separador ';') en ``carpeta``. Devuelve las rutas."""
    carpeta.mkdir(parents=True, exist_ok=True)
    for p in carpeta.glob("*.csv"):
        p.unlink()
    todas = [("Léeme", ["Hoja", "Contenido"],
              [["Estado de la construcción", estado_construccion(raiz)],
               ["Generada", f"{datetime.date.today():%d/%m/%Y} con convertir.py v{VERSION}"]]
              + [[n, d] for n, d in DESCRIPCIONES]),
             ("Resumen", COLUMNAS_RESUMEN, valores_resumen(hojas))]
    for nombre, filas in hojas.items():
        cabecera, filas, _ = cabecera_y_filas(nombre, filas)
        todas.append((nombre, cabecera, filas))
    rutas = []
    for nombre, cabecera, filas in todas:
        ruta = carpeta / nombre_csv(nombre)
        escribir_csv_filas(ruta, cabecera, filas)
        rutas.append(ruta)
    return rutas
