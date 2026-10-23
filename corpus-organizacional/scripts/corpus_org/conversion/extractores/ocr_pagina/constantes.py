"""Umbrales compartidos por las partes del OCR."""

TIEMPO_MAX_MEJORA = 150.0   # segundos por pagina o imagen para seguir probando tratamientos
CONFIANZA_OBJETIVO = 80.0   # confianza media de Tesseract que debe alcanzar cada pagina (calidad antes que velocidad)
FONDO_OSCURO = 175          # gris medio de una celda con relleno de color
CONFIANZA_RELECTURA = 60    # confianza media minima para aceptar la relectura de una celda
MIN_PALABRAS_SOSPECHA = 20     # con menos palabras leidas (una foto, una hoja casi vacia) no se prueban las orientaciones
