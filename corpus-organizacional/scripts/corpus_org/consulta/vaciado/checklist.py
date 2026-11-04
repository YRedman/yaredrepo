"""Checklist de completitud y calidad: ¿el K4 presentado trae lo necesario para pasarse a la plantilla metodologica?

Por formulario se evaluan nueve criterios (Si / Parcial / No / N/A), el % de completitud, la carga laboral (horas al mes segun la
formula de la plantilla y una alerta frente a la capacidad) y dos notas de calidad de 1 a 5 (coherencia entre las funciones y el nivel del
puesto, y especificidad). La calidad es una **estimacion heuristica** (palabras clave y conteos, sin interpretar el texto): sirve para
priorizar la revision del consultor, no para calificar a la persona.
"""

import re
from dataclasses import dataclass, field

from ...comun.texto import norm
from . import calculo, valores
from .k4 import HOJAS, K4

SI, PARCIAL, NO, NA = "Sí", "Parcial", "No", "N/A"
PESO = {SI: 1.0, PARCIAL: 0.5, NO: 0.0}
UMBRAL_LISTO = 0.80                  # % de completitud desde el cual el formulario esta listo
UMBRAL_MINIMO = 0.50                 # por debajo, no se debe pasar a la plantilla
LISTO, CON_RESERVAS, NO_LISTO = "Listo", "Con reservas", "No listo"
CARGA_ALTA, CARGA_LIMITE, CARGA_BAJA = 1.20, 1.00, 0.60       # horas / capacidad
MINIMO_FUNCIONES = 3
MINIMO_RELACIONES = 3

# (clave de hoja del K4, nombre del criterio tal como se muestra)
CRITERIOS = (("general", "Datos generales (reporta a, área, supervisados)"), ("proposito", "Objetivo / propósito del puesto"),
             ("responsabilidades", "Funciones principales"), ("actividades", "Frecuencia y tiempo por función"),
             ("responsabilidades_nivel", "Responsabilidades y nivel de decisión"), ("relaciones", "Relaciones internas / externas"),
             ("educacion", "Formación y experiencia"), ("competencias", "Competencias y conocimientos técnicos"),
             ("kpis", "Indicadores de desempeño (KPIs)"))
CRITICOS = ("Datos generales", "Funciones principales", "Frecuencia y tiempo")       # un «No» aqui deja el formulario «No listo»

NIVELES_DEL_PUESTO = (
    (3, ("director", "directora", "gerente", "vicepresidente", "vicepresidenta", "presidente", "presidenta", "subdirector", "subdirectora", "ceo")),
    (2, ("jefe", "jefa", "coordinador", "coordinadora", "supervisor", "supervisora", "lider", "encargado", "encargada", "responsable")),
    (1, ("analista", "asistente", "auxiliar", "tecnico", "tecnica", "operador", "operadora", "asesor", "asesora", "ejecutivo", "ejecutiva",
         "especialista", "secretaria", "mensajero", "digitador", "digitadora", "cajero", "cajera", "vendedor", "vendedora")))
VERBOS_ESTRATEGICOS = ("defin", "dirig", "aprob", "decid", "planific", "establec", "lider", "represent", "negoci", "autoriz", "formul",
                       "gobern", "articul", "orient")
VERBOS_OPERATIVOS = ("digit", "registr", "archiv", "transcrib", "ingres", "escane", "imprim", "envi", "copi", "tramit", "llen", "clasific",
                     "foli", "fotocopi", "recib", "entreg", "atend")
FRASES_GENERICAS = ("otras funciones", "demas funciones", "las demas que", "segun se requiera", "segun sea necesario", "cuando se requiera",
                    "tareas asignadas", "labores asignadas", "funciones asignadas", "apoyo en general", "dar soporte", "apoyar en", "gestion general",
                    "y otros", "etc", "varios", "diversas", "lo que se requiera")


@dataclass
class Criterio:
    nombre: str
    estado: str
    detalle: str = ""


