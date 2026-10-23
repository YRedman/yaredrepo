"""Imagenes de las paginas con texto: logos, firmas, diagramas y capturas cuyo texto se lee con OCR."""

import collections
import math
import re

from ..maquetacion import agrupar_filas
from ..ocr import configurar_pytesseract
from ..ocr_pagina import CONFIANZA_OBJETIVO, es_etiqueta_de_firma, leer_region
from .encabezados import MIN_REPETICION
from .lineas import dentro, palabras_ocr

MAX_IMAGENES_OCR = 30           # imagenes grandes por documento cuyo texto se lee con OCR
MIN_PALABRAS_IMAGEN = 6         # palabras de 4+ letras para considerar que una imagen trae texto
AREA_IMAGEN_GRANDE = 0.06       # fraccion de la pagina a partir de la cual una imagen es un diagrama
AREA_IMAGEN_MINIMA = 400        # puntos cuadrados: una imagen mas pequena no se menciona
DISTANCIA_ETIQUETA_FIRMA = 50   # puntos sobre la imagen donde puede estar su etiqueta de firma


def imagenes_por_pagina(pdf, n_paginas):
    """(imagenes de cada pagina, huellas de logos): un logo es una imagen repetida en la mayoria de las paginas."""
    info_img = []
    cuenta = collections.Counter()
    for page in pdf:
        try:
            info = page.get_image_info(hashes=True)
        except Exception:
            info = []
        info_img.append(info)
        cuenta.update({i.get("digest") for i in info if i.get("digest")})
    min_rep = max(2, math.ceil(MIN_REPETICION * n_paginas))
    logos = {k for k, c in cuenta.items() if n_paginas >= 2 and c >= min_rep}
    return info_img, logos


class ImagenesDePagina:
    """Agrega al documento las marcas (y el texto leido con OCR) de las imagenes de contenido de cada pagina."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.info_img, self.logos = imagenes_por_pagina(ctx.pdf, ctx.d.paginas)
        self.imagenes_leidas = 0
        self.firmas_ignoradas = []

    def _texto_de_imagen(self, i, rect):
        """(lineas, confianza) del texto que el OCR lee dentro de una imagen grande que no trae texto digital;
        None si no hay OCR, la imagen ya tiene texto digital encima o no se lee nada util."""
        ctx = self.ctx
        if not ctx.idioma_ocr() or self.imagenes_leidas >= MAX_IMAGENES_OCR:
            return None
        if sum(l["chars"] for l in ctx.paginas_lineas[i] if dentro(l, rect)) >= 20:
            return None
        self.imagenes_leidas += 1
        try:
            res = leer_region(ctx.pdf[i], rect, ctx.idioma_ocr(), configurar_pytesseract())
        except Exception as e:
            ctx.d.notas.append(f"OCR de una imagen falló en la página {i + 1}: {e}")
            return None
        if res is None or sum(1 for L in res.lineas for _ in re.findall(r"[^\W\d_]{4,}", L["texto"])) < MIN_PALABRAS_IMAGEN:
            return None
        return res

    def _es_firma(self, i, r):
        """True si la imagen ``r`` es el trazo de una firma: tiene al lado (a la misma altura) o encima (hasta 50 pt) una
        etiqueta de firma («Firma del Colaborador», «Director / Gerente Sr. / Gerente del área:»)."""
        return any(es_etiqueta_de_firma(l["texto"]) and l["y1"] >= r.y0 - DISTANCIA_ETIQUETA_FIRMA and l["y0"] <= r.y1 + 6
                   for l in self.ctx.paginas_lineas[i])

    def agregar(self, i, corte_sup, corte_inf, w, h):
        ctx = self.ctx
        for im in self.info_img[i]:
            r = ctx.fitz.Rect(im["bbox"])
            if im.get("digest") in self.logos:
                continue
            cy = (r.y0 + r.y1) / 2
            if cy < corte_sup or cy > corte_inf:
                continue
            if abs(r) > AREA_IMAGEN_MINIMA and self._es_firma(i, r):
                # una firma manuscrita no es contenido: ni se lee con OCR ni cuenta como imagen o diagrama
                if i + 1 not in self.firmas_ignoradas:
                    self.firmas_ignoradas.append(i + 1)
                    ctx.d.notas.append(f"Página {i + 1}: se ignoró una firma manuscrita (imagen junto a una etiqueta de firma).")
                continue
            if abs(r) > AREA_IMAGEN_GRANDE * w * h:
                self._diagrama(i, r)
            elif abs(r) > AREA_IMAGEN_MINIMA:
                ctx.d.imagenes_omitidas += 1
                ctx.marca(i, r.y0, r.x0, "[IMAGEN OMITIDA]")

    def _diagrama(self, i, r):
        """Una imagen grande: se marca y, si trae texto legible, se agrega el que lee el OCR."""
        ctx = self.ctx
        ctx.d.diagramas.append(i + 1)
        lectura = self._texto_de_imagen(i, r)
        if lectura is not None and lectura.confianza >= CONFIANZA_OBJETIVO:
            ctx.marca(i, r.y0, r.x0, f"[DIAGRAMA O IMAGEN: ver página {i + 1} del documento original; texto leído "
                                     f"de la imagen con OCR (confianza {lectura.confianza:.0f} %), revisar "
                                     "contra el original]")
            for f in agrupar_filas(lectura.lineas):
                f["pagina"] = i
                f["ocr"] = True
                ctx.items.append((i, f["y0"], f["x0"], f))
            ctx.d.crudo_ocr |= palabras_ocr([L["texto"] for L in lectura.lineas])
            ctx.d.notas.append(f"Página {i + 1}: texto leído de una imagen con OCR ({lectura.mejora}; "
                               f"confianza {lectura.confianza:.0f} %).")
            return
        if lectura is not None:
            ctx.d.avisos.append(f"p.{i + 1}: una imagen trae texto poco legible (OCR {lectura.confianza:.0f} % < "
                                f"{CONFIANZA_OBJETIVO:.0f} % aun mejorando la imagen): revise el original")
        ctx.marca(i, r.y0, r.x0, f"[DIAGRAMA O IMAGEN: ver página {i + 1} del documento original]")
