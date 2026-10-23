"""Modo ``construir``: inventario, conversion, contexto, publicacion, validacion y huellas en una sola orden.

Publica en salida_corpus/copilot/fuente-corpus (un solo skill listo para comprimir). Termina con 0 (LISTO PARA
PUBLICAR), 2 (REQUIERE REVISIÓN) o 3 (PENDIENTE DE REVISIÓN VISUAL).
"""

import argparse
import contextlib
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ... import VERSION
from ...comun.archivos import escribir_csv, leer_csv
from ...comun.errores import CorpusError
from ...comun.esquema import ARCHIVO_CATALOGO, ARCHIVO_EQUIVALENCIAS, ARCHIVO_INVENTARIO, ARCHIVO_RESUMEN, COLUMNAS_INVENTARIO
from ...comun.estructura import (ARCHIVO_NOTA_UBICACION, CARPETA_PUBLICADA, LLAVE_NOTA_UBICACION, NOMBRE_SKILL_MD,
                                 NOTA_UBICACION_SKILL, SKILL_CONTEXTO, SKILL_CORPUS, SKILL_DOCUMENTOS, informe_limites,
                                 rutas_publicadas)
from ...comun.tipos import TIPOS_AREA, tipo as tipo_documento
from ...consulta.matriz import ARCHIVO_MATRIZ, escribir_matriz
from ..bitacora import Tee, guardar_bitacora
from ..entradas import buscar_entradas, localizar, partes_ruta
from ..informe import generar_informe
from ..inventario import escribir_equivalencias, leer_equivalencias, migrar_fila, tipo_de_carpeta
from ..materiales_contexto import (archivos_no_leidos, contexto_anterior, copiar_datos_de_contexto,
                                   documentos_de_area_del_contexto, equivalencias_de_contexto)
from ..publicacion import escribir_huellas, limpiar_generados, publicar_corpus
from ..resumen import escribir_resumen_construccion
from ..validacion import MUESTRA_REVISION, leer_revisados, validar_publicacion
from ..skills import CARPETA_SCRIPTS
from .base import Modo, agregar_argumentos_de_conversion, agregar_argumentos_de_lista, raiz_de_construccion
from .contexto import ejecutar_contexto
from .convertir import ejecutar_conversion
from .inventariar import Inventariar

REVISIONES_MOSTRADAS = 15


@dataclass
class Construccion:
    """Las carpetas de una construccion y los argumentos con que se pidio."""
    args: argparse.Namespace
    entrada: Path
    raiz_salida: Path
    control: Path
    publicado: Path
    contexto: Path = None

    @classmethod
    def desde(cls, args):
        entrada = Path(args.entrada).resolve()
        raiz_salida = raiz_de_construccion(args)
        contexto = Path(args.contexto).resolve() if args.contexto else None
        if contexto is not None and not contexto.is_dir():
            raise CorpusError(f"La carpeta de contexto no existe: {contexto}")
        return cls(args, entrada, raiz_salida, raiz_salida / "control", raiz_salida / CARPETA_PUBLICADA, contexto)

    @property
    def opciones_comunes(self):
        """Lo que reciben tal cual la conversion de area y la del contexto."""
        a = self.args
        return dict(salida=str(self.control), sin_verificacion_cruzada=a.sin_verificacion_cruzada,
                    tiempo_max=a.tiempo_max, trabajadores=getattr(a, "trabajadores", 0))


# ---------------------------------------------------------------------------
# 1) inventario
# ---------------------------------------------------------------------------

def _copiar_si_distinto(origen, destino):
    if Path(origen).resolve() != Path(destino).resolve():
        shutil.copy2(origen, destino)


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


def _nombre_de_lista(c, extra_filas):
    """La lista de archivos del inventario: la adjunta o, si no hay, la que se arma con las carpetas de tipo
    (o una vacia si solo hay documentos de area en la carpeta de contexto)."""
    entrada, control = c.entrada, c.control
    encontrada = localizar(c.args.lista, entrada)
    if not encontrada or Path(encontrada).resolve().parent == control.resolve():
        generada = _lista_desde_carpeta(entrada, c.raiz_salida, control)
        if generada:
            return str(generada)
        if extra_filas:
            (control / "lista.txt").write_text("", encoding="utf-8")
            return str(control / "lista.txt")
    return c.args.lista


