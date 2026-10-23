"""Modo ``contexto``: convierte los materiales de contexto como documentos generales (ORG-GEN, GLO-GEN...)."""

from dataclasses import dataclass
from pathlib import Path

from ... import VERSION
from ...comun.archivos import escribir_csv, leer_csv_opcional
from ...comun.errores import CorpusError
from ...comun.esquema import (ARCHIVO_EQUIVALENCIAS, ARCHIVO_INVENTARIO_CONTEXTO, COLUMNAS_INVENTARIO,
                              inventario_activo)
from ...comun.texto import norm
from ...comun.tipos import AREA_GENERAL, NOMBRE_AREA_GENERAL, nombre_archivo
from ..bitacora import registrar_tiempos
from ..configuracion import EXT_RECONOCIDAS, EXT_TEXTO
from ..entradas import buscar_entradas
from ..huella import huella
from ..inventario import escribir_equivalencias, inventario_contexto, quitar_copias_contexto
from ..lote import Grupo, convertir_grupos
from ..materiales_contexto import es_material_de_contexto
from .base import (Modo, agregar_argumentos_de_conversion, carpeta_salida, imprimir_archivos_generados,
                   opciones_de_conversion)


@dataclass
class ResultadoContexto:
    """Resultado de convertir el contexto: un grupo por tipo general (ORG_GEN, GLO_GEN...)."""
    grupos: list
    equivalencias: list

    @property
    def documentos(self):
        return [r for g in self.grupos for r in g.documentos]

    @property
    def convertidos(self):
        return [r for g in self.grupos for r in g.convertidos]

    @property
    def archivos_generados(self):
        return [p for g in self.grupos for p in g.archivos_generados]


def _materiales(carpeta, salida, excluir):
    """Archivos de contexto ordenados por nombre, sin los excluidos ni los archivos de control."""
    entradas = buscar_entradas(carpeta, salida, EXT_RECONOCIDAS | EXT_TEXTO)
    return sorted((p for p in entradas if norm(p.name) not in excluir and es_material_de_contexto(p)),
                  key=lambda p: norm(p.name))


def _grupos_por_tipo(filas):
    """Un ``Grupo`` por tipo general (ORG, GLO, MPR, CTX...) con los materiales activos de ese tipo."""
    por_tipo = {}
    for f in inventario_activo(filas):
        por_tipo.setdefault(f["codigo"].split("-")[0], []).append(f)
    return [Grupo(t, AREA_GENERAL, NOMBRE_AREA_GENERAL, filas_t, {f["codigo"]: f["path"] for f in filas_t},
                  nombre_archivo(t, AREA_GENERAL)[:-3])
            for t, filas_t in por_tipo.items()]


def _imprimir_resultado(res, total_materiales):
    print(f"Materiales: {total_materiales} · convertidos: {len(res.convertidos)} · "
          f"errores: {sum(1 for r in res.documentos if r.estado == 'ERROR')}")
    for r in res.documentos:
        if r.ok:
            print(f"- {r.codigo} {r.archivo}: texto presente {r.verificacion.cobertura:.1f} %")
        else:
            print(f"- {r.codigo} {r.archivo}: {r.estado} {r.error}")
    imprimir_archivos_generados(res.archivos_generados)


def ejecutar_contexto(args):
    """Convierte los materiales de contexto como documentos generales: un tipo por material (organigrama,
    indicadores, glosario, mapa de procesos...) numerado dentro de GEN con codigos estables."""
    salida = carpeta_salida(args)
    carpeta = Path(args.entrada)
    excluir = {norm(x) for x in (args.excluir or [])}
    entradas = _materiales(carpeta, salida, excluir)
    if not entradas and excluir:
        print("CONTEXTO: no hay documentos generales (todo el material de contexto es de área o son datos).")
        return ResultadoContexto([], [])
    if not entradas:
        raise CorpusError("No encontré PDF, Word, .md, .csv ni .txt para el contexto.")
    inv_path = salida / ARCHIVO_INVENTARIO_CONTEXTO
    base = leer_csv_opcional(inv_path)
    if not getattr(args, "incluir_duplicados", False):
        entradas, avisos_copias = quitar_copias_contexto(entradas, carpeta)
        for a in avisos_copias:
            print(f"AVISO: {a}")
    filas, equivalencias = inventario_contexto(entradas, carpeta, base, getattr(args, "anteriores", None))
    escribir_csv(inv_path, COLUMNAS_INVENTARIO, filas)
    if equivalencias:
        escribir_equivalencias(salida / ARCHIVO_EQUIVALENCIAS, equivalencias)
    print(f"CONTEXTO · convertir.py v{VERSION} · huella {huella()}")
    opciones = opciones_de_conversion(args)
    opciones.raiz_contexto, opciones.raiz_entrada = carpeta, None      # estos archivos se muestran como contexto/..., no entrada/...
    grupos = _grupos_por_tipo(filas)
    res = ResultadoContexto(convertir_grupos(grupos, salida, opciones), equivalencias)
    registrar_tiempos(salida, res.documentos, anexar=True)
    _imprimir_resultado(res, sum(len(g.filas) for g in grupos))
    return res


class Contexto(Modo):
    nombre = "contexto"

    def configurar(self, parser):
        parser.add_argument("--excluir", nargs="*", default=[])
        agregar_argumentos_de_conversion(parser)

    def ejecutar(self, args):
        ejecutar_contexto(args)
