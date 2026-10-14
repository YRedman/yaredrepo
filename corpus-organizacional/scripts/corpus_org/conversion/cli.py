"""Linea de comandos de ``convertir.py``: interpreta argumentos, orquesta y muestra resultados."""

import argparse
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .. import VERSION
from ..comun.archivos import escribir_csv, leer_csv
from ..comun.errores import CorpusError
from ..comun.esquema import (AREA_SIN_ASIGNAR, ARCHIVO_AREAS_DOCUMENTOS, ARCHIVO_AREAS_EXTRA, ARCHIVO_CATALOGO,
                             ARCHIVO_EQUIVALENCIAS, ARCHIVO_INDICE, ARCHIVO_INVENTARIO, ARCHIVO_INVENTARIO_CONTEXTO,
                             ARCHIVO_KPIS, ARCHIVO_RESUMEN, COLUMNAS_CATALOGO, COLUMNAS_INVENTARIO, PREFIJO_DIC,
                             inventario_activo, tipo_desde_texto)
from ..comun.estructura import CARPETA_PUBLICADA, NOMBRE_SKILL_MD, informe_limites, rutas_publicadas
from ..comun.texto import norm
from ..comun.tipos import (AREA_GENERAL, NOMBRE_AREA_GENERAL, RE_CODIGO_ANTERIOR, TIPOS_AREA, nombre_archivo,
                           tipo as tipo_documento)
from .asignacion import asignar_archivos, grupos_a_convertir
from .configuracion import EXT_RECONOCIDAS, EXT_TEXTO
from .extractores.ocr import diagnostico
from ..consulta.matriz import ARCHIVO_MATRIZ, escribir_matriz
from .entradas import buscar_entradas, entrada_por_defecto, localizar, partes_ruta
from .huella import huella
from .inventario import (RE_CODIGO_DEP, actualizar_plantilla_areas, candidatos_codigo, clave_documento,
                         construir_inventario, documentos_de_area_en_contexto, escribir_equivalencias,
                         inventario_contexto, inventario_provisional,
                         leer_areas, leer_base, leer_catalogo_codigos, leer_equivalencias, migrar_fila,
                         parsear_lista, tipo_de_carpeta)
from .lote import Grupo, OpcionesConversion, procesar_grupo
from .publicacion import (MUESTRA_REVISION, escribir_huellas, escribir_resumen_construccion,
                          leer_revisados, limpiar_generados, publicar_corpus, validar_publicacion)


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

def generar_inventario(entrada, salida, nombre_lista, nombre_catalogo=None, incluir_duplicados=False, base=None,
                       extra_filas=None):
    """Lee lista.txt y escribe inventario_maestro.csv y catalogo.csv en ``salida``.

    ``base`` es un inventario anterior: sus codigos se conservan (codigos estables). ``extra_filas`` son
    documentos de area que estan fuera de la entrada (procedimientos, politicas... de la carpeta de contexto).
    """
    lista = localizar(nombre_lista, entrada)
    if not lista:
        raise CorpusError(f"No encontré la lista de archivos '{nombre_lista}'. Adjúntala al chat.")
    ruta_areas = localizar(ARCHIVO_AREAS_DOCUMENTOS, entrada) or Path(entrada) / ARCHIVO_AREAS_DOCUMENTOS
    filas, ignoradas = parsear_lista(lista, leer_areas(ruta_areas) if Path(ruta_areas).is_file() else None)
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
    if inventario_base and inventario_base.equivalencias:
        escribir_equivalencias(salida / ARCHIVO_EQUIVALENCIAS, inventario_base.equivalencias)
        print(f"Códigos migrados a la codificación TTT-AAA-NN: {len(inventario_base.equivalencias)} "
              f"(tabla en {salida / ARCHIVO_EQUIVALENCIAS})")
    return inv


