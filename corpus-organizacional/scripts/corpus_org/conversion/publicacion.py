"""Publicacion del corpus: indice consolidado, copia limpia a publicado/ y validacion."""

import collections
import datetime
import hashlib
import math
import re
import shutil
from dataclasses import dataclass, field
from typing import Dict, List

from .. import VERSION
from ..comun.archivos import escribir_csv, leer_csv, leer_texto
from ..comun.esquema import (AREA_SIN_ASIGNAR, AVISO_ESCANEADO, ARCHIVO_AREAS_DOCUMENTOS, ARCHIVO_AREAS_EXTRA, ARCHIVO_CATALOGO, ARCHIVO_HUELLAS, ARCHIVO_INDICE,
                             ARCHIVO_INVENTARIO, ARCHIVO_KPIS, ARCHIVO_REVISADOS, ARCHIVO_REVISION, COLUMNAS_INDICE,
                             PATRON_CODIGO, PREFIJO_DIC, PREFIJO_REPORTE, estado_no_publicable, inventario_activo)
from ..comun.markdown import esc_celda
from .huella import huella

RE_DOC_MD = re.compile(rf"^## \[({PATRON_CODIGO})\]", re.M)
# Archivos que genera la conversion en control/ y que se regeneran en cada construccion.
PATRONES_GENERADOS = ("P_*.md", "D_*.md", "contexto.md", f"{PREFIJO_DIC}*.csv", f"{PREFIJO_REPORTE}*.md",
                      ARCHIVO_KPIS, ARCHIVO_AREAS_EXTRA)
# Archivos de control/ que se publican tal cual (si existen).
PUBLICADOS_TAL_CUAL = (ARCHIVO_INVENTARIO, ARCHIVO_CATALOGO, ARCHIVO_KPIS, ARCHIVO_AREAS_EXTRA)
MUESTRA_REVISION = 0.10

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

    @property
    def listo(self):
        return not self.problemas and not self.duplicados and not self.revision_visual

    @property
    def estado(self):
        """REQUIERE REVISIÓN (hay errores) > PENDIENTE DE REVISIÓN VISUAL > LISTO PARA PUBLICAR."""
        if self.problemas or self.duplicados:
            return REQUIERE
        return PENDIENTE if self.revision_visual else LISTO

    @property
    def codigo_salida(self):
        return CODIGO_SALIDA[self.estado]


def limpiar_generados(control):
    """Borra lo que genero una construccion anterior para que no se mezcle con la nueva.

    Sin esto, un DIC parcial de una corrida previa (p. ej. DIC_P_COM_01-05.csv) quedaba junto al
    completo y aparecian codigos duplicados que no existen.
    """
    borrados = []
    for patron in PATRONES_GENERADOS:
        for p in control.glob(patron):
            if p.is_file():
                p.unlink()
                borrados.append(p)
    return borrados


def consolidar_indices(control, publicado):
    """Une todos los DIC_*.csv en un indice maestro. Devuelve (ruta, codigos duplicados)."""
    por_codigo = collections.OrderedDict()
    duplicados = []
    for p in sorted(control.glob(f"{PREFIJO_DIC}*.csv")):
        for f in leer_csv(p):
            c = (f.get("codigo") or "").strip().upper()
            if not c:
                continue
            if c in por_codigo:
                duplicados.append(c)
            por_codigo[c] = {k: f.get(k, "") for k in COLUMNAS_INDICE}
    indice = publicado / ARCHIVO_INDICE
    escribir_csv(indice, COLUMNAS_INDICE, list(por_codigo.values()))
    return indice, sorted(set(duplicados))


def publicar_corpus(control, publicado):
    """Copia a publicado/ solo datos utilizables; reportes y DIC parciales quedan en control/."""
    publicado.mkdir(parents=True, exist_ok=True)
    for p in publicado.iterdir():
        if p.is_file():
            p.unlink()
    copiados = []
    for p in sorted(control.glob("*.md")):
        if not p.name.upper().startswith(PREFIJO_REPORTE):
            copiados.append(shutil.copy2(p, publicado / p.name))
    for nombre in PUBLICADOS_TAL_CUAL:
        p = control / nombre
        if p.is_file():
            copiados.append(shutil.copy2(p, publicado / nombre))
    indice, duplicados = consolidar_indices(control, publicado)
    copiados.append(indice)
    return copiados, duplicados


