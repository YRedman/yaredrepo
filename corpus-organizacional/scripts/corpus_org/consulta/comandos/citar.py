import difflib
import re

from ...comun.errores import CorpusError
from ...comun.esquema import RE_CODIGO, RE_SECCION
from ...comun.texto import norm, recortar_palabras, tokens
from ...comun.tipos import AREA_GENERAL, es_general
from .base import Comando

COBERTURA_LITERAL = 1.0          # todas las palabras de la afirmacion, en el mismo orden y juntas
COBERTURA_PARCIAL = 0.6          # fraccion de las palabras de la afirmacion que deben estar en el documento
VENTANA_EXTRA = 6                # palabras de margen al comparar la afirmacion con una ventana del documento
PALABRAS_PASAJE = 45
RE_MARCA_MD = re.compile(r"[|*_`>#]+")


def _lineas_de_texto(d):
    """[(numero de linea en el archivo, seccion, texto limpio)] de las lineas con contenido de un documento."""
    res, seccion = [], ""
    for k, l in enumerate(d.lineas):
        m = RE_SECCION.match(l)
        if m:
            seccion = m.group(2).strip()
            continue
        if l.startswith(">") or not l.strip() or set(l.strip()) <= {"|", "-", ":", " "}:
            continue
        texto = RE_MARCA_MD.sub(" ", l)
        if norm(texto):
            res.append((d.inicio + k + 1, seccion, " ".join(texto.split())))
    return res


def respaldo(d, afirmacion):
    """(veredicto, linea, seccion, pasaje, cobertura) de una afirmacion frente al texto de un documento.

    LITERAL: la afirmacion aparece tal cual (sin importar mayusculas ni acentos); PARCIAL: la mayoria de sus
    palabras estan juntas en un pasaje; NINGUNO: no aparece.
    """
    buscada = tokens(afirmacion)
    if not buscada:
        return "NINGUNO", 0, "", "", 0.0
    lineas = _lineas_de_texto(d)
    palabras = []                                   # (palabra, indice de la linea de origen)
    for i, (_n, _s, t) in enumerate(lineas):
        palabras += [(p, i) for p in tokens(t)]
    solo = [p for p, _ in palabras]
    n = len(buscada)
    for k in range(len(solo) - n + 1):
        if solo[k:k + n] == buscada:
            _n, sec, texto = lineas[palabras[k][1]]
            return "LITERAL", lineas[palabras[k][1]][0], sec, texto, 1.0
    conjunto = set(buscada)
    mejor = (0.0, 0)
    ancho = n + VENTANA_EXTRA
    for k in range(0, max(1, len(solo) - 1)):
        ventana = solo[k:k + ancho]
        if not ventana:
            break
        cubiertas = len(conjunto & set(ventana)) / len(conjunto)
        if cubiertas > mejor[0]:
            mejor = (cubiertas, k)
    cobertura, k = mejor
    if cobertura >= COBERTURA_PARCIAL:
        _n, sec, texto = lineas[palabras[k][1]]
        mas_cerca = max(lineas[max(0, palabras[k][1] - 1):palabras[k][1] + 2],
                        key=lambda x: difflib.SequenceMatcher(None, norm(x[2]), norm(afirmacion)).ratio())
        return "PARCIAL", mas_cerca[0], mas_cerca[1] or sec, mas_cerca[2], cobertura
    return "NINGUNO", 0, "", "", cobertura


def _especificidad(cp, c):
    partes = c.split("-")
    area = partes[1] if len(partes) > 2 else ""
    if es_general(c) or area == AREA_GENERAL:
        return ("GENERAL (GEN): contexto o norma de toda la empresa, no es específico de un área; "
                "no lo presentes como propio de un área")
    a = cp.areas.get(area)
    return f"Específico del área {a.nombre} ({area})" if a else "Específico de un área"


class Citar(Comando):
    nombre = "citar"
    ayuda = "Confirma que un documento existe y, con --texto, que respalda una afirmacion (aval de la fuente)."

    def configurar(self, parser):
        parser.add_argument("codigos", nargs="+", help="uno o varios codigos de documento (p. ej. DES-CAL-07)")
        parser.add_argument("--texto", action="append", default=[],
                            help="afirmacion que debe respaldar el documento (se puede repetir)")

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        faltan, sin_respaldo = [], []
        for crudo in args.codigos:
            c = crudo.strip().upper()
            if not RE_CODIGO.match(c) or c not in cp.docs:
                faltan.append(c)
                try:
                    ctx.exigir_documento(c)
                except CorpusError as e:
                    s.linea(f"NO EXISTE · {c}: {e.mensaje}")
                continue
            d, m = cp.docs[c], cp.meta.get(c, {})
            s.linea()
            s.linea(f"EXISTE · {c} · {cp.nombre(c)}")
            filas = [["Especificidad", _especificidad(cp, c)],
                     ["Archivo original", m.get("archivo_origen") or d.archivo],
                     ["Ubicación del original", m.get("ruta_original") or "(no registrada: vuelva a construir)"],
                     ["Versión · vigencia · estado", " · ".join(x for x in (m.get("version"), m.get("fecha_vigencia"),
                                                                           m.get("estado_documental")) if x) or "—"],
                     ["Texto del original presente", m.get("cobertura") or "—"],
                     ["Dónde está en el corpus", d.ubicacion]]
            if m.get("area_propietaria"):
                filas.append(["Área propietaria", m["area_propietaria"]])
            s.tabla(["Dato", "Valor"], filas)
            for afirmacion in args.texto:
                v, linea, sec, pasaje, cob = respaldo(d, afirmacion)
                s.linea()
                if v == "LITERAL":
                    s.linea(f"RESPALDADO (literal) · {c} · línea {linea}" + (f" · sección «{sec}»" if sec else ""))
                    s.linea(f"  «{recortar_palabras(pasaje, PALABRAS_PASAJE)}»")
                elif v == "PARCIAL":
                    s.linea(f"RESPALDO PARCIAL ({cob:.0%} de las palabras) · {c} · línea {linea}"
                            + (f" · sección «{sec}»" if sec else "") + ": confirme la redacción con el pasaje")
                    s.linea(f"  «{recortar_palabras(pasaje, PALABRAS_PASAJE)}»")
                else:
                    sin_respaldo.append((c, afirmacion))
                    s.linea(f"SIN RESPALDO · {c} no contiene «{recortar_palabras(afirmacion, 20)}» "
                            f"(coincide el {cob:.0%} de sus palabras). No la presentes como dicha por este documento.")
        if faltan:
            raise CorpusError("No existen en el corpus: " + ", ".join(faltan) + ". No cites documentos que no existan.", 2)
        if sin_respaldo:
            raise CorpusError(f"{len(sin_respaldo)} afirmación(es) sin respaldo en el documento citado.", 3)