def _inventario_para_construir(c, extra_filas=()):
    """Con lista.txt el inventario se regenera conservando los codigos del anterior (si existe).
    Sin lista.txt, la lista se arma con las carpetas de tipo (Descriptivos, Procedimientos, Protocolos,
    Políticas) de la entrada; si no las hay, se usa el inventario adjunto tal cual."""
    args, entrada, control = c.args, c.entrada, c.control
    base_control = control / ARCHIVO_INVENTARIO
    previo = localizar(args.inventario, entrada) or (base_control if base_control.is_file() else None)
    lista = _nombre_de_lista(c, extra_filas)
    if localizar(lista, entrada):
        base = None
        if previo:
            base = control / "inventario_base.csv"
            _copiar_si_distinto(previo, base)
        Inventariar().ejecutar(argparse.Namespace(
            entrada=str(entrada), salida=str(control), lista=lista, catalogo=args.catalogo,
            incluir_duplicados=args.incluir_duplicados, base=str(base) if base else None,
            extra_filas=list(extra_filas)))
    elif previo:
        _copiar_si_distinto(previo, base_control)
        escribir_equivalencias(control / ARCHIVO_EQUIVALENCIAS, migrar_inventario(base_control))
        cat = localizar(args.catalogo, entrada) if args.catalogo else None
        if cat:
            shutil.copy2(cat, control / ARCHIVO_CATALOGO)
    else:
        raise CorpusError("No hay documentos en carpetas de tipo (" + ", ".join(
            tipo_documento(t).plural for t in TIPOS_AREA) + ") dentro de la entrada "
            "(ni lista.txt o inventario_maestro.csv).")


# ---------------------------------------------------------------------------
# 2) y 3) conversion
# ---------------------------------------------------------------------------

def _convertir_documentos_de_area(c, de_area):
    ejecutar_conversion(argparse.Namespace(
        entrada=str(c.entrada), inventario=str(c.control / ARCHIVO_INVENTARIO), tipo=None, dep=None, departamento=None,
        contexto=str(c.contexto) if c.contexto else None, extra_entradas=[Path(f["ruta"]) for f in de_area],
        **c.opciones_comunes))


def _convertir_contexto(c, de_area, repetidos, anteriores):
    """Documentos generales (ORG-GEN, GLO-GEN...) en un grupo aparte, para no convertir como contexto los documentos
    operativos. Los indicadores van a kpis.csv. Devuelve los errores de conversion."""
    no_contexto = copiar_datos_de_contexto(c.contexto, c.control) + [f["archivo"] for f in de_area] + repetidos
    res = ejecutar_contexto(argparse.Namespace(entrada=str(c.contexto), excluir=no_contexto, anteriores=anteriores,
                                               **c.opciones_comunes))
    return [f"{r.codigo} {r.archivo}: {r.estado} {r.error}".strip() for r in res.documentos if not r.ok]


# ---------------------------------------------------------------------------
# 4) publicacion
# ---------------------------------------------------------------------------

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
    anteriores = [publicado / n for n in (SKILL_CONTEXTO, SKILL_DOCUMENTOS) if (publicado / n).is_dir()]
    if anteriores:
        destino = raiz_salida / "anterior_dos_skills"
        destino.mkdir(exist_ok=True)
        for carpeta in anteriores:
            if (destino / carpeta.name).exists():
                shutil.rmtree(destino / carpeta.name, ignore_errors=True)
            shutil.move(str(carpeta), str(destino / carpeta.name))
        avisos.append(f"Las carpetas {' y '.join(c.name for c in anteriores)} (la publicación anterior en dos skills) se "
                      f"movieron a salida_corpus/{destino.name}/: Copilot admite un solo skill y ahora se publica "
                      f"copilot/{SKILL_CORPUS}/. No las suba; puede borrarlas.")
    if (raiz_salida / "publicado").is_dir():
        avisos.append("La carpeta salida_corpus/publicado/ es de una versión anterior y ya no se usa: la "
                      f"publicación está en salida_corpus/{CARPETA_PUBLICADA}/. Puede borrarla.")


def _skill_md_de_origen(args):
    """El SKILL.md que se copia al skill: ``--skill-md`` o el SKILL.md junto a scripts/ en el repositorio; None si no hay."""
    candidatos = [getattr(args, "skill_md", None), CARPETA_SCRIPTS.parent / NOMBRE_SKILL_MD]
    for c in candidatos:
        if c and Path(c).is_file():
            return Path(c).resolve()
    return None


