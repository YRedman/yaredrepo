"""Tipos de documento y codificacion del corpus: TTT-AAA-NN.

TTT es el tipo (3 letras), AAA el area (3 letras o GEN) y NN el numero (dos digitos; tres si el grupo
pasa de 99). Para agregar un tipo nuevo basta con agregar una fila a ``TIPOS_DOCUMENTO``: los patrones,
los nombres de archivo, los filtros de los comandos y la estructura de skills se derivan de esta tabla.

- Tipos de area (``general=False``): van en el skill fuente-documentos, en una carpeta por tipo
  (DES/, PRD/...). Se reconocen por la carpeta de entrada (Descriptivos\\, Procedimientos\\...).
  Politicas y protocolos que aplican a mas de un area o a toda la empresa llevan el area GEN.
- Tipos generales (``general=True``): documentos de contexto, siempre con area GEN; van en el skill
  fuente-contexto. Se clasifican por la subcarpeta de contexto o por palabras del nombre del archivo.
"""

import re
from dataclasses import dataclass
from typing import Optional, Tuple

from .texto import norm

AREA_GENERAL = "GEN"
NOMBRE_AREA_GENERAL = "General"


@dataclass(frozen=True)
class TipoDocumento:
    codigo: str                    # DES
    nombre: str                    # Descriptivo de puesto
    plural: str                    # Descriptivos de puesto
    general: bool = False          # True: documento general de contexto (area GEN)
    carpetas: Tuple[str, ...] = ()  # inicio del nombre de la carpeta de entrada (normalizado, sin acentos)
    palabras: Tuple[str, ...] = ()  # palabras del nombre de archivo o subcarpeta de contexto que identifican el tipo
    anterior: str = ""             # letra del codigo anterior (D-, P-) para la migracion


TIPOS_DOCUMENTO = (
    # --- documentos de area: skill fuente-documentos -------------------------------------------
    TipoDocumento("DES", "Descriptivo de puesto", "Descriptivos de puesto", carpetas=("descrip", "perfil"),
                  palabras=("descriptivo", "perfil de puesto", "perfiles de puesto"), anterior="D"),
    TipoDocumento("PRD", "Procedimiento", "Procedimientos", carpetas=("procedim", "proceso"),
                  palabras=("procedimiento", "ficha de proceso", "fichas de proceso", "fdp", "instructivo"),
                  anterior="P"),
    TipoDocumento("PRO", "Protocolo", "Protocolos", carpetas=("protocol",), palabras=("protocolo",)),
    TipoDocumento("POL", "Política", "Políticas", carpetas=("politic", "normativ", "reglament"),
                  palabras=("politica", "normativa", "reglamento", "lineamiento")),
    # --- documentos generales de contexto (area GEN); los indicadores van en kpis.csv --
    TipoDocumento("ORG", "Organigrama", "Organigramas", general=True,
                  palabras=("organigrama", "estructura organizacional")),
    TipoDocumento("GLO", "Glosario", "Glosarios", general=True, palabras=("glosario",)),
    TipoDocumento("MPR", "Mapa de procesos", "Mapas de procesos", general=True,
                  palabras=("mapa de procesos", "mapa de proceso")),
    # Contexto que no coincide con ningun tipo general anterior (agregar tipos arriba para clasificarlo).
    TipoDocumento("CTX", "Contexto general", "Contexto general", general=True),
)
TIPO_CONTEXTO_POR_DEFECTO = "CTX"

POR_CODIGO = {t.codigo: t for t in TIPOS_DOCUMENTO}
TIPOS_AREA = tuple(t.codigo for t in TIPOS_DOCUMENTO if not t.general)
TIPOS_GENERALES = tuple(t.codigo for t in TIPOS_DOCUMENTO if t.general)
TIPOS_PROCESO = ("PRD", "PRO")   # documentos con actividades y responsables: participacion de puestos

# --- patrones (solo tipos conocidos: un codigo interno del cliente como ABC-FOR-040 no es del corpus) ---
_TIPOS_RE = "|".join(t.codigo for t in TIPOS_DOCUMENTO)
PATRON_CODIGO = rf"(?:{_TIPOS_RE})-[A-Z0-9]{{3}}-\d{{2,3}}"
PATRON_CODIGO_ANTERIOR = r"[PDC]-[A-Z0-9]{3}-\d{2,3}"
RE_CODIGO_ANTERIOR = re.compile(rf"^({PATRON_CODIGO_ANTERIOR})$", re.I)
RE_ARCHIVO_DOCUMENTOS = re.compile(rf"^({_TIPOS_RE})_([A-Z0-9]{{3}})\.md$")


def tipo(codigo_tipo) -> Optional[TipoDocumento]:
    return POR_CODIGO.get((codigo_tipo or "").strip().upper())


def familia(codigo_tipo):
    """Como se analiza un tipo: 'D' (descriptivo de puesto), 'P' (procedimiento, protocolo, politica:
    objetivo, alcance, desarrollo con actividades) o 'C' (contexto general, sin campos clave)."""
    t = tipo(codigo_tipo)
    if t is None:
        return "C"
    if t.general:
        return "C"
    return "D" if t.codigo == "DES" else "P"


def tipo_de_codigo(codigo):
    """'DES' de 'DES-SEG-01'."""
    return (codigo or "").split("-")[0].upper()


def area_de(codigo):
    """'SEG' de 'DES-SEG-01'."""
    partes = (codigo or "").split("-")
    return partes[1].upper() if len(partes) > 1 else ""