def escribir_huellas(publicado):
    """SHA-256 de cada archivo publicado; ``corpus.py verificar`` los recalcula para detectar cambios manuales."""
    lineas = [f"# convertir.py v{VERSION} · huella del código {huella()} · {datetime.datetime.now():%Y-%m-%d %H:%M}"]
    for p in sorted(publicado.iterdir()):
        if p.is_file() and p.name != ARCHIVO_HUELLAS:
            lineas.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}")
    (publicado / ARCHIVO_HUELLAS).write_text("\n".join(lineas) + "\n", encoding="utf-8")


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


def _cobertura(valor):
    return float((valor or "").replace("%", "").strip().replace(",", "."))


def _muestra(codigos, fraccion):
    """Muestra reproducible (siempre la misma para los mismos codigos) de una fraccion de los documentos."""
    n = math.ceil(fraccion * len(codigos)) if codigos and fraccion else 0
    return sorted(codigos, key=lambda c: hashlib.sha256(c.encode()).hexdigest())[:n]


def validar_publicacion(publicado, duplicados=(), revisados=frozenset(), muestra=MUESTRA_REVISION,
                        errores_contexto=(), control=None):
    """Valida inventario, indice, textos, cobertura y estructura del corpus publicado.

    - Problemas (REQUIERE REVISIÓN): codigos duplicados, documentos sin convertir o sin texto, texto
      del original que falta (cobertura < 100 %), palabras que no estan en el original y errores del contexto.
    - Revision visual (PENDIENTE DE REVISIÓN VISUAL): documentos con avisos de estructura y una muestra
      del ``muestra`` de los demas, hasta que su codigo este en revision_visual_ok.txt.
    """
    v = Validacion(duplicados=list(duplicados))
    indice_p, inv_p = publicado / ARCHIVO_INDICE, publicado / ARCHIVO_INVENTARIO
    filas = leer_csv(indice_p) if indice_p.is_file() else []
    inventario = inventario_activo(leer_csv(inv_p)) if inv_p.is_file() else []
    cod_indice = {(f.get("codigo") or "").upper() for f in filas if f.get("codigo")}
    cod_inv = {(f.get("codigo") or "").upper() for f in inventario if f.get("codigo")}
    if not filas:
        v.problemas.append("El índice consolidado está vacío.")
    if duplicados:
        v.problemas.append("Códigos duplicados: " + ", ".join(duplicados))
    if errores_contexto:
        v.problemas.append("Materiales de contexto que no se pudieron convertir: " + "; ".join(errores_contexto))
    faltan = sorted(cod_inv - cod_indice)
    sobran = sorted(c for c in cod_indice - cod_inv if not c.startswith("C-"))
    if faltan:
        v.problemas.append("Documentos inventariados sin convertir: " + ", ".join(faltan))
    sin_area = sorted((f.get("codigo") or "") for f in inventario if (f.get("departamento") or "") == AREA_SIN_ASIGNAR)
    if sin_area:
        v.problemas.append(f"Documentos sin área ({len(sin_area)}; códigos provisionales): escriba su área en "
                           f"{ARCHIVO_AREAS_DOCUMENTOS} y vuelva a construir. " + ", ".join(sin_area[:20])
                           + (" …" if len(sin_area) > 20 else ""))
    if sobran:
        v.avisos.append("Documentos fuera del inventario: " + ", ".join(sobran))
    cod_md = set()
    for p in publicado.glob("*.md"):
        cod_md.update(RE_DOC_MD.findall(p.read_text(encoding="utf-8", errors="replace")))
    sin_texto = sorted(cod_indice - cod_md)
    if sin_texto:
        v.problemas.append("Filas del índice sin texto Markdown: " + ", ".join(sin_texto))
    bajos, agregadas, no_publicables, escaneados = [], [], [], []
    revision = collections.OrderedDict()
    for f in filas:
        c = (f.get("codigo") or "").upper()
        try:
            if f.get("cobertura") and _cobertura(f["cobertura"]) < 100.0:
                bajos.append(f"{c} ({f['cobertura']})")
        except ValueError:
            v.problemas.append(f"Cobertura no interpretable: {c} = {f.get('cobertura')}")
        if (f.get("palabras_agregadas") or "").strip():
            agregadas.append(f"{c} ({f['palabras_agregadas'][:60]})")
        if AVISO_ESCANEADO in (f.get("detalle_avisos") or ""):
            escaneados.append(c)
        if (f.get("avisos_estructura") or "0").strip() not in ("", "0"):
            revision[c] = (f.get("detalle_avisos") or "")[:200]
        if estado_no_publicable(f.get("estado_documental", "")):
            no_publicables.append(f"{c} ({f.get('estado_documental')})")
    if bajos:
        v.problemas.append("Texto del original que no aparece en el Markdown (cobertura < 100 %): " + ", ".join(bajos))
    if agregadas:
        v.problemas.append("Palabras que no están en el original (posible texto corrupto): " + "; ".join(agregadas))
    if escaneados:
        v.problemas.append(f"Documentos con páginas escaneadas que no se pudieron leer ({len(escaneados)}; su texto no "
                           "está en el corpus): instale Tesseract con el idioma español y pytesseract, o use la "
                           "versión digital. " + ", ".join(escaneados))
    if no_publicables:
        v.avisos.append("Excluidos de las consultas por su estado documental: " + ", ".join(no_publicables))
    resto = sorted(c for c in cod_indice if c not in revision and not c.startswith("C-"))
    for c in _muestra(resto, muestra):
        revision[c] = f"muestra aleatoria ({muestra:.0%})"
    v.revision_visual = collections.OrderedDict((c, m) for c, m in revision.items() if c not in revisados)
    if control is not None:
        escribir_csv(control / ARCHIVO_REVISION, ["codigo", "motivo", "revisado"],
                     [{"codigo": c, "motivo": m, "revisado": "sí" if c in revisados else ""}
                      for c, m in revision.items()])
    v.documentos_inventariados = len(cod_inv)
    v.documentos_indexados = len(cod_indice)
    v.documentos_con_texto = len(cod_md & cod_indice)
    return v


