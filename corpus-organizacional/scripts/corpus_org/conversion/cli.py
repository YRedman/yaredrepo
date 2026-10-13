"""Linea de comandos de ``convertir.py``: interpreta argumentos, orquesta y muestra resultados."""

import argparse
import shutil
import sys
import time
from pathlib import Path

from .. import VERSION
from ..comun.archivos import escribir_csv, leer_csv
from ..comun.errores import CorpusError
from ..comun.esquema import (AREA_SIN_ASIGNAR, ARCHIVO_AREAS_DOCUMENTOS, ARCHIVO_AREAS_EXTRA, ARCHIVO_CATALOGO, ARCHIVO_INVENTARIO, ARCHIVO_KPIS,
                             ARCHIVO_RESUMEN, COLUMNAS_CATALOGO, COLUMNAS_INVENTARIO, inventario_activo,
                             tipo_desde_texto)
from ..comun.texto import norm
from .asignacion import asignar_archivos, grupos_a_convertir
from .configuracion import EXT_RECONOCIDAS, EXT_TEXTO
from .extractores.ocr import diagnostico
from ..consulta.matriz import escribir_matriz
from .copilot import ARCHIVO_INSTRUCCIONES, MAX_ARCHIVOS, exportar_copilot
from .entradas import buscar_entradas, entrada_por_defecto, localizar, partes_ruta
from .huella import huella
from .inventario import (RE_CODIGO_DEP, actualizar_plantilla_areas, candidatos_codigo, clave_documento,
                         construir_inventario, inventario_provisional, leer_areas, leer_base,
                         leer_catalogo_codigos, parsear_lista, tipo_de_carpeta)
from .lote import Grupo, OpcionesConversion, procesar_grupo
from .publicacion import (MUESTRA_REVISION, escribir_huellas, escribir_resumen_construccion, leer_revisados,
                          limpiar_generados, publicar_corpus, validar_publicacion)


# Archivos de control que pueden estar junto al contexto y no son material de contexto.
ARCHIVOS_NO_CONTEXTO = ("lista", "inventario_maestro", "catalogo")


def carpeta_salida(args):
    s = Path(args.salida) if args.salida else Path(args.entrada) / "salida"
    s.mkdir(parents=True, exist_ok=True)
    return s


def _opciones(args):
    return OpcionesConversion(verificacion_cruzada=not args.sin_verificacion_cruzada,
                              tiempo_max=args.tiempo_max or 0)


# ---------------------------------------------------------------------------
# inventario
# ---------------------------------------------------------------------------

def generar_inventario(entrada, salida, nombre_lista, nombre_catalogo=None, incluir_duplicados=False, base=None):
    """Lee lista.txt y escribe inventario_maestro.csv y catalogo.csv en ``salida``.

    ``base`` es un inventario anterior: sus codigos se conservan (codigos estables).
    """
    lista = localizar(nombre_lista, entrada)
    if not lista:
        raise CorpusError(f"No encontré la lista de archivos '{nombre_lista}'. Adjúntala al chat.")
    ruta_areas = localizar(ARCHIVO_AREAS_DOCUMENTOS, entrada) or Path(entrada) / ARCHIVO_AREAS_DOCUMENTOS
    filas, ignoradas = parsear_lista(lista, leer_areas(ruta_areas) if Path(ruta_areas).is_file() else None)
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
    fijados = {}
    if nombre_catalogo:
        cat = localizar(nombre_catalogo, entrada)
        if not cat:
            raise CorpusError(f"No encontré el catálogo '{nombre_catalogo}'.")
        fijados = leer_catalogo_codigos(cat)
    inventario_base = None
    if base:
        ruta_base = localizar(base, entrada)
        if not ruta_base:
            raise CorpusError(f"No encontré el inventario base '{base}'.")
        inventario_base = leer_base(ruta_base)
    inv = construir_inventario(filas, ignoradas, fijados, incluir_duplicados, inventario_base)
    escribir_csv(salida / ARCHIVO_INVENTARIO, COLUMNAS_INVENTARIO, inv.documentos)
    escribir_csv(salida / ARCHIVO_CATALOGO, COLUMNAS_CATALOGO, inv.catalogo)
    return inv


