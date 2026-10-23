"""Conversion de un grupo de documentos (un tipo de un departamento) a Markdown e indice."""

import concurrent.futures
import multiprocessing
import os
import re
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from ..comun.archivos import escribir_csv
from ..comun.esquema import (COLUMNAS_INDICE, NO_ESPECIFICADO, PREFIJO_DIC, PREFIJO_REPORTE, RE_MARCAS,
                             SEPARADOR_LISTA)
from ..comun.texto import recortar_palabras, tokens
from ..comun.tipos import familia, tipo as tipo_documento
from .analisis import analizar
from .analisis.puesto import avisar_nombre_puesto
from .extractores import extractor_para
from .modelo import DocumentoConvertido
from .render import render_documento
from .reportes import escribir_reporte
from .verificacion import verificar


MAX_TRABAJADORES = 4           # mas procesos que esto no acortan la corrida: el OCR ya usa varios nucleos
MIN_DOCUMENTOS_PARALELO = 4    # con menos documentos no compensa arrancar procesos


def trabajadores_por_defecto():
    """Procesos para convertir documentos a la vez: los nucleos del equipo menos uno, hasta MAX_TRABAJADORES."""
    return max(1, min(MAX_TRABAJADORES, (os.cpu_count() or 2) - 1))


@dataclass
class OpcionesConversion:
    verificacion_cruzada: bool = True
    tiempo_max: float = 0          # segundos; 0 = sin limite
    inicio: float = field(default_factory=time.time)
    raiz_entrada: object = None    # carpetas de las que se muestra la ruta relativa del original
    raiz_contexto: object = None
    trabajadores: int = 1          # procesos en paralelo (1 = un documento a la vez)
    _pool: object = field(default=None, repr=False, compare=False)
    _futuros: dict = field(default_factory=dict, repr=False, compare=False)

    def tiempo_agotado(self):
        return bool(self.tiempo_max) and time.time() - self.inicio > self.tiempo_max

    # -- conversion en paralelo ----------------------------------------------------------------------------------

    def lanzar(self, grupos):
        """Empieza ya la conversion de todos los documentos de ``grupos`` en procesos aparte; ``procesar_grupo`` recoge
        cada resultado en su orden. Sin efecto si hay un solo trabajador o pocos documentos."""
        trabajos = [(g, f, g.archivos[f["codigo"]]) for g in grupos for f in g.filas if g.archivos.get(f["codigo"])]
        if self.trabajadores <= 1 or len(trabajos) < MIN_DOCUMENTOS_PARALELO:
            return
        # los documentos grandes primero: el ultimo en terminar no debe ser el mas largo
        trabajos.sort(key=lambda t: -_tamano(t[2]))
        try:
            self._pool = concurrent.futures.ProcessPoolExecutor(
                max_workers=min(self.trabajadores, len(trabajos)), mp_context=multiprocessing.get_context("spawn"),
                initializer=_iniciar_trabajador)
            for g, f, p in trabajos:
                self._futuros[(g.nombre_base, f["codigo"])] = self._pool.submit(_trabajo, p, f, g, self)
        except Exception:                       # sin procesos (entorno restringido): se convierte uno a uno
            self.cerrar()

    def resultado(self, grupo, fila, path):
        futuro = self._futuros.pop((grupo.nombre_base, fila["codigo"]), None)
        if futuro is not None:
            try:
                return futuro.result()
            except Exception:                   # el proceso murio (memoria) o no pudo devolver el resultado: se rehace aqui
                pass
        return _trabajo(path, fila, grupo, self)

    def cerrar(self):
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
        self._pool, self._futuros = None, {}

    def __getstate__(self):                     # al enviarlo a un proceso no viajan el pool ni los futuros
        estado = dict(self.__dict__)
        estado["_pool"], estado["_futuros"] = None, {}
        return estado


