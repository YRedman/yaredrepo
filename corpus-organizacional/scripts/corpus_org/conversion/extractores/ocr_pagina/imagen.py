"""OCR de una imagen suelta (captura, foto, diagrama): por teselas y con las etiquetas agrupadas."""

import collections
import re
import time

from ....comun.texto import nfc
from .constantes import CONFIANZA_OBJETIVO, MIN_PALABRAS_SOSPECHA, TIEMPO_MAX_MEJORA
from .modelo import PaginaOCR
from .orientacion import orientacion_por_prueba, orientar
from .pagina import elegir_lectura
from .recetas import receta_nitidez, RECETAS
from .texto import leer_tesseract, lineas_de_datos, sin_duplicadas


PROPORCION_RUIDO = 0.8         # en una imagen, descartar tantas palabras como se conservan hace sospechar de la orientacion
LADO_MIN_IMAGEN = 2000         # px: una imagen pequena (captura, foto) se amplia hasta este lado mayor antes del OCR
AMPLIACION_MAX = 4
TESELA = (1100, 800, 150)      # ancho, alto y solape (px) de las teselas con que se lee un diagrama
ESCALA_TESELA = 2.5            # el texto de un diagrama de flujo es chico: cada tesela se amplia antes del OCR
CONF_PALABRA_MIN = 60          # una palabra con menos confianza en una imagen es ruido de iconos y lineas


def _validas(palabras):
    """(palabras que se conservan, cantidad descartada): confianza >= CONF_PALABRA_MIN y alguna letra o numero."""
    buenas = [p for p in palabras if p[5] >= CONF_PALABRA_MIN and re.search(r"[^\W_]", p[0])
              and (len(p[0]) > 1 or p[0].isdigit() or p[0].lower() in "aeoyuz")]
    return buenas, len(palabras) - len(buenas)


def _por_teselas(gris, idioma, pytesseract, receta=None, escala=ESCALA_TESELA):
    """Palabras de una imagen grande leida por teselas ampliadas (psm 11, texto disperso); coordenadas de ``gris``."""
    from PIL import Image
    ancho, alto, solape = TESELA
    palabras = []
    for y in range(0, max(1, gris.height - solape), alto - solape):
        for x in range(0, max(1, gris.width - solape), ancho - solape):
            t = gris.crop((x, y, min(x + ancho, gris.width), min(y + alto, gris.height)))
            t = t.resize((int(t.width * escala), int(t.height * escala)), Image.LANCZOS)
            if receta is not None:
                try:
                    t = receta(t)
                except ImportError:
                    pass
            for tx, x0, y0, x1, y1, conf, clave in leer_tesseract(t, idioma, pytesseract, psm=11):
                palabras.append((tx, x0 / escala + x, y0 / escala + y, x1 / escala + x, y1 / escala + y, conf,
                                 (x, y) + tuple(clave)))
    return sin_duplicadas(palabras)


def agrupar_etiquetas(palabras):
    """Reconstruye el texto de cada caja, decision o flecha de un diagrama a partir de sus palabras sueltas.

    Dos palabras son de la misma etiqueta si estan en la misma linea y casi pegadas, o en lineas apiladas que se
    solapan en horizontal (texto centrado en varias lineas). Devuelve [(texto, y0, x0)] en orden de lectura."""
    pal = [p for p in palabras if p[4] > p[2]]
    n = len(pal)
    padre = list(range(n))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for i in range(n):
        a = pal[i]
        for j in range(i + 1, n):
            b = pal[j]
            ha, hb = a[4] - a[2], b[4] - b[2]
            h = min(ha, hb)
            if max(ha, hb) > 1.8 * h:
                continue
            en_linea = abs((a[2] + a[4]) / 2 - (b[2] + b[4]) / 2) < 0.5 * h and max(b[1] - a[3], a[1] - b[3]) <= 0.9 * h
            apiladas = (-0.2 * h <= max(b[2] - a[4], a[2] - b[4]) <= 0.6 * h
                        and min(a[3], b[3]) - max(a[1], b[1]) > 0)
            if en_linea or apiladas:
                padre[raiz(i)] = raiz(j)
    grupos = collections.defaultdict(list)
    for i in range(n):
        grupos[raiz(i)].append(pal[i])
    etiquetas = []
    for g in grupos.values():
        g.sort(key=lambda p: ((p[2] + p[4]) / 2, p[1]))
        lineas, actual = [], [g[0]]
        for p in g[1:]:
            if abs((p[2] + p[4]) / 2 - (actual[0][2] + actual[0][4]) / 2) < 0.6 * (p[4] - p[2]):
                actual.append(p)
            else:
                lineas.append(actual)
                actual = [p]
        lineas.append(actual)
        texto = " ".join(" ".join(p[0] for p in sorted(l, key=lambda p: p[1])) for l in lineas)
        etiquetas.append((nfc(texto), min(p[2] for p in g), min(p[1] for p in g)))
    return sorted(etiquetas, key=lambda e: (round(e[1] / 80), e[2]))