def modo_inventario(args):
    salida = carpeta_salida(args)
    inv = generar_inventario(args.entrada, salida, args.lista, args.catalogo, args.incluir_duplicados,
                             getattr(args, "base", None), getattr(args, "extra_filas", None))
    activos = inventario_activo(inv.documentos)
    print(f"INVENTARIO · convertir.py v{VERSION} · huella {huella()}")
    print()
    print(f"Rutas leídas: {inv.rutas_validas + len(inv.ignoradas)} · documentos válidos: {len(activos)} · "
          f"ignoradas: {len(inv.ignoradas)}" + (" · códigos estables desde el inventario base"
                                                 if getattr(args, "base", None) else ""))
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
        if tipo_filtro not in TIPOS_AREA:
            raise CorpusError("Sin inventario hay que indicar --tipo " + "|".join(TIPOS_AREA) + ".")
        cod = dep_filtro or candidatos_codigo(args.departamento)[0]
        if not RE_CODIGO_DEP.match(cod):
            raise CorpusError(f"El código de departamento '{cod}' debe tener 3 letras.")
        print("AVISO: conversión sin inventario. Los códigos dependen de los archivos adjuntos en esta corrida;")
        print("       adjunta todos los documentos del departamento a la vez para que la numeración sea la definitiva.")
        return inventario_provisional(entradas, tipo_filtro, cod, args.departamento), tipo_filtro, cod
    inv_path = localizar(args.inventario, args.entrada)
    if not inv_path:
        raise CorpusError(f"No encontré '{args.inventario}'. Adjunta inventario_maestro.csv al chat, "
                          "o indica --departamento \"Nombre\" --tipo " + "|".join(TIPOS_AREA)
                          + " para convertir sin inventario.")
    inventario = leer_csv(inv_path)
    if not inventario or "codigo" not in inventario[0]:
        raise CorpusError("El inventario no tiene la columna 'codigo'. ¿Es el archivo correcto?")
    inventario = [migrar_fila(f) for f in inventario_activo(inventario)]
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
    entradas = buscar_entradas(Path(args.entrada), salida) + list(getattr(args, "extra_entradas", None) or [])
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

@dataclass
class ResultadoContexto:
    """Resultado de convertir el contexto: un grupo por tipo general (ORG_GEN, KPI_GEN...)."""
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