def escribir_resumen_construccion(path, v, publicados):
    lineas = [
        "# Resumen de construcción del corpus", "",
        f"- Fecha: {datetime.datetime.now():%Y-%m-%d %H:%M}",
        f"- convertir.py: v{VERSION} · huella {huella()}",
        f"- Resultado: **{v.estado}**", "",
        f"- Documentos inventariados: {v.documentos_inventariados}",
        f"- Documentos indexados: {v.documentos_indexados}",
        f"- Documentos con texto: {v.documentos_con_texto}",
        f"- Archivos publicados: {len(publicados)}", "",
    ]
    if v.problemas:
        lineas += ["## Problemas", ""] + ["- " + x for x in v.problemas] + [""]
    if v.revision_visual:
        lineas += ["## Revisión visual pendiente", "",
                   "Abra cada documento original junto a su Markdown. Cuando esté correcto, agregue su código a "
                   f"`{ARCHIVO_REVISADOS}` (uno por línea) y vuelva a ejecutar `construir`.", "",
                   "| Código | Motivo |", "|---|---|"]
        lineas += [f"| {c} | {esc_celda(m)} |" for c, m in v.revision_visual.items()] + [""]
    if v.avisos:
        lineas += ["## Avisos", ""] + ["- " + x for x in v.avisos] + [""]
    lineas += ["## Carpetas", "",
               f"- `publicado/`: archivos que puede consumir el agente (con `{ARCHIVO_HUELLAS}`).",
               f"- `control/`: reportes, diccionarios parciales, `{ARCHIVO_REVISION}` y evidencia de QA.", ""]
    path.write_text("\n".join(lineas), encoding="utf-8")