def modo_inventario(args):
    salida = carpeta_salida(args)
    inv = generar_inventario(args.entrada, salida, args.lista, args.catalogo, args.incluir_duplicados,
                             getattr(args, "base", None))
    activos = inventario_activo(inv.documentos)
    d = sum(1 for f in activos if f["tipo"] == "Descriptivo")
    print(f"INVENTARIO · convertir.py v{VERSION} · huella {huella()}")
    print()
    print(f"Rutas leídas: {inv.rutas_validas + len(inv.ignoradas)} · documentos válidos: {len(activos)} · "
          f"ignoradas: {len(inv.ignoradas)}" + (" · códigos estables desde el inventario base"
                                                 if getattr(args, "base", None) else ""))
    print(f"Descriptivos: {d} · Procedimientos: {len(activos) - d} · Departamentos: {len(inv.departamentos)}")
    print()
    print("| Departamento | Código | Descriptivos | Procedimientos |")
    print("|---|---|---|---|")
    for r in inv.catalogo:
        print(f"| {r['departamento']} | {r['codigo']} | {r['descriptivos']} | {r['procedimientos']} |")
    if inv.avisos or inv.ignoradas:
        print()
        print("AVISOS")
        for a in inv.avisos:
            print(f"- {a}")
        for l, motivo in inv.ignoradas[:50]:
            print(f"- Ignorada ({motivo}): {l}")
        if len(inv.ignoradas) > 50:
            print(f"- ... y {len(inv.ignoradas) - 50} rutas ignoradas más")
    print()
    print("ARCHIVOS GENERADOS")
    print(f"- {salida / ARCHIVO_INVENTARIO}")
    print(f"- {salida / ARCHIVO_CATALOGO}")


# ---------------------------------------------------------------------------
# convertir
# ---------------------------------------------------------------------------

def _inventario_para_convertir(args, entradas):
    """(inventario, tipo_filtro, dep_filtro) segun haya inventario o se convierta un piloto sin el."""
    tipo_filtro = tipo_desde_texto(args.tipo) if args.tipo else None
    dep_filtro = args.dep.upper() if args.dep else None
    if args.departamento:
        if tipo_filtro not in ("P", "D"):
            raise CorpusError("Sin inventario hay que indicar --tipo P o --tipo D.")
        cod = dep_filtro or candidatos_codigo(args.departamento)[0]
        if not RE_CODIGO_DEP.match(cod):
            raise CorpusError(f"El código de departamento '{cod}' debe tener 3 letras.")
        print("AVISO: conversión sin inventario. Los códigos dependen de los archivos adjuntos en esta corrida;")
        print("       adjunta todos los documentos del departamento a la vez para que la numeración sea la definitiva.")
        return inventario_provisional(entradas, tipo_filtro, cod, args.departamento), tipo_filtro, cod
    inv_path = localizar(args.inventario, args.entrada)
    if not inv_path:
        raise CorpusError(f"No encontré '{args.inventario}'. Adjunta inventario_maestro.csv al chat, "
                          "o indica --departamento \"Nombre\" --tipo P|D para convertir sin inventario.")
    inventario = leer_csv(inv_path)
    if not inventario or "codigo" not in inventario[0]:
        raise CorpusError("El inventario no tiene la columna 'codigo'. ¿Es el archivo correcto?")
    inventario = inventario_activo(inventario)
    return inventario, tipo_filtro, dep_filtro


