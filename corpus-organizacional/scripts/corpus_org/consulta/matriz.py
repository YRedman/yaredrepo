"""Matriz organizacional en Excel: base de datos del corpus publicado para revisarla sin ejecutar codigo.

Hojas: Léeme, Resumen (formulas), Puestos, Funciones, Relaciones, Perfil y requisitos, Normativa citada,
Procedimientos, Políticas y protocolos, Documentos generales, Participación, Puestos x Procedimientos,
Indicadores y Revisión. Cada hoja se exporta tambien a un CSV (UTF-8, separador ';') en matriz/.
Todo sale del corpus publicado: lo que no esta en un documento no se completa.
"""

import collections
import datetime
import re
from dataclasses import dataclass, field
from typing import List

from .. import VERSION
from ..comun.archivos import escribir_csv_filas, leer_csv, leer_texto
from ..comun.errores import CorpusError
from ..comun.esquema import ARCHIVO_RESUMEN, ARCHIVO_REVISION, AVISO_ESCANEADO, area_de
from ..comun.markdown import celdas
from ..comun.texto import norm, sin_acentos
from ..comun.tipos import es_general, familia, tipo as tipo_documento, tipo_de_codigo
from .parser import lineas_contenido
from .participacion import calcular_participacion
from .puestos import DetectorPuestos
from .repositorio import cargar_corpus

ARCHIVO_MATRIZ = "matriz_organizacional.xlsx"
MAX_TEXTO_CELDA = 3000

RE_FUNCIONES = re.compile(r"funci[oó]n|funciones|responsabilidad")
RE_EVIDENCIA = re.compile(r"evidencia|entregable")
RE_RELACION = re.compile(r"tipo de relaci")
RE_PERFIL = re.compile(r"requisit|competenc|cara[cs]ter[ií]stica|formaci|experienc|conocimient|perfil|habilidad|"
                       r"idioma|acceso|herramienta")
# Referencias a normativa interna o externa, en el orden en que se clasifican.
TIPOS_NORMATIVA = (
    ("Política", re.compile(r"\bpol[ií]ticas?\b", re.I)),
    ("Protocolo", re.compile(r"\bprotocolos?\b", re.I)),
    ("Procedimiento", re.compile(r"\bprocedimientos?\b", re.I)),
    ("Reglamento", re.compile(r"\breglamentos?\b", re.I)),
    ("Manual", re.compile(r"\bmanual(es)?\b", re.I)),
    ("Instructivo", re.compile(r"\binstructivos?\b", re.I)),
    ("Norma", re.compile(r"\bnormas?\b|\bnormativas?\b|\bISO\s?\d", re.I)),
    ("Ley", re.compile(r"\bley(es)?\b", re.I)),
    ("Código de documento", re.compile(r"\b[A-Z]{2,5}(?:-[A-Z]{2,5}){1,3}-\d{2,4}\b")),
)


@dataclass
class Tabla:
    seccion: str
    cabecera: List[str]
    filas: List[List[str]] = field(default_factory=list)


def tablas(doc):
    """Tablas completas (cabecera y filas) de un documento publicado, con la seccion donde estan."""
    res, actual = [], None
    for lc in lineas_contenido(doc):
        if not lc.es_tabla:
            actual = None
            continue
        if lc.es_cabecera:
            actual = Tabla(lc.seccion, celdas(lc.texto))
            res.append(actual)
        elif actual is not None:
            actual.filas.append(celdas(lc.texto))
    return res


def _limpia(s):
    return re.sub(r"\s+", " ", (s or "").replace("[CELDA COMBINADA]", "")).strip()


def _sin_vineta(s):
    return re.sub(r"^\s*(?:[-•●▪*»]|\d{1,2}[.)])\s+", "", s or "").strip()


# ---------------------------------------------------------------------------
# Extraccion por documento
# ---------------------------------------------------------------------------

