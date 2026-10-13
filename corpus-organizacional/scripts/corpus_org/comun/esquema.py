"""Contrato de datos entre la conversion y la consulta.

Todo lo que ``convertir.py`` escribe y ``corpus.py`` lee se define aqui una
sola vez, para que ambos scripts no puedan desalinearse.
"""

import re

from .texto import norm
from .tipos import (AREA_GENERAL, PATRON_CODIGO, TIPOS_AREA, area_de, tipo_desde_texto,  # noqa: F401
                    tipo_de_codigo)

# nombres de comun/tipos.py que el resto del paquete importa desde aqui
_REEXPORTADOS = (AREA_GENERAL, area_de, tipo_desde_texto, tipo_de_codigo)

# Codigos del corpus: TTT-AAA-NN (DES-SEG-01, PRD-SEG-01, POL-GEN-01, ORG-GEN-01). Ver comun/tipos.py.
RE_CODIGO = re.compile(rf"^{PATRON_CODIGO}$", re.I)
RE_TITULO_DOC = re.compile(rf"^## \[({PATRON_CODIGO})\]\s*(.*)$")
RE_SECCION = re.compile(rf"^(#{{3,6}})\s+(?:\[{PATRON_CODIGO}\]\s*)?(.*)$")

INICIO_TITULO_ENCABEZADO_PIE = "Datos de encabezado y pie"
TITULO_ENCABEZADO_PIE = INICIO_TITULO_ENCABEZADO_PIE + " del documento original"
MARCA_COMBINADA = " [CELDA COMBINADA]"
NO_ESPECIFICADO = "[NO ESPECIFICADO]"
RE_MARCAS = re.compile(r"\[(?:NO ESPECIFICADO|DIAGRAMA[^\]]*|ORGANIGRAMA[^\]]*|IMAGEN[^\]]*|CELDA COMBINADA|NOTA AL PIE[^\]]*|"
                       r"CUADRO DE TEXTO|TEXTO OCR[^\]]*|PÁGINA ESCANEADA[^\]]*|ILEGIBLE|"
                       rf"{PATRON_CODIGO})\]")

# Columnas del indice (DIC_*.csv parciales e indice_corpus.csv consolidado).
COLUMNAS_INDICE = [
    "codigo", "tipo", "codigo_departamento", "departamento", "nombre", "archivo_origen", "codigo_interno",
    "version", "estado_documental", "fecha_vigencia", "propietario", "responsable", "macroproceso", "proceso",
    "proposito_literal", "nombre_puesto", "reporta_a", "supervisa_a", "secciones", "actividades",
    "subprocedimientos", "codigos_citados", "campos_no_especificados", "paginas", "palabras", "cobertura",
    "archivo_md", "linea_inicio", "linea_fin",
    # v3.3: control de calidad por documento (al final para no mover las columnas anteriores)
    "palabras_agregadas", "avisos_estructura", "detalle_avisos",
    # v3.5: lectura OCR (paginas escaneadas y confianza media de Tesseract, 0-100)
    "paginas_ocr", "confianza_ocr",
    # v4.0: area que emite una politica o protocolo (si el documento la trae)
    "area_propietaria",
]
SEPARADOR_LISTA = " | "

ARCHIVO_INDICE = "indice_corpus.csv"
ARCHIVO_INVENTARIO = "inventario_maestro.csv"
# materiales de contexto (documentos generales ORG-GEN-01...): codigos estables entre construcciones
ARCHIVO_INVENTARIO_CONTEXTO = "inventario_contexto.csv"
ARCHIVO_CATALOGO = "catalogo.csv"
ARCHIVO_RESUMEN = "RESUMEN_CONSTRUCCION.md"
ARCHIVO_HUELLAS = "huellas.sha256"
ARCHIVO_KPIS = "kpis.csv"
ARCHIVO_AREAS_EXTRA = "areas_extra.csv"
ARCHIVO_REVISADOS = "revision_visual_ok.txt"
ARCHIVO_REVISION = "revision_visual.csv"
# Area de cada documento que no esta en una carpeta de area (entrada\Descriptivos\archivo.pdf).
ARCHIVO_AREAS_DOCUMENTOS = "areas.csv"
AREA_SIN_ASIGNAR = "Sin Área"
# Aviso de un PDF con paginas escaneadas que no se pudieron leer (no hay OCR): su texto no esta en el corpus.
AVISO_ESCANEADO = "páginas escaneadas sin texto"
# Un documento leido con OCR pasa a revision visual solo si la confianza media de Tesseract es menor.
CONFIANZA_OCR_REVISION = 85.0
PREFIJO_DIC = "DIC_"
PREFIJO_REPORTE = "REPORTE_"
COLUMNAS_INVENTARIO = ["codigo", "tipo", "codigo_departamento", "departamento", "archivo", "ruta_original",
                       "observaciones", "estado_inventario"]
ARCHIVO_EQUIVALENCIAS = "equivalencias_codigos.csv"
COLUMNAS_EQUIVALENCIAS = ["codigo_anterior", "codigo_nuevo"]
INVENTARIO_ACTIVO, INVENTARIO_RETIRADO = "ACTIVO", "RETIRADO"
# una columna por tipo de area (DES, PRD, PRO, POL...) con la cantidad de documentos
COLUMNAS_CATALOGO = ["departamento", "codigo"] + list(TIPOS_AREA)

# Estados documentales que no se publican por defecto.
ESTADOS_NO_PUBLICABLES = ("borrador", "sustituido", "obsoleto", "inactivo", "no vigente", "cancelado", "anulado",
                          "derogado")


def estado_no_publicable(estado):
    """True si el estado documental indica que el documento no esta vigente.

    Compara por palabra completa al inicio del valor: 'Obsoleto' y 'No vigente desde 2023'
    son no publicables; 'Vigente' o un valor vacio no lo son.
    """
    n = norm(estado).strip(" .:;-")
    return any(n == e or n.startswith(e + " ") for e in ESTADOS_NO_PUBLICABLES)


def inventario_activo(filas):
    """Filas del inventario que deben existir: las RETIRADAS solo reservan su codigo."""
    return [f for f in filas if (f.get("estado_inventario") or INVENTARIO_ACTIVO).upper() != INVENTARIO_RETIRADO]
