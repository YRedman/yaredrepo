"""Inventario maestro: codigos de departamento, numeracion de documentos y materiales de contexto.

- ``lista``: entrada (lista.txt y areas.csv).  - ``departamentos``: codigos de 3 letras y numeracion.
- ``claves``: identidad de un documento.  - ``construccion``: el inventario maestro.
- ``equivalencias``: migracion de codigos anteriores e inventario base.  - ``contexto``: carpeta de contexto.
"""

from .claves import clave_documento, quitar_duplicados
from .construccion import construir_inventario, inventario_provisional
from .contexto import (clasificar_material, documentos_de_area_en_contexto, inventario_contexto, quitar_copias_contexto,
                       tipo_de_contexto)
from .departamentos import candidatos_codigo, leer_catalogo_codigos
from .equivalencias import escribir_equivalencias, leer_base, leer_equivalencias, migrar_fila
from .lista import actualizar_plantilla_areas, leer_areas, localizar_areas, parsear_lista
from .modelo import RE_CODIGO_DEP, Inventario, InventarioBase

__all__ = [
    "RE_CODIGO_DEP", "Inventario", "InventarioBase", "actualizar_plantilla_areas", "candidatos_codigo",
    "clasificar_material", "clave_documento", "construir_inventario", "documentos_de_area_en_contexto",
    "escribir_equivalencias", "inventario_contexto", "inventario_provisional", "leer_areas", "leer_base",
    "leer_catalogo_codigos", "leer_equivalencias", "localizar_areas", "migrar_fila", "parsear_lista",
    "quitar_copias_contexto", "quitar_duplicados", "tipo_de_contexto"]