def funciones(doc):
    """[(funcion, evidencia)]: filas de la tabla de funciones; si no hay tabla, las viñetas de la seccion."""
    res = []
    for t in tablas(doc):
        cab = [norm(c) for c in t.cabecera]
        if not cab or any(RE_RELACION.search(c) for c in cab):
            continue
        if RE_FUNCIONES.search(cab[0]) or (RE_FUNCIONES.search(norm(t.seccion)) and len(cab) <= 3):
            j_ev = next((j for j, c in enumerate(cab) if RE_EVIDENCIA.search(c)), None)
            for f in t.filas:
                funcion = _limpia(f[0]) if f else ""
                evidencia = _limpia(f[j_ev]) if j_ev is not None and j_ev < len(f) else ""
                if funcion and not RE_FUNCIONES.fullmatch(norm(funcion)):
                    res.append((funcion, evidencia))
    if res:
        return res
    for lc in lineas_contenido(doc):
        if not lc.es_tabla and RE_FUNCIONES.search(norm(lc.seccion)) and re.match(r"^\s*(?:-|\d{1,2}[.)])\s", lc.texto):
            res.append((_sin_vineta(lc.texto), ""))
    return res


def relaciones(doc):
    """[(area o puesto de interaccion, tipo de relacion)] de la tabla 'Áreas de Relacionamiento'."""
    res = []
    for t in tablas(doc):
        if any(RE_RELACION.search(norm(c)) for c in t.cabecera):
            for f in t.filas:
                no_vacias = [_limpia(x) for x in f if _limpia(x)]
                if len(no_vacias) >= 2:
                    res.append((no_vacias[0], no_vacias[-1]))
    return res


def perfil(doc):
    """[(seccion, requisito, detalle)] de las tablas de requisitos, competencias y caracteristicas."""
    res = []
    for t in tablas(doc):
        cab = [norm(c) for c in t.cabecera]
        if any(RE_RELACION.search(c) for c in cab) or (cab and RE_FUNCIONES.search(cab[0])):
            continue
        titulo = _limpia(t.cabecera[0]) if t.cabecera else ""
        if not (RE_PERFIL.search(norm(titulo)) or RE_PERFIL.search(norm(t.seccion))):
            continue
        seccion = titulo if RE_PERFIL.search(norm(titulo)) else t.seccion
        for f in t.filas:
            f = [_limpia(x) for x in f]
            if any(f):
                res.append((seccion, f[0], " | ".join(x for x in f[1:] if x)))
    return res


def normativa(doc):
    """[(tipo, mencion, seccion)]: lineas o celdas que citan politicas, procedimientos, normas o codigos."""
    res, vistos = [], set()
    for lc in lineas_contenido(doc):
        if lc.es_cabecera:
            continue
        textos = celdas(lc.texto) if lc.es_tabla else [lc.texto]
        for texto in textos:
            texto = _limpia(texto)
            for tipo, patron in TIPOS_NORMATIVA:
                if patron.search(texto) and (tipo, texto) not in vistos:
                    vistos.add((tipo, texto))
                    res.append((tipo, texto, lc.seccion))
    return res


# ---------------------------------------------------------------------------
# Libro
# ---------------------------------------------------------------------------

def _estado_construccion(raiz):
    p = raiz / ARCHIVO_RESUMEN
    m = re.search(r"Resultado:\s*\**([^*\n]+)", leer_texto(p)) if p.is_file() else None
    return m.group(1).strip() if m else "desconocido"


def _revision(raiz):
    """{codigo: revisado (bool)} de control/revision_visual.csv."""
    p = raiz / "control" / ARCHIVO_REVISION
    return {(f.get("codigo") or "").upper(): bool((f.get("revisado") or "").strip()) for f in leer_csv(p)} \
        if p.is_file() else {}


def _lectura(fila):
    avisos = fila.get("detalle_avisos") or ""
    if AVISO_ESCANEADO in avisos or (fila.get("palabras") or "").strip() == "0":
        return "Sin texto (escaneado)"
    if (fila.get("paginas_ocr") or "").strip() or "OCR en" in avisos:
        conf = (fila.get("confianza_ocr") or "").strip()
        detalle = f"confianza {float(conf):.0f} %" if conf else "confianza desconocida"
        revisar = "OCR en" in avisos or not conf
        return f"OCR ({detalle}{'; revisar contra el original' if revisar else ''})"
    return "Digital"