@dataclass
class Checklist:
    archivo: str = ""
    puesto: str = ""
    criterios: list = field(default_factory=list)
    porcentaje: float = 0.0
    horas_mes: float = 0.0
    capacidad: float = 0.0
    alerta: str = ""
    coherencia: int = 0
    especificidad: int = 0
    promedio: float = 0.0
    detalle_calidad: list = field(default_factory=list)
    veredicto: str = ""
    motivo_veredicto: str = ""

    def criterio(self, prefijo):
        return next((c for c in self.criterios if c.nombre.startswith(prefijo)), None)


def _dato(fila, campo):
    """Texto del campo, o None si esta vacio o es un pendiente («VALIDAR: …») o un «sin dato»."""
    t = fila.texto(campo) if fila is not None else None
    if t is None or valores.es_validar(t) or norm(t) in ("n/d", "nd", "pendiente", "-", "—", "s/d"):
        return None
    return t


def _falta(k4, clave):
    return HOJAS[clave][0] in k4.hojas_faltantes


def _enumerar(faltan):
    return "falta: " + ", ".join(faltan)


# -- criterios ----------------------------------------------------------------------------------------------------------

def _datos_generales(k4):
    if _falta(k4, "general"):
        return NA, "la hoja no está en el formulario"
    f = (k4.filas("general") or [None])[0]
    if f is None:
        return NO, "la hoja «8. Información General» no tiene registro"
    tiene = {"reporta a": _dato(f, "reporta"), "área": _dato(f, "area"),
             "supervisados": _dato(f, "personas") or _dato(f, "puestos_cargo")}
    faltan = [k for k, v in tiene.items() if not v]
    return (SI, "") if not faltan else ((PARCIAL if len(faltan) < 3 else NO), _enumerar(faltan))


def _proposito(k4):
    if _falta(k4, "proposito"):
        return NA, "la hoja no está en el formulario"
    f = (k4.filas("proposito") or [None])[0]
    proposito = _dato(f, "proposito")
    complemento = _dato(f, "objetivos") or _dato(f, "funcion_clave")
    if proposito and complemento:
        return SI, ""
    if proposito or complemento:
        return PARCIAL, _enumerar(["objetivos o función clave"] if proposito else ["propósito principal"])
    return NO, "sin propósito ni objetivos"


def _funciones(k4):
    if _falta(k4, "responsabilidades") and _falta(k4, "actividades"):
        return NA, "las hojas no están en el formulario"
    n_resp = sum(1 for f in k4.filas("responsabilidades") if _dato(f, "funcion"))
    n_act = sum(1 for f in k4.filas("actividades") if _dato(f, "actividad"))
    if n_resp >= MINIMO_FUNCIONES:
        return SI, f"{n_resp} funciones, {n_act} actividades"
    if n_resp or n_act:
        return PARCIAL, f"{n_resp} funciones y {n_act} actividades (se esperan al menos {MINIMO_FUNCIONES} funciones)"
    return NO, "sin funciones ni actividades"


def _frecuencia_y_tiempo(k4):
    if _falta(k4, "actividades"):
        return NA, "la hoja no está en el formulario"
    actividades = [f for f in k4.filas("actividades") if _dato(f, "actividad")]
    if not actividades:
        return NO, "sin actividades"
    completas = 0
    for f in actividades:
        t = valores.minutos(f.celda("tiempo"))[0] if f.celda("tiempo") else None
        v = valores.volumen(f.celda("volumen"))[0] if f.celda("volumen") else None
        p = valores.frecuencia(f.texto("periodo"))[0]
        completas += bool(t and v is not None and p)
    detalle = f"{completas} de {len(actividades)} actividades con tiempo, volumen y período"
    if completas == len(actividades) or completas / len(actividades) >= 0.9:
        return SI, detalle
    return (PARCIAL if completas else NO), detalle


def _nivel_de_decision(k4):
    if _falta(k4, "responsabilidades"):
        return NA, "la hoja no está en el formulario"
    funciones = [f for f in k4.filas("responsabilidades") if _dato(f, "funcion")]
    if not funciones:
        return NO, "sin funciones"
    con_nivel = sum(1 for f in funciones if _dato(f, "nivel"))
    detalle = f"{con_nivel} de {len(funciones)} funciones con nivel de responsabilidad"
    return (SI if con_nivel == len(funciones) else PARCIAL if con_nivel else NO), detalle