def _imprimir_resumen_conversion(resultados, asignacion):
    print()
    print("| Grupo | Departamento | En inventario | Convertidos | Texto presente (mín.) | No adjuntos | Errores |")
    print("|---|---|---|---|---|---|---|")
    for res in resultados:
        g, docs = res.grupo, res.documentos
        minimo = min((r.verificacion.cobertura for r in res.convertidos), default=0)
        total = len(asignacion.grupos[(g.tipo, g.codigo_dep)])
        print(f"| {g.tipo}_{g.codigo_dep} | {g.departamento} | {total} | {len(res.convertidos)} | {minimo:.1f} % | "
              f"{sum(1 for r in docs if r.estado == 'NO ADJUNTO')} | {sum(1 for r in docs if r.estado == 'ERROR')} |")
    for res in resultados:
        g = res.grupo
        hechos = {r.codigo for r in res.convertidos}
        faltan = [f["codigo"] for f in asignacion.grupos[(g.tipo, g.codigo_dep)] if f["codigo"] not in hechos]
        if faltan:
            print()
            print(f"Faltan por convertir en {g.tipo}_{g.codigo_dep} ({len(faltan)}): {', '.join(faltan)}")
    for res in resultados:
        malos = [r for r in res.documentos if r.motivos_consola()]
        if malos:
            print()
            print(f"Revisar en {res.grupo.tipo}_{res.grupo.codigo_dep}:")
            for r in malos:
                print(f"- {r.codigo} {r.archivo}: {'; '.join(r.motivos_consola())}")


def ejecutar_conversion(args):
    opciones = _opciones(args)
    salida = carpeta_salida(args)
    entradas = buscar_entradas(Path(args.entrada), salida)
    inventario, tipo_filtro, dep_filtro = _inventario_para_convertir(args, entradas)
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
    print(f"CONVERSIÓN · convertir.py v{VERSION} · huella {huella()}")
    resultados = [procesar_grupo(g, salida, opciones) for g in grupos_a_convertir(asignacion)]
    _imprimir_resumen_conversion(resultados, asignacion)
    usados = asignacion.usados
    sobrantes = [p for p in entradas if str(p) not in usados]
    if sobrantes:
        print()
        print("Archivos adjuntos que no se usaron en esta corrida (no están en el inventario o pertenecen a otro grupo):")
        for p in sobrantes:
            print(f"- {p.name}")
    print()
    print("ARCHIVOS GENERADOS")
    for res in resultados:
        for p in res.archivos_generados:
            print(f"- {p}")
    print(f"\nTiempo: {time.time() - opciones.inicio:.1f} s")
    return resultados


def modo_convertir(args):
    ejecutar_conversion(args)


# ---------------------------------------------------------------------------
# contexto
# ---------------------------------------------------------------------------

def ejecutar_contexto(args):
    salida = carpeta_salida(args)
    excluir = {norm(x) for x in (args.excluir or [])}
    entradas = buscar_entradas(Path(args.entrada), salida, EXT_RECONOCIDAS | EXT_TEXTO)
    entradas = sorted((p for p in entradas
                       if norm(p.name) not in excluir and not norm(p.name).startswith(ARCHIVOS_NO_CONTEXTO)),
                      key=lambda p: norm(p.name))
    if not entradas:
        raise CorpusError("No encontré PDF, Word, .md, .csv ni .txt para el contexto.")
    filas, mapa = [], {}
    for i, p in enumerate(entradas, 1):
        cod = f"C-CTX-{i:02d}"
        filas.append({"codigo": cod, "archivo": p.name, "departamento": ""})
        mapa[cod] = p
    print(f"CONTEXTO · convertir.py v{VERSION} · huella {huella()}")
    res = procesar_grupo(Grupo("C", "CTX", "", filas, mapa, "contexto"), salida, _opciones(args))
    print(f"Materiales: {len(filas)} · convertidos: {len(res.convertidos)} · "
          f"errores: {sum(1 for r in res.documentos if r.estado == 'ERROR')}")
    for r in res.documentos:
        if r.ok:
            print(f"- {r.codigo} {r.archivo}: texto presente {r.verificacion.cobertura:.1f} %")
        else:
            print(f"- {r.codigo} {r.archivo}: {r.estado} {r.error}")
    print()
    print("ARCHIVOS GENERADOS")
    for p in res.archivos_generados:
        print(f"- {p}")
    return res


