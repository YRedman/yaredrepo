"""Matriz organizacional en Excel: base de datos del corpus publicado para revisarla sin ejecutar codigo.

Hojas: Léeme, Resumen (formulas), Puestos, Funciones, Relaciones, Perfil y requisitos, Normativa citada,
Procedimientos, Políticas y protocolos, Documentos generales, Participación, Puestos x Procedimientos,
Indicadores y Revisión. Cada hoja se exporta tambien a un CSV (UTF-8, separador ';') en matriz/.
Todo sale del corpus publicado: lo que no esta en un documento no se completa.
"""

import collections
import datetime
import re

from .. import VERSION
from ..comun.archivos import escribir_csv_filas, leer_csv, leer_texto
from ..comun.errores import CorpusError
from ..comun.estructura import CARPETA_PUBLICADA, rutas_publicadas
from ..comun.esquema import ARCHIVO_RESUMEN, ARCHIVO_REVISION, AVISO_ESCANEADO, area_de
from ..comun.texto import sin_acentos
from ..comun.tipos import TIPOS_PROCESO, es_general, tipo as tipo_documento, tipo_de_codigo
from .cadena import calcular_enlaces, tipo_de_codigo_cliente
from .extraccion import alcance, funciones, normativa, perfil, relaciones
from .participacion import calcular_participacion
from .puestos import DetectorPuestos
from .repositorio import cargar_corpus