def _relaciones(k4):
    if _falta(k4, "relaciones"):
        return NA, "la hoja no está en el formulario"
    filas = [f for f in k4.filas("relaciones") if (_dato(f, "area") or _dato(f, "contacto")) and (_dato(f, "motivo") or _dato(f, "recibida"))]
    tipos = " ".join(norm(f.texto("tipo") or "") for f in filas)
    internas, externas = "intern" in tipos, "extern" in tipos
    detalle = f"{len(filas)} relaciones completas" + (" (internas y externas)" if internas and externas else "")
    if len(filas) >= MINIMO_RELACIONES or (internas and externas and len(filas) >= 2):
        return SI, detalle
    return (PARCIAL, detalle) if filas else (NO, "sin relaciones completas")


def _formacion_y_experiencia(k4):
    if _falta(k4, "educacion"):
        return NA, "la hoja no está en el formulario"
    filas = k4.filas("educacion")
    academica = any(valores.escolaridad(f.texto("nivel")) for f in filas)
    texto = norm(" ".join(f.texto(c) or "" for f in filas for c in ("nivel", "area", "certificaciones")))
    experiencia = bool(re.search(r"experiencia|\banos?\b|\baños?\b", texto))
    if academica and experiencia:
        return SI, ""
    if academica or experiencia:
        return PARCIAL, _enumerar(["experiencia"] if academica else ["nivel académico"])
    return NO, "sin formación ni experiencia"


def _competencias(k4):
    if _falta(k4, "competencias"):
        return NA, "la hoja no está en el formulario"
    filas = [f for f in k4.filas("competencias") if _dato(f, "competencia")]
    if not filas:
        return NO, "sin competencias"
    tipos = {valores.tipo_competencia(f.texto("tipo")) for f in filas}
    sin_nivel = sum(1 for f in filas if not valores.nivel(f.texto("nivel")))
    faltan = [t for t in ("Técnica", "Conductual") if t not in tipos]
    if not faltan and not sin_nivel:
        return SI, f"{len(filas)} competencias"
    partes = [f"sin competencias de tipo {', '.join(t.lower() for t in faltan)}" if faltan else "", f"{sin_nivel} sin nivel" if sin_nivel else ""]
    return PARCIAL, "; ".join(p for p in partes if p)


def _kpis(k4):
    if _falta(k4, "proposito"):
        return NA, "la hoja no está en el formulario"
    f = (k4.filas("proposito") or [None])[0]
    texto = _dato(f, "resultados")
    if not texto:
        return NO, "sin resultados esperados ni indicadores"
    items = [x for x in re.split(r"[\n;•·]+|\s-\s", texto) if len(x.strip()) > 3]
    return (SI, f"{len(items)} indicadores") if len(items) >= 2 else (PARCIAL, "un solo indicador")


EVALUADORES = {"general": _datos_generales, "proposito": _proposito, "responsabilidades": _funciones, "actividades": _frecuencia_y_tiempo,
               "responsabilidades_nivel": _nivel_de_decision, "relaciones": _relaciones, "educacion": _formacion_y_experiencia,
               "competencias": _competencias, "kpis": _kpis}


# -- carga laboral ------------------------------------------------------------------------------------------------------

def horas_estimadas(k4, dias_mes=calculo.DIAS_POR_MES):
    """Horas al mes del puesto con la misma formula y las mismas interpretaciones del K4 que usa el vaciado."""
    total = 0.0
    for f in k4.filas("actividades"):
        t = valores.minutos(f.celda("tiempo"))[0] if f.celda("tiempo") else None
        v = valores.volumen(f.celda("volumen"))[0] if f.celda("volumen") else None
        periodo = valores.frecuencia(f.texto("periodo"))[0]
        retrabajo = valores.retrabajo(f.celda("retrabajo"))[0] if f.celda("retrabajo") else None
        indirecto = valores.minutos(f.celda("indirecto"))[0] if f.celda("indirecto") else None
        periodo_final, eventos, _ = valores.periodo_para_plantilla(periodo, v)
        dedicacion = (min(1.0, indirecto / t) if indirecto and t else 1.0) if t is not None else None
        total += calculo.horas_mes(t, 0, eventos, periodo_final, retrabajo, dedicacion, dias_mes)
    return total


