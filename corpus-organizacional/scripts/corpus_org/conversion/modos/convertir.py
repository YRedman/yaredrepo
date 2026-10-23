"""Modo ``convertir``: convierte a Markdown los documentos de area (DES, PRD, PRO, POL) segun el inventario."""

import time
from pathlib import Path

from ... import VERSION
from ...comun.archivos import leer_csv
from ...comun.errores import CorpusError
from ...comun.esquema import ARCHIVO_INVENTARIO, inventario_activo, tipo_desde_texto
from ...comun.tipos import TIPOS_AREA
from ..asignacion import asignar_archivos, grupos_a_convertir
from ..bitacora import registrar_tiempos
from ..entradas import buscar_entradas, localizar
from ..huella import huella
from ..inventario import RE_CODIGO_DEP, candidatos_codigo, inventario_provisional, migrar_fila
from ..lote import convertir_grupos
from .base import (Modo, agregar_argumentos_de_conversion, carpeta_salida, imprimir_archivos_generados,
                   opciones_de_conversion)


def _inventario_provisional(args, entradas, tipo_filtro, dep_filtro):
    """Inventario de un piloto sin inventario_maestro.csv: solo los archivos adjuntos de un tipo y un departamento."""
    if tipo_filtro not in TIPOS_AREA:
        raise CorpusError("Sin inventario hay que indicar --tipo " + "|".join(TIPOS_AREA) + ".")
    cod = dep_filtro or candidatos_codigo(args.departamento)[0]
    if not RE_CODIGO_DEP.match(cod):
        raise CorpusError(f"El código de departamento '{cod}' debe tener 3 letras.")
    print("AVISO: conversión sin inventario. Los códigos dependen de los archivos adjuntos en esta corrida;")
    print("       adjunta todos los documentos del departamento a la vez para que la numeración sea la definitiva.")
    return inventario_provisional(entradas, tipo_filtro, cod, args.departamento), cod


def _inventario_para_convertir(args, entradas):
    """(inventario, tipo_filtro, dep_filtro) segun haya inventario o se convierta un piloto sin el."""
    tipo_filtro = tipo_desde_texto(args.tipo) if args.tipo else None
    dep_filtro = args.dep.upper() if args.dep else None
    if args.departamento:
        inventario, dep_filtro = _inventario_provisional(args, entradas, tipo_filtro, dep_filtro)
        return inventario, tipo_filtro, dep_filtro
    inv_path = localizar(args.inventario, args.entrada)
    if not inv_path:
        raise CorpusError(f"No encontré '{args.inventario}'. Adjunta inventario_maestro.csv al chat, "
                          "o indica --departamento \"Nombre\" --tipo " + "|".join(TIPOS_AREA)
                          + " para convertir sin inventario.")
    inventario = leer_csv(inv_path)
    if not inventario or "codigo" not in inventario[0]:
        raise CorpusError("El inventario no tiene la columna 'codigo'. ¿Es el archivo correcto?")
    return [migrar_fila(f) for f in inventario_activo(inventario)], tipo_filtro, dep_filtro


def _imprimir_tabla_de_grupos(resultados, asignacion):
    print()
    print("| Grupo | Departamento | En inventario | Convertidos | Texto presente (mín.) | No adjuntos | Errores |")
    print("|---|---|---|---|---|---|---|")
    for res in resultados:
        g, docs = res.grupo, res.documentos
        minimo = min((r.verificacion.cobertura for r in res.convertidos), default=0)
        total = len(asignacion.grupos[(g.tipo, g.codigo_dep)])
        print(f"| {g.tipo}_{g.codigo_dep} | {g.departamento} | {total} | {len(res.convertidos)} | {minimo:.1f} % | "
              f"{sum(1 for r in docs if r.estado == 'NO ADJUNTO')} | {sum(1 for r in docs if r.estado == 'ERROR')} |")


