"""Conversion de un grupo de documentos (un tipo de un departamento) a Markdown e indice."""

import os
import time
import traceback
from dataclasses import dataclass, field
from typing import Dict, List

from ..comun.archivos import escribir_csv
from ..comun.esquema import (COLUMNAS_INDICE, NO_ESPECIFICADO, PREFIJO_DIC, PREFIJO_REPORTE, RE_MARCAS,
                             SEPARADOR_LISTA, TIPOS, TIPOS_PLURAL)
from ..comun.texto import recortar_palabras, tokens
from .analisis import analizar
from .extractores import extractor_para
from .modelo import DocumentoConvertido
from .render import render_documento
from .reportes import escribir_reporte
from .verificacion import verificar


@dataclass
class OpcionesConversion:
    verificacion_cruzada: bool = True
    tiempo_max: float = 0          # segundos; 0 = sin limite
    inicio: float = field(default_factory=time.time)

    def tiempo_agotado(self):
        return bool(self.tiempo_max) and time.time() - self.inicio > self.tiempo_max


@dataclass
class Grupo:
    tipo: str                      # P, D o C
    codigo_dep: str
    departamento: str
    filas: List[dict]              # filas del inventario a procesar
    archivos: Dict[str, object]    # codigo -> Path del archivo adjunto
    nombre_base: str               # P_COM, D_ALM_01-05, contexto...
    completo: bool = True

    @property
    def es_contexto(self):
        return self.tipo == "C"

    @property
    def titulo(self):
        if self.es_contexto:
            return "Contexto"
        return f"{TIPOS_PLURAL[self.tipo]} · {self.departamento} ({self.codigo_dep})"


@dataclass
class ResultadoGrupo:
    grupo: Grupo
    documentos: List[DocumentoConvertido]
    archivos_generados: list

    @property
    def convertidos(self):
        return [r for r in self.documentos if r.ok]


def convertir_documento(path, fila, grupo, opciones):
    """Extrae, analiza, renderiza y verifica un archivo. Devuelve (DocumentoConvertido, lineas_md, cuerpo)."""
    doc = extractor_para(path, opciones.verificacion_cruzada).extraer(path)
    bloques, analisis = analizar(doc, grupo.tipo)
    titulo = os.path.splitext(fila["archivo"])[0]
    md, cuerpo = render_documento(doc, bloques, analisis, fila["codigo"], grupo.tipo,
                                  "" if grupo.es_contexto else grupo.departamento, fila["archivo"], titulo)
    v = verificar(doc, bloques, analisis, cuerpo)
    r = DocumentoConvertido(codigo=fila["codigo"], archivo=fila["archivo"], estado="OK", doc=doc,
                            analisis=analisis, verificacion=v, palabras=len(tokens(RE_MARCAS.sub(" ", cuerpo))))
    return r, md


def fila_indice(r, grupo, archivo_md, linea_ini, linea_fin):
    """Fila del indice (DIC_*.csv) de un documento convertido."""
    a, meta, ctx = r.analisis, r.analisis.metadatos, grupo.es_contexto
    campos = a.campos
    proposito = recortar_palabras(campos.get("objetivo") or campos.get("proposito", ""), 40)
    es_d = grupo.tipo == "D"
    return {
        "codigo": r.codigo, "tipo": TIPOS[grupo.tipo], "codigo_departamento": "" if ctx else grupo.codigo_dep,
        "departamento": "" if ctx else grupo.departamento, "nombre": os.path.splitext(r.archivo)[0],
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
    }


def _encabezado_md(grupo):
    if grupo.es_contexto:
        intro = "Materiales de contexto. Cada material empieza con \"## [C-NN]\"; lo demás es el texto original."
    else:
        intro = ("Documentos de este archivo: {N}. Cada documento empieza con \"## [CÓDIGO]\"; "
                 "el bloque con \">\" son metadatos de conversión y lo demás es el texto original.")
    return [f"# {grupo.titulo}", "", intro, ""]


def procesar_grupo(grupo, salida, opciones):
    """Convierte el grupo y escribe ``<nombre>.md``, ``DIC_<nombre>.csv`` y ``REPORTE_<nombre>.md``."""
    lineas_md = _encabezado_md(grupo)
    archivo_md = grupo.nombre_base + ".md"
    indice, documentos = [], []
    for fila in grupo.filas:
        path = grupo.archivos.get(fila["codigo"])
        if path is None:
            documentos.append(DocumentoConvertido(fila["codigo"], fila["archivo"], "NO ADJUNTO"))
            continue
        if opciones.tiempo_agotado():
            documentos.append(DocumentoConvertido(fila["codigo"], fila["archivo"], "PENDIENTE (tiempo)"))
            continue
        try:
            r, md = convertir_documento(path, fila, grupo, opciones)
        except Exception as e:
            documentos.append(DocumentoConvertido(fila["codigo"], fila["archivo"], "ERROR",
                                                  error=f"{type(e).__name__}: {e}",
                                                  traza=traceback.format_exc(limit=3)))
            continue
        linea_ini = len(lineas_md) + 1
        lineas_md.extend(md)
        indice.append(fila_indice(r, grupo, archivo_md, linea_ini, len(lineas_md)))
        documentos.append(r)

    resultado = ResultadoGrupo(grupo, documentos, [])
    lineas_md[2] = lineas_md[2].replace("{N}", str(len(resultado.convertidos)))
    if resultado.convertidos:
        md_path = salida / archivo_md
        md_path.write_text("\n".join(lineas_md).rstrip() + "\n", encoding="utf-8")
        dic_path = salida / f"{PREFIJO_DIC}{grupo.nombre_base}.csv"
        escribir_csv(dic_path, COLUMNAS_INDICE, indice)
        resultado.archivos_generados += [md_path, dic_path]
    resultado.archivos_generados.append(
        escribir_reporte(salida / f"{PREFIJO_REPORTE}{grupo.nombre_base}.md", grupo, documentos))
    return resultado
