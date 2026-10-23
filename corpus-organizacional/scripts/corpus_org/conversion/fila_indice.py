"""Fila del indice (DIC_*.csv) de un documento convertido."""

import os

from ..comun.esquema import NO_ESPECIFICADO, SEPARADOR_LISTA
from ..comun.texto import recortar_palabras
from ..comun.tipos import tipo as tipo_documento


def fila_indice(r, grupo, archivo_md, linea_ini, linea_fin):
    """Fila del indice (DIC_*.csv) de un documento convertido."""
    a, meta, ctx = r.analisis, r.analisis.metadatos, grupo.es_contexto
    campos = a.campos
    proposito = recortar_palabras(campos.get("objetivo") or campos.get("proposito", ""), 40)
    es_d = grupo.familia == "D"
    td = tipo_documento(grupo.tipo)
    return {
        "codigo": r.codigo, "tipo": td.nombre if td else grupo.tipo, "codigo_departamento": grupo.codigo_dep,
        "departamento": grupo.departamento, "nombre": os.path.splitext(r.archivo)[0],
        "archivo_origen": r.archivo, "codigo_interno": meta.codigo_interno, "version": meta.version,
        "estado_documental": meta.estado_documental, "fecha_vigencia": meta.fecha_vigencia,
        "propietario": meta.propietario, "responsable": meta.responsable,
        "macroproceso": recortar_palabras(campos.get("macroproceso", ""), 30),
        "proceso": recortar_palabras(meta.proceso, 30),
        "proposito_literal": proposito or ("" if ctx else NO_ESPECIFICADO),
        "nombre_puesto": campos.get("nombre_puesto", "") if es_d else "",
        "reporta_a": campos.get("reporta_a", "") if es_d else "",
        "supervisa_a": campos.get("supervisa_a", "") if es_d else "",
        "secciones": SEPARADOR_LISTA.join(a.titulos),
        "actividades": SEPARADOR_LISTA.join(a.actividades),
        "subprocedimientos": SEPARADOR_LISTA.join(a.subprocedimientos),
        "codigos_citados": ", ".join(a.codigos_citados),
        "campos_no_especificados": ", ".join(a.faltantes),
        "paginas": r.doc.paginas or "", "palabras": r.palabras, "cobertura": f"{r.verificacion.cobertura:.1f} %",
        "archivo_md": archivo_md, "linea_inicio": linea_ini, "linea_fin": linea_fin,
        "palabras_agregadas": ", ".join(r.verificacion.agregadas[:20]),
        "avisos_estructura": len(r.avisos), "detalle_avisos": SEPARADOR_LISTA.join(r.avisos),
        "paginas_ocr": ", ".join(map(str, r.doc.paginas_ocr)),
        "confianza_ocr": f"{r.doc.confianza_ocr:.1f}" if r.doc.confianza_ocr is not None else "",
        "area_propietaria": meta.area_propietaria,
        "ruta_original": r.ruta,
    }