def modo_contexto(args):
    ejecutar_contexto(args)


# ---------------------------------------------------------------------------
# construir
# ---------------------------------------------------------------------------

def _lista_desde_carpeta(entrada, raiz_salida, control):
    """Escribe control/lista.txt con los documentos de ``entrada`` que estan en una carpeta Descriptivos o
    Procedimientos (directamente o en una subcarpeta de area). Devuelve su ruta o None si no hay ninguno."""
    rutas = []
    for p in sorted(buscar_entradas(entrada, raiz_salida)):
        partes = partes_ruta(p.relative_to(entrada))
        if any(tipo_de_carpeta(x) for x in partes[-3:-1]):
            rutas.append(str(p))
    if not rutas:
        return None
    lista = control / "lista.txt"
    lista.write_text("\n".join(rutas) + "\n", encoding="utf-8")
    print(f"lista.txt generada con {len(rutas)} documentos de {entrada}")
    return lista


def _inventario_para_construir(args, entrada, control, raiz_salida):
    """Con lista.txt el inventario se regenera conservando los codigos del anterior (si existe).
    Sin lista.txt, la lista se arma con las carpetas Descriptivos/Procedimientos de la entrada; si no
    las hay, se usa el inventario adjunto tal cual."""
    base_control = control / ARCHIVO_INVENTARIO
    previo = localizar(args.inventario, entrada) or (base_control if base_control.is_file() else None)
    encontrada = localizar(args.lista, entrada)
    if not encontrada or Path(encontrada).resolve().parent == control.resolve():
        generada = _lista_desde_carpeta(entrada, raiz_salida, control)
        if generada:
            args.lista = str(generada)
    if localizar(args.lista, entrada):
        base = None
        if previo:
            base = control / "inventario_base.csv"
            if Path(previo).resolve() != base.resolve():
                shutil.copy2(previo, base)
        modo_inventario(argparse.Namespace(entrada=str(entrada), salida=str(control), lista=args.lista,
                                           catalogo=args.catalogo, incluir_duplicados=args.incluir_duplicados,
                                           base=str(base) if base else None))
    elif previo:
        if Path(previo).resolve() != base_control.resolve():
            shutil.copy2(previo, base_control)
        cat = localizar(args.catalogo, entrada) if args.catalogo else None
        if cat:
            shutil.copy2(cat, control / ARCHIVO_CATALOGO)
    else:
        raise CorpusError("No hay documentos en carpetas Descriptivos o Procedimientos dentro de la entrada "
                          "(ni lista.txt o inventario_maestro.csv).")


def unir_csv(rutas, destino):
    """Une varios CSV con las mismas columnas (la primera fila de cada uno es el encabezado)."""
    cabecera, filas = None, []
    for p in rutas:
        r = leer_csv(p)
        if r:
            cabecera = cabecera or list(r[0].keys())
            filas += r
    if cabecera:
        escribir_csv(destino, cabecera, filas)


def _datos_de_contexto(contexto, control):
    """Copia a control/ los datos estructurados del contexto: kpi*.csv (unidos en kpis.csv) y areas_extra.csv.

    Devuelve los nombres de archivo que no son material de contexto (no se convierten a contexto.md).
    """
    kpis = sorted(p for p in contexto.iterdir() if p.suffix.lower() == ".csv" and norm(p.name).startswith("kpi"))
    if kpis:
        unir_csv(kpis, control / ARCHIVO_KPIS)
    extra = [p for p in contexto.iterdir() if norm(p.name) == ARCHIVO_AREAS_EXTRA]
    if extra:
        shutil.copy2(extra[0], control / ARCHIVO_AREAS_EXTRA)
    return [p.name for p in extra]