def _imprimir_faltantes(resultados, asignacion):
    for res in resultados:
        g = res.grupo
        hechos = {r.codigo for r in res.convertidos}
        faltan = [f for f in asignacion.grupos[(g.tipo, g.codigo_dep)] if f["codigo"] not in hechos]
        if not faltan:
            continue
        print()
        print(f"Faltan por convertir en {g.tipo}_{g.codigo_dep} ({len(faltan)}): " + ", ".join(f["codigo"] for f in faltan))
        for f in (f for f in faltan if f["codigo"] not in g.archivos):
            print(f"- {f['codigo']} «{f['archivo']}»: está en el inventario pero no encontré ese archivo en la carpeta "
                  "de entrada. ¿Se movió, se borró o cambió de nombre? Si hay una lista.txt antigua en la entrada, "
                  "bórrela para que el inventario se arme con las carpetas.")


def _imprimir_documentos_a_revisar(resultados):
    for res in resultados:
        malos = [r for r in res.documentos if r.motivos_consola()]
        if not malos:
            continue
        print()
        print(f"Revisar en {res.grupo.tipo}_{res.grupo.codigo_dep}:")
        for r in malos:
            print(f"- {r.codigo} {r.ruta or r.archivo}: {'; '.join(r.motivos_consola())}")


def _imprimir_resumen_conversion(resultados, asignacion):
    _imprimir_tabla_de_grupos(resultados, asignacion)
    _imprimir_faltantes(resultados, asignacion)
    _imprimir_documentos_a_revisar(resultados)


def _asignar(args, entradas, inventario, tipo_filtro, dep_filtro):
    asignacion = asignar_archivos(inventario, entradas, tipo_filtro, dep_filtro, raiz=args.entrada)
    if asignacion.ambiguos and not (tipo_filtro and dep_filtro):
        print("AVISO: estos archivos tienen el mismo nombre en más de un departamento o tipo. "
              "Vuelve a ejecutar indicando --tipo y --dep:")
        for p in asignacion.ambiguos:
            print(f"- {Path(p).name}")
    if not asignacion.asignados:
        nombres = "\n".join(f"- {p.name}" for p in entradas)
        raise CorpusError("No encontré archivos adjuntos que coincidan con el inventario.\n"
                          f"Archivos encontrados en el entorno:\n{nombres}")
    return asignacion


def ejecutar_conversion(args):
    opciones = opciones_de_conversion(args)
    salida = carpeta_salida(args)
    entradas = buscar_entradas(Path(args.entrada), salida) + list(getattr(args, "extra_entradas", None) or [])
    inventario, tipo_filtro, dep_filtro = _inventario_para_convertir(args, entradas)
    asignacion = _asignar(args, entradas, inventario, tipo_filtro, dep_filtro)
    print(f"CONVERSIÓN · convertir.py v{VERSION} · huella {huella()}")
    resultados = convertir_grupos(list(grupos_a_convertir(asignacion)), salida, opciones)
    _imprimir_resumen_conversion(resultados, asignacion)
    registrar_tiempos(salida, [r for res in resultados for r in res.documentos])
    sobrantes = [p for p in entradas if str(p) not in asignacion.usados]
    if sobrantes:
        print()
        print("Archivos adjuntos que no se usaron en esta corrida (no están en el inventario o pertenecen a otro grupo):")
        for p in sobrantes:
            print(f"- {p.name}")
    imprimir_archivos_generados(p for res in resultados for p in res.archivos_generados)
    print(f"\nTiempo: {time.time() - opciones.inicio:.1f} s")
    return resultados


class Convertir(Modo):
    nombre = "convertir"

    def configurar(self, parser):
        parser.add_argument("--inventario", default=ARCHIVO_INVENTARIO)
        parser.add_argument("--tipo", default=None, help="DES, PRD, PRO o POL, para convertir solo ese tipo.")
        parser.add_argument("--dep", default=None, help="Código de 3 letras, para convertir solo ese departamento.")
        parser.add_argument("--departamento", default=None,
                            help="Nombre del departamento, para convertir sin inventario (piloto).")
        agregar_argumentos_de_conversion(parser)

    def ejecutar(self, args):
        ejecutar_conversion(args)
