"""Reglas sencillas para proponer lo que el K4 no trae y que la plantilla pide (Valor, cliente, impacto, prioridad…).

Cada funcion devuelve ``(valor, motivo)``. El valor siempre es una opcion de la lista de la plantilla; el motivo explica la regla y
va en la nota de la celda, que se rotula «Inferido» y se escribe en letra morada para que el consultor la valide a mano. No son
conclusiones: son un punto de partida para no dejar la celda vacia.
"""

import re

from ...comun.texto import norm

PALABRAS_DE_DESPERDICIO = ("reproces", "retrabaj", "rehac", "reenvi", "duplic", "esperar", "espera de", "repetir", "corregir errores")
PALABRAS_NECESARIAS = ("report", "control", "audit", "cumpl", "normativ", "regulat", "aprob", "autoriz", "firm", "archiv", "document", "legal",
                       "seguimiento", "monitore", "revis", "verific", "concili", "informe", "supervis")
PALABRAS_DE_GOBIERNO = ("aprob", "autoriz", "audit", "cumplimiento", "normativ", "politic", "supervis", "gobern", "regulat", "estrateg",
                        "direccion", "lineamiento", "comite")
PALABRAS_DE_SOPORTE = ("administr", "registr", "archiv", "soporte", "apoyo", "logistic", "contab", "factur", "nomina", "tecnolog",
                       "mantenimiento", "limpieza", "compras", "tesoreria", "recursos humanos", "capacitacion")
PALABRAS_EXTERNAS = ("cliente", "paciente", "proveedor", "usuario", "institucion", "ministerio", "gobierno", "licitacion", "hospital",
                     "aseguradora", "afiliado", "distribuidor", "regulador", "ente ")
PALABRAS_INTERNAS = ("area", "equipo", "gerencia", "direccion", "colaborador", "interno", "comite", "jefe", "departamento", "personal")
PALABRAS_SIN_PESO = {"para", "como", "desde", "hasta", "sobre", "entre", "segun", "cada", "este", "esta", "estos", "estas", "otros", "otras",
                     "todos", "todas", "mediante", "dentro", "puesto", "area", "areas", "proceso", "procesos", "actividad", "actividades",
                     "gestion", "realizar", "ejecutar"}
PUNTOS = {"Bajo": 1, "Medio": 2, "Alto": 3}
HORAS_PARA_AUTOMATIZAR = 10.0
UMBRAL_IMPACTO_ALTO, UMBRAL_IMPACTO_MEDIO = 0.15, 0.05


def _contiene(texto, palabras):
    t = norm(texto or "")
    return next((p for p in palabras if p in t), None)


def tipo_de_proceso(texto):
    """Core, Soporte o Gobierno/Control a partir de las palabras de la actividad."""
    p = _contiene(texto, PALABRAS_DE_GOBIERNO)
    if p:
        return "Gobierno/Control", f"el texto menciona «{p}…» (actividad de gobierno o control)"
    p = _contiene(texto, PALABRAS_DE_SOPORTE)
    if p:
        return "Soporte", f"el texto menciona «{p}…» (actividad de apoyo)"
    return "Core", "sin palabras de apoyo ni de control: se asume una actividad del proceso principal (Core)"


def valor_de_actividad(texto, tipo_proceso, retrabajo=None):
    """VA, NVA-N o NVA: desperdicio si el texto lo dice, necesaria si es control o apoyo, VA si es del proceso principal."""
    p = _contiene(texto, PALABRAS_DE_DESPERDICIO)
    if p:
        return "NVA", f"el texto menciona «{p}…» (reproceso o espera)"
    p = _contiene(texto, PALABRAS_NECESARIAS)
    if p or tipo_proceso == "Gobierno/Control":
        return "NVA-N", f"es una actividad de control, seguimiento o cumplimiento{f' («{p}…»)' if p else ''}: necesaria pero no agrega valor directo"
    if tipo_proceso == "Soporte":
        return "NVA-N", "actividad de apoyo (Soporte): necesaria, sin valor directo para el cliente"
    return "VA", "actividad del proceso principal (Core) sin palabras de control ni de desperdicio"


def cliente_de(texto):
    """Interno, Externo o Mixto segun a quien menciona la actividad."""
    externo, interno = _contiene(texto, PALABRAS_EXTERNAS), _contiene(texto, PALABRAS_INTERNAS)
    if externo and interno:
        return "Mixto", f"menciona «{externo}…» y «{interno}…»"
    if externo:
        return "Externo", f"menciona «{externo}…»"
    if interno:
        return "Interno", f"menciona «{interno}…»"
    return "Interno", "sin señales de un cliente externo: se asume interno"


