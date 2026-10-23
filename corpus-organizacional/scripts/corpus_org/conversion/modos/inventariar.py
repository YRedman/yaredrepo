"""Modo ``inventario``: lee la lista de archivos y escribe inventario_maestro.csv y catalogo.csv."""

from pathlib import Path

from ... import VERSION
from ...comun.archivos import escribir_csv
from ...comun.errores import CorpusError
from ...comun.esquema import (ARCHIVO_CATALOGO, ARCHIVO_EQUIVALENCIAS, ARCHIVO_INVENTARIO, AREA_SIN_ASIGNAR,
                              COLUMNAS_CATALOGO, COLUMNAS_INVENTARIO, inventario_activo)
from ...comun.tipos import TIPOS_AREA, tipo as tipo_documento
from ..entradas import localizar
from ..huella import huella
from ..inventario import (actualizar_plantilla_areas, clave_documento, construir_inventario, escribir_equivalencias,
                          leer_base, leer_catalogo_codigos, localizar_areas, parsear_lista)
from .base import Modo, agregar_argumentos_de_lista, carpeta_salida

AVISOS_MOSTRADOS = 50


def _filas_de_la_lista(entrada, nombre_lista, extra_filas):
    """(filas, ignoradas) de la lista de archivos mas los documentos de area de otras carpetas. Avisa de los que no
    tienen area y los agrega a areas.csv."""
    lista = localizar(nombre_lista, entrada)
    if not lista:
        raise CorpusError(f"No encontré la lista de archivos '{nombre_lista}'. Adjúntala al chat.")
    ruta_areas, areas = localizar_areas(entrada)
    filas, ignoradas = parsear_lista(lista, areas)
    filas += list(extra_filas or [])
    if not filas:
        raise CorpusError("La lista no contiene rutas válidas. Use carpetas Descriptivos\\<Área>\\archivo.pdf "
                          "o Descriptivos\\archivo.pdf con el área en areas.csv.")
    if any("sin_area" in f for f in filas):
        agregados = actualizar_plantilla_areas(Path(ruta_areas), filas)
        sin_area = len({clave_documento(f["archivo"]) for f in filas if f.get("sin_area")})
        if agregados:
            print(f"Se agregaron {agregados} archivos a {ruta_areas}: escriba el área de cada uno en la columna 'area'.")
        if sin_area:
            print(f"AVISO: {sin_area} documentos sin área quedan en «{AREA_SIN_ASIGNAR}» con códigos provisionales "
                  f"(complete {ruta_areas}).")
    return filas, ignoradas


def _localizar_o_fallar(nombre, entrada, descripcion):
    ruta = localizar(nombre, entrada)
    if not ruta:
        raise CorpusError(f"No encontré {descripcion} '{nombre}'.")
    return ruta


def generar_inventario(entrada, salida, nombre_lista, nombre_catalogo=None, incluir_duplicados=False, base=None,
                       extra_filas=None):
    """Lee lista.txt y escribe inventario_maestro.csv y catalogo.csv en ``salida``.

    ``base`` es un inventario anterior: sus codigos se conservan (codigos estables). ``extra_filas`` son
    documentos de area que estan fuera de la entrada (procedimientos, politicas... de la carpeta de contexto).
    """
    filas, ignoradas = _filas_de_la_lista(entrada, nombre_lista, extra_filas)
    fijados = leer_catalogo_codigos(_localizar_o_fallar(nombre_catalogo, entrada, "el catálogo")) \
        if nombre_catalogo else {}
    inventario_base = leer_base(_localizar_o_fallar(base, entrada, "el inventario base")) if base else None
    inv = construir_inventario(filas, ignoradas, fijados, incluir_duplicados, inventario_base)
    escribir_csv(salida / ARCHIVO_INVENTARIO, COLUMNAS_INVENTARIO, inv.documentos)
    escribir_csv(salida / ARCHIVO_CATALOGO, COLUMNAS_CATALOGO, inv.catalogo)
    migrados = inventario_base.equivalencias if inventario_base else []
    if migrados or inv.equivalencias:
        escribir_equivalencias(salida / ARCHIVO_EQUIVALENCIAS, migrados + inv.equivalencias)
    if migrados:
        print(f"Códigos migrados a la codificación TTT-AAA-NN: {len(migrados)} "
              f"(tabla en {salida / ARCHIVO_EQUIVALENCIAS})")
    return inv


def _imprimir_inventario(inv, salida, con_base):
    activos = inventario_activo(inv.documentos)
    print(f"INVENTARIO · convertir.py v{VERSION} · huella {huella()}")
    print()
    print(f"Rutas leídas: {inv.rutas_validas + len(inv.ignoradas)} · documentos válidos: {len(activos)} · "
          f"ignoradas: {len(inv.ignoradas)}" + (" · códigos estables desde el inventario base" if con_base else ""))
    conteo = " · ".join(f"{tipo_documento(t).plural} ({t}): {sum(r[t] for r in inv.catalogo)}" for t in TIPOS_AREA)
    print(f"{conteo} · Departamentos: {len(inv.departamentos)}")
    print()
    print("| Departamento | Código | " + " | ".join(TIPOS_AREA) + " |")
    print("|---|---|" + "---|" * len(TIPOS_AREA))
    for r in inv.catalogo:
        print(f"| {r['departamento']} | {r['codigo']} | " + " | ".join(str(r[t]) for t in TIPOS_AREA) + " |")
    if inv.avisos or inv.ignoradas:
        print()
        print("AVISOS")
        for a in inv.avisos:
            print(f"- {a}")
        for ruta, motivo in inv.ignoradas[:AVISOS_MOSTRADOS]:
            print(f"- Ignorada ({motivo}): {ruta}")
        if len(inv.ignoradas) > AVISOS_MOSTRADOS:
            print(f"- ... y {len(inv.ignoradas) - AVISOS_MOSTRADOS} rutas ignoradas más")
    print()
    print("ARCHIVOS GENERADOS")
    print(f"- {salida / ARCHIVO_INVENTARIO}")
    print(f"- {salida / ARCHIVO_CATALOGO}")


class Inventariar(Modo):
    nombre = "inventario"

    def configurar(self, parser):
        agregar_argumentos_de_lista(parser)
        parser.add_argument("--base", default=None,
                            help="Inventario anterior: sus códigos se conservan (los nuevos van al final).")

    def ejecutar(self, args):
        salida = carpeta_salida(args)
        base = getattr(args, "base", None)
        inv = generar_inventario(args.entrada, salida, args.lista, args.catalogo, args.incluir_duplicados, base,
                                 getattr(args, "extra_filas", None))
        _imprimir_inventario(inv, salida, bool(base))
