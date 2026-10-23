"""Texto de Tesseract: palabras, celdas, encabezado y relectura de las celdas dudosas."""

import collections
import re

from ....comun.texto import nfc, norm
from .constantes import CONFIANZA_RELECTURA, FONDO_OSCURO


CONFIANZA_BAJA = 60         # confianza de Tesseract por debajo de la cual una palabra es dudosa
TINTA_MIN_CELDA = 150       # pixeles oscuros minimos para releer una celda que el OCR dejo vacia
RE_BORDE = re.compile(r"[|\[\]{}()'`´‘’!¡:;.,_\-—–=~]+")   # bordes de tabla leidos como caracteres
# viñeta leida como letra o simbolo ("e 100%", "+ Redacción"): seguida de mayuscula o digito
RE_VINETA_OCR = re.compile(r"(^|\s)[e¢«°•*»©+]\s+(?=[A-ZÁÉÍÓÚÑ0-9])")
RE_ENCABEZADO = re.compile(r"c[oó]digo|versi[oó]n|vigen|p[aá]gina", re.I)


def palabras_tesseract(datos):
    """[(texto, x0, y0, x1, y1, conf, clave_linea)] de la salida image_to_data de Tesseract."""
    res = []
    for k in range(len(datos["text"])):
        t = (datos["text"][k] or "").strip()
        try:
            conf = float(datos["conf"][k])
        except (TypeError, ValueError):
            conf = -1
        if not t or conf < 0 or RE_BORDE.fullmatch(t) or (len(t) == 1 and not t.isdigit() and conf < CONFIANZA_BAJA):
            continue   # bordes leidos como caracteres y letras sueltas dudosas (manchas, viñetas)
        x, y, w, h = datos["left"][k], datos["top"][k], datos["width"][k], datos["height"][k]
        res.append((t, x, y, x + w, y + h, conf, (datos["block_num"][k], datos["par_num"][k], datos["line_num"][k])))
    return res


def _dentro_de(p, q):
    """Fraccion del area de la palabra ``p`` que queda dentro de la palabra ``q``."""
    ancho = min(p[3], q[3]) - max(p[1], q[1])
    alto = min(p[4], q[4]) - max(p[2], q[2])
    if ancho <= 0 or alto <= 0:
        return 0.0
    return ancho * alto / max((p[3] - p[1]) * (p[4] - p[2]), 1)


def sin_duplicadas(palabras):
    """Quita lecturas repetidas: palabras o fragmentos que caen dentro de otra palabra mas grande.

    Tesseract a veces lee dos veces el texto en negrita ("Nivel Nivel de E Educación ión"). Se
    conservan primero las palabras grandes y se descarta lo que queda casi entero dentro de ellas;
    una viñeta junto a "100%" no se toca porque no cae dentro.
    """
    res = []
    for p in sorted(palabras, key=lambda p: (-(p[3] - p[1]) * (p[4] - p[2]), -p[5])):
        if not any(_dentro_de(p, q) > 0.6 for q in res):
            res.append(p)
    return res


def texto_celda(celda):
    """Texto de una celda en orden de lectura (renglones de arriba abajo, palabras de izquierda a derecha)."""
    palabras = sorted(sin_duplicadas(celda.palabras), key=lambda p: ((p[2] + p[4]) / 2, p[1]))
    renglones = []
    for p in palabras:
        cy, alto = (p[2] + p[4]) / 2, max(p[4] - p[2], 1)
        if renglones and abs(cy - renglones[-1][0]) < 0.6 * alto:
            renglones[-1][1].append(p)
        else:
            renglones.append([cy, [p]])
    texto = nfc(" ".join(" ".join(w[0] for w in sorted(r, key=lambda w: w[1])) for _, r in renglones)).strip()
    return RE_VINETA_OCR.sub(lambda m: m.group(1) + "• ", texto)


def repartir(palabras, tablas):
    """Pone cada palabra en la celda que contiene su centro. Devuelve las palabras que no estan en tablas."""
    fuera = []
    for p in palabras:
        cx, cy = (p[1] + p[3]) / 2, (p[2] + p[4]) / 2
        celda = next((c for t in tablas for f in t.filas for c in f if c.contiene(cx, cy)), None)
        if celda is None:
            fuera.append(p)
        else:
            celda.palabras.append(p)
    return fuera


