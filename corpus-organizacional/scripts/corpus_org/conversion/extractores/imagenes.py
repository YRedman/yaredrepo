"""Texto dentro de imagenes incrustadas en un documento de Office (captura pegada en una hoja, foto de una diapositiva)."""

import io
import re

from .maquetacion import agrupar_filas, bloques_desde_items
from .ocr_pagina import CONFIANZA_OBJETIVO

MIN_PALABRAS_IMAGEN = 6      # palabras de 4+ letras para considerar que una imagen trae texto
LADO_MIN_PX = 300            # una imagen mas chica (icono, vineta) no se lee


def hash_imagen(datos):
    import hashlib
    return hashlib.md5(datos).hexdigest()


def es_imagen_de_contenido(datos):
    """False para iconos y logos chicos (menos de LADO_MIN_PX en alguno de sus lados) o ilegibles."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(datos)) as im:
            return min(im.size) >= LADO_MIN_PX
    except Exception:
        return False


def texto_de_imagen(d, bloques, donde, n_unidad, datos):
    """Lee con OCR el texto de una imagen y lo agrega a ``bloques`` bajo una marca.

    ``donde``: «la hoja «X»» o «la diapositiva 3» (para la marca); ``n_unidad``: numero de hoja o diapositiva, que
    se anota como pagina leida con OCR. Sin OCR o sin texto legible deja solo la marca."""
    from .ocr import configurar_pytesseract, idioma_ocr
    marca = f"[IMAGEN EN {donde}"
    idioma = idioma_ocr()
    if not idioma:
        d.imagenes_omitidas += 1
        bloques.append({"k": "marca", "texto": marca + ": no se pudo leer (falta OCR); ver el original]"})
        return
    try:
        from PIL import Image
        from .ocr_pagina import leer_imagen
        from .pdf import palabras_ocr
        res = leer_imagen(Image.open(io.BytesIO(datos)), idioma, configurar_pytesseract())
    except Exception as e:
        d.notas.append(f"OCR de una imagen falló en {donde}: {e}")
        bloques.append({"k": "marca", "texto": marca + "; ver el original]"})
        return
    utiles = sum(1 for L in res.lineas for _ in re.findall(r"[^\W\d_]{4,}", L["texto"]))
    if utiles < MIN_PALABRAS_IMAGEN:
        d.diagramas.append(n_unidad)
        bloques.append({"k": "marca", "texto": marca + "; sin texto legible, ver el original]"})
        return
    d.paginas_ocr.append(n_unidad)
    d.idioma_ocr = idioma
    d.confianzas_ocr += res.confianzas
    d.crudo_ocr |= palabras_ocr([L["texto"] for L in res.lineas])
    bloques.append({"k": "marca", "texto": marca + f": texto leído con OCR (confianza {res.confianza:.0f} %), "
                                                   "revisar contra el original]"})
    filas = agrupar_filas(res.lineas)
    for f in filas:
        f["pagina"] = 0
        f["ocr"] = True
    bloques += bloques_desde_items(filas)
    if res.confianza < CONFIANZA_OBJETIVO:
        d.avisos.append(f"la imagen de {donde} se leyó con {res.confianza:.0f} % de confianza "
                        f"(menos de {CONFIANZA_OBJETIVO:.0f} %): revise el original")