def _validar(c, publicado, duplicados, errores_contexto, avisos_publicacion):
    equivalencias = leer_equivalencias(c.control / ARCHIVO_EQUIVALENCIAS)
    revisados = {equivalencias.get(x, x) for x in leer_revisados(c.raiz_salida, c.control, c.entrada)}
    validacion = validar_publicacion(publicado, duplicados, revisados, c.args.muestra_revision, errores_contexto,
                                     c.control)
    validacion.avisos += avisos_publicacion
    aviso_formatos = archivos_no_leidos(c.contexto, c.control) if c.contexto is not None else None
    if aviso_formatos:
        validacion.avisos.append(aviso_formatos)
    if equivalencias:
        validacion.avisos.append(f"Codificación TTT-AAA-NN: {len(equivalencias)} códigos anteriores tienen su "
                                 f"equivalencia en {ARCHIVO_EQUIVALENCIAS}.")
    return validacion


def _escribir_matriz(raiz_salida, validacion):
    """Matriz Excel. Un problema aqui (archivo abierto, permisos) no debe perder la construccion."""
    try:
        matriz = escribir_matriz(raiz_salida)
    except (CorpusError, OSError) as e:
        validacion.avisos.append(f"No se generó la matriz Excel: {getattr(e, 'mensaje', e)}")
        return None
    if matriz.name != ARCHIVO_MATRIZ:
        validacion.avisos.append(f"{ARCHIVO_MATRIZ} estaba abierto (¿en Excel?); la matriz nueva se guardó "
                                 f"como «{matriz.name}». Cierre el archivo anterior y reemplácelo.")
    return matriz


def _copiar_skill_md(args, rutas, nota, validacion):
    """Copia el SKILL.md del repositorio al skill y avisa si falta o no explica donde queda cargado el skill."""
    skill_md = _skill_md_de_origen(args)
    destino = rutas.skill / NOMBRE_SKILL_MD
    if skill_md is not None:
        shutil.copy2(skill_md, destino)
        print(f"SKILL.md copiado a {destino.parent.name}/ desde {skill_md}")
    if not destino.is_file():
        validacion.avisos.append(f"Falta {rutas.skill.name}/{NOMBRE_SKILL_MD}: póngalo como SKILL.md junto a la carpeta "
                                 "scripts/ del repositorio (se copia solo) o cópielo en esa carpeta antes de comprimirla.")
    elif LLAVE_NOTA_UBICACION not in destino.read_text(encoding="utf-8", errors="replace"):
        validacion.avisos.append(f"El {rutas.skill.name}/{NOMBRE_SKILL_MD} no explica dónde queda cargado el skill "
                                 f"({LLAVE_NOTA_UBICACION}): el agente puede buscarlo en una ruta equivocada. Agregue "
                                 f"la nota de {nota.name}.")


def _publicar_y_validar(c, errores_contexto):
    """Publicacion en el skill, indice maestro, validacion, matriz, SKILL.md y huellas. Devuelve lo que se imprime."""
    avisos_publicacion = []
    _limpiar_publicacion_anterior(c.raiz_salida, c.publicado, avisos_publicacion)
    publicados, duplicados = publicar_corpus(c.control, c.publicado, avisos_publicacion)
    rutas = rutas_publicadas(c.publicado)
    validacion = _validar(c, c.publicado, duplicados, errores_contexto, avisos_publicacion)
    resumen = c.raiz_salida / ARCHIVO_RESUMEN
    escribir_resumen_construccion(resumen, validacion, publicados)      # la matriz lee de aqui el estado
    matriz = _escribir_matriz(c.raiz_salida, validacion)
    nota = c.raiz_salida / ARCHIVO_NOTA_UBICACION          # fuera de lo publicado: es para pegar en el SKILL.md del equipo
    nota.write_text(NOTA_UBICACION_SKILL, encoding="utf-8")
    _copiar_skill_md(c.args, rutas, nota, validacion)
    medidas, avisos_limites = informe_limites([rutas.skill])
    validacion.avisos += avisos_limites
    escribir_resumen_construccion(resumen, validacion, publicados, medidas)
    shutil.copy2(resumen, rutas.indice / ARCHIVO_RESUMEN)
    escribir_huellas(c.publicado)      # al final: cubren todo lo publicado en el skill
    return validacion, rutas, medidas, matriz, resumen


# ---------------------------------------------------------------------------
# 5) resultado en la consola
# ---------------------------------------------------------------------------

