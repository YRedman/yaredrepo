"""Actividades de un procedimiento, tomadas de las tablas de su desarrollo."""

from ...comun.esquema import MARCA_COMBINADA
from ...comun.texto import norm
from ..configuracion import COLUMNAS_ACTIVIDAD, COLUMNAS_RESPONSABLE


def _columna(cabecera, prefijos):
    """Indice de la primera columna cuya cabecera empieza con alguno de ``prefijos`` (en orden de preferencia)."""
    for prefijo in prefijos:
        j = next((j for j, c in enumerate(cabecera) if c.startswith(prefijo)), None)
        if j is not None:
            return j
    return None


def _actividades_de_tabla(filas):
    cabecera = [norm(c) for c in filas[0]]
    ia = _columna(cabecera, COLUMNAS_ACTIVIDAD)
    if ia is None:
        return []
    ir = _columna(cabecera, COLUMNAS_RESPONSABLE)
    actividades = []
    for f in filas[1:]:
        if ia >= len(f) or f[ia].endswith(MARCA_COMBINADA):
            continue   # una celda combinada repite la actividad de arriba
        actividad = f[ia].strip()
        if not actividad:
            continue
        responsable = f[ir].replace(MARCA_COMBINADA, "").strip() if ir is not None and ir < len(f) else ""
        actividades.append(actividad + (f" (Responsable: {responsable})" if responsable else ""))
    return actividades


def actividades_del_desarrollo(secciones):
    """Actividades documentadas en la seccion de desarrollo de un procedimiento.

    Si el desarrollo tiene tablas, son sus filas (columna Actividad/Descripcion...) con su responsable;
    si no, sus vinetas. Las vinetas de otras secciones (alcance, politicas, referencias) nunca son actividades.
    """
    actividades = []
    for _titulo, campo, bloques in secciones:
        if campo != "desarrollo":
            continue
        desde_tablas = [a for b in bloques if b["k"] == "tabla" and len(b["filas"]) >= 2
                        for a in _actividades_de_tabla(b["filas"])]
        actividades += desde_tablas or [b["texto"].strip() for b in bloques if b["k"] == "li" and b.get("texto", "").strip()]
    return actividades
