"""Lo que el informe lee de una construccion: el indice, el inventario, la revision visual, los tiempos y el log."""

import collections
import datetime
import json
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from ...comun.archivos import leer_csv_opcional
from ...comun.esquema import (ARCHIVO_DATOS, ARCHIVO_INDICE, ARCHIVO_INVENTARIO, ARCHIVO_LOG, ARCHIVO_RESUMEN,
                              ARCHIVO_REVISION, ARCHIVO_TIEMPOS)
from ...comun.estructura import CARPETA_PUBLICADA, rutas_publicadas
from ...comun.tipos import TIPOS_AREA
from .elementos import numero

ESTADOS = {
    "LISTO PARA PUBLICAR": ("ok", "Listo para publicar"),
    "PENDIENTE DE REVISIÓN VISUAL": ("aviso", "Pendiente de revisión visual"),
    "REQUIERE REVISIÓN": ("error", "Requiere revisión"),
}


def _leer_csv(ruta):
    try:
        return leer_csv_opcional(ruta)
    except (OSError, ValueError):
        return []


def _leer_json(ruta):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8")) if Path(ruta).is_file() else {}
    except ValueError:
        return {}


def _leer_texto(ruta):
    return Path(ruta).read_text(encoding="utf-8", errors="replace") if Path(ruta).is_file() else ""


def _estado_de(texto):
    m = re.search(r"Resultado:\s*\**\s*([A-ZÁÉÍÓÚÑ ]+?)\s*\**\s*$", texto or "", re.M)
    return m.group(1).strip() if m else ""


def _lineas_de(texto, prefijo):
    return [l[len(prefijo):].strip() for l in (texto or "").splitlines() if l.startswith(prefijo)]


def tipo_de(fila):
    return fila["codigo"].split("-")[0]


@dataclass
class DatosInforme:
    """Todo lo que necesitan las secciones del informe, leido una sola vez."""
    datos: dict                       # construccion.json: version, fecha, carpetas de los originales
    texto_log: str
    resumen: str
    indice: list                      # filas de indice_corpus.csv
    inventario: list
    revision: list
    tiempos: dict = field(default_factory=dict)      # codigo -> segundos

    @classmethod
    def leer(cls, raiz_salida, texto_log=None):
        raiz = Path(raiz_salida)
        control = raiz / "control"
        rutas = rutas_publicadas(raiz / CARPETA_PUBLICADA)
        if texto_log is None:
            texto_log = _leer_texto(control / ARCHIVO_LOG)
        return cls(datos=_leer_json(control / ARCHIVO_DATOS), texto_log=texto_log,
                   resumen=_leer_texto(raiz / ARCHIVO_RESUMEN), indice=_leer_csv(rutas.indice / ARCHIVO_INDICE),
                   inventario=_leer_csv(control / ARCHIVO_INVENTARIO), revision=_leer_csv(control / ARCHIVO_REVISION),
                   tiempos={f["codigo"]: numero(f.get("segundos")) for f in _leer_csv(control / ARCHIVO_TIEMPOS)})

    # -- estado -------------------------------------------------------------------------------------------------

    @property
    def estado(self):
        """(clase CSS, etiqueta) del resultado de la construccion."""
        texto = _estado_de(self.texto_log) or _estado_de(self.resumen) or "DESCONOCIDO"
        return ESTADOS.get(texto, ("aviso", texto.capitalize()))

    @property
    def fecha(self):
        return self.datos.get("fecha") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    @cached_property
    def errores(self):
        return _lineas_de(self.texto_log, "ERROR: ") or _lineas_de(self.resumen, "- ERROR: ")

    @cached_property
    def avisos(self):
        avisos = _lineas_de(self.texto_log, "AVISO: ")
        if avisos:
            return avisos
        return [l.strip("- ").strip() for l in self.resumen.splitlines() if l.startswith("- ") and "aviso" in l.lower()]

    # -- documentos ---------------------------------------------------------------------------------------------

    @cached_property
    def por_tipo(self):
        return collections.Counter(tipo_de(f) for f in self.indice)

    @cached_property
    def areas(self):
        return sorted({(f["codigo_departamento"], f["departamento"]) for f in self.indice if tipo_de(f) in TIPOS_AREA})

    @cached_property
    def con_ocr(self):
        return [f for f in self.indice if (f.get("paginas_ocr") or "").strip()]

    @cached_property
    def pendientes(self):
        return [f for f in self.revision if not (f.get("revisado") or "").strip()]

    @cached_property
    def cobertura_minima(self):
        return min((numero(f.get("cobertura"), 100.0) for f in self.indice), default=100.0)

    @property
    def segundos_total(self):
        return self.datos.get("segundos_total") or sum(self.tiempos.values())

    @cached_property
    def por_codigo(self):
        return {f["codigo"]: f for f in self.indice}
