"""OCR de una pagina de PDF escaneada o de una region de ella, mejorando la imagen si hace falta."""

import re
import time

from .constantes import CONFIANZA_OBJETIVO, CONFIANZA_RELECTURA, MIN_PALABRAS_SOSPECHA, TIEMPO_MAX_MEJORA
from .firmas import quitar_firmas, quitar_firmas_en_lineas, rotulo_de_firma
from .geometria import lineas_imagen, tablas_imagen
from .modelo import PaginaOCR
from .orientacion import angulo_inclinacion, giro_por_osd, orientacion_por_prueba, orientar
from .recetas import RECETAS
from .texto import (es_caja, es_encabezado, leer_tesseract, lineas_de_datos, normalizar_lectura, promedio, releer_celda,
                    repartir, texto_celda, texto_de, textos_encabezado)


DPI_OCR = 300
DPI_OCR_ALTO = 400          # una pasada extra, con el mejor tratamiento, cuando la confianza no llega al objetivo
TONOS_MEDIOS_FOTO = 0.30        # fraccion de pixeles ni claros ni oscuros: una foto tiene muchos, una hoja de texto casi ninguno
MAX_CELDAS_FOTO = 12            # mas celdas que esto, sin texto y con tonos medios, es una foto y no una tabla
MIN_PALABRAS_TEXTO = 8          # palabras de 4+ letras que debe leer el OCR para tratar la pagina como texto
CONFIANZA_SIN_ESPERANZA = 40.0  # si ningun tratamiento a 300 dpi pasa de esto, 400 dpi no lo salvara
ANGULO_MIN = 0.1            # grados: una inclinacion menor no se corrige
DPI_PRUEBA = 150               # resolucion de las lecturas de prueba de orientacion
CONFIANZA_SOSPECHA = 70        # una pagina mal orientada se lee con basura (alrededor de 55 %); entre 70 y 80 es una mala copia, no una orientacion


def leer_pagina(page, idioma, pytesseract):
    """OCR de una pagina escaneada con tablas, cajas de organigrama y encabezado separados.

    Calidad antes que velocidad: si la confianza media no llega a ``CONFIANZA_OBJETIVO`` se vuelve a leer con
    la pagina girada (si esta de lado), mas contraste, nitidez, brillo, blanco y negro y mayor resolucion, y se
    conserva la mejor lectura. El tratamiento usado queda en ``mejora``.
    """
    def etiqueta(nombre, dpi, giro, espejo=False):
        partes = ([nombre] + ([f"{dpi} dpi"] if dpi != DPI_OCR else []) + ([f"giro de {giro}°"] if giro else [])
                  + (["reflejada"] if espejo else []))
        return ", ".join(partes)

    def leer(dpi, nombre, receta, giro, espejo):
        res = _leer_pagina_con(page, idioma, pytesseract, dpi, receta, giro, espejo)
        res.mejora, res.dpi, res.orientacion, res.espejo = etiqueta(nombre, dpi, giro, espejo), dpi, giro, espejo
        lecturas.append((res, nombre, receta))
        return res

    inicio, giro, espejo, lecturas = time.monotonic(), 0, False, []
    intentos = [(DPI_OCR, nombre, receta) for nombre, receta in RECETAS]
    while intentos:
        dpi, nombre, receta = intentos.pop(0)
        res = leer(dpi, nombre, receta, giro, espejo)
        if len(lecturas) == 1 and res.confianza >= CONFIANZA_OBJETIVO:
            return res                                  # la lectura normal ya llega al objetivo
        if time.monotonic() - inicio > TIEMPO_MAX_MEJORA:
            break
        if dpi == DPI_OCR and nombre == "original" and giro == 0 and not espejo:
            # pagina de lado, al reves o reflejada: primero el OSD de Tesseract y, si no basta, una lectura de prueba
            # de las 8 orientaciones (el OSD no ve los reflejos)
            candidatas = []
            giro_osd = giro_por_osd(_imagen_pagina(page, dpi), pytesseract)
            if giro_osd:
                candidatas.append((giro_osd, False))
            for g, e in candidatas:
                girada = leer(dpi, nombre, None, g, e)
                if girada.confianza >= CONFIANZA_OBJETIVO:
                    return girada
                if _mejor_lectura(girada, res):
                    giro, espejo = g, e
            mejor_hasta_ahora = max((x[0] for x in lecturas), key=lambda r: r.confianza)
            if len(mejor_hasta_ahora.confianzas) >= MIN_PALABRAS_SOSPECHA and mejor_hasta_ahora.confianza < CONFIANZA_SOSPECHA:
                g, e = orientacion_por_prueba(_imagen_pagina(page, DPI_PRUEBA), idioma, pytesseract)
                if (g, e) != (0, False) and (g, e) not in candidatas:
                    probada = leer(dpi, nombre, None, g, e)
                    if probada.confianza >= CONFIANZA_OBJETIVO:
                        return probada
                    if _mejor_lectura(probada, max((x[0] for x in lecturas), key=lambda r: r.confianza)):
                        giro, espejo = g, e
        if len(lecturas) == 2 and giro == 0 and not espejo and all(
                x[0].palabras_utiles < MIN_PALABRAS_TEXTO for x in lecturas):
            return elegir_lectura(lecturas)[0]     # la lectura normal y la de contraste y nitidez no sacan texto: es una foto
        if not intentos and dpi == DPI_OCR and not elegir_lectura(lecturas, solo_buenas=True):
            parcial = elegir_lectura(lecturas)
            if parcial is not None and parcial[0].confianza >= CONFIANZA_SIN_ESPERANZA:     # ultimo recurso: 400 dpi
                intentos.append((DPI_OCR_ALTO, parcial[1], parcial[2]))
    return elegir_lectura(lecturas)[0]


