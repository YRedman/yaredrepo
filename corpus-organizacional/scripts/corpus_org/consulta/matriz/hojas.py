"""Las filas de cada hoja de la matriz, calculadas del corpus publicado.

Para agregar una hoja: una funcion ``hoja_*`` que recibe el ``ContextoMatriz`` y devuelve sus filas, una linea en
``HOJAS`` y sus columnas en ``esquema.COLUMNAS``.
"""

import collections
from dataclasses import dataclass
from functools import cached_property

from ...comun.archivos import leer_csv_opcional
from ...comun.estructura import CARPETA_PUBLICADA, rutas_publicadas
from ...comun.esquema import ARCHIVO_REVISION, AVISO_ESCANEADO, area_de
from ...comun.tipos import TIPOS_PROCESO, es_general, tipo as tipo_documento, tipo_de_codigo
from ..cadena import calcular_enlaces, tipo_de_codigo_cliente
from ..extraccion import alcance, funciones, normativa, perfil, relaciones
from ..participacion import calcular_participacion
from ..puestos import DetectorPuestos
from ..repositorio import cargar_corpus


def _revision(raiz):
    """{codigo: revisado (bool)} de control/revision_visual.csv."""
    return {(f.get("codigo") or "").upper(): bool((f.get("revisado") or "").strip())
            for f in leer_csv_opcional(raiz / "control" / ARCHIVO_REVISION)}


def lectura_de(fila):
    """Calidad de lectura de un documento: Digital, OCR (con su confianza) o Sin texto."""
    avisos = fila.get("detalle_avisos") or ""
    if AVISO_ESCANEADO in avisos or (fila.get("palabras") or "").strip() == "0":
        return "Sin texto (escaneado)"
    if (fila.get("paginas_ocr") or "").strip() or "OCR en" in avisos:
        conf = (fila.get("confianza_ocr") or "").strip()
        detalle = f"confianza {float(conf):.0f} %" if conf else "confianza desconocida"
        revisar = "OCR en" in avisos or not conf
        return f"OCR ({detalle}{'; revisar contra el original' if revisar else ''})"
    return "Digital"


def nombre_de_tipo(codigo):
    t = tipo_documento(tipo_de_codigo(codigo))
    return t.nombre if t else tipo_de_codigo(codigo)


@dataclass
class Ficha:
    """Un documento de area con lo que casi todas las hojas necesitan de el."""
    codigo: str
    meta: dict
    doc: object
    area: str
    nombre: str
    lectura: str
    pendiente: bool
    estado_revision: str

    @property
    def ubicacion(self):
        return self.doc.ubicacion if self.doc else ""


class ContextoMatriz:
    """El corpus publicado y lo derivado de el que comparten las hojas (se calcula una vez)."""

    def __init__(self, raiz):
        self.raiz = raiz
        self.corpus = cargar_corpus(rutas_publicadas(raiz / CARPETA_PUBLICADA).skill_contexto, incluir_no_vigentes=True)
        self.detector = DetectorPuestos.desde_corpus(self.corpus)
        self.revision = _revision(raiz)

    def _codigos(self, *tipos):
        return sorted(c for c in self.corpus.meta if tipo_de_codigo(c) in tipos)

    @cached_property
    def descriptivos(self):
        return self._codigos("DES")

    @cached_property
    def procedimientos(self):
        return self._codigos(*TIPOS_PROCESO)           # PRD y PRO

    @cached_property
    def politicas(self):
        return self._codigos("POL")

    @cached_property
    def generales(self):
        return sorted(c for c in self.corpus.meta if es_general(c))

    @cached_property
    def de_area(self):
        """Los documentos de area en el orden de las hojas: descriptivos, procedimientos y protocolos, politicas."""
        return self.descriptivos + self.procedimientos + self.politicas

    def ficha(self, codigo):
        meta = self.corpus.meta[codigo]
        pendiente = codigo in self.revision and not self.revision[codigo]
        estado = "Pendiente" if pendiente else ("Revisado" if codigo in self.revision else "No requerida")
        return Ficha(codigo, meta, self.corpus.doc(codigo), meta.get("departamento", ""), self.corpus.nombre(codigo),
                     lectura_de(meta), pendiente, estado)

    @cached_property
    def fichas(self):
        return {c: self.ficha(c) for c in self.de_area}

    @cached_property
    def participacion(self):
        """(participacion calculada, {(puesto, procedimiento): roles})."""
        part = calcular_participacion(self.corpus, self.procedimientos, self.detector)
        cruces = collections.defaultdict(set)
        for fp in part.filas:
            cruces[(fp.puesto.codigo, fp.procedimiento)].add(fp.rol)
        return part, cruces

    def jefe(self, texto, codigo):
        """(codigo, tipo de coincidencia) del puesto mencionado en 'Reporta a', si esta en el corpus."""
        for m in self.detector.detectar(texto or "", area_de(codigo)):
            if m.puesto is not None and m.puesto.codigo != codigo:
                return m.puesto.codigo, m.etiqueta
        return "", ""

    def puesto_mencionado(self, texto, codigo):
        """El puesto del corpus al que se refiere ``texto`` (o None), buscando primero en el area de ``codigo``."""
        return next((m for m in self.detector.detectar(texto, area_de(codigo)) if m.puesto is not None), None)