def _tamano(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _iniciar_trabajador():
    # Tesseract usa varios hilos por lectura; con varios procesos a la vez compiten entre si y todos van mas lento
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")


@dataclass
class Grupo:
    tipo: str                      # codigo de tipo: DES, PRD, PRO, POL u ORG, KPI... (generales)
    codigo_dep: str
    departamento: str
    filas: List[dict]              # filas del inventario a procesar
    archivos: Dict[str, object]    # codigo -> Path del archivo adjunto
    nombre_base: str               # PRD_COM, DES_ALM_01-05, ORG_GEN...
    completo: bool = True

    @property
    def es_contexto(self):
        return familia(self.tipo) == "C"

    @property
    def familia(self):
        """'D', 'P' o 'C': como se analiza el documento (ver comun/tipos.py)."""
        return familia(self.tipo)

    @property
    def titulo(self):
        td = tipo_documento(self.tipo)
        plural = td.plural if td else self.tipo
        if self.es_contexto:
            return f"{plural} · General ({self.codigo_dep})"
        return f"{plural} · {self.departamento} ({self.codigo_dep})"


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
    bloques, analisis = analizar(doc, grupo.familia)
    titulo = os.path.splitext(fila["archivo"])[0]
    if grupo.familia == "D":
        avisar_nombre_puesto(analisis, titulo)
    md, cuerpo = render_documento(doc, bloques, analisis, fila["codigo"], grupo.tipo,
                                  grupo.departamento, fila["archivo"], titulo)
    v = verificar(doc, bloques, analisis, cuerpo)
    r = DocumentoConvertido(codigo=fila["codigo"], archivo=fila["archivo"], estado="OK", doc=doc,
                            analisis=analisis, verificacion=v, palabras=len(tokens(RE_MARCAS.sub(" ", cuerpo))),
                            ruta=ruta_original(fila, grupo, opciones, path))
    return r, md


def _trabajo(path, fila, grupo, opciones):
    """(DocumentoConvertido, lineas_md) de un archivo; sin lineas (``None``) si no hubo tiempo o fallo la conversion.
    Se ejecuta en el proceso principal o en un trabajador."""
    if opciones.tiempo_agotado():
        return DocumentoConvertido(fila["codigo"], fila["archivo"], "PENDIENTE (tiempo)",
                                   ruta=ruta_original(fila, grupo, opciones, path)), None
    inicio = time.time()
    try:
        r, md = convertir_documento(path, fila, grupo, opciones)
        r.segundos = time.time() - inicio
        return r, md
    except Exception as e:
        return DocumentoConvertido(fila["codigo"], fila["archivo"], "ERROR", error=f"{type(e).__name__}: {e}",
                                   traza=traceback.format_exc(limit=3), segundos=time.time() - inicio,
                                   ruta=ruta_original(fila, grupo, opciones, path)), None


def ruta_original(fila, grupo, opciones=None, path=None):
    """Donde esta el archivo para revisarlo: 'entrada/<ruta>' o 'contexto/<ruta>', relativa a esa carpeta.

    Se parte del archivo realmente leido (``path``): un documento de area que vino de la carpeta de contexto
    (procedimientos, politicas...) se muestra como 'contexto/...' aunque su fila del inventario base traiga otra
    ruta. Sin archivo (no adjunto) se usa la ruta del inventario; si no cuelga de ninguna carpeta, sus tres
    ultimas partes (Tipo/Departamento/Archivo)."""
    raices = ((getattr(opciones, "raiz_contexto", None), "contexto"), (getattr(opciones, "raiz_entrada", None), "entrada"))
    candidatos = [str(path)] if path is not None else []
    candidatos.append((fila.get("ruta_original") or fila.get("archivo") or "").strip())
    for ruta in candidatos:
        for raiz, etiqueta in raices:
            if raiz is None:
                continue
            try:
                return f"{etiqueta}/" + Path(ruta).resolve().relative_to(Path(raiz).resolve()).as_posix()
            except (ValueError, OSError):
                continue
    partes = [x for x in re.split(r"[\\/]+", candidatos[-1]) if x]
    if grupo.es_contexto or fila.get("desde_contexto"):
        return "contexto/" + "/".join(partes)
    return "entrada/" + "/".join(partes[-3:] if len(partes) > 3 else partes)


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


def _encabezado_md(grupo):
    if grupo.es_contexto:
        intro = ("Documentos generales de contexto: {N}. Cada material empieza con \"## [CÓDIGO] Título\"; "
                 "lo demás es el texto original.")
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
            documentos.append(DocumentoConvertido(fila["codigo"], fila["archivo"], "NO ADJUNTO",
                                                  ruta=ruta_original(fila, grupo, opciones)))
            continue
        r, md = opciones.resultado(grupo, fila, path)
        if md is None:
            documentos.append(r)
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


def convertir_grupos(grupos, salida, opciones):
    """Convierte los grupos (en paralelo si ``opciones`` lo permite) y devuelve un ``ResultadoGrupo`` por grupo."""
    try:
        opciones.lanzar(grupos)
        return [procesar_grupo(g, salida, opciones) for g in grupos]
    finally:
        opciones.cerrar()