def modo_construir(args):
    """Inventario, conversion, contexto opcional, publicacion, validacion y huellas en una sola orden.

    Termina con 0 (LISTO PARA PUBLICAR), 2 (REQUIERE REVISIÓN) o 3 (PENDIENTE DE REVISIÓN VISUAL).
    """
    entrada = Path(args.entrada).resolve()
    raiz_salida = Path(args.salida).resolve() if args.salida else entrada / "salida_corpus"
    control, publicado = raiz_salida / "control", raiz_salida / "publicado"
    control.mkdir(parents=True, exist_ok=True)
    publicado.mkdir(parents=True, exist_ok=True)
    contexto = Path(args.contexto).resolve() if args.contexto else None
    if contexto is not None and not contexto.is_dir():
        raise CorpusError(f"La carpeta de contexto no existe: {contexto}")
    limpiar_generados(control)

    # 1) Inventario (codigos estables si ya habia uno).
    _inventario_para_construir(args, entrada, control, raiz_salida)

    # 2) Conversion de descriptivos y procedimientos.
    comunes = dict(salida=str(control), sin_verificacion_cruzada=args.sin_verificacion_cruzada,
                   tiempo_max=args.tiempo_max)
    ejecutar_conversion(argparse.Namespace(entrada=str(entrada), inventario=str(control / ARCHIVO_INVENTARIO),
                                           tipo=None, dep=None, departamento=None, **comunes))

    # 3) Contexto opcional, en carpeta separada para no convertir documentos operativos como contexto.
    errores_contexto = []
    if contexto is not None:
        no_contexto = _datos_de_contexto(contexto, control)
        res = ejecutar_contexto(argparse.Namespace(entrada=str(contexto), excluir=no_contexto, **comunes))
        errores_contexto = [f"{r.codigo} {r.archivo}: {r.estado} {r.error}".strip() for r in res.documentos if not r.ok]

    # 4) Publicacion limpia, indice maestro, validacion y huellas.
    publicados, duplicados = publicar_corpus(control, publicado)
    validacion = validar_publicacion(publicado, duplicados, leer_revisados(raiz_salida, control, entrada),
                                     args.muestra_revision, errores_contexto, control)
    escribir_huellas(publicado)
    resumen_path = raiz_salida / ARCHIVO_RESUMEN
    escribir_resumen_construccion(resumen_path, validacion, publicados)
    carpeta_copilot = exportar_copilot(raiz_salida, args.max_archivos_copilot)
    try:
        matriz = escribir_matriz(raiz_salida)
    except CorpusError as e:
        matriz = None
        validacion.avisos.append(f"No se generó la matriz Excel: {e.mensaje}")
    print("\nCONSTRUIR CORPUS · convertir.py v" + VERSION)
    print("Resultado: " + validacion.estado)
    print(f"Publicado: {publicado}")
    print(f"Control: {control}")
    print(f"Resumen: {resumen_path}")
    print(f"Copilot: {carpeta_copilot} ({len(list(carpeta_copilot.iterdir()))} archivos de conocimiento; "
          f"instrucciones en {raiz_salida / ARCHIVO_INSTRUCCIONES})")
    if matriz:
        print(f"Matriz Excel: {matriz}")
    for x in validacion.problemas:
        print("ERROR: " + x)
    if validacion.revision_visual:
        pendientes = list(validacion.revision_visual.items())
        print(f"REVISIÓN VISUAL PENDIENTE ({len(pendientes)}): "
              + ", ".join(f"{c} ({m[:50]})" for c, m in pendientes[:15]))
    for x in validacion.avisos:
        print("AVISO: " + x)
    if validacion.codigo_salida:
        sys.exit(validacion.codigo_salida)


def modo_copilot(args):
    """Regenera el paquete para Copilot desde una construccion existente (por ejemplo con otro limite)."""
    raiz = Path(args.salida or "salida_corpus").resolve()
    carpeta = exportar_copilot(raiz, args.max_archivos_copilot)
    archivos = sorted(carpeta.iterdir())
    print(f"COPILOT · convertir.py v{VERSION}")
    print(f"Conocimiento ({len(archivos)} archivos) en {carpeta}:")
    for p in archivos:
        print(f"- {p.name} ({p.stat().st_size // 1024} KB)")
    print(f"Instrucciones del agente: {raiz / ARCHIVO_INSTRUCCIONES}")