def alerta_de_carga(horas, capacidad):
    if not horas:
        return "Sin datos"
    razon = horas / capacidad
    if razon > CARGA_ALTA:
        etiqueta = "Alta: sobrecarga"
    elif razon > CARGA_LIMITE:
        etiqueta = "Media: al límite"
    elif razon < CARGA_BAJA:
        etiqueta = "Baja: subutilización"
    else:
        etiqueta = "Sin alerta"
    return f"{etiqueta} ({razon:.0%} de la capacidad)"


# -- calidad (heuristica) -----------------------------------------------------------------------------------------------

def _nivel_del_puesto(titulo):
    """3 directivo, 2 jefatura, 1 operativo según la primera palabra clave del cargo; None si no hay ninguna."""
    for palabra in re.findall(r"[a-z]+", norm(titulo or "")):
        for nivel, claves in NIVELES_DEL_PUESTO:
            if palabra in claves:
                return nivel
    return None


def _verbo(texto):
    primera = (re.findall(r"[a-z]+", norm(texto or "")) or [""])[0]
    if primera.startswith(VERBOS_ESTRATEGICOS):
        return "estrategico"
    if primera.startswith(VERBOS_OPERATIVOS):
        return "operativo"
    return None


def _textos_de_trabajo(k4):
    funciones = [f.texto("funcion") for f in k4.filas("responsabilidades") if f.texto("funcion")]
    actividades = [f.texto("actividad") for f in k4.filas("actividades") if f.texto("actividad")]
    return funciones + actividades


def coherencia(k4):
    """(1 a 5, razones): ¿lo que hace el puesto corresponde a su nivel? Se compara el tipo de verbos con el cargo y el nivel de responsabilidad."""
    general = (k4.filas("general") or [None])[0]
    nivel = _nivel_del_puesto(general.texto("puesto") if general else "")
    verbos = [v for v in (_verbo(t) for t in _textos_de_trabajo(k4)) if v]
    niveles_resp = [norm(f.texto("nivel") or "") for f in k4.filas("responsabilidades") if f.texto("nivel")]
    if nivel is None and not verbos:
        return 3, ["sin señales suficientes (cargo no reconocido y verbos sin clasificar): nota neutra"]
    puntaje, razones = 5, []
    if verbos:
        est, ope = verbos.count("estrategico") / len(verbos), verbos.count("operativo") / len(verbos)
        if nivel == 3 and ope >= 0.5:
            puntaje, razones = puntaje - 3, razones + [f"cargo directivo con {ope:.0%} de funciones operativas"]
        elif nivel == 3 and ope >= 0.3:
            puntaje, razones = puntaje - 1, razones + [f"cargo directivo con {ope:.0%} de funciones operativas"]
        if nivel == 1 and est >= 0.5:
            puntaje, razones = puntaje - 3, razones + [f"cargo operativo con {est:.0%} de funciones estratégicas"]
        elif nivel == 1 and est >= 0.3:
            puntaje, razones = puntaje - 1, razones + [f"cargo operativo con {est:.0%} de funciones estratégicas"]
        if nivel == 2 and ope >= 0.7:
            puntaje, razones = puntaje - 2, razones + [f"jefatura con {ope:.0%} de funciones operativas"]
    if niveles_resp:
        altos = sum(1 for n in niveles_resp if n.startswith("alto")) / len(niveles_resp)
        bajos = sum(1 for n in niveles_resp if n.startswith("bajo")) / len(niveles_resp)
        if nivel == 1 and altos >= 0.5:
            puntaje, razones = puntaje - 1, razones + [f"cargo operativo con {altos:.0%} de funciones de responsabilidad alta"]
        if nivel == 3 and bajos >= 0.5:
            puntaje, razones = puntaje - 1, razones + [f"cargo directivo con {bajos:.0%} de funciones de responsabilidad baja"]
    return max(1, puntaje), razones or ["el tipo de funciones y el nivel de responsabilidad son coherentes con el cargo"]


