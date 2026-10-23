"""Validacion del corpus publicado: inventario, indice, textos, cobertura y revision visual."""

import collections
import hashlib
import math
from dataclasses import dataclass, field
from typing import Dict, List

from ..comun.archivos import escribir_csv, leer_csv_opcional, leer_texto
from ..comun.esquema import (ARCHIVO_AREAS_DOCUMENTOS, ARCHIVO_INDICE, ARCHIVO_INVENTARIO, ARCHIVO_REVISADOS,
                             ARCHIVO_REVISION, AREA_SIN_ASIGNAR, AVISO_ESCANEADO, RE_DOC_MD, estado_no_publicable,
                             inventario_activo)
from ..comun.estructura import markdown_de_documentos, rutas_publicadas
from ..comun.texto import porcentaje
from ..comun.tipos import es_general

MUESTRA_REVISION = 0.10
CODIGOS_MOSTRADOS = 20
CARACTERES_DE_PALABRAS = 60
CARACTERES_DE_AVISO = 200

LISTO, PENDIENTE, REQUIERE = "LISTO PARA PUBLICAR", "PENDIENTE DE REVISIÓN VISUAL", "REQUIERE REVISIÓN"
CODIGO_SALIDA = {LISTO: 0, REQUIERE: 2, PENDIENTE: 3}


@dataclass
class Validacion:
    documentos_inventariados: int = 0
    documentos_indexados: int = 0
    documentos_con_texto: int = 0
    duplicados: List[str] = field(default_factory=list)
    problemas: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    revision_visual: Dict[str, str] = field(default_factory=dict)   # codigo -> motivo (pendientes)
    ubicacion: Dict[str, tuple] = field(default_factory=dict)       # codigo -> (archivo, ruta del original)
    con_problemas: Dict[str, List[str]] = field(default_factory=dict)  # codigo -> problemas de su texto

    @property
    def estado(self):
        """REQUIERE REVISIÓN (hay errores) > PENDIENTE DE REVISIÓN VISUAL > LISTO PARA PUBLICAR."""
        if self.problemas or self.duplicados:
            return REQUIERE
        return PENDIENTE if self.revision_visual else LISTO

    @property
    def codigo_salida(self):
        return CODIGO_SALIDA[self.estado]

    def ubicacion_de(self, codigo):
        """(archivo, ruta del original) de un documento; vacios si no esta en el indice."""
        return self.ubicacion.get(codigo, ("", ""))


def leer_revisados(*carpetas):
    """Codigos ya revisados visualmente: uno por linea en revision_visual_ok.txt ('#' inicia un comentario)."""
    codigos = set()
    for carpeta in carpetas:
        p = carpeta / ARCHIVO_REVISADOS
        if p.is_file():
            for linea in leer_texto(p).splitlines():
                c = linea.split("#", 1)[0].strip().upper()
                if c:
                    codigos.add(c)
    return codigos


def muestra_reproducible(codigos, fraccion):
    """Muestra reproducible (siempre la misma para los mismos codigos) de una fraccion de los documentos."""
    n = math.ceil(fraccion * len(codigos)) if codigos and fraccion else 0
    return sorted(codigos, key=lambda c: hashlib.sha256(c.encode()).hexdigest())[:n]


def _codigos(filas):
    return {(f.get("codigo") or "").upper() for f in filas if f.get("codigo")}


def _validar_inventario(v, filas, inventario, errores_contexto):
    """Duplicados, documentos sin convertir, sin area o fuera del inventario."""
    cod_indice, cod_inv = _codigos(filas), _codigos(inventario)
    if not filas:
        v.problemas.append("El índice consolidado está vacío.")
    if v.duplicados:
        v.problemas.append("Códigos duplicados: " + ", ".join(v.duplicados))
    if errores_contexto:
        v.problemas.append("Materiales de contexto que no se pudieron convertir: " + "; ".join(errores_contexto))
    faltan = sorted(cod_inv - cod_indice)
    if faltan:
        v.problemas.append("Documentos inventariados sin convertir: " + ", ".join(faltan))
    sin_area = sorted((f.get("codigo") or "") for f in inventario if (f.get("departamento") or "") == AREA_SIN_ASIGNAR)
    if sin_area:
        v.problemas.append(f"Documentos sin área ({len(sin_area)}; códigos provisionales): escriba su área en "
                           f"{ARCHIVO_AREAS_DOCUMENTOS} y vuelva a construir. " + ", ".join(sin_area[:CODIGOS_MOSTRADOS])
                           + (" …" if len(sin_area) > CODIGOS_MOSTRADOS else ""))
    sobran = sorted(c for c in cod_indice - cod_inv if not es_general(c))
    if sobran:
        v.avisos.append("Documentos fuera del inventario: " + ", ".join(sobran))


def _codigos_con_texto(rutas):
    """Codigos que tienen su texto en algun Markdown publicado (documentos/ y contexto/)."""
    codigos = set()
    for p in markdown_de_documentos(rutas.documentos) + sorted(rutas.contexto.glob("*.md")):
        codigos.update(RE_DOC_MD.findall(p.read_text(encoding="utf-8", errors="replace")))
    return codigos