def _jefe(detector, texto, codigo):
    """(codigo, tipo de coincidencia) del puesto mencionado en 'Reporta a', si esta en el corpus."""
    for m in detector.detectar(texto or "", area_de(codigo)):
        if m.puesto is not None and m.puesto.codigo != codigo:
            return m.puesto.codigo, m.etiqueta
    return "", ""


def _nombre_tipo(codigo):
    t = tipo_documento(tipo_de_codigo(codigo))
    return t.nombre if t else tipo_de_codigo(codigo)


def datos_matriz(raiz):
    """Filas de cada hoja (listas de listas) calculadas del corpus publicado en ``raiz``/publicado."""
    corpus = cargar_corpus(raiz / "publicado", incluir_no_vigentes=True)
    detector = DetectorPuestos.desde_corpus(corpus)
    revision = _revision(raiz)
    hojas = collections.OrderedDict((k, []) for k in (
        "Puestos", "Funciones", "Relaciones", "Perfil y requisitos", "Normativa citada", "Procedimientos",
        "Políticas y protocolos", "Documentos generales", "Participación", "Puestos x Procedimientos",
        "Indicadores", "Revisión"))
    descriptivos = sorted(c for c in corpus.meta if tipo_de_codigo(c) == "DES")
    procedimientos = sorted(c for c in corpus.meta if tipo_de_codigo(c) == "PRD")
    normativos = sorted(c for c in corpus.meta if familia(tipo_de_codigo(c)) == "P" and c not in procedimientos)
    for c in sorted(c for c in corpus.meta if es_general(c)):
        f = corpus.meta[c]
        hojas["Documentos generales"].append([c, _nombre_tipo(c), corpus.nombre(c), f.get("archivo_origen", ""),
                                              _lectura(f), corpus.doc(c).ubicacion if corpus.doc(c) else ""])
    for c in descriptivos + procedimientos + normativos:
        f, doc = corpus.meta[c], corpus.doc(c)
        area, nombre = f.get("departamento", ""), corpus.nombre(c)
        lectura = _lectura(f)
        pendiente = c in revision and not revision[c]
        estado_rev = "Pendiente" if pendiente else ("Revisado" if c in revision else "No requerida")
        if c in normativos:
            hojas["Políticas y protocolos"].append([
                c, _nombre_tipo(c), area, f.get("area_propietaria", ""), nombre, f.get("proposito_literal", ""),
                f.get("propietario", ""), f.get("responsable", ""), f.get("codigo_interno", ""),
                f.get("version", ""), f.get("fecha_vigencia", ""), f.get("estado_documental", ""), lectura,
                estado_rev])
        elif tipo_de_codigo(c) == "DES":
            jefe, coincidencia = _jefe(detector, f.get("reporta_a"), c)
            hojas["Puestos"].append([
                c, area, nombre, f.get("reporta_a", ""), jefe, coincidencia, f.get("supervisa_a", ""),
                f.get("proposito_literal", ""), f.get("codigo_interno", ""), f.get("version", ""),
                f.get("fecha_vigencia", ""), f.get("estado_documental", ""), lectura, estado_rev,
                f.get("archivo_origen", ""), doc.ubicacion if doc else ""])
            for n, (funcion, evidencia) in enumerate(funciones(doc), 1):
                hojas["Funciones"].append([c, area, nombre, n, funcion, evidencia])
            for otro, tipo in relaciones(doc):
                rel = next((m for m in detector.detectar(otro, area_de(c)) if m.puesto is not None), None)
                hojas["Relaciones"].append([c, area, nombre, otro, tipo,
                                            rel.puesto.codigo if rel else "", rel.puesto.nombre if rel else ""])
            for seccion, requisito, detalle in perfil(doc):
                hojas["Perfil y requisitos"].append([c, area, nombre, seccion, requisito, detalle])
        else:
            hojas["Procedimientos"].append([
                c, area, nombre, f.get("proposito_literal", ""), f.get("propietario", ""), f.get("responsable", ""),
                f.get("codigo_interno", ""), f.get("version", ""), f.get("fecha_vigencia", ""),
                f.get("estado_documental", ""), f.get("actividades", ""), lectura, estado_rev])
        for tipo, mencion, seccion in normativa(doc):
            hojas["Normativa citada"].append([c, area, nombre, tipo, mencion, seccion])
        if lectura != "Digital" or c in revision:
            hojas["Revisión"].append([c, area, nombre, lectura, f.get("detalle_avisos", "") or
                                      ("muestra aleatoria" if c in revision else ""),
                                      "Pendiente" if pendiente or c not in revision else "Revisado", ""])
    part = calcular_participacion(corpus, procedimientos + normativos, detector)
    cruces = collections.defaultdict(set)
    for fp in part.filas:
        hojas["Participación"].append([fp.puesto.codigo, fp.puesto.nombre, fp.procedimiento,
                                       corpus.nombre(fp.procedimiento), fp.rol, fp.coincidencia, fp.evidencia])
        cruces[(fp.puesto.codigo, fp.procedimiento)].add(fp.rol)
    for rol, procs in part.sin_descriptivo.items():
        for p in sorted(procs):
            hojas["Participación"].append(["", rol, p, corpus.nombre(p), "", "sin descriptivo en el corpus", ""])
    if cruces:
        procs = sorted({p for _, p in cruces})
        hojas["Puestos x Procedimientos"].append(["Código", "Puesto"] + procs)
        for cod in sorted({c for c, _ in cruces}):
            hojas["Puestos x Procedimientos"].append(
                [cod, corpus.nombre(cod)] + [", ".join(sorted(cruces.get((cod, p), ()))) for p in procs])
    if corpus.kpis:
        columnas = list(corpus.kpis[0].keys())
        hojas["Indicadores"] = [columnas] + [[k.get(x, "") for x in columnas] for k in corpus.kpis]
    return corpus, hojas


