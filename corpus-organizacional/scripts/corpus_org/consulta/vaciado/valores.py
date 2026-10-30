"""Normaliza lo que la gente escribe en el K4 a los valores que acepta la plantilla.

Cada funcion devuelve ``(valor, nota)``: ``valor`` es None cuando no se puede interpretar con seguridad (la celda se deja
vacia y el dato va a la hoja de puntos a validar) y ``nota`` explica una interpretacion que el revisor debe conocer.
"""

import re

from ...comun.texto import norm
from .xlsx import serie_a_fecha

SIN_DATO = {"", "n/d", "nd", "n/a", "na", "no aplica", "no aplica.", "ninguno", "ninguna", "-", "—", "s/d", "pendiente"}
MINUTOS_POR_DIA_HORAS = 24 * 60

FRECUENCIAS = ["Diaria", "Semanal", "Quincenal", "Mensual", "Trimestral", "Semestral", "Anual", "Eventual"]
EVENTOS_POR_ANIO = {"Bimestral": 6}                  # periodos que la plantilla no tiene: se expresan en otro periodo
_SINONIMOS_FRECUENCIA = {
    "diaria": "Diaria", "diario": "Diaria", "diariamente": "Diaria", "cada dia": "Diaria", "todos los dias": "Diaria",
    "semanal": "Semanal", "semanalmente": "Semanal", "cada semana": "Semanal",
    "quincenal": "Quincenal", "quincenalmente": "Quincenal",
    "mensual": "Mensual", "mensualmente": "Mensual", "cada mes": "Mensual",
    "bimestral": "Bimestral", "bimestralmente": "Bimestral",
    "trimestral": "Trimestral", "trimestralmente": "Trimestral",
    "semestral": "Semestral", "semestralmente": "Semestral",
    "anual": "Anual", "anualmente": "Anual", "cada ano": "Anual",
    "eventual": "Eventual", "eventualmente": "Eventual", "ocasional": "Eventual",
}
# lo que se escribe como frecuencia pero en realidad es «cuando surge»: en la plantilla es «Eventual»
_COMO_EVENTUAL = {"a demanda", "por evento", "unica", "por demanda", "segun demanda"}
ESCOLARIDADES = ["Primaria", "Secundaria", "Técnica", "Universitaria", "Especialización", "Maestría", "Doctorado"]
_SINONIMOS_ESCOLARIDAD = (
    ("doctor", "Doctorado"), ("phd", "Doctorado"), ("maestr", "Maestría"), ("master", "Maestría"), ("mba", "Maestría"),
    ("posgrado", "Especialización"), ("postgrado", "Especialización"), ("especializ", "Especialización"),
    ("diplomado", "Especialización"), ("licenciatura", "Universitaria"), ("universit", "Universitaria"),
    ("grado", "Universitaria"), ("ingenier", "Universitaria"), ("tecnic", "Técnica"), ("tecnolog", "Técnica"),
    ("bachiller", "Secundaria"), ("secundaria", "Secundaria"), ("primaria", "Primaria"))
MODALIDADES = ["Presencial", "Híbrido", "Remoto", "Campo"]
NIVELES = ["Básico", "Intermedio", "Avanzado", "Experto"]
TIPOS_COMPETENCIA = ["Técnica", "Conductual", "Liderazgo", "Calidad/SGQ", "Digital", "Regulatoria"]
TIPOS_PROCESO = ["Core", "Soporte", "Gobierno/Control"]
AUTOMATIZACIONES = ["Manual", "Semiautomatizada", "Automatizada"]


def _texto(valor):
    return " ".join(str(valor).replace("\xa0", " ").split())


def sin_dato(valor):
    return valor is None or (isinstance(valor, str) and norm(valor) in SIN_DATO)


def _numero(texto):
    """float de '12', '12,5', '1.5' o None."""
    t = texto.strip().replace(",", ".")
    return float(t) if re.fullmatch(r"-?\d+(\.\d+)?", t) else None


def minutos(celda):
    """Minutos de una celda de tiempo: 480, '45 min', '2 h', '1:30', '1h30', '20-30' (promedio). 0 = sin dato."""
    valor = celda.valor if hasattr(celda, "valor") else celda
    if sin_dato(valor):
        return None, None
    if isinstance(valor, bool):
        return None, "valor no numérico"
    if isinstance(valor, (int, float)):
        if getattr(celda, "es_hora", False):
            return round(valor * MINUTOS_POR_DIA_HORAS, 2), f"hora escrita como h:mm; se leyó como {valor * 24:g} h"
        if getattr(celda, "es_fecha", False):
            return None, f"Excel lo convirtió en la fecha {serie_a_fecha(valor):%d/%m/%Y}"
        return (None, "tiempo 0 (= sin dato)") if valor == 0 else (float(valor), None)
    t = norm(_texto(valor))
    m = re.fullmatch(r"(\d+):(\d{1,2})(?::\d{1,2})?", t)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2)), f"«{valor}» leído como horas:minutos"
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*h(?:ora|oras|rs|r)?\s*(?:y\s*)?(\d+)?\s*(?:min|minutos|m)?", t)
    if m:
        horas = float(m.group(1).replace(",", ".")) * 60
        return horas + (int(m.group(2)) if m.group(2) else 0), f"«{valor}» convertido a minutos"
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(?:a|-|–|—|y)\s*(\d+(?:[.,]\d+)?)\s*(h|hora|horas|min|minutos|m)?", t)
    if m:
        a, b = (float(g.replace(",", ".")) for g in m.groups()[:2])
        factor = 60 if (m.group(3) or "").startswith("h") else 1
        return (a + b) / 2 * factor, f"rango «{valor}» reemplazado por su promedio"
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(?:min|mins|minutos|minuto|m)?", t)
    if m:
        v = float(m.group(1).replace(",", "."))
        return (None, "tiempo 0 (= sin dato)") if v == 0 else (v, None)
    return None, f"no se pudo interpretar el tiempo «{valor}»"


