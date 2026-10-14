"""Extraccion de datos de un documento publicado: tablas, funciones, relaciones, perfil, normativa citada y alcance.

Lo comparten la matriz Excel, el comando ``normativa`` y el ``briefing``. Todo es literal del documento.
"""

import re
from dataclasses import dataclass, field
from typing import List

from ..comun.markdown import celdas
from ..comun.texto import norm
from .parser import lineas_contenido

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


def alcance(doc):
    """Texto literal de la seccion de alcance (o aplicacion) de un documento; vacio si no la tiene."""
    partes, dentro = [], False
    for lc in lineas_contenido(doc):
        principal = norm(lc.seccion.split(" › ")[0])
        if RE_ALCANCE.match(principal):
            if not lc.es_cabecera and not lc.texto.startswith("|---"):
                partes.append(_sin_vineta(_limpia(" ".join(celdas(lc.texto)) if lc.es_tabla else lc.texto)))
            dentro = True
        elif dentro:
            break
    return " ".join(x for x in partes if x).strip()


RE_ALCANCE = re.compile(r"^(?:\d+[.)]?\s*)?(alcance|aplicacion|campo de aplicacion|ambito)")