COLUMNAS = {
    "Puestos": [("Código", 12), ("Área", 22), ("Puesto", 34), ("Reporta a (según el documento)", 34),
                ("Código del jefe en el corpus", 14), ("Coincidencia del jefe", 16),
                ("Supervisa a (según el documento)", 30), ("Propósito / objetivo del puesto", 60),
                ("Código interno", 18), ("Versión", 9), ("Vigencia", 12), ("Estado documental", 14),
                ("Calidad de lectura", 22), ("Revisión visual", 14), ("Archivo original", 40),
                ("Ubicación en el corpus", 22)],
    "Funciones": [("Código", 12), ("Área", 22), ("Puesto", 34), ("N.º", 6), ("Función", 70),
                  ("Evidencia de cumplimiento / entregable", 45)],
    "Relaciones": [("Código", 12), ("Área", 22), ("Puesto", 34), ("Área o puesto de interacción", 40),
                   ("Tipo de relación", 26), ("Código relacionado en el corpus", 14), ("Puesto relacionado", 34)],
    "Perfil y requisitos": [("Código", 12), ("Área", 22), ("Puesto", 34), ("Sección", 26), ("Requisito", 34),
                            ("Detalle", 70)],
    "Normativa citada": [("Código", 12), ("Área", 22), ("Documento", 34), ("Tipo de referencia", 18),
                         ("Texto donde se cita (literal)", 80), ("Sección", 26)],
    "Procedimientos": [("Código", 12), ("Área", 22), ("Procedimiento", 34), ("Propósito", 50), ("Propietario", 24),
                       ("Responsable", 24), ("Código interno", 18), ("Versión", 9), ("Vigencia", 12),
                       ("Estado documental", 14), ("Actividades", 70), ("Calidad de lectura", 22),
                       ("Revisión visual", 14)],
    "Participación": [("Código del puesto", 14), ("Puesto", 34), ("Procedimiento", 14),
                      ("Nombre del procedimiento", 34), ("Rol", 18), ("Coincidencia", 22),
                      ("Evidencia (texto literal)", 80)],
    "Políticas y protocolos": [("Código", 12), ("Tipo", 12), ("Área de aplicación", 22),
                               ("Área propietaria", 22), ("Documento", 34), ("Propósito", 50), ("Propietario", 24),
                               ("Responsable", 24), ("Código interno", 18), ("Versión", 9), ("Vigencia", 12),
                               ("Estado documental", 14), ("Calidad de lectura", 22), ("Revisión visual", 14)],
    "Documentos generales": [("Código", 12), ("Tipo", 18), ("Documento", 40), ("Archivo original", 40),
                             ("Calidad de lectura", 22), ("Ubicación en el corpus", 22)],
    "Revisión": [("Código", 12), ("Área", 22), ("Documento", 34), ("Calidad de lectura", 22),
                 ("Motivo de la revisión", 70), ("Estado", 12), ("Observaciones del auditor", 50)],
}
VACIAS = {
    "Procedimientos": "El corpus todavía no tiene procedimientos. Al agregarlos (carpeta Procedimientos) esta hoja "
                      "y las de participación se llenan solas.",
    "Participación": "Sin procedimientos en el corpus: no hay participación de puestos que mostrar.",
    "Puestos x Procedimientos": "Sin procedimientos en el corpus: la matriz se llena cuando se agreguen.",
    "Indicadores": "El contexto no trae un archivo kpi*.csv.",
    "Políticas y protocolos": "El corpus todavía no tiene políticas ni protocolos (carpetas Políticas y "
                              "Protocolos de la entrada).",
    "Documentos generales": "La construcción no tuvo carpeta de contexto (organigramas, indicadores, glosario…).",
}
DESCRIPCIONES = [
    ("Resumen", "Conteos por área (puestos, OCR, funciones, relaciones, pendientes) calculados con fórmulas."),
    ("Puestos", "Un puesto por fila: área, a quién reporta y a quién supervisa (literal), el código del jefe si "
                "está en el corpus, propósito, versión, vigencia y calidad de lectura."),
    ("Funciones", "Una función por fila con su evidencia o entregable, tal como aparece en el descriptivo."),
    ("Relaciones", "Áreas y puestos con los que interactúa cada puesto y el tipo de relación (subordinación, "
                   "reporte directo, pares, equipo interdisciplinario, matricial)."),
    ("Perfil y requisitos", "Educación, experiencia, competencias y características especiales de cada puesto."),
    ("Normativa citada", "Cada texto donde un documento menciona una política, protocolo, procedimiento, norma, "
                         "reglamento, manual, ley o código de documento. Es la cita literal: no interpreta."),
    ("Procedimientos", "Un procedimiento por fila con propietario, responsable, versión y actividades."),
    ("Políticas y protocolos", "Una política o protocolo por fila. «Área de aplicación» es General si aplica a "
                               "varias áreas o a toda la empresa; «Área propietaria» es el área que la emite, si "
                               "el documento la indica."),
    ("Documentos generales", "Organigramas, indicadores, glosarios, mapas de procesos y otros documentos de "
                             "contexto (área GEN)."),
    ("Participación", "Qué puesto aparece en qué procedimiento, protocolo o política y con qué rol (ejecuta, "
                      "aprueba, revisa…)."),
    ("Puestos x Procedimientos", "Matriz: filas = puestos, columnas = procedimientos, protocolos y políticas, "
                                 "celda = rol."),
    ("Indicadores", "KPIs del contexto (meta y medición)."),
    ("Revisión", "Documentos que deben compararse con el original (OCR, tablas partidas, muestra). La columna "
                 "amarilla es para las observaciones del auditor."),
]


