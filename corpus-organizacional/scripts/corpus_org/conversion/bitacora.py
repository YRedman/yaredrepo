"""Lo que una corrida deja escrito de si misma: el log de la consola, los datos de la construccion y los tiempos."""

import io
import json
import time
from pathlib import Path

from .. import VERSION
from ..comun.archivos import escribir_csv, leer_csv
from ..comun.esquema import ARCHIVO_DATOS, ARCHIVO_LOG, ARCHIVO_TIEMPOS

COLUMNAS_TIEMPOS = ["codigo", "archivo", "ruta_original", "segundos", "paginas", "paginas_ocr", "confianza_ocr", "estado"]
DOCUMENTOS_LENTOS_MOSTRADOS = 5


class Tee:
    """Escribe en la consola y guarda una copia del texto (el log que luego se publica como informe HTML)."""

    def __init__(self, flujo):
        self.flujo, self.copia = flujo, io.StringIO()

    def write(self, texto):
        self.copia.write(texto)
        return self.flujo.write(texto)

    def flush(self):
        self.flujo.flush()

    def __getattr__(self, nombre):
        return getattr(self.flujo, nombre)

    @property
    def texto(self):
        return self.copia.getvalue()


def guardar_bitacora(control, texto_log, entrada, contexto, inicio):
    """Escribe control/log_construccion.txt y control/construccion.json (de donde el informe toma la version, la
    fecha y las carpetas de los originales)."""
    control = Path(control)
    control.mkdir(parents=True, exist_ok=True)
    (control / ARCHIVO_LOG).write_text(texto_log, encoding="utf-8")
    datos = {"version": VERSION, "fecha": time.strftime("%Y-%m-%d %H:%M"), "entrada": str(entrada),
             "contexto": str(contexto) if contexto else "", "segundos_total": round(time.time() - inicio, 1)}
    (control / ARCHIVO_DATOS).write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def _fila_de_tiempo(r):
    d = r.doc
    return {"codigo": r.codigo, "archivo": r.archivo, "ruta_original": r.ruta, "segundos": f"{r.segundos:.1f}",
            "paginas": (d.paginas if d else "") or "", "paginas_ocr": len(d.paginas_ocr) if d else "",
            "confianza_ocr": f"{d.confianza_ocr:.1f}" if d and d.confianza_ocr is not None else "",
            "estado": r.estado}


def registrar_tiempos(salida, documentos, anexar=False):
    """Escribe control/tiempos_conversion.csv (lo que tardo cada documento) y muestra los mas lentos."""
    ruta = Path(salida) / ARCHIVO_TIEMPOS
    previas = leer_csv(ruta) if anexar and ruta.is_file() else []
    escribir_csv(ruta, COLUMNAS_TIEMPOS, previas + [_fila_de_tiempo(r) for r in documentos])
    lentos = sorted((r for r in documentos if r.segundos), key=lambda r: -r.segundos)[:DOCUMENTOS_LENTOS_MOSTRADOS]
    if lentos:
        total = sum(r.segundos for r in documentos)
        print()
        print("Documentos más lentos (segundos): " + " · ".join(f"{r.codigo} {r.segundos:.0f} s" for r in lentos))
        print(f"Tiempo de conversión sumado de los documentos: {total:.0f} s en {len(documentos)} documentos "
              f"({total / max(len(documentos), 1):.1f} s en promedio).")
