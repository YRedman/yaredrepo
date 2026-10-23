"""Analisis de un documento extraido: secciones, campos clave, actividades y codigos citados."""

from ..configuracion import BLOQUES_INICIALES_METADATOS, CAMPOS_CLAVE
from ..metadatos import extraer_metadatos
from ..modelo import Analisis
from .actividades import actividades_del_desarrollo
from .agrupacion import separar_secciones
from .campos import campos_de_secciones, campos_por_etiqueta, campos_por_relacionamiento, nombre_por_titulo
from .citas import codigos_citados
from .diagramas import sustituir_diagramas
from .estructura import avisos_de_estructura


def analizar(doc, tipo):
    """Devuelve ``(bloques_publicables, Analisis)`` sin modificar ``doc``."""
    a = Analisis()
    bloques = sustituir_diagramas(doc.bloques, a) if tipo == "P" else list(doc.bloques)
    bloques, secciones = separar_secciones(bloques, tipo, a)
    a.campos = campos_de_secciones(secciones)
    if tipo == "D":
        campos_por_etiqueta(bloques, a.campos)
        campos_por_relacionamiento(bloques, a.campos)
        nombre_por_titulo(bloques, a.campos)
    a.subprocedimientos = [b["texto"] for _t, campo, bs in secciones if campo == "desarrollo"
                           for b in bs if b["k"] == "h"]
    a.titulos = [s[0] for s in secciones]
    a.faltantes = [nombre for campo, nombre in CAMPOS_CLAVE.get(tipo, []) if not a.campos.get(campo, "").strip()]
    # En materiales de contexto (glosarios, organigramas) las tablas "Etiqueta | Valor" son contenido,
    # no metadatos del documento: ahi solo se lee el encabezado.
    iniciales = [] if tipo == "C" else bloques[:BLOQUES_INICIALES_METADATOS]
    a.metadatos = extraer_metadatos(doc.encabezado, iniciales)
    a.actividades = actividades_del_desarrollo(secciones) if tipo == "P" else []
    a.codigos_citados = codigos_citados(doc.encabezado, bloques, a.metadatos.codigo_interno)
    a.avisos += avisos_de_estructura(bloques, len(doc.diagramas), doc.hoja_de_calculo)
    return bloques, a