def _cabecera_y_filas(nombre, filas):
    """(cabecera, filas, anchos) de una hoja; una hoja vacia lleva una nota que explica por que."""
    columnas = COLUMNAS.get(nombre)
    if columnas:
        cabecera, anchos = [c for c, _ in columnas], [a for _, a in columnas]
    elif filas:
        cabecera, filas = filas[0], filas[1:]
        anchos = [14, 34] + [16] * (len(cabecera) - 2) if nombre == "Puestos x Procedimientos" \
            else [20] * len(cabecera)
    else:
        cabecera, anchos = ["Nota"], [100]
    filas = [[str(x)[:MAX_TEXTO_CELDA] if isinstance(x, str) else x for x in f] for f in filas]
    if not filas and nombre in VACIAS:
        filas = [[VACIAS[nombre]] + [""] * (len(cabecera) - 1)]
    return cabecera, filas, anchos


COLUMNAS_RESUMEN = ["Área", "Puestos", "Leídos con OCR", "Sin texto", "Funciones", "Relaciones",
                    "Pendientes de revisión"]


def _areas_resumen(hojas):
    return sorted({f[1] for f in hojas["Puestos"]} | {f[1] for f in hojas["Procedimientos"]}
                  | {f[2] for f in hojas["Políticas y protocolos"]})


