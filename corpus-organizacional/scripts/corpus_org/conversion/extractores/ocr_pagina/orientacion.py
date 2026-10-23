"""Orientacion de una pagina o imagen: inclinacion, giro de 90° y espejo (se prueba cual se lee mejor)."""

import re

from .constantes import CONFIANZA_OBJETIVO
from .geometria import bordes_de_imagen
from .texto import leer_tesseract


def _nitidez(img, angulo):
    """Puntaje de lo horizontales que quedan las lineas largas al rotar ``angulo`` grados."""
    import numpy as np
    filas = bordes_de_imagen(np.asarray(img.rotate(angulo, fillcolor=255)), 0).mean(axis=1)
    return float((filas ** 4).sum())


def angulo_inclinacion(img, maximo=2.0):
    """Ángulo (grados, sentido de PIL.rotate) que endereza una página escaneada torcida.

    Se elige el ángulo que hace más nítidas las filas de tinta: la suma de los cuadrados de la tinta
    por fila es máxima cuando renglones y líneas quedan horizontales. Primero una búsqueda gruesa
    sobre la imagen reducida y después una fina alrededor del mejor valor.
    """
    chica, media = img.reduce(4), img.reduce(2)
    gruesos = [k * 0.25 for k in range(-int(maximo / 0.25), int(maximo / 0.25) + 1)]
    base = max(gruesos, key=lambda a: _nitidez(chica, a))
    finos = [base + k * 0.025 for k in range(-10, 11)]
    return max(finos, key=lambda a: _nitidez(media, a))


def giro_por_osd(img, pytesseract):
    """Grados (0, 90, 180, 270) que hay que girar la pagina para que el texto quede derecho, segun el OSD de
    Tesseract. 0 si no esta disponible (necesita osd.traineddata) o no hay certeza."""
    try:
        osd = pytesseract.image_to_osd(img, config="--psm 0")
    except Exception:
        return 0
    giro = re.search(r"Rotate:\s*(\d+)", osd)
    conf = re.search(r"Orientation confidence:\s*([\d.]+)", osd)
    if giro and conf and float(conf.group(1)) >= 2.0 and int(giro.group(1)) in (90, 180, 270):
        return int(giro.group(1))
    return 0


ORIENTACIONES = ((0, False), (0, True), (180, False), (180, True), (90, False), (270, False), (90, True), (270, True))
LADO_PRUEBA = 1200             # px: la imagen de prueba se reduce a este lado mayor
MIN_PALABRAS_PRUEBA = 8        # palabras fiables que debe leer una orientacion para preferirla
PALABRAS_PRUEBA_SEGURA = 30    # con tantas palabras fiables y el factor de abajo no se siguen probando orientaciones
FACTOR_PRUEBA = 2.0            # y su puntaje debe superar este multiplo del de la orientacion actual


def _puntaje_texto(palabras):
    """(suma de la confianza, cantidad) de las palabras de 3+ letras con confianza >= 80: una pagina mal orientada da
    pocas palabras fiables (letras al reves o reflejadas se leen como basura de baja confianza)."""
    buenas = [p[5] for p in palabras if p[5] >= CONFIANZA_OBJETIVO and len(re.findall(r"[^\W\d_]", p[0])) >= 3]
    return sum(buenas), len(buenas)


def orientacion_por_prueba(gris, idioma, pytesseract):
    """(giro, espejo) con que se lee mejor una imagen en grises, o (0, False) si la actual ya es la mejor.

    Lee una banda central de la imagen reducida en las 8 orientaciones (4 giros, con y sin reflejo), empezando por las
    mas probables (reflejada, al reves), y se queda con la de mayor puntaje fiable. Solo cambia de orientacion si da al
    menos MIN_PALABRAS_PRUEBA palabras fiables y FACTOR_PRUEBA veces el puntaje de la actual: no se cambia por ruido."""
    escala = min(1.0, LADO_PRUEBA / max(gris.width, gris.height))
    chica = gris.resize((max(1, int(gris.width * escala)), max(1, int(gris.height * escala)))) if escala < 1.0 else gris
    resultados = {}
    for giro, espejo in ORIENTACIONES:
        img = orientar(chica, giro, espejo)
        banda = img.crop((0, int(img.height * 0.15), img.width, int(img.height * 0.75)))      # sin margenes ni pie
        try:
            resultados[(giro, espejo)] = _puntaje_texto(leer_tesseract(banda, idioma, pytesseract, psm=6))
        except Exception:
            resultados[(giro, espejo)] = (0.0, 0)
        puntaje, palabras = resultados[(giro, espejo)]
        if (giro, espejo) != (0, False) and palabras >= PALABRAS_PRUEBA_SEGURA and \
                puntaje >= FACTOR_PRUEBA * max(resultados[(0, False)][0], 1.0):
            return giro, espejo                  # una orientacion clara: no hace falta probar las demas
    actual = resultados[(0, False)][0]
    mejor = max(resultados, key=lambda k: resultados[k][0])
    if mejor != (0, False) and resultados[mejor][1] >= MIN_PALABRAS_PRUEBA and resultados[mejor][0] >= FACTOR_PRUEBA * max(actual, 1.0):
        return mejor
    return 0, False


def orientar(img, giro=0, espejo=False):
    """La imagen girada ``giro`` grados (sentido de las agujas del reloj: 0, 90, 180, 270) y, si ``espejo``, reflejada
    de izquierda a derecha (un escaneo hecho «por detras» o con la camara frontal)."""
    from PIL import ImageOps
    if giro:
        img = img.rotate(-giro, expand=True, fillcolor=255)
    return ImageOps.mirror(img) if espejo else img