def elegir_lectura(lecturas, solo_buenas=False, por_cantidad=False):
    """(lectura, nombre, receta) preferida: entre las que llegan a CONFIANZA_OBJETIVO, la que recupera mas texto
    (otra con 90 % de confianza pero 20 palabras de 150 no sirve); si ninguna llega, la de mayor confianza sin
    perder texto. Con ``solo_buenas`` devuelve None si ninguna llega al objetivo."""
    buenas = [x for x in lecturas if x[0].confianza >= CONFIANZA_OBJETIVO]
    if buenas:
        return max(buenas, key=lambda x: (len(x[0].confianzas), x[0].confianza))
    if solo_buenas or not lecturas:
        return None
    if por_cantidad:     # imagenes: lo que mas texto fiable aporta (cantidad de palabras por su confianza)
        return max(lecturas, key=lambda x: sum(x[0].confianzas))
    mejor = lecturas[0]
    for x in lecturas[1:]:
        if _mejor_lectura(x[0], mejor[0]):
            mejor = x
    return mejor


def leer_region(page, rect, idioma, pytesseract):
    """OCR del texto dentro de una imagen o grafico de una pagina digital (``rect`` en puntos).

    Texto disperso (psm 11). Igual que en una pagina escaneada, si la confianza no llega a
    ``CONFIANZA_OBJETIVO`` se prueban mas contraste, nitidez, brillo, blanco y negro y mayor resolucion.
    Devuelve un ``PaginaOCR`` con las lineas en coordenadas de la pagina, o None si no se pudo leer.
    """
    def leer(dpi, nombre, receta):
        pix = page.get_pixmap(dpi=dpi, clip=rect)
        if pix.width < 8 or pix.height < 8:          # imagen recortada fuera de la pagina o de un punto: no hay nada que leer
            return PaginaOCR(lineas=[], confianzas=[]), False
        img = _pixmap_a_gris(pix)
        if receta is not None:
            try:
                img = receta(img)
            except ImportError:
                pass
        palabras = leer_tesseract(img, idioma, pytesseract, psm=11)
        res = PaginaOCR(lineas=[], confianzas=[p[5] for p in palabras])
        for L in lineas_de_datos(palabras, 72.0 / dpi):
            L["x0"], L["x1"] = L["x0"] + rect.x0, L["x1"] + rect.x0
            L["y0"], L["y1"] = L["y0"] + rect.y0, L["y1"] + rect.y0
            res.lineas.append(L)
        res.mejora, res.dpi = nombre if dpi == DPI_OCR else f"{nombre}, {dpi} dpi", dpi
        return res, bool(palabras)

    inicio, lecturas = time.monotonic(), []
    intentos = [(DPI_OCR, nombre, receta) for nombre, receta in RECETAS]
    while intentos:
        dpi, nombre, receta = intentos.pop(0)
        res, hay_texto = leer(dpi, nombre, receta)
        lecturas.append((res, nombre, receta))
        if len(lecturas) == 1 and (res.confianza >= CONFIANZA_OBJETIVO or not hay_texto):
            return res                                  # buena lectura, o una foto sin texto: nada que mejorar
        if time.monotonic() - inicio > TIEMPO_MAX_MEJORA:
            break
        if not intentos and dpi == DPI_OCR and not elegir_lectura(lecturas, solo_buenas=True):
            parcial = elegir_lectura(lecturas)
            if parcial is not None and parcial[0].confianza >= CONFIANZA_SIN_ESPERANZA:
                intentos.append((DPI_OCR_ALTO, parcial[1], parcial[2]))
    return elegir_lectura(lecturas)[0]