def valores_resumen(hojas):
    """Las mismas cuentas de la hoja Resumen (que en Excel son formulas), ya calculadas, con fila Total."""
    filas = []
    for area in _areas_resumen(hojas):
        puestos = [f for f in hojas["Puestos"] if f[1] == area]
        filas.append([area, len(puestos), sum(1 for f in puestos if str(f[12]).startswith("OCR")),
                      sum(1 for f in puestos if str(f[12]).startswith("Sin texto")),
                      sum(1 for f in hojas["Funciones"] if f[1] == area),
                      sum(1 for f in hojas["Relaciones"] if f[1] == area),
                      sum(1 for f in hojas["Revisión"] if f[1] == area and f[5] == "Pendiente")])
    filas.append(["Total"] + [sum(f[k] for f in filas) for k in range(1, len(COLUMNAS_RESUMEN))])
    return filas


def _nombre_csv(i, hoja):
    slug = re.sub(r"[^a-z0-9]+", "_", sin_acentos(hoja).lower()).strip("_")
    return f"{i:02d}_{slug}.csv"


def exportar_csv(hojas, raiz, carpeta):
    """Un CSV por hoja de la matriz (UTF-8, separador ';') en ``carpeta``. Devuelve las rutas."""
    carpeta.mkdir(parents=True, exist_ok=True)
    for p in carpeta.glob("*.csv"):
        p.unlink()
    todas = [("Léeme", ["Hoja", "Contenido"],
              [["Estado de la construcción", _estado_construccion(raiz)],
               ["Generada", f"{datetime.date.today():%d/%m/%Y} con convertir.py v{VERSION}"]]
              + [[n, d] for n, d in DESCRIPCIONES]),
             ("Resumen", COLUMNAS_RESUMEN, valores_resumen(hojas))]
    for nombre, filas in hojas.items():
        cabecera, filas, _ = _cabecera_y_filas(nombre, filas)
        todas.append((nombre, cabecera, filas))
    rutas = []
    for i, (nombre, cabecera, filas) in enumerate(todas, 1):
        ruta = carpeta / _nombre_csv(i, nombre)
        escribir_csv_filas(ruta, cabecera, filas)
        rutas.append(ruta)
    return rutas


def escribir_matriz(raiz, destino=None, carpeta_csv=None):
    """Escribe <raiz>/matriz_organizacional.xlsx (requiere openpyxl) y, con ``carpeta_csv``, un CSV por
    hoja (solo biblioteca estandar). Devuelve la ruta del Excel."""
    corpus, hojas = datos_matriz(raiz)
    if carpeta_csv is not None:
        exportar_csv(hojas, raiz, carpeta_csv)
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise CorpusError("Falta openpyxl para escribir el Excel: python -m pip install openpyxl")
    destino = destino or raiz / ARCHIVO_MATRIZ
    fuente, negrita = Font(name="Arial", size=10), Font(name="Arial", size=10, bold=True, color="FFFFFF")
    relleno_cab = PatternFill("solid", fgColor="1F4E78")
    relleno_auditor = PatternFill("solid", fgColor="FFFF00")
    ajuste = Alignment(wrap_text=True, vertical="top")

    wb = Workbook()
    leeme = wb.active
    leeme.title = "Léeme"
    for nombre, filas in hojas.items():
        ws = wb.create_sheet(nombre)
        cabecera, filas, anchos = _cabecera_y_filas(nombre, filas)
        ws.append(cabecera)
        for f in filas:
            ws.append(f)
        for j, a in enumerate(anchos, 1):
            ws.column_dimensions[get_column_letter(j)].width = a
        for fila in ws.iter_rows():
            for celda in fila:
                celda.font, celda.alignment = fuente, ajuste
        for celda in ws[1]:
            celda.font, celda.fill = negrita, relleno_cab
        if nombre == "Revisión":
            for k in range(2, ws.max_row + 1):
                ws.cell(k, 7).fill = relleno_auditor
        ws.freeze_panes = "A2" if nombre != "Puestos x Procedimientos" else "C2"
        ws.auto_filter.ref = ws.dimensions

    _leeme(leeme, corpus, hojas, raiz, fuente)
    _resumen(wb.create_sheet("Resumen", 1), hojas, fuente)
    wb.calculation.fullCalcOnLoad = True
    return guardar_libro(wb, destino)