def _imprimir_resultado(c, validacion, rutas, medidas, matriz, resumen):
    print("\nCONSTRUIR CORPUS · convertir.py v" + VERSION)
    print("Resultado: " + validacion.estado)
    print(f"Carpeta para comprimir y subir como skill (en {c.publicado}):")
    print(f"- {rutas.skill.name}")
    for m in medidas:
        print(f"  {m}")
    print(f"Control: {c.control}")
    print(f"Resumen: {resumen}")
    if matriz:
        print(f"Matriz Excel: {matriz}")
    for x in validacion.problemas:
        print("ERROR: " + x)
    if validacion.revision_visual:
        pendientes = list(validacion.revision_visual.items())
        print(f"REVISIÓN VISUAL PENDIENTE ({len(pendientes)}); ubicación de cada original en "
              f"{resumen.name} y control/revision_visual.csv:")
        for codigo, motivo in pendientes[:REVISIONES_MOSTRADAS]:
            print(f"- {codigo} {validacion.ubicacion_de(codigo)[1]} ({motivo[:60]})")
        if len(pendientes) > REVISIONES_MOSTRADAS:
            print(f"- … y {len(pendientes) - REVISIONES_MOSTRADAS} más")
    for codigo, motivos in validacion.con_problemas.items():
        print(f"- PROBLEMA en {codigo} {validacion.ubicacion_de(codigo)[1]}: {'; '.join(motivos)}")
    for x in validacion.avisos:
        print("AVISO: " + x)


def construir(args):
    """Todo el flujo. Termina con ``sys.exit`` si el resultado no es LISTO PARA PUBLICAR."""
    c = Construccion.desde(args)
    c.control.mkdir(parents=True, exist_ok=True)
    c.publicado.mkdir(parents=True, exist_ok=True)
    anteriores = contexto_anterior(c.control, c.raiz_salida)
    limpiar_generados(c.control)

    # Los procedimientos, politicas/normativas, protocolos y descriptivos que estan en la carpeta de contexto
    # son documentos de area: se inventarian, convierten y validan como los de la entrada.
    de_area, repetidos = documentos_de_area_del_contexto(c.contexto, c.entrada, c.raiz_salida) \
        if c.contexto is not None else ([], [])

    # 1) Inventario (codigos estables si ya habia uno; los codigos D-/P- anteriores se migran).
    _inventario_para_construir(c, de_area)
    if de_area:
        print(f"Documentos de área en la carpeta de contexto: {len(de_area)} "
              f"({', '.join(sorted({f['tipo'] for f in de_area}))})")
        escribir_equivalencias(c.control / ARCHIVO_EQUIVALENCIAS, equivalencias_de_contexto(c.control, de_area, anteriores))

    # 2) Conversion de los documentos de area (DES, PRD, PRO, POL).
    _convertir_documentos_de_area(c, de_area)

    # 3) Contexto opcional.
    errores_contexto = _convertir_contexto(c, de_area, repetidos, anteriores) if c.contexto is not None else []

    # 4) Publicacion, validacion y huellas.
    validacion, rutas, medidas, matriz, resumen = _publicar_y_validar(c, errores_contexto)
    _imprimir_resultado(c, validacion, rutas, medidas, matriz, resumen)
    if validacion.codigo_salida:
        sys.exit(validacion.codigo_salida)


def _guardar_informe(args, tee, inicio):
    """El log y el informe HTML. Un informe que no se puede escribir no debe tumbar la construccion."""
    raiz_salida = raiz_de_construccion(args)
    try:
        contexto = Path(args.contexto).resolve() if args.contexto else None
        guardar_bitacora(raiz_salida / "control", tee.texto, Path(args.entrada).resolve(), contexto, inicio)
        print(f"Informe HTML (ábralo con doble clic): {generar_informe(raiz_salida, tee.texto)}")
    except OSError as e:
        print(f"AVISO: no se pudo escribir el informe HTML: {e}")


class Construir(Modo):
    nombre = "construir"

    def configurar(self, parser):
        agregar_argumentos_de_lista(parser)
        parser.add_argument("--inventario", default=ARCHIVO_INVENTARIO)
        parser.add_argument("--contexto", default=None,
                            help="Carpeta separada con organigrama, glosario y otros materiales de contexto.")
        parser.add_argument("--skill-md", default=None,
                            help="SKILL.md que se copia al skill publicado (por defecto el SKILL.md junto a scripts/).")
        parser.add_argument("--muestra-revision", type=float, default=MUESTRA_REVISION,
                            help="Fracción de documentos sin avisos que se revisan visualmente (0 = ninguno).")
        agregar_argumentos_de_conversion(parser)

    def ejecutar(self, args):
        """``construir`` mas el log guardado (control/log_construccion.txt) y el informe HTML (INFORME_CONSTRUCCION.html)."""
        inicio = time.time()
        tee, codigo = Tee(sys.stdout), 0
        try:
            with contextlib.redirect_stdout(tee):
                construir(args)
        except SystemExit as e:                 # 2 = REQUIERE REVISION, 3 = PENDIENTE DE REVISION VISUAL
            codigo = e.code or 0
        _guardar_informe(args, tee, inicio)
        if codigo:
            sys.exit(codigo)