def ejecutar_contexto(args):
    """Convierte los materiales de contexto como documentos generales: un tipo por material (organigrama,
    indicadores, glosario, mapa de procesos...) numerado dentro de GEN con codigos estables."""
    salida = carpeta_salida(args)
    carpeta = Path(args.entrada)
    excluir = {norm(x) for x in (args.excluir or [])}
    entradas = buscar_entradas(carpeta, salida, EXT_RECONOCIDAS | EXT_TEXTO)
    entradas = sorted((p for p in entradas
                       if norm(p.name) not in excluir and not norm(p.name).startswith(ARCHIVOS_NO_CONTEXTO)),
                      key=lambda p: norm(p.name))
    if not entradas and excluir:
        print("CONTEXTO: no hay documentos generales (todo el material de contexto es de área o son datos).")
        return ResultadoContexto([], [])
    if not entradas:
        raise CorpusError("No encontré PDF, Word, .md, .csv ni .txt para el contexto.")
    inv_path = salida / ARCHIVO_INVENTARIO_CONTEXTO
    base = leer_csv(inv_path) if inv_path.is_file() else []
    filas, equivalencias = inventario_contexto(entradas, carpeta, base, getattr(args, "anteriores", None))
    escribir_csv(inv_path, COLUMNAS_INVENTARIO, filas)
    if equivalencias:
        escribir_equivalencias(salida / ARCHIVO_EQUIVALENCIAS, equivalencias)
    print(f"CONTEXTO · convertir.py v{VERSION} · huella {huella()}")
    por_tipo = {}
    for f in inventario_activo(filas):
        por_tipo.setdefault(f["codigo"].split("-")[0], []).append(f)
    grupos = []
    for t, filas_t in por_tipo.items():
        mapa = {f["codigo"]: f["path"] for f in filas_t}
        grupo = Grupo(t, AREA_GENERAL, NOMBRE_AREA_GENERAL, filas_t, mapa, nombre_archivo(t, AREA_GENERAL)[:-3])
        grupos.append(procesar_grupo(grupo, salida, _opciones(args)))
    res = ResultadoContexto(grupos, equivalencias)
    print(f"Materiales: {sum(len(v) for v in por_tipo.values())} · convertidos: {len(res.convertidos)} · "
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


def migrar_inventario(path):
    """Pasa a TTT-AAA-NN un inventario con codigos anteriores (D-/P-). Devuelve las equivalencias."""
    equivalencias = []
    filas = [migrar_fila(f, equivalencias) for f in leer_csv(path)]
    if equivalencias:
        escribir_csv(path, COLUMNAS_INVENTARIO, filas)
    return equivalencias


def _inventario_para_construir(args, entrada, control, raiz_salida, extra_filas=()):
    """Con lista.txt el inventario se regenera conservando los codigos del anterior (si existe).
    Sin lista.txt, la lista se arma con las carpetas de tipo (Descriptivos, Procedimientos, Protocolos,
    Políticas) de la entrada; si no las hay, se usa el inventario adjunto tal cual."""
    base_control = control / ARCHIVO_INVENTARIO
    previo = localizar(args.inventario, entrada) or (base_control if base_control.is_file() else None)
    encontrada = localizar(args.lista, entrada)
    if not encontrada or Path(encontrada).resolve().parent == control.resolve():
        generada = _lista_desde_carpeta(entrada, raiz_salida, control)
        if generada:
            args.lista = str(generada)
        elif extra_filas:   # solo hay documentos de area en la carpeta de contexto
            (control / "lista.txt").write_text("", encoding="utf-8")
            args.lista = str(control / "lista.txt")
    if localizar(args.lista, entrada):
        base = None
        if previo:
            base = control / "inventario_base.csv"
            if Path(previo).resolve() != base.resolve():
                shutil.copy2(previo, base)
        modo_inventario(argparse.Namespace(entrada=str(entrada), salida=str(control), lista=args.lista,
                                           catalogo=args.catalogo, incluir_duplicados=args.incluir_duplicados,
                                           base=str(base) if base else None, extra_filas=list(extra_filas)))
    elif previo:
        if Path(previo).resolve() != base_control.resolve():
            shutil.copy2(previo, base_control)
        escribir_equivalencias(control / ARCHIVO_EQUIVALENCIAS, migrar_inventario(base_control))
        cat = localizar(args.catalogo, entrada) if args.catalogo else None
        if cat:
            shutil.copy2(cat, control / ARCHIVO_CATALOGO)
    else:
        raise CorpusError("No hay documentos en carpetas de tipo (" + ", ".join(
            tipo_documento(t).plural for t in TIPOS_AREA) + ") dentro de la entrada "
            "(ni lista.txt o inventario_maestro.csv).")


def documentos_de_area_del_contexto(contexto, entrada, raiz_salida):
    """Filas de inventario de los documentos de area (PRD, POL, PRO, DES) de la carpeta de contexto."""
    archivos = [p for p in buscar_entradas(contexto, raiz_salida)
                if not norm(p.name).startswith(ARCHIVOS_NO_CONTEXTO)]
    ruta_areas = localizar(ARCHIVO_AREAS_DOCUMENTOS, entrada) or Path(entrada) / ARCHIVO_AREAS_DOCUMENTOS
    areas = leer_areas(ruta_areas) if Path(ruta_areas).is_file() else None
    return documentos_de_area_en_contexto(archivos, contexto, areas)


def equivalencias_de_contexto(control, de_area, anteriores):
    """(codigo anterior, codigo nuevo) de los materiales de contexto que ahora son documentos de area: su
    C-CTX-NN de la codificacion anterior o su codigo general (CTX-GEN-NN...) de una construccion previa."""
    rutas = {f["ruta"] for f in de_area}
    nuevos = {clave_documento(f["archivo"]): f["codigo"] for f in leer_csv(control / ARCHIVO_INVENTARIO)
              if f.get("ruta_original") in rutas}
    previos = control / ARCHIVO_INVENTARIO_CONTEXTO
    generales = {clave_documento(f.get("archivo", "")): f["codigo"]
                 for f in (inventario_activo(leer_csv(previos)) if previos.is_file() else [])}
    pares = []
    for clave, nuevo in nuevos.items():
        for viejo in (anteriores.get(clave), generales.get(clave)):
            if viejo and viejo != nuevo:
                pares.append((viejo, nuevo))
    return pares


def contexto_anterior(control, raiz_salida):
    """{clave_documento(archivo): C-CTX-NN} de una construccion con la codificacion anterior, para numerar
    primero esos materiales y registrar su equivalencia. Vacio si no la hay."""
    fuentes = [control / f"{PREFIJO_DIC}contexto.csv", raiz_salida / "publicado" / ARCHIVO_INDICE]
    anteriores = {}
    for p in fuentes:
        for f in (leer_csv(p) if p.is_file() else []):
            c = (f.get("codigo") or "").strip().upper()
            if RE_CODIGO_ANTERIOR.match(c) and c.startswith("C-") and f.get("archivo_origen"):
                anteriores.setdefault(clave_documento(f["archivo_origen"]), c)
    return anteriores


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

    Devuelve los nombres de archivo que no son documentos de contexto: los indicadores se quedan en kpis.csv
    (no se crea un Markdown de indicadores).
    """
    kpis = sorted(p for p in contexto.iterdir() if p.suffix.lower() == ".csv" and norm(p.name).startswith("kpi"))
    if kpis:
        unir_csv(kpis, control / ARCHIVO_KPIS)
    extra = [p for p in contexto.iterdir() if norm(p.name) == ARCHIVO_AREAS_EXTRA]
    if extra:
        shutil.copy2(extra[0], control / ARCHIVO_AREAS_EXTRA)
    return [p.name for p in kpis + extra]


def _limpiar_publicacion_anterior(raiz_salida, publicado, avisos):
    """Quita el paquete de 20 archivos de versiones anteriores (copilot/NN_*.md e instrucciones) y avisa
    de la carpeta publicado/ de la v4.0 inicial, que ya no se usa."""
    if publicado.is_dir():
        for p in publicado.glob("*.md"):
            if re.match(r"^\d\d_", p.name):
                p.unlink()
    instrucciones = raiz_salida / "instrucciones_copilot.md"
    if instrucciones.is_file():
        instrucciones.unlink()
    if (raiz_salida / "publicado").is_dir():
        avisos.append("La carpeta salida_corpus/publicado/ es de una versión anterior y ya no se usa: la "
                      f"publicación está en salida_corpus/{CARPETA_PUBLICADA}/. Puede borrarla.")


def modo_construir(args):
    """Inventario, conversion, contexto opcional, publicacion, validacion y huellas en una sola orden.

    Publica en salida_corpus/copilot/fuente-documentos y fuente-contexto (dos carpetas listas para comprimir).
    Termina con 0 (LISTO PARA PUBLICAR), 2 (REQUIERE REVISIÓN) o 3 (PENDIENTE DE REVISIÓN VISUAL).
    """
    entrada = Path(args.entrada).resolve()
    raiz_salida = Path(args.salida).resolve() if args.salida else entrada / "salida_corpus"
    control, publicado = raiz_salida / "control", raiz_salida / CARPETA_PUBLICADA
    control.mkdir(parents=True, exist_ok=True)
    publicado.mkdir(parents=True, exist_ok=True)
    contexto = Path(args.contexto).resolve() if args.contexto else None
    if contexto is not None and not contexto.is_dir():
        raise CorpusError(f"La carpeta de contexto no existe: {contexto}")
    anteriores = contexto_anterior(control, raiz_salida)
    limpiar_generados(control)

    # Los procedimientos, politicas/normativas, protocolos y descriptivos que estan en la carpeta de contexto
    # son documentos de area: se inventarian, convierten y validan como los de la entrada.
    de_area = documentos_de_area_del_contexto(contexto, entrada, raiz_salida) if contexto is not None else []

    # 1) Inventario (codigos estables si ya habia uno; los codigos D-/P- anteriores se migran).
    _inventario_para_construir(args, entrada, control, raiz_salida, de_area)
    if de_area:
        print(f"Documentos de área en la carpeta de contexto: {len(de_area)} "
              f"({', '.join(sorted({f['tipo'] for f in de_area}))})")
        escribir_equivalencias(control / ARCHIVO_EQUIVALENCIAS,
                               equivalencias_de_contexto(control, de_area, anteriores))

    # 2) Conversion de los documentos de area (DES, PRD, PRO, POL).
    comunes = dict(salida=str(control), sin_verificacion_cruzada=args.sin_verificacion_cruzada,
                   tiempo_max=args.tiempo_max)
    ejecutar_conversion(argparse.Namespace(entrada=str(entrada), inventario=str(control / ARCHIVO_INVENTARIO),
                                           tipo=None, dep=None, departamento=None,
                                           extra_entradas=[Path(f["ruta"]) for f in de_area], **comunes))

    # 3) Contexto opcional (documentos generales ORG-GEN, GLO-GEN...), en carpeta separada para no
    #    convertir documentos operativos como contexto. Los indicadores van a kpis.csv.
    errores_contexto = []
    if contexto is not None:
        no_contexto = _datos_de_contexto(contexto, control)
        no_contexto += [f["archivo"] for f in de_area]
        res = ejecutar_contexto(argparse.Namespace(entrada=str(contexto), excluir=no_contexto,
                                                   anteriores=anteriores, **comunes))
        errores_contexto = [f"{r.codigo} {r.archivo}: {r.estado} {r.error}".strip() for r in res.documentos if not r.ok]

    # 4) Publicacion en las dos carpetas, indice maestro y validacion.
    avisos_publicacion = []
    _limpiar_publicacion_anterior(raiz_salida, publicado, avisos_publicacion)
    publicados, duplicados = publicar_corpus(control, publicado, avisos_publicacion)
    rutas = rutas_publicadas(publicado)
    equivalencias = leer_equivalencias(control / ARCHIVO_EQUIVALENCIAS)
    revisados = {equivalencias.get(c, c) for c in leer_revisados(raiz_salida, control, entrada)}
    validacion = validar_publicacion(publicado, duplicados, revisados, args.muestra_revision, errores_contexto,
                                     control)
    validacion.avisos += avisos_publicacion
    if equivalencias:
        validacion.avisos.append(f"Codificación TTT-AAA-NN: {len(equivalencias)} códigos anteriores tienen su "
                                 f"equivalencia en {ARCHIVO_EQUIVALENCIAS}.")
    resumen_path = raiz_salida / ARCHIVO_RESUMEN
    escribir_resumen_construccion(resumen_path, validacion, publicados)      # la matriz lee de aqui el estado
    # salidas derivadas: un problema aqui (archivo abierto, permisos) no debe perder la construccion
    try:
        matriz = escribir_matriz(raiz_salida)
        if matriz.name != ARCHIVO_MATRIZ:
            validacion.avisos.append(f"{ARCHIVO_MATRIZ} estaba abierto (¿en Excel?); la matriz nueva se guardó "
                                     f"como «{matriz.name}». Cierre el archivo anterior y reemplácelo.")
    except (CorpusError, OSError) as e:
        matriz = None
        validacion.avisos.append(f"No se generó la matriz Excel: {getattr(e, 'mensaje', e)}")
    for skill in (rutas.skill_contexto, rutas.documentos):
        if not (skill / NOMBRE_SKILL_MD).is_file():
            validacion.avisos.append(f"Falta {skill.name}/{NOMBRE_SKILL_MD}: lo provee el equipo; cópielo en esa "
                                     "carpeta antes de comprimirla (el script no lo escribe).")
    medidas, avisos_limites = informe_limites([rutas.skill_contexto, rutas.documentos])
    validacion.avisos += avisos_limites
    escribir_resumen_construccion(resumen_path, validacion, publicados, medidas)
    shutil.copy2(resumen_path, rutas.indice / ARCHIVO_RESUMEN)
    # 5) Huellas al final: cubren todo lo publicado en las dos carpetas.
    escribir_huellas(publicado)
    print("\nCONSTRUIR CORPUS · convertir.py v" + VERSION)
    print("Resultado: " + validacion.estado)
    print(f"Carpetas para comprimir y subir como skills (en {publicado}):")
    print(f"- {rutas.documentos.name}")
    print(f"- {rutas.skill_contexto.name}")
    for m in medidas:
        print(f"  {m}")
    print(f"Control: {control}")
    print(f"Resumen: {resumen_path}")
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


def modo_matriz(args):
    """Regenera la matriz Excel y sus CSV desde una construccion existente."""
    raiz = Path(args.salida or "salida_corpus").resolve()
    publicado = raiz / CARPETA_PUBLICADA
    print(f"MATRIZ · convertir.py v{VERSION}")
    matriz = escribir_matriz(raiz)
    escribir_huellas(publicado)
    print(f"Matriz Excel y un CSV por hoja en: {matriz.parent}")
    print(f"Matriz Excel: {matriz}")


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
         "construir": modo_construir,
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
            sp.add_argument("--tipo", default=None, help="DES, PRD, PRO o POL, para convertir solo ese tipo.")
            sp.add_argument("--dep", default=None, help="Código de 3 letras, para convertir solo ese departamento.")
            sp.add_argument("--departamento", default=None,
                            help="Nombre del departamento, para convertir sin inventario (piloto).")
        if nombre == "contexto":
            sp.add_argument("--excluir", nargs="*", default=[])
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