def modo_matriz(args):
    """Regenera la matriz Excel desde una construccion existente."""
    raiz = Path(args.salida or "salida_corpus").resolve()
    print(f"MATRIZ · convertir.py v{VERSION}")
    print(f"Matriz Excel: {escribir_matriz(raiz)}")


def modo_diagnostico(args):
    """Comprueba PyMuPDF, pytesseract, Pillow, Tesseract y el idioma español."""
    print(f"DIAGNÓSTICO · convertir.py v{VERSION}")
    lineas = diagnostico()
    for ok, texto in lineas:
        print(("OK     " if ok else "FALTA  ") + texto)
    if all(ok for ok, _ in lineas):
        print("\nTodo listo: las páginas escaneadas se leerán con OCR.")
    else:
        print("\nSin OCR las páginas escaneadas quedan sin texto (el resultado será REQUIERE REVISIÓN).")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Argumentos
# ---------------------------------------------------------------------------

MODOS = {"inventario": modo_inventario, "convertir": modo_convertir, "contexto": modo_contexto,
         "construir": modo_construir, "copilot": modo_copilot,
         "diagnostico": modo_diagnostico, "matriz": modo_matriz}


def crear_parser():
    ap = argparse.ArgumentParser(description="Conversión y construcción del corpus organizacional.")
    sub = ap.add_subparsers(dest="modo", required=True)
    for nombre in MODOS:
        sp = sub.add_parser(nombre)
        sp.add_argument("--entrada", default=None,
                        help="Carpeta donde están los archivos adjuntos (por defecto /mnt/data o la actual).")
        sp.add_argument("--salida", default=None, help="Carpeta de salida.")
        if nombre in ("inventario", "construir"):
            sp.add_argument("--lista", default="lista.txt")
            sp.add_argument("--catalogo", default=None, help="catalogo.csv editado con los códigos de departamento.")
            sp.add_argument("--incluir-duplicados", action="store_true",
                            help="Conserva el mismo documento en .pdf y .docx o sus copias '(1)'.")
        if nombre == "inventario":
            sp.add_argument("--base", default=None,
                            help="Inventario anterior: sus códigos se conservan (los nuevos van al final).")
        if nombre in ("convertir", "construir"):
            sp.add_argument("--inventario", default=ARCHIVO_INVENTARIO)
        if nombre == "convertir":
            sp.add_argument("--tipo", default=None, help="P o D, para convertir solo ese tipo.")
            sp.add_argument("--dep", default=None, help="Código de 3 letras, para convertir solo ese departamento.")
            sp.add_argument("--departamento", default=None,
                            help="Nombre del departamento, para convertir sin inventario (piloto).")
        if nombre == "contexto":
            sp.add_argument("--excluir", nargs="*", default=[])
        if nombre in ("construir", "copilot"):
            sp.add_argument("--max-archivos-copilot", type=int, default=MAX_ARCHIVOS,
                            help="Máximo de archivos del paquete para el conocimiento de Copilot.")
        if nombre == "construir":
            sp.add_argument("--contexto", default=None,
                            help="Carpeta separada con organigrama, glosario y otros materiales de contexto.")
            sp.add_argument("--muestra-revision", type=float, default=MUESTRA_REVISION,
                            help="Fracción de documentos sin avisos que se revisan visualmente (0 = ninguno).")
        if nombre in ("convertir", "contexto", "construir"):
            sp.add_argument("--sin-verificacion-cruzada", action="store_true")
            sp.add_argument("--tiempo-max", type=float, default=0,
                            help="Segundos máximos; lo que no alcance queda como pendiente.")
    return ap


def main(argv=None):
    args = crear_parser().parse_args(argv)
    if args.entrada is None:
        args.entrada = entrada_por_defecto()
    try:
        MODOS[args.modo](args)
    except CorpusError as e:
        print(f"ERROR: {e.mensaje}")
        sys.exit(e.codigo_salida)
