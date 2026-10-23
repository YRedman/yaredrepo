"""Informe HTML de la construccion: el mismo log de la consola, pero para revisarlo con la vista.

Un solo archivo (``salida_corpus/INFORME_CONSTRUCCION.html``) sin dependencias ni red: estilos y filtros en linea,
claro y oscuro segun el sistema, que se abre con doble clic. Resume el resultado, las alertas, la cobertura por area, la
revision visual pendiente (con enlace a cada original), la calidad de lectura (OCR), los tiempos y todos los
documentos con busqueda y orden. Lee lo que ya escribio ``construir`` (indice, ``control/``) y el log de la consola
guardado en ``control/log_construccion.txt``.

Para agregar una seccion: una funcion en ``secciones.py`` y una linea en ``SECCIONES``.
"""

from pathlib import Path

from ...comun.esquema import ARCHIVO_INFORME
from . import secciones
from .datos import DatosInforme
from .elementos import esc
from .estilos import CSS, JS

SECCIONES = (secciones.navegacion, secciones.tarjetas, secciones.alertas, secciones.cobertura, secciones.revision_visual,
             secciones.calidad_de_lectura, secciones.tiempos, secciones.documentos, secciones.log)


def _cabecera(d):
    clase, etiqueta = d.estado
    return ("<header><h1>Informe de construcción del corpus</h1>"
            f'<div class="suave">convertir.py v{esc(d.datos.get("version", ""))} · {esc(d.fecha)} · '
            f'<span class="estado {clase}">{esc(etiqueta)}</span></div></header>')


def construir_html(d):
    """El HTML completo del informe para los datos de una construccion."""
    return ('<!doctype html><html lang="es"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>Informe de construcción del corpus</title><style>{CSS}</style></head><body>"
            + _cabecera(d) + "<main>" + "".join(seccion(d) for seccion in SECCIONES)
            + f"</main><script>{JS}</script></body></html>")


def generar_informe(raiz_salida, texto_log=None, destino=None):
    """Escribe el informe HTML de la ultima construccion y devuelve su ruta."""
    destino = Path(destino) if destino else Path(raiz_salida) / ARCHIVO_INFORME
    destino.write_text(construir_html(DatosInforme.leer(raiz_salida, texto_log)), encoding="utf-8")
    return destino
