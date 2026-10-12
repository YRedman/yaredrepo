"""Publicacion del corpus: indice consolidado, copia limpia a publicado/ y validacion."""

import collections
import datetime
import re
import shutil
from dataclasses import dataclass, field
from typing import List

from .. import VERSION
from ..comun.archivos import escribir_csv, leer_csv
from ..comun.esquema import (ARCHIVO_CATALOGO, ARCHIVO_INDICE, ARCHIVO_INVENTARIO, COLUMNAS_INDICE, PATRON_CODIGO,
                             PREFIJO_DIC, PREFIJO_REPORTE)

RE_DOC_MD = re.compile(rf"^## \[({PATRON_CODIGO})\]", re.M)
# Archivos que genera la conversion en control/ y que se regeneran en cada construccion.
PATRONES_GENERADOS = ("P_*.md", "D_*.md", "contexto.md", f"{PREFIJO_DIC}*.csv", f"{PREFIJO_REPORTE}*.md")


@dataclass
class Validacion:
    documentos_inventariados: int = 0
    documentos_indexados: int = 0
    documentos_con_texto: int = 0
    duplicados: List[str] = field(default_factory=list)
    problemas: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)

    @property
    def listo(self):
        return not self.problemas and not self.duplicados

    @property
    def estado(self):
        return "LISTO PARA PUBLICAR" if self.listo else "REQUIERE REVISIÓN"


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
    for nombre in (ARCHIVO_INVENTARIO, ARCHIVO_CATALOGO):
        p = control / nombre
        if p.is_file():
            copiados.append(shutil.copy2(p, publicado / nombre))
    indice, duplicados = consolidar_indices(control, publicado)
    copiados.append(indice)
    return copiados, duplicados


def _cobertura(valor):
    return float((valor or "").replace("%", "").strip().replace(",", "."))


def validar_publicacion(publicado, duplicados=()):
    """Valida inventario, indice, textos y cobertura del corpus publicado."""
    v = Validacion(duplicados=list(duplicados))
    indice_p, inv_p = publicado / ARCHIVO_INDICE, publicado / ARCHIVO_INVENTARIO
    filas = leer_csv(indice_p) if indice_p.is_file() else []
    inventario = leer_csv(inv_p) if inv_p.is_file() else []
    cod_indice = {(f.get("codigo") or "").upper() for f in filas if f.get("codigo")}
    cod_inv = {(f.get("codigo") or "").upper() for f in inventario if f.get("codigo")}
    if not filas:
        v.problemas.append("El índice consolidado está vacío.")
    if duplicados:
        v.problemas.append("Códigos duplicados: " + ", ".join(duplicados))
    faltan = sorted(cod_inv - cod_indice)
    sobran = sorted(c for c in cod_indice - cod_inv if not c.startswith("C-"))
    if faltan:
        v.problemas.append("Documentos inventariados sin convertir: " + ", ".join(faltan))
    if sobran:
        v.avisos.append("Documentos fuera del inventario: " + ", ".join(sobran))
    cod_md = set()
    for p in publicado.glob("*.md"):
        cod_md.update(RE_DOC_MD.findall(p.read_text(encoding="utf-8", errors="replace")))
    sin_texto = sorted(cod_indice - cod_md)
    if sin_texto:
        v.problemas.append("Filas del índice sin texto Markdown: " + ", ".join(sin_texto))
    bajos = []
    for f in filas:
        try:
            if f.get("cobertura") and _cobertura(f["cobertura"]) < 100.0:
                bajos.append(f.get("codigo", ""))
        except ValueError:
            v.avisos.append(f"Cobertura no interpretable: {f.get('codigo', '')} = {f.get('cobertura')}")
    if bajos:
        v.avisos.append("Cobertura menor a 100 %: " + ", ".join(bajos))
    v.documentos_inventariados = len(cod_inv)
    v.documentos_indexados = len(cod_indice)
    v.documentos_con_texto = len(cod_md & cod_indice)
    return v


def escribir_resumen_construccion(path, v, publicados):
    lineas = [
        "# Resumen de construcción del corpus", "",
        f"- Fecha: {datetime.datetime.now():%Y-%m-%d %H:%M}",
        f"- convertir.py: v{VERSION}",
        f"- Resultado: **{v.estado}**", "",
        f"- Documentos inventariados: {v.documentos_inventariados}",
        f"- Documentos indexados: {v.documentos_indexados}",
        f"- Documentos con texto: {v.documentos_con_texto}",
        f"- Archivos publicados: {len(publicados)}", "",
    ]
    if v.problemas:
        lineas += ["## Problemas", ""] + ["- " + x for x in v.problemas] + [""]
    if v.avisos:
        lineas += ["## Avisos", ""] + ["- " + x for x in v.avisos] + [""]
    lineas += ["## Carpetas", "", "- `publicado/`: archivos que puede consumir el agente.",
               "- `control/`: reportes, diccionarios parciales y evidencia de QA.", ""]
    path.write_text("\n".join(lineas), encoding="utf-8")