def es_general(codigo):
    """True si el codigo es de un documento general de contexto (tipo general o area GEN de un tipo general)."""
    t = tipo(tipo_de_codigo(codigo))
    return bool(t and t.general)


def nombre_archivo(codigo_tipo, codigo_area):
    """Archivo publicado de un tipo y area: DES_SEG.md, POL_GEN.md, ORG_GEN.md."""
    return f"{codigo_tipo}_{codigo_area}.md"


def tipo_desde_texto(texto):
    """Codigo de tipo a partir de 'DES', 'Descriptivo de puesto', 'procedimiento', 'D' (anterior)..."""
    t = (texto or "").strip()
    if not t:
        return None
    if t.upper() in POR_CODIGO:
        return t.upper()
    n = norm(t)
    for td in TIPOS_DOCUMENTO:
        if n in (norm(td.nombre), norm(td.plural)) or (td.anterior and t.upper() == td.anterior):
            return td.codigo
    for td in TIPOS_DOCUMENTO:
        if n and (norm(td.nombre).startswith(n) or any(n.startswith(c) for c in td.carpetas)):
            return td.codigo
    return None


def tipo_de_carpeta(nombre):
    """Tipo de area por el nombre de la carpeta de entrada: 'Descriptivos' -> DES, 'Políticas' -> POL."""
    n = norm(nombre)
    for td in TIPOS_DOCUMENTO:
        if not td.general and any(n.startswith(c) for c in td.carpetas):
            return td.codigo
    return None


def tipo_general_de(nombre_archivo_o_carpeta):
    """Tipo general de un material de contexto por su subcarpeta o su nombre de archivo, o None."""
    n = norm(re.sub(r"[_\-.]+", " ", nombre_archivo_o_carpeta or ""))
    if n.upper() in TIPOS_GENERALES:
        return n.upper()
    for td in TIPOS_DOCUMENTO:
        if td.general and (n == norm(td.nombre) or n == norm(td.plural)
                           or any(re.search(rf"(?<!\w){re.escape(p)}", n) for p in td.palabras)):
            return td.codigo
    return None


def _con_palabra(texto, palabras):
    n = norm(re.sub(r"[_\-.]+", " ", texto or ""))
    return any(re.search(rf"(?<!\w){re.escape(p)}", n) for p in palabras)


def tipos_candidatos(nombre):
    """Todos los tipos que un nombre de carpeta o archivo indica, en el orden de la tabla (puede haber varios:
    «Políticas y procedimientos» es POL y PRD; «Estructura organizacional y descriptivos» es ORG y DES)."""
    res = []
    for td in TIPOS_DOCUMENTO:
        if td.general:
            if td.codigo in TIPOS_GENERALES and tipo_general_de(nombre) == td.codigo:
                res.append(td.codigo)
        elif _con_palabra(nombre, td.palabras) or tipo_de_carpeta(nombre) == td.codigo:
            res.append(td.codigo)
    return res


def tipo_de_material(nombre_archivo_o_carpeta):
    """Tipo de un material de la carpeta de contexto (subcarpeta o nombre de archivo).

    Primero los tipos de area (un 'Procedimiento de indicadores' es un procedimiento, una 'Normativa' una
    politica) y luego los generales (organigrama, glosario...). None si no se reconoce."""
    for td in TIPOS_DOCUMENTO:
        if not td.general and (_con_palabra(nombre_archivo_o_carpeta, td.palabras)
                               or tipo_de_carpeta(nombre_archivo_o_carpeta) == td.codigo):
            return td.codigo
    return tipo_general_de(nombre_archivo_o_carpeta)


def es_area_general(nombre_area):
    """True si el area indicada significa 'toda la empresa' (para politicas y protocolos)."""
    return norm(nombre_area) in ("gen", "general", "toda la empresa", "empresa", "corporativo", "corporativa",
                                 "varias areas", "multiples areas", "transversal")


def codigo_nuevo_desde_anterior(codigo):
    """D-SEG-01 -> DES-SEG-01; P-SEG-01 -> PRD-SEG-01. Los C-CTX se clasifican aparte (por archivo)."""
    m = RE_CODIGO_ANTERIOR.match(codigo or "")
    if not m:
        return None
    letra, area, num = codigo.upper().split("-")
    for td in TIPOS_DOCUMENTO:
        if td.anterior == letra:
            return f"{td.codigo}-{area}-{num}"
    return None


FILTRO_GENERAL = AREA_GENERAL       # --tipo GEN: documentos con area GEN (generales y de toda la empresa)
FILTROS_TIPO = TIPOS_AREA + (FILTRO_GENERAL,)


def filtro_tipo(texto):
    """Valor de --tipo: DES, PRD, PRO, POL o GEN (tambien acepta el nombre del tipo). Error si no se reconoce."""
    t = (texto or "").strip()
    if t.upper() == FILTRO_GENERAL or es_area_general(t):
        return FILTRO_GENERAL
    codigo = tipo_desde_texto(t)
    if not codigo:
        raise ValueError(f"tipo desconocido '{texto}' (use {'|'.join(FILTROS_TIPO)})")
    return codigo


def cumple_tipo(codigo, filtro):
    """True si el codigo del documento corresponde al filtro de --tipo (sin filtro, siempre)."""
    if not filtro:
        return True
    if filtro == FILTRO_GENERAL:
        return area_de(codigo) == AREA_GENERAL
    return tipo_de_codigo(codigo) == filtro