def volumen(celda):
    """Cantidad de veces: 3, '2,5', '2-4' (promedio). Una fecha es un rango que Excel convirtio: no se interpreta."""
    valor = celda.valor if hasattr(celda, "valor") else celda
    if sin_dato(valor):
        return None, None
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if getattr(celda, "es_fecha", False):
            return None, f"Excel lo convirtió en la fecha {serie_a_fecha(valor):%d/%m/%Y} (¿un rango como «2-4»?)"
        return float(valor), None
    t = norm(_texto(valor))
    n = _numero(t)
    if n is not None:
        return n, None
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(?:a|-|–|—|y)\s*(\d+(?:[.,]\d+)?)", t)
    if m:
        a, b = (float(g.replace(",", ".")) for g in m.groups())
        return (a + b) / 2, f"rango «{valor}» reemplazado por su promedio"
    return None, f"no se pudo interpretar el volumen «{valor}»"


def retrabajo(celda):
    """Fraccion de retrabajo (0.1 = 10 %). Un numero mayor que 1 podria ser minutos: no se interpreta."""
    valor = celda.valor if hasattr(celda, "valor") else celda
    if sin_dato(valor):
        return None, None
    if isinstance(valor, str):
        t = norm(_texto(valor))
        m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*%", t)
        if m:
            return float(m.group(1).replace(",", ".")) / 100, None
        valor = _numero(t)
        if valor is None:
            return None, f"no se pudo interpretar el retrabajo «{celda.valor if hasattr(celda, 'valor') else celda}»"
    if getattr(celda, "es_fecha", False):
        return None, "Excel lo convirtió en una fecha"
    if 0 <= valor <= 1:
        return float(valor), None
    return None, f"retrabajo {valor:g} es mayor que 1: ¿son minutos? La plantilla espera una fracción (0.1 = 10 %)"


def de_lista(valor, lista, sinonimos=None):
    """El valor de ``lista`` que corresponde al texto (sin acentos ni mayusculas); None si no calza."""
    if sin_dato(valor) or not isinstance(valor, str):
        return None
    t = norm(_texto(valor))
    for opcion in lista:
        if norm(opcion) == t:
            return opcion
    if sinonimos:
        for clave, opcion in sinonimos.items() if isinstance(sinonimos, dict) else sinonimos:
            if t == clave or (len(clave) > 4 and t.startswith(clave)):
                return opcion
    return None


def frecuencia(valor):
    """(periodo, nota): uno de FRECUENCIAS, o 'Bimestral' (que la plantilla no tiene), o None."""
    if sin_dato(valor) or not isinstance(valor, str):
        return None, None
    t = norm(_texto(valor))
    if t in _COMO_EVENTUAL:
        return "Eventual", f"«{valor}» se registró como «Eventual»"
    return _SINONIMOS_FRECUENCIA.get(t), None


def periodo_para_plantilla(periodo, eventos):
    """Convierte un periodo que la plantilla no tiene en uno equivalente. Bimestral: 6 veces al ano.

    Devuelve (periodo, eventos, nota); las horas por mes que calcula la plantilla son las mismas.
    """
    if periodo in EVENTOS_POR_ANIO:
        n = EVENTOS_POR_ANIO[periodo]
        return "Anual", (eventos * n if eventos is not None else None), f"{periodo} convertido a Anual × {n} (mismas horas)"
    return periodo, eventos, None


def escolaridad(valor):
    if sin_dato(valor) or not isinstance(valor, str):
        return None
    t = norm(_texto(valor))
    for raiz, opcion in _SINONIMOS_ESCOLARIDAD:
        if raiz in t:
            return opcion
    return None


def modalidad(valor):
    if sin_dato(valor) or not isinstance(valor, str):
        return None
    t = norm(_texto(valor))
    for raiz, opcion in (("hibrid", "Híbrido"), ("presencial", "Presencial"), ("remot", "Remoto"), ("teletrabajo", "Remoto"),
                         ("campo", "Campo")):
        if t.startswith(raiz):
            return opcion
    return None


def nivel(valor):
    return de_lista(valor, NIVELES)


def tipo_competencia(valor):
    return de_lista(valor, TIPOS_COMPETENCIA, {"tecnica": "Técnica", "conductual": "Conductual", "sgq": "Calidad/SGQ",
                                              "calidad": "Calidad/SGQ"})


def tipo_proceso(valor):
    return de_lista(valor, TIPOS_PROCESO, {"gobierno": "Gobierno/Control", "control": "Gobierno/Control"})


def automatizacion(valor):
    return de_lista(valor, AUTOMATIZACIONES)


def entero_o_texto(valor):
    """Para mostrar un numero sin '.0'."""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)