def guardar_libro(wb, destino):
    """Guarda el libro; si el archivo esta abierto (Excel lo bloquea en Windows) lo guarda con otro nombre.

    Devuelve la ruta donde quedo guardado. Asi una construccion larga no termina en error por un
    archivo abierto: la matriz nueva queda al lado, con la fecha y hora en el nombre.
    """
    try:
        wb.save(destino)
        return destino
    except PermissionError:
        alterno = destino.with_name(f"{destino.stem} {datetime.datetime.now():%Y-%m-%d %H%M%S}{destino.suffix}")
        wb.save(alterno)
        return alterno


def _leeme(ws, corpus, hojas, raiz, fuente):
    from openpyxl.styles import Alignment, Font
    titulo = Font(name="Arial", size=14, bold=True)
    negrita = Font(name="Arial", size=10, bold=True)
    filas = [
        ("Matriz organizacional", titulo),
        (f"Generada el {datetime.date.today():%d/%m/%Y} con convertir.py v{VERSION} a partir del corpus publicado.",
         fuente),
        (f"Estado de la construcción del corpus: {_estado_construccion(raiz)}.", negrita),
        ("Todo el contenido es literal de los documentos. Las columnas «Código del jefe en el corpus» y «Código "
         "relacionado» son cruces automáticos por nombre de puesto; «probable» indica que el nombre no es idéntico.",
         fuente),
        ("«Calidad de lectura» = Digital (texto del PDF), OCR (documento escaneado: revisar contra el original) o "
         "Sin texto. Los documentos «Pendiente» en la hoja Revisión aún no se compararon con el original.", fuente),
        ("", fuente),
        ("Hojas", negrita),
    ]
    for texto, f in filas:
        ws.append([texto])
        ws.cell(ws.max_row, 1).font = f
    for nombre, desc in DESCRIPCIONES:
        ws.append([nombre, desc])
        ws.cell(ws.max_row, 1).font = negrita
        ws.cell(ws.max_row, 2).font = fuente
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 110
    for fila in ws.iter_rows():
        for celda in fila:
            celda.alignment = Alignment(wrap_text=True, vertical="top")


def _resumen(ws, hojas, fuente):
    """Conteos por área con fórmulas sobre las otras hojas."""
    from openpyxl.styles import Font, PatternFill
    ws.append(COLUMNAS_RESUMEN)
    for celda in ws[1]:
        celda.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="1F4E78")
    areas = _areas_resumen(hojas)
    for r, area in enumerate(areas, 2):
        ws.append([area,
                   f"=COUNTIF('Puestos'!$B:$B,$A{r})",
                   f"=COUNTIFS('Puestos'!$B:$B,$A{r},'Puestos'!$M:$M,\"OCR*\")",
                   f"=COUNTIFS('Puestos'!$B:$B,$A{r},'Puestos'!$M:$M,\"Sin texto*\")",
                   f"=COUNTIF('Funciones'!$B:$B,$A{r})",
                   f"=COUNTIF('Relaciones'!$B:$B,$A{r})",
                   f"=COUNTIFS('Revisión'!$B:$B,$A{r},'Revisión'!$F:$F,\"Pendiente\")"])
    ultima = ws.max_row
    ws.append(["Total"] + [f"=SUM({col}2:{col}{ultima})" for col in "BCDEFG"])
    for fila in ws.iter_rows(min_row=2):
        for celda in fila:
            celda.font = fuente
    for celda in ws[ws.max_row]:
        celda.font = Font(name="Arial", size=10, bold=True)
    ws.column_dimensions["A"].width = 30
    for col in "BCDEFG":
        ws.column_dimensions[col].width = 16
    ws.freeze_panes = "A2"