class _RevisionDeFilas:
    """Recorre las filas del indice buscando texto ausente, palabras agregadas, paginas sin leer, estados no vigentes
    y documentos con avisos de estructura (los que van a revision visual)."""

    def __init__(self, v):
        self.v = v
        self.bajos, self.agregadas, self.no_publicables, self.escaneados = [], [], [], []
        self.revision = collections.OrderedDict()           # codigo -> motivo de la revision visual

    def _con_problema(self, codigo, texto):
        self.v.con_problemas.setdefault(codigo, []).append(texto)

    def revisar(self, f):
        c = (f.get("codigo") or "").upper()
        self.v.ubicacion[c] = (f.get("archivo_origen") or "", f.get("ruta_original") or "")
        self._cobertura(c, f)
        palabras = (f.get("palabras_agregadas") or "").strip()
        if palabras:
            self.agregadas.append(f"{c} ({f['palabras_agregadas'][:CARACTERES_DE_PALABRAS]})")
            self._con_problema(c, "palabras que no están en el original: " + f["palabras_agregadas"][:CARACTERES_DE_PALABRAS])
        if AVISO_ESCANEADO in (f.get("detalle_avisos") or ""):
            self.escaneados.append(c)
            self._con_problema(c, "páginas escaneadas sin leer")
        if (f.get("avisos_estructura") or "0").strip() not in ("", "0"):
            self.revision[c] = (f.get("detalle_avisos") or "")[:CARACTERES_DE_AVISO]
        if estado_no_publicable(f.get("estado_documental", "")):
            self.no_publicables.append(f"{c} ({f.get('estado_documental')})")

    def _cobertura(self, codigo, f):
        try:
            if f.get("cobertura") and porcentaje(f["cobertura"]) < 100.0:
                self.bajos.append(f"{codigo} ({f['cobertura']})")
                self._con_problema(codigo, f"texto del original ausente (cobertura {f['cobertura']})")
        except ValueError:
            self.v.problemas.append(f"Cobertura no interpretable: {codigo} = {f.get('cobertura')}")

    def informar(self):
        v = self.v
        if self.bajos:
            v.problemas.append("Texto del original que no aparece en el Markdown (cobertura < 100 %): "
                               + ", ".join(self.bajos))
        if self.agregadas:
            v.problemas.append("Palabras que no están en el original (posible texto corrupto): "
                               + "; ".join(self.agregadas))
        if self.escaneados:
            v.problemas.append(f"Documentos con páginas escaneadas que no se pudieron leer ({len(self.escaneados)}; su "
                               "texto no está en el corpus): instale Tesseract con el idioma español y pytesseract, o "
                               "use la versión digital. " + ", ".join(self.escaneados))
        if self.no_publicables:
            v.avisos.append("Excluidos de las consultas por su estado documental: " + ", ".join(self.no_publicables))


def _revision_visual(v, revision, cod_indice, revisados, muestra):
    """Agrega la muestra aleatoria a los documentos con avisos y deja en ``v`` los que siguen sin revisar."""
    resto = sorted(c for c in cod_indice if c not in revision and not es_general(c))
    for c in muestra_reproducible(resto, muestra):
        revision[c] = f"muestra aleatoria ({muestra:.0%})"
    v.revision_visual = collections.OrderedDict((c, m) for c, m in revision.items() if c not in revisados)


def _escribir_revision(control, v, revision, revisados):
    escribir_csv(control / ARCHIVO_REVISION, ["codigo", "motivo", "revisado", "archivo", "ruta_original"],
                 [{"codigo": c, "motivo": m, "revisado": "sí" if c in revisados else "",
                   "archivo": v.ubicacion_de(c)[0], "ruta_original": v.ubicacion_de(c)[1]}
                  for c, m in revision.items()])


def validar_publicacion(publicado, duplicados=(), revisados=frozenset(), muestra=MUESTRA_REVISION,
                        errores_contexto=(), control=None):
    """Valida inventario, indice, textos, cobertura y estructura del corpus publicado.

    - Problemas (REQUIERE REVISIÓN): codigos duplicados, documentos sin convertir o sin texto, texto
      del original que falta (cobertura < 100 %), palabras que no estan en el original y errores del contexto.
    - Revision visual (PENDIENTE DE REVISIÓN VISUAL): documentos con avisos de estructura y una muestra
      del ``muestra`` de los demas, hasta que su codigo este en revision_visual_ok.txt.
    """
    v = Validacion(duplicados=list(duplicados))
    rutas = rutas_publicadas(publicado)
    filas = leer_csv_opcional(rutas.indice / ARCHIVO_INDICE)
    inventario = inventario_activo(leer_csv_opcional(rutas.indice / ARCHIVO_INVENTARIO))
    cod_indice, cod_inv = _codigos(filas), _codigos(inventario)
    _validar_inventario(v, filas, inventario, errores_contexto)
    cod_md = _codigos_con_texto(rutas)
    sin_texto = sorted(cod_indice - cod_md)
    if sin_texto:
        v.problemas.append("Filas del índice sin texto Markdown: " + ", ".join(sin_texto))
    auditoria = _RevisionDeFilas(v)
    for f in filas:
        auditoria.revisar(f)
    auditoria.informar()
    _revision_visual(v, auditoria.revision, cod_indice, revisados, muestra)
    if control is not None:
        _escribir_revision(control, v, auditoria.revision, revisados)
    v.documentos_inventariados = len(cod_inv)
    v.documentos_indexados = len(cod_indice)
    v.documentos_con_texto = len(cod_md & cod_indice)
    return v
