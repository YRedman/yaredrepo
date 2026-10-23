"""Lo que define la forma de la matriz: columnas y anchos de cada hoja, notas de hoja vacia, descripciones y CSV."""

import re

from ...comun.texto import sin_acentos

MAX_TEXTO_CELDA = 3000

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
COLUMNAS_RESUMEN = ["Área", "Puestos", "Leídos con OCR", "Sin texto", "Funciones", "Relaciones",
                    "Pendientes de revisión"]
NOMBRES_CSV = {"Léeme": "leeme", "Resumen": "resumen", "Puestos": "puestos", "Funciones": "funciones",
               "Relaciones": "relaciones", "Perfil y requisitos": "perfil_requisitos",
               "Normativa citada": "normativa_citada", "Cadena documental": "cadena_documental",
               "Procedimientos": "procedimientos",
               "Políticas y protocolos": "politicas_protocolos", "Documentos generales": "documentos_generales",
               "Participación": "participacion", "Puestos x Procedimientos": "puestos_x_procedimientos",
               "Indicadores": "indicadores", "Revisión": "revision"}


def nombre_csv(hoja):
    """Archivo CSV de una hoja: Puestos -> puestos.csv, Perfil y requisitos -> perfil_requisitos.csv."""
    return NOMBRES_CSV.get(hoja) and NOMBRES_CSV[hoja] + ".csv" \
        or re.sub(r"[^a-z0-9]+", "_", sin_acentos(hoja).lower()).strip("_") + ".csv"


def cabecera_y_filas(nombre, filas):
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