ARCHIVO_MATRIZ = "matriz_organizacional.xlsx"
MAX_TEXTO_CELDA = 3000

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
    corpus = cargar_corpus(rutas_publicadas(raiz / CARPETA_PUBLICADA).skill_contexto, incluir_no_vigentes=True)
    detector = DetectorPuestos.desde_corpus(corpus)
    revision = _revision(raiz)
    hojas = collections.OrderedDict((k, []) for k in (
        "Puestos", "Funciones", "Relaciones", "Perfil y requisitos", "Normativa citada", "Cadena documental",
        "Procedimientos",
        "Políticas y protocolos", "Documentos generales", "Participación", "Puestos x Procedimientos",
        "Indicadores", "Revisión"))
    descriptivos = sorted(c for c in corpus.meta if tipo_de_codigo(c) == "DES")
    procedimientos = sorted(c for c in corpus.meta if tipo_de_codigo(c) in TIPOS_PROCESO)      # PRD y PRO
    normativos = sorted(c for c in corpus.meta if tipo_de_codigo(c) in ("PRO", "POL"))        # hoja de politicas
    politicas = sorted(c for c in corpus.meta if tipo_de_codigo(c) == "POL")
    for c in sorted(c for c in corpus.meta if es_general(c)):
        f = corpus.meta[c]
        hojas["Documentos generales"].append([c, _nombre_tipo(c), corpus.nombre(c), f.get("archivo_origen", ""),
                                              _lectura(f), corpus.doc(c).ubicacion if corpus.doc(c) else ""])
    for c in descriptivos + procedimientos + politicas:
        f, doc = corpus.meta[c], corpus.doc(c)
        area, nombre = f.get("departamento", ""), corpus.nombre(c)
        lectura = _lectura(f)
        pendiente = c in revision and not revision[c]
        estado_rev = "Pendiente" if pendiente else ("Revisado" if c in revision else "No requerida")
        if c in normativos:            # politicas y protocolos: area de aplicacion, area propietaria y alcance
            hojas["Políticas y protocolos"].append([
                c, _nombre_tipo(c), area, f.get("area_propietaria", ""), alcance(doc), f.get("version", ""),
                f.get("fecha_vigencia", ""), f.get("estado_documental", ""), nombre, f.get("proposito_literal", ""),
                f.get("propietario", ""), f.get("responsable", ""), f.get("codigo_interno", ""), lectura,
                estado_rev])
        if tipo_de_codigo(c) == "DES":
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
        if c in procedimientos:
            hojas["Procedimientos"].append([
                c, _nombre_tipo(c), area, nombre, f.get("proposito_literal", ""), f.get("propietario", ""), f.get("responsable", ""),
                f.get("codigo_interno", ""), f.get("version", ""), f.get("fecha_vigencia", ""),
                f.get("estado_documental", ""), f.get("actividades", ""), lectura, estado_rev])
        for tipo, mencion, seccion in normativa(doc):
            hojas["Normativa citada"].append([c, area, nombre, tipo, mencion, seccion])
        if lectura != "Digital" or c in revision:
            hojas["Revisión"].append([c, area, nombre, lectura, f.get("detalle_avisos", "") or
                                      ("muestra aleatoria" if c in revision else ""),
                                      "Pendiente" if pendiente or c not in revision else "Revisado", ""])
    for e in calcular_enlaces(corpus.meta):
        if es_general(e.origen):
            continue
        hojas["Cadena documental"].append([
            e.origen, _nombre_tipo(e.origen), corpus.meta[e.origen].get("departamento", ""), corpus.nombre(e.origen),
            e.citado, tipo_de_codigo_cliente(e.citado), e.destino, _nombre_tipo(e.destino) if e.destino else "",
            corpus.meta[e.destino].get("departamento", "") if e.destino else "",
            corpus.nombre(e.destino) if e.destino else "", e.via or "no está en el corpus"])
    part = calcular_participacion(corpus, procedimientos, detector)
    cruces = collections.defaultdict(set)
    for fp in part.filas:
        hojas["Participación"].append([fp.puesto.codigo, fp.puesto.nombre, fp.procedimiento,
                                       corpus.nombre(fp.procedimiento), _nombre_tipo(fp.procedimiento), fp.rol,
                                       fp.coincidencia, fp.evidencia])
        cruces[(fp.puesto.codigo, fp.procedimiento)].add(fp.rol)
    for rol, procs in part.sin_descriptivo.items():
        for p in sorted(procs):
            hojas["Participación"].append(["", rol, p, corpus.nombre(p), _nombre_tipo(p), "",
                                           "sin descriptivo en el corpus", ""])
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
    "Cadena documental": [("Código que cita", 14), ("Tipo", 14), ("Área", 22), ("Documento que cita", 34),
                          ("Código citado (literal)", 22), ("Tipo del código citado", 16),
                          ("Código en el corpus", 14), ("Tipo", 14), ("Área", 22), ("Documento citado", 34),
                          ("Cómo se unió", 18)],
    "Procedimientos": [("Código", 12), ("Tipo", 14), ("Área", 22), ("Procedimiento", 34), ("Propósito", 50),
                       ("Propietario", 24),
                       ("Responsable", 24), ("Código interno", 18), ("Versión", 9), ("Vigencia", 12),
                       ("Estado documental", 14), ("Actividades", 70), ("Calidad de lectura", 22),
                       ("Revisión visual", 14)],
    "Participación": [("Código del puesto", 14), ("Puesto", 34), ("Procedimiento", 14),
                      ("Nombre del procedimiento", 34), ("Tipo", 14), ("Rol", 18), ("Coincidencia", 22),
                      ("Evidencia (texto literal)", 80)],
    "Políticas y protocolos": [("Código", 12), ("Tipo", 12), ("Área", 22), ("Área propietaria", 22),
                               ("Alcance (literal)", 70), ("Versión", 9), ("Vigencia", 12),
                               ("Estado documental", 14), ("Documento", 34), ("Propósito", 50),
                               ("Propietario", 24), ("Responsable", 24), ("Código interno", 18),
                               ("Calidad de lectura", 22), ("Revisión visual", 14)],
    "Documentos generales": [("Código", 12), ("Tipo", 18), ("Documento", 40), ("Archivo original", 40),
                             ("Calidad de lectura", 22), ("Ubicación en el corpus", 22)],
    "Revisión": [("Código", 12), ("Área", 22), ("Documento", 34), ("Calidad de lectura", 22),
                 ("Motivo de la revisión", 70), ("Estado", 12), ("Observaciones del auditor", 50)],
}
VACIAS = {
    "Procedimientos": "El corpus todavía no tiene procedimientos ni protocolos. Al agregarlos (carpetas "
                      "Procedimientos y Protocolos) esta hoja y las de participación se llenan solas.",
    "Cadena documental": "Los documentos del corpus no citan códigos de otros documentos.",
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
    ("Cadena documental", "Cada código de documento que un documento cita, unido al documento del corpus que lo "
                          "tiene como código interno (igual o su final). Si no está en el corpus, queda marcado: "
                          "son los documentos que faltan para completar la cadena."),
    ("Procedimientos", "Un procedimiento (PRD) o protocolo (PRO) por fila, con su tipo, propietario, responsable, "
                       "versión y actividades."),
    ("Políticas y protocolos", "Una política (POL) o protocolo (PRO) por fila. «Área» es General si aplica a "
                               "varias áreas o a toda la empresa; «Área propietaria» es el área que lo emite, si "
                               "el documento la indica; «Alcance (literal)» es el texto de su sección de alcance."),
    ("Documentos generales", "Organigramas, indicadores, glosarios, mapas de procesos y otros documentos de "
                             "contexto (área GEN)."),
    ("Participación", "Qué puesto aparece en qué procedimiento o protocolo (con su tipo) y con qué rol (ejecuta, "
                      "aprueba, revisa…)."),
    ("Puestos x Procedimientos", "Matriz: filas = puestos, columnas = procedimientos y protocolos, celda = rol."),
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
    return sorted({f[1] for f in hojas["Puestos"]} | {f[2] for f in hojas["Procedimientos"]}
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


NOMBRES_CSV = {"Léeme": "leeme", "Resumen": "resumen", "Puestos": "puestos", "Funciones": "funciones",
               "Relaciones": "relaciones", "Perfil y requisitos": "perfil_requisitos",
               "Normativa citada": "normativa_citada", "Cadena documental": "cadena_documental",
               "Procedimientos": "procedimientos",
               "Políticas y protocolos": "politicas_protocolos", "Documentos generales": "documentos_generales",
               "Participación": "participacion", "Puestos x Procedimientos": "puestos_x_procedimientos",
               "Indicadores": "indicadores", "Revisión": "revision"}


def _nombre_csv(hoja):
    """Archivo CSV de una hoja: Puestos -> puestos.csv, Perfil y requisitos -> perfil_requisitos.csv."""
    return NOMBRES_CSV.get(hoja) and NOMBRES_CSV[hoja] + ".csv" \
        or re.sub(r"[^a-z0-9]+", "_", sin_acentos(hoja).lower()).strip("_") + ".csv"


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
    for nombre, cabecera, filas in todas:
        ruta = carpeta / _nombre_csv(nombre)
        escribir_csv_filas(ruta, cabecera, filas)
        rutas.append(ruta)
    return rutas


def escribir_matriz(raiz, destino=None):
    """Escribe en <raiz>/copilot/fuente-contexto/matriz/ matriz_organizacional.xlsx (requiere openpyxl) y un CSV
    por hoja (solo biblioteca estandar). ``raiz`` es salida_corpus. Devuelve la ruta del Excel."""
    corpus, hojas = datos_matriz(raiz)
    carpeta = rutas_publicadas(raiz / CARPETA_PUBLICADA).matriz
    exportar_csv(hojas, raiz, carpeta)
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise CorpusError("Falta openpyxl para escribir el Excel: python -m pip install openpyxl")
    destino = destino or carpeta / ARCHIVO_MATRIZ
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