# ---------------------------------------------------------------------------
# una funcion por hoja
# ---------------------------------------------------------------------------

def hoja_puestos(m):
    filas = []
    for c in m.descriptivos:
        x, f = m.fichas[c], m.fichas[c].meta
        jefe, coincidencia = m.jefe(f.get("reporta_a"), c)
        filas.append([c, x.area, x.nombre, f.get("reporta_a", ""), jefe, coincidencia, f.get("supervisa_a", ""),
                      f.get("proposito_literal", ""), f.get("codigo_interno", ""), f.get("version", ""),
                      f.get("fecha_vigencia", ""), f.get("estado_documental", ""), x.lectura, x.estado_revision,
                      f.get("archivo_origen", ""), x.ubicacion])
    return filas


def hoja_funciones(m):
    return [[c, m.fichas[c].area, m.fichas[c].nombre, n, funcion, evidencia]
            for c in m.descriptivos for n, (funcion, evidencia) in enumerate(funciones(m.fichas[c].doc), 1)]


def hoja_relaciones(m):
    filas = []
    for c in m.descriptivos:
        x = m.fichas[c]
        for otro, tipo in relaciones(x.doc):
            rel = m.puesto_mencionado(otro, c)
            filas.append([c, x.area, x.nombre, otro, tipo, rel.puesto.codigo if rel else "",
                          rel.puesto.nombre if rel else ""])
    return filas


def hoja_perfil(m):
    return [[c, m.fichas[c].area, m.fichas[c].nombre, seccion, requisito, detalle]
            for c in m.descriptivos for seccion, requisito, detalle in perfil(m.fichas[c].doc)]


def hoja_normativa(m):
    return [[c, m.fichas[c].area, m.fichas[c].nombre, tipo, mencion, seccion]
            for c in m.de_area for tipo, mencion, seccion in normativa(m.fichas[c].doc)]


def hoja_cadena(m):
    corpus, filas = m.corpus, []
    for e in calcular_enlaces(corpus.meta):
        if es_general(e.origen):
            continue
        filas.append([
            e.origen, nombre_de_tipo(e.origen), corpus.meta[e.origen].get("departamento", ""), corpus.nombre(e.origen),
            e.citado, tipo_de_codigo_cliente(e.citado), e.destino, nombre_de_tipo(e.destino) if e.destino else "",
            corpus.meta[e.destino].get("departamento", "") if e.destino else "",
            corpus.nombre(e.destino) if e.destino else "", e.via or "no está en el corpus"])
    return filas