def _palabras(texto):
    return {p for p in re.findall(r"[a-z]{5,}", norm(texto or "")) if p not in PALABRAS_SIN_PESO}


def coincidencia(texto, candidatos, minimo=2):
    """(candidato, palabras en comun) con mas palabras en comun con ``texto`` (al menos ``minimo``); None si ninguno."""
    base = _palabras(texto)
    mejor = None
    for c in candidatos:
        comunes = base & _palabras(c)
        if len(comunes) >= minimo and (mejor is None or len(comunes) > len(mejor[1])):
            mejor = (c, comunes)
    return (mejor[0], sorted(mejor[1])) if mejor else None


def impacto_de(horas, total_horas):
    """Bajo, Medio o Alto segun la parte de la carga mensual del puesto que representa la actividad."""
    if not total_horas or not horas:
        return "Medio", "no hay horas calculadas para medir el peso de la actividad"
    parte = horas / total_horas
    nivel = "Alto" if parte >= UMBRAL_IMPACTO_ALTO else "Medio" if parte >= UMBRAL_IMPACTO_MEDIO else "Bajo"
    return nivel, f"la actividad es el {parte:.0%} de la carga mensual del puesto ({horas:.1f} h)"


def probabilidad_de(retrabajo):
    if retrabajo:
        return "Alto", f"ya ocurre: el K4 declara retrabajo de {retrabajo:.0%}"
    return "Medio", "el K4 no dice con qué frecuencia ocurre el riesgo"


def accion_de(valor, automatizacion, horas, retrabajo):
    """Eliminar, Simplificar, Estandarizar, Automatizar o Mantener segun el valor de la actividad y su forma de ejecución."""
    if valor == "NVA":
        return "Eliminar", "la actividad no agrega valor ni es necesaria (NVA)"
    if retrabajo:
        return "Estandarizar", f"hay retrabajo de {retrabajo:.0%}: estandarizar el método reduce los errores"
    if automatizacion == "Manual" and (horas or 0) >= HORAS_PARA_AUTOMATIZAR:
        return "Automatizar", f"es manual y consume {horas:.1f} h al mes"
    if valor == "NVA-N":
        return "Simplificar", "es necesaria pero no agrega valor directo (NVA-N): conviene simplificarla"
    return "Mantener", "no hay señales de desperdicio ni de retrabajo"


def esfuerzo_de(accion):
    nivel = {"Eliminar": "Bajo", "Simplificar": "Medio", "Estandarizar": "Medio", "Redistribuir": "Medio", "Automatizar": "Alto",
             "Centralizar": "Alto", "Mantener": "Muy bajo"}[accion]
    return nivel, f"esfuerzo típico de la acción «{accion}»"


def prioridad_de(impacto, probabilidad):
    puntos = PUNTOS[impacto] + PUNTOS[probabilidad]
    nivel = "Alta" if puntos >= 5 else "Media" if puntos == 4 else "Baja"
    return nivel, f"impacto {impacto} y probabilidad {probabilidad}"


def tipo_de_competencia(nombre):
    """Tipo de competencia (lista de la plantilla) por las palabras del nombre; Técnica si no hay ninguna."""
    for tipo, palabras in (("Conductual", ("liderazgo", "comunic", "equipo", "orden", "negociaci", "adaptab", "empat", "proactiv", "responsab")),
                           ("Calidad/SGQ", ("calidad", "iso", "sgq", "mejora continua")),
                           ("Digital", ("digital", "excel", "sistema", "tecnolog", "software", "datos")),
                           ("Regulatoria", ("legal", "legisl", "ley ", "normativ", "regulat", "cumplimiento"))):
        p = _contiene(nombre, palabras)
        if p:
            return tipo, f"el nombre de la competencia menciona «{p}…»"
    return "Técnica", "sin palabras que indiquen otro tipo: se asume una competencia técnica"


def nivel_del_cargo(titulo):
    """Categoría del cargo (texto libre) según la primera palabra clave del título; None si no hay."""
    for palabra in re.findall(r"[a-z]+", norm(titulo or "")):
        for categoria, claves in (("Directivo", ("director", "directora", "vicepresidente", "vicepresidenta", "presidente", "presidenta", "gerente")),
                                  ("Mando medio", ("jefe", "jefa", "coordinador", "coordinadora", "supervisor", "supervisora", "encargado", "encargada")),
                                  ("Profesional / operativo", ("analista", "asistente", "auxiliar", "tecnico", "tecnica", "asesor", "asesora",
                                                              "especialista", "ejecutivo", "ejecutiva", "operador", "operadora"))):
            if palabra in claves:
                return categoria, f"el cargo dice «{palabra}»"
    return None