def _mejor_lectura(nueva, actual):
    """La nueva lectura gana si tiene mas confianza sin perder texto (al menos 90 % de las palabras)."""
    return (nueva.confianza > actual.confianza + 0.5 and len(nueva.confianzas) >= 0.9 * len(actual.confianzas)) or \
        (not actual.confianzas and bool(nueva.confianzas))


def _pixmap_a_gris(pix):
    """Imagen PIL en grises de un pixmap de PyMuPDF, sin pasar por un PNG (codificarlo y leerlo costaba ~0,2 s)."""
    from PIL import Image
    img = Image.frombytes("L" if pix.n == 1 else "RGB", (pix.width, pix.height), pix.samples)
    return img if pix.n == 1 else img.convert("L")


def _imagen_pagina(page, dpi, giro=0, espejo=False):
    return orientar(_pixmap_a_gris(page.get_pixmap(dpi=dpi)), giro, espejo)


def _preparar(page, dpi, receta, giro, espejo=False):
    """Imagen de la pagina lista para el OCR: girada, con el tratamiento ``receta`` y enderezada."""
    from PIL import Image
    img = _imagen_pagina(page, dpi, giro, espejo)
    if receta is not None:
        try:
            img = receta(img)
        except ImportError:
            pass
    try:
        angulo = angulo_inclinacion(img)
        if abs(angulo) >= ANGULO_MIN:
            img = img.rotate(angulo, resample=Image.BICUBIC, fillcolor=255)
    except ImportError:
        pass
    return img


def _leer_pagina_con(page, idioma, pytesseract, dpi, receta, giro, espejo=False):
    """Una pasada de OCR de la pagina a ``dpi`` con un tratamiento de imagen (``receta``), un giro y, si hace falta,
    reflejada."""
    img = _preparar(page, dpi, receta, giro, espejo)
    palabras = leer_tesseract(img, idioma, pytesseract)
    tablas = []
    gris = None
    try:
        import numpy as np
        gris = np.asarray(img)
        tablas = tablas_imagen(*lineas_imagen(gris), gris, palabras)
    except ImportError:
        pass
    fuera = repartir(palabras, tablas)
    celdas = sum(len(f) for t in tablas for f in t.filas)
    foto = (gris is not None and celdas > MAX_CELDAS_FOTO and float(((gris > 60) & (gris < 200)).mean()) >= TONOS_MEDIOS_FOTO
            and sum(1 for p in palabras if re.search(r"[^\W\d_]{4,}", p[0])) < MIN_PALABRAS_TEXTO)
    if gris is not None and not foto:     # una foto da decenas de "celdas" sin texto: releerlas una a una no lee nada
        for t in tablas:
            for f in t.filas:
                for c in f:
                    nuevas = releer_celda(img, gris, c, idioma, pytesseract)
                    # se queda con la lectura de la celda sola si leyo algo y con mas confianza
                    if nuevas and promedio(nuevas) >= CONFIANZA_RELECTURA and (
                            not c.palabras or (promedio(nuevas) > promedio(c.palabras) and
                                               len(texto_de(nuevas)) >= 0.8 * len(texto_celda(c)))):
                        c.palabras = nuevas
    firmas = quitar_firmas(tablas)
    fuera, firmas_linea = quitar_firmas_en_lineas(fuera)
    esc = 72.0 / dpi
    res = PaginaOCR(lineas=lineas_de_datos(fuera, esc), firmas=firmas + firmas_linea, orientacion=giro, espejo=espejo)
    for t in tablas:
        res.confianzas += [p[5] for f in t.filas for c in f for p in c.palabras]
        if es_encabezado(t, img.height):
            res.encabezado += textos_encabezado(t)
        elif es_caja(t, img.width):
            texto = texto_celda(t.filas[0][0])
            if texto:
                res.cajas.append((t.y0 * esc, t.x0 * esc, texto))
        else:
            filas = [[rotulo_de_firma(c) for c in f] for f in t.textos() if any(f)]
            if filas:
                xs = [c.x0 * esc for c in t.filas[0]]
                res.tablas.append((t.y0 * esc, t.x0 * esc, t.y1 * esc, t.x1 * esc, normalizar_lectura(filas), xs))
    res.confianzas += [p[5] for p in fuera]
    return res