def hoja_procedimientos(m):
    filas = []
    for c in m.procedimientos:
        x, f = m.fichas[c], m.fichas[c].meta
        filas.append([c, nombre_de_tipo(c), x.area, x.nombre, f.get("proposito_literal", ""), f.get("propietario", ""),
                      f.get("responsable", ""), f.get("codigo_interno", ""), f.get("version", ""),
                      f.get("fecha_vigencia", ""), f.get("estado_documental", ""), f.get("actividades", ""),
                      x.lectura, x.estado_revision])
    return filas


def hoja_politicas(m):
    """Politicas y protocolos: area de aplicacion, area propietaria y alcance."""
    filas = []
    for c in m.de_area:
        if tipo_de_codigo(c) not in ("PRO", "POL"):
            continue
        x, f = m.fichas[c], m.fichas[c].meta
        filas.append([c, nombre_de_tipo(c), x.area, f.get("area_propietaria", ""), alcance(x.doc), f.get("version", ""),
                      f.get("fecha_vigencia", ""), f.get("estado_documental", ""), x.nombre,
                      f.get("proposito_literal", ""), f.get("propietario", ""), f.get("responsable", ""),
                      f.get("codigo_interno", ""), x.lectura, x.estado_revision])
    return filas


def hoja_generales(m):
    corpus = m.corpus
    return [[c, nombre_de_tipo(c), corpus.nombre(c), corpus.meta[c].get("archivo_origen", ""), lectura_de(corpus.meta[c]),
             corpus.doc(c).ubicacion if corpus.doc(c) else ""] for c in m.generales]


def hoja_participacion(m):
    corpus = m.corpus
    part, _ = m.participacion
    filas = [[fp.puesto.codigo, fp.puesto.nombre, fp.procedimiento, corpus.nombre(fp.procedimiento),
              nombre_de_tipo(fp.procedimiento), fp.rol, fp.coincidencia, fp.evidencia] for fp in part.filas]
    for rol, procs in part.sin_descriptivo.items():
        filas += [["", rol, p, corpus.nombre(p), nombre_de_tipo(p), "", "sin descriptivo en el corpus", ""]
                  for p in sorted(procs)]
    return filas


def hoja_puestos_x_procedimientos(m):
    """Matriz: filas = puestos, columnas = procedimientos y protocolos, celda = rol."""
    _, cruces = m.participacion
    if not cruces:
        return []
    procs = sorted({p for _, p in cruces})
    filas = [["Código", "Puesto"] + procs]
    for cod in sorted({c for c, _ in cruces}):
        filas.append([cod, m.corpus.nombre(cod)] + [", ".join(sorted(cruces.get((cod, p), ()))) for p in procs])
    return filas


def hoja_indicadores(m):
    kpis = m.corpus.kpis
    if not kpis:
        return []
    columnas = list(kpis[0].keys())
    return [columnas] + [[k.get(x, "") for x in columnas] for k in kpis]


def hoja_revision(m):
    filas = []
    for c in m.de_area:
        x = m.fichas[c]
        if x.lectura != "Digital" or c in m.revision:
            filas.append([c, x.area, x.nombre, x.lectura,
                          x.meta.get("detalle_avisos", "") or ("muestra aleatoria" if c in m.revision else ""),
                          "Pendiente" if x.pendiente or c not in m.revision else "Revisado", ""])
    return filas


HOJAS = (("Puestos", hoja_puestos), ("Funciones", hoja_funciones), ("Relaciones", hoja_relaciones),
         ("Perfil y requisitos", hoja_perfil), ("Normativa citada", hoja_normativa), ("Cadena documental", hoja_cadena),
         ("Procedimientos", hoja_procedimientos), ("Políticas y protocolos", hoja_politicas),
         ("Documentos generales", hoja_generales), ("Participación", hoja_participacion),
         ("Puestos x Procedimientos", hoja_puestos_x_procedimientos), ("Indicadores", hoja_indicadores),
         ("Revisión", hoja_revision))


def datos_matriz(raiz):
    """(corpus, {hoja: filas}) calculados del corpus publicado en ``raiz``/copilot."""
    m = ContextoMatriz(raiz)
    return m.corpus, collections.OrderedDict((nombre, construir(m)) for nombre, construir in HOJAS)