def es_encabezado(tabla, alto_pagina):
    """La tabla del formato arriba de la pagina con Código, Versión, Vigencia o Página."""
    texto = " ".join(" ".join(f) for f in tabla.textos())
    return tabla.y0 < 0.2 * alto_pagina and len(RE_ENCABEZADO.findall(texto)) >= 2


def es_caja(tabla, ancho_pagina):
    """Una sola celda angosta: una caja de organigrama."""
    return len(tabla.filas) == 1 and len(tabla.filas[0]) == 1 and (tabla.x1 - tabla.x0) < 0.35 * ancho_pagina


def textos_encabezado(tabla):
    """Celdas del encabezado con al menos una palabra legible (descarta el ruido del logo)."""
    res = []
    for f in tabla.textos():
        for t in f:
            if re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3}|\d", t) and t not in res:
                res.append(t)
    return res


def leer_tesseract(img, idioma, pytesseract, psm=3):
    # pytesseract guarda la imagen en un archivo temporal con su formato: el PNG comprime y tarda ~0,15 s por lectura;
    # un TIFF sin comprimir se escribe al instante y Tesseract lo lee igual (un BMP de 8 bits cambia la lectura)
    if img.mode in ("L", "RGB") and not img.format:
        img.format = "TIFF"
    return palabras_tesseract(pytesseract.image_to_data(
        img, lang=idioma, config=f"--oem 1 --psm {psm}", output_type=pytesseract.Output.DICT))


def releer_celda(img, gris, celda, idioma, pytesseract):
    """Vuelve a leer sola una celda con fondo de color o con lectura poco confiable.

    Se recorta sin los bordes, se invierte si el texto es claro sobre fondo oscuro y se lee como un
    bloque de texto. Devuelve las palabras en coordenadas de la pagina, o None si no aplica.
    """
    from PIL import ImageOps
    m = 4
    caja = (int(celda.x0) + m, int(celda.y0) + m, int(celda.x1) - m, int(celda.y1) - m)
    if caja[2] - caja[0] < 20 or caja[3] - caja[1] < 20:
        return None
    zona = gris[caja[1]:caja[3], caja[0]:caja[2]]
    if float(zona.mean()) >= FONDO_OSCURO:
        if celda.palabras and promedio(celda.palabras) >= CONFIANZA_RELECTURA:
            return None    # fondo claro y lectura confiable: no hace falta releer
        if not celda.palabras and (zona < 128).sum() < TINTA_MIN_CELDA:
            return None    # celda vacia de verdad
    recorte = img.crop(caja)
    if (zona < 100).mean() > 0.5:      # texto claro sobre fondo oscuro
        recorte = ImageOps.invert(recorte)
    palabras = leer_tesseract(ImageOps.autocontrast(recorte), idioma, pytesseract, psm=6)
    return [(t, caja[0] + x0, caja[1] + y0, caja[0] + x1, caja[1] + y1, conf, k)
            for t, x0, y0, x1, y1, conf, k in palabras]


def texto_de(palabras):
    return " ".join(p[0] for p in palabras)


def promedio(palabras):
    return sum(p[5] for p in palabras) / len(palabras) if palabras else 0.0


def normalizar_lectura(filas):
    """Misma cantidad de columnas en todas las filas (las celdas combinadas se completan vacias)."""
    n = max(len(f) for f in filas)
    return [f + [""] * (n - len(f)) for f in filas]


def lineas_de_datos(palabras, esc):
    """Lineas de texto (formato de las lineas de una pagina digital) agrupando por linea de Tesseract."""
    lineas = collections.OrderedDict()
    for t, x0, y0, x1, y1, _conf, clave in palabras:
        L = lineas.setdefault(clave, {"palabras": [], "x0": x0, "y0": y0, "x1": x1, "y1": y1})
        L["palabras"].append(t)
        L["x0"], L["y0"] = min(L["x0"], x0), min(L["y0"], y0)
        L["x1"], L["y1"] = max(L["x1"], x1), max(L["y1"], y1)
    salida = []
    for L in lineas.values():
        texto = nfc(" ".join(L["palabras"]))
        texto = re.sub(r"^[e¢«°•*»©]\s+(?=[A-ZÁÉÍÓÚÑ])", "• ", texto)
        if not norm(texto):
            continue
        salida.append({"texto": texto, "x0": L["x0"] * esc, "y0": L["y0"] * esc, "x1": L["x1"] * esc,
                       "y1": L["y1"] * esc, "tam": 0.0, "bold": False, "font": "ocr", "spans": [],
                       "chars": len(texto.replace(" ", "")), "ocr": True})
    return salida