def _lectura(palabras, esc, nombre, disperso):
    buenas, descartadas = _validas(palabras)
    res = PaginaOCR(lineas=lineas_de_datos(buenas, esc), confianzas=[p[5] for p in buenas])
    res.mejora, res.disperso, res.descartadas = nombre, disperso, descartadas
    if disperso:
        res.etiquetas = agrupar_etiquetas(buenas)
    return res


def leer_imagen(imagen, idioma, pytesseract, probar_orientacion=True):
    """OCR de una imagen suelta (la captura de un documento pegada en una hoja de Excel, un diagrama de flujo):
    PIL.Image -> ``PaginaOCR`` con las lineas en pixeles de la imagen original.

    Se prueban dos lecturas y se conserva la que recupera mas texto fiable: la imagen entera ampliada a un lado
    mayor de ``LADO_MIN_IMAGEN`` px y leida como pagina (documentos, capturas), y la imagen por teselas ampliadas
    leida como texto disperso con mas nitidez (diagramas de flujo, de texto chico). Las palabras con menos de
    ``CONF_PALABRA_MIN`` de confianza se descartan: son ruido de iconos y flechas, y no bajan la confianza del
    texto que si se leyo. Si no llega a ``CONFIANZA_OBJETIVO`` se prueban mas contraste, brillo y blanco y negro y, si la
    imagen parece tener texto mal orientado (al reves, de lado o reflejado), las demas orientaciones."""
    from PIL import Image
    if imagen.mode in ("RGBA", "LA", "P"):                  # el fondo transparente se leeria como negro
        rgba = imagen.convert("RGBA")
        fondo = Image.new("RGB", rgba.size, "white")
        fondo.paste(rgba, mask=rgba.split()[3])
        imagen = fondo
    gris = imagen.convert("L")
    escala = min(AMPLIACION_MAX, max(1.0, LADO_MIN_IMAGEN / max(gris.size)))
    grande = gris.resize((int(gris.width * escala), int(gris.height * escala)), Image.LANCZOS) if escala > 1.0 else gris
    inicio, lecturas = time.monotonic(), []

    def completa(nombre, receta):
        img = receta(grande) if receta is not None else grande
        return _lectura(leer_tesseract(img, idioma, pytesseract, psm=3), 1.0 / escala, nombre, False)

    def teselas(nombre, receta):
        pal = _por_teselas(gris, idioma, pytesseract, receta)
        return _lectura(pal, 1.0, nombre + ", teselas", True)

    intentos = [(completa, "original", None), (teselas, "nitidez", receta_nitidez)]
    for nombre, receta in RECETAS[1:]:
        if nombre != "contraste y nitidez":
            intentos += [(completa, nombre, receta), (teselas, nombre, receta)]
    for k, (funcion, nombre, receta) in enumerate(intentos):
        res = funcion(nombre, receta)
        lecturas.append((res, nombre, receta))
        if k == 0 and not res.confianzas and not res.descartadas:
            return res                                       # sin texto: una foto, nada que mejorar
        if k == 0 and probar_orientacion and len(res.confianzas) + res.descartadas >= MIN_PALABRAS_SOSPECHA and (
                res.confianza < CONFIANZA_OBJETIVO or res.descartadas >= PROPORCION_RUIDO * max(len(res.confianzas), 1)):
            # confianza baja, o mas palabras descartadas por ruido que conservadas (texto reflejado o al reves)
            giro, espejo = orientacion_por_prueba(gris, idioma, pytesseract)
            if (giro, espejo) != (0, False):
                otra = leer_imagen(orientar(gris, giro, espejo), idioma, pytesseract, probar_orientacion=False)
                if otra.confianza > res.confianza and len(otra.confianzas) >= len(res.confianzas):
                    otra.orientacion, otra.espejo = giro, espejo
                    return otra
        if k >= 1 and elegir_lectura(lecturas, por_cantidad=True)[0].confianza >= CONFIANZA_OBJETIVO:
            break                                            # la lectura con mas texto ya llega a CONFIANZA_OBJETIVO
        if time.monotonic() - inicio > TIEMPO_MAX_MEJORA:
            break
    return elegir_lectura(lecturas, por_cantidad=True)[0]