def especificidad(k4):
    """(1 a 5, razones): ¿las funciones y actividades son concretas (cifras, siglas, descripcion con detalle) o genericas?"""
    elementos = [(f.texto("actividad") or "") + " " + (f.texto("descripcion") or "") for f in k4.filas("actividades") if f.texto("actividad")]
    elementos += [f.texto("funcion") or "" for f in k4.filas("responsabilidades") if f.texto("funcion")]
    if not elementos:
        return 1, ["sin funciones ni actividades que evaluar"]
    concretos = sum(1 for t in elementos if len(t.split()) >= 8 or re.search(r"\d", t) or re.search(r"\b[A-ZÁÉÍÓÚ]{2,}\b", t))
    razon = concretos / len(elementos)
    puntaje = 5 if razon >= 0.8 else 4 if razon >= 0.6 else 3 if razon >= 0.4 else 2 if razon >= 0.2 else 1
    razones = [f"{concretos} de {len(elementos)} funciones o actividades con detalle concreto (8 o más palabras, cifras o siglas)"]
    genericas = [t for t in elementos if any(frase in norm(t) for frase in FRASES_GENERICAS)]
    if len(genericas) >= 2:
        puntaje = max(1, puntaje - 1)
        razones.append(f"{len(genericas)} con frases genéricas («apoyar en…», «otras funciones», «etc.»)")
    return puntaje, razones


# -- evaluacion ---------------------------------------------------------------------------------------------------------

def evaluar(k4: K4, archivo="", dias_mes=calculo.DIAS_POR_MES, horas_mes=None):
    """Checklist de un K4. ``horas_mes``: si el vaciado ya las calculo (con las actividades de la entrevista), se usan esas."""
    c = Checklist(archivo=archivo)
    general = (k4.filas("general") or [None])[0]
    c.puesto = (general.texto("puesto") if general else "") or ""
    for clave, nombre in CRITERIOS:
        estado, detalle = EVALUADORES[clave](k4)
        c.criterios.append(Criterio(nombre, estado, detalle))
    aplican = [x for x in c.criterios if x.estado != NA]
    c.porcentaje = sum(PESO[x.estado] for x in aplican) / len(aplican) if aplican else 0.0
    c.horas_mes = horas_estimadas(k4, dias_mes) if horas_mes is None else horas_mes
    c.capacidad = calculo.HORAS_POR_DIA * dias_mes
    c.alerta = alerta_de_carga(c.horas_mes, c.capacidad)
    c.coherencia, razones_c = coherencia(k4)
    c.especificidad, razones_e = especificidad(k4)
    c.promedio = round((c.coherencia + c.especificidad) / 2, 1)
    c.detalle_calidad = [f"Coherencia {c.coherencia}/5: " + "; ".join(razones_c), f"Especificidad {c.especificidad}/5: " + "; ".join(razones_e)]
    _veredicto(c)
    return c


def _veredicto(c):
    criticos_no = [x.nombre for x in c.criterios if x.nombre.startswith(CRITICOS) and x.estado == NO]
    criticos_parcial = [x.nombre for x in c.criterios if x.nombre.startswith(CRITICOS) and x.estado == PARCIAL]
    otros_no = [x.nombre for x in c.criterios if x.estado == NO and x.nombre not in criticos_no]
    if criticos_no or c.porcentaje < UMBRAL_MINIMO:
        c.veredicto = NO_LISTO
        c.motivo_veredicto = ("falta lo esencial: " + ", ".join(criticos_no)) if criticos_no else f"completitud {c.porcentaje:.0%} (mínimo {UMBRAL_MINIMO:.0%})"
    elif c.porcentaje < UMBRAL_LISTO or criticos_parcial or otros_no:
        c.veredicto = CON_RESERVAS
        motivos = [f"completitud {c.porcentaje:.0%} (listo desde {UMBRAL_LISTO:.0%})"] if c.porcentaje < UMBRAL_LISTO else []
        c.motivo_veredicto = "; ".join(motivos + ([f"parcial: {', '.join(criticos_parcial)}"] if criticos_parcial else [])
                                       + ([f"sin datos: {', '.join(otros_no)}"] if otros_no else []))
    else:
        c.veredicto, c.motivo_veredicto = LISTO, f"completitud {c.porcentaje:.0%}"
