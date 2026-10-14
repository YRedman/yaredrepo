"""Protocolos y politicas GEN (de varias areas o de toda la empresa) que son pertinentes para un area.

Un GEN es pertinente solo si su texto lo dice, nunca por afinidad de tema:
- menciona al area (nombre, codigo o alias)               -> ``Menciona al área``
- menciona a uno de sus puestos                            -> ``Menciona al puesto <nombre>``
- su seccion de alcance aplica a toda la empresa / areas   -> ``Alcance: toda la empresa``
"""

import collections
import re

from ..comun.tipos import AREA_GENERAL, tipo_de_codigo
from ..comun.texto import norm
from .areas import patrones_area
from .entidades import quitar_exclusiones
from .extraccion import alcance

TIPOS_PERTINENTES = ("PRO", "POL")
MOTIVO_AREA = "Menciona al área"
MOTIVO_EMPRESA = "Alcance: toda la empresa"
MOTIVO_DEL_AREA = "Del área"
MAX_PUESTOS_EN_MOTIVO = 3
RE_TODA_LA_EMPRESA = re.compile(
    r"(?<!\w)(?:toda la (?:empresa|organizacion|compania|institucion|corporacion)|"
    r"todas las (?:areas|gerencias|direcciones|unidades|dependencias|sedes|filiales)|"
    r"todos los (?:departamentos|procesos de la empresa))(?!\w)")


def alcance_es_toda_la_empresa(doc):
    """True si la seccion de alcance dice que aplica a toda la empresa o a todas las areas."""
    return RE_TODA_LA_EMPRESA.search(norm(alcance(doc))) is not None


def motivos(corpus, codigo, cod_area, detector):
    """Lista de motivos por los que el documento GEN ``codigo`` es pertinente para el area (vacia = no lo es)."""
    patrones = patrones_area(set(corpus.alias.get(cod_area, ())) | {cod_area})
    menciona_area, puestos = False, collections.OrderedDict()
    for _seccion, linea in corpus.cuerpo(codigo):
        if not menciona_area:
            texto = quitar_exclusiones(linea, corpus.exclusiones)
            menciona_area = any(p.search(texto) for p in patrones)
        for m in detector.detectar(linea, AREA_GENERAL):
            if m.tipo == "exacta" and m.asignada and m.puesto.area == cod_area:
                puestos.setdefault(m.puesto.codigo, m.puesto.nombre)
    res = []
    if menciona_area:
        res.append(MOTIVO_AREA)
    nombres = list(puestos.values())
    if nombres:
        res.append("Menciona al puesto " + ", ".join(nombres[:MAX_PUESTOS_EN_MOTIVO])
                   + (" …" if len(nombres) > MAX_PUESTOS_EN_MOTIVO else ""))
    if alcance_es_toda_la_empresa(corpus.doc(codigo)):
        res.append(MOTIVO_EMPRESA)
    return res


def gen_pertinentes(corpus, cod_area, detector):
    """{tipo: {codigo GEN: 'motivo; motivo'}} de los protocolos y politicas GEN pertinentes para el area."""
    res = {t: collections.OrderedDict() for t in TIPOS_PERTINENTES}
    if cod_area == AREA_GENERAL or AREA_GENERAL not in corpus.areas:
        return res
    for c in corpus.areas[AREA_GENERAL].codigos():
        t = tipo_de_codigo(c)
        if t in TIPOS_PERTINENTES and c in corpus.docs:
            m = motivos(corpus, c, cod_area, detector)
            if m:
                res[t][c] = "; ".join(m)
    return res
