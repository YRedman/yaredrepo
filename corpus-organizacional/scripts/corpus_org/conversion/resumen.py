"""RESUMEN_CONSTRUCCION.md: el resultado de la validacion para leerlo sin abrir la consola."""

import datetime

from .. import VERSION
from ..comun.esquema import ARCHIVO_HUELLAS, ARCHIVO_REVISADOS, ARCHIVO_REVISION
from ..comun.estructura import CARPETA_DOCUMENTOS, SKILL_CORPUS
from ..comun.markdown import esc_celda
from .huella import huella


def _tabla_de_documentos(v, filas, ultima_columna):
    """Tabla markdown Codigo | Archivo | Ubicacion del original | ``ultima_columna`` de {codigo: texto}."""
    lineas = [f"| Código | Archivo | Ubicación del original | {ultima_columna} |", "|---|---|---|---|"]
    for codigo, texto in filas.items():
        archivo, ruta = v.ubicacion_de(codigo)
        lineas.append(f"| {codigo} | {esc_celda(archivo)} | `{esc_celda(ruta)}` | {esc_celda(texto)} |")
    return lineas + [""]


def _lista(titulo, items):
    return [f"## {titulo}", ""] + ["- " + x for x in items] + [""]


def escribir_resumen_construccion(path, v, publicados, medidas=()):
    lineas = [
        "# Resumen de construcción del corpus", "",
        f"- Fecha: {datetime.datetime.now():%Y-%m-%d %H:%M}",
        f"- convertir.py: v{VERSION} · huella {huella()}",
        f"- Resultado: **{v.estado}**", "",
        f"- Documentos inventariados: {v.documentos_inventariados}",
        f"- Documentos indexados: {v.documentos_indexados}",
        f"- Documentos con texto: {v.documentos_con_texto}",
        f"- Archivos publicados: {len(publicados)}", "",
    ]
    if medidas:
        lineas += _lista("Peso y número de archivos por carpeta", medidas)
    if v.problemas:
        lineas += _lista("Problemas", v.problemas)
    if v.con_problemas:
        lineas += ["## Documentos con problemas y dónde está su original", ""]
        lineas += _tabla_de_documentos(v, {c: "; ".join(m) for c, m in v.con_problemas.items()}, "Problema")
    if v.revision_visual:
        lineas += ["## Revisión visual pendiente", "",
                   "Abra cada documento original junto a su Markdown. Cuando esté correcto, agregue su código a "
                   f"`{ARCHIVO_REVISADOS}` (uno por línea) y vuelva a ejecutar `construir`.", ""]
        lineas += _tabla_de_documentos(v, v.revision_visual, "Motivo")
    if v.avisos:
        lineas += _lista("Avisos", v.avisos)
    lineas += ["## Carpetas", "",
               f"- `copilot/{SKILL_CORPUS}/`: el único skill. `{CARPETA_DOCUMENTOS}/` (documentos de área, una carpeta por "
               "tipo: DES, PRD, PRO, POL), `contexto/` (documentos generales y kpis.csv), `indice/` (índice, "
               f"inventario, equivalencias, `{ARCHIVO_HUELLAS}` y este resumen), `matriz/` y `scripts/`.",
               f"- `control/`: reportes, diccionarios parciales, `{ARCHIVO_REVISION}` y evidencia de QA "
               "(no se publica).", ""]
    path.write_text("\n".join(lineas), encoding="utf-8")
