"""Lectura de una pagina escaneada: OCR con la estructura de tablas reconstruida desde la imagen.

El OCR de Tesseract reconoce bien las palabras, pero una tabla escaneada sale como texto corrido
(las columnas se mezclan) y el texto claro sobre fondo de color se pierde. Aqui:

1. Se detectan en la imagen las lineas de las tablas (trazos finos horizontales y verticales) y los
   rellenos de color, y con ellos la cuadricula de celdas.
2. Cada palabra del OCR se ubica en su celda por su posicion; las demas quedan como lineas de texto.
3. Las celdas con fondo oscuro o de color se vuelven a leer recortadas, invertidas si el texto es
   claro y ampliadas.
4. La tabla de arriba con "Código", "Versión", "Vigencia" o "Página" es el encabezado del formato.
5. Se conserva la confianza de cada palabra para decidir que paginas necesitan revision.

Requiere numpy (deteccion de lineas); sin numpy se usa solo el OCR de texto corrido.

Partes: ``modelo`` (resultados), ``geometria`` (lineas y tablas de la imagen), ``texto`` (palabras y celdas),
``orientacion`` (giro, espejo e inclinacion), ``firmas``, ``recetas`` (mejoras de imagen), ``pagina`` (una pagina de
PDF) e ``imagen`` (una imagen suelta).
"""

from .constantes import CONFIANZA_OBJETIVO
from .firmas import es_etiqueta_de_firma
from .imagen import leer_imagen
from .pagina import MIN_PALABRAS_TEXTO, leer_pagina, leer_region

__all__ = ["CONFIANZA_OBJETIVO", "MIN_PALABRAS_TEXTO", "es_etiqueta_de_firma", "leer_imagen", "leer_pagina", "leer_region"]
