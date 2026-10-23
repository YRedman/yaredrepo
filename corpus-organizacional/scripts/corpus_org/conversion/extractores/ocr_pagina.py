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
"""

import collections
import difflib
import time
import re
from dataclasses import dataclass, field
from typing import List

from ...comun.texto import nfc, norm

DPI_OCR = 300
DPI_OCR_ALTO = 400          # una pasada extra, con el mejor tratamiento, cuando la confianza no llega al objetivo
TIEMPO_MAX_MEJORA = 150.0   # segundos por pagina o imagen para seguir probando tratamientos
TONOS_MEDIOS_FOTO = 0.30        # fraccion de pixeles ni claros ni oscuros: una foto tiene muchos, una hoja de texto casi ninguno
MAX_CELDAS_FOTO = 12            # mas celdas que esto, sin texto y con tonos medios, es una foto y no una tabla
MIN_PALABRAS_TEXTO = 8          # palabras de 4+ letras que debe leer el OCR para tratar la pagina como texto
CONFIANZA_SIN_ESPERANZA = 40.0  # si ningun tratamiento a 300 dpi pasa de esto, 400 dpi no lo salvara
CONFIANZA_OBJETIVO = 80.0   # confianza media de Tesseract que debe alcanzar cada pagina (calidad antes que velocidad)
CONTRASTE_DIST = 5          # px: distancia a la que se compara cada pixel con su entorno
CONTRASTE_MIN = 20          # diferencia de gris para considerar un pixel parte de un borde
GROSOR_MAX_LINEA = 8        # px: un trazo mas grueso es un relleno, no una linea
LARGO_MIN_H = 0.05          # fraccion del ancho de la pagina para una linea horizontal (cajas angostas)
LARGO_MIN_V = 30            # px para un trazo vertical
ANGULO_MIN = 0.1            # grados: una inclinacion menor no se corrige
TOLERANCIA = 10             # px para decidir si un trazo toca otro
FONDO_OSCURO = 175          # gris medio de una celda con relleno de color
CONFIANZA_BAJA = 60         # confianza de Tesseract por debajo de la cual una palabra es dudosa
TINTA_MIN_CELDA = 150       # pixeles oscuros minimos para releer una celda que el OCR dejo vacia
CONFIANZA_RELECTURA = 60    # confianza media minima para aceptar la relectura de una celda
RE_BORDE = re.compile(r"[|\[\]{}()'`´‘’!¡:;.,_\-—–=~]+")   # bordes de tabla leidos como caracteres
# viñeta leida como letra o simbolo ("e 100%", "+ Redacción"): seguida de mayuscula o digito
RE_VINETA_OCR = re.compile(r"(^|\s)[e¢«°•*»©+]\s+(?=[A-ZÁÉÍÓÚÑ0-9])")
RE_ENCABEZADO = re.compile(r"c[oó]digo|versi[oó]n|vigen|p[aá]gina", re.I)


@dataclass
class Segmento:
    pos: float      # y (horizontal) o x (vertical), en px
    ini: float      # x0 (horizontal) o y0 (vertical)
    fin: float


@dataclass
class Celda:
    x0: float
    y0: float
    x1: float
    y1: float
    palabras: list = field(default_factory=list)   # (texto, x0, y0, x1, y1, conf)

    def contiene(self, cx, cy):
        return self.x0 - 2 <= cx <= self.x1 + 2 and self.y0 - 2 <= cy <= self.y1 + 2


@dataclass
class TablaImagen:
    filas: List[List[Celda]]

    @property
    def x0(self):
        return min(c.x0 for f in self.filas for c in f)

    @property
    def x1(self):
        return max(c.x1 for f in self.filas for c in f)

    @property
    def y0(self):
        return self.filas[0][0].y0

    @property
    def y1(self):
        return self.filas[-1][0].y1

    def textos(self):
        return [[texto_celda(c) for c in f] for f in self.filas]


def _receta_nitidez(img):
    from PIL import ImageFilter, ImageOps
    return ImageOps.autocontrast(img, cutoff=1).filter(ImageFilter.UnsharpMask(radius=2, percent=160, threshold=3))


def _receta_brillo(img):
    """Aclara una pagina oscura u oscurece una palida (gamma segun el gris medio) y estira el contraste."""
    from PIL import ImageOps
    import numpy as np
    media = float(np.asarray(img).mean())
    gamma = 1.0
    if media < 140:
        gamma = 0.6
    elif media > 225:
        gamma = 1.6
    tabla = [int(255 * ((v / 255.0) ** gamma)) for v in range(256)]
    return ImageOps.autocontrast(img.point(tabla), cutoff=1)


def _receta_binarizada(img):
    """Blanco y negro con el umbral de Otsu y sin motas (fondos con ruido o sellos de color)."""
    from PIL import Image, ImageFilter, ImageOps
    import numpy as np
    gris = np.asarray(ImageOps.autocontrast(img, cutoff=1))
    hist = np.bincount(gris.ravel(), minlength=256).astype(float)
    total, suma = hist.sum(), (hist * np.arange(256)).sum()
    mejor, w0, s0, umbral = -1.0, 0.0, 0.0, 128
    for t in range(256):
        w0 += hist[t]
        s0 += t * hist[t]
        if w0 == 0 or w0 == total:
            continue
        m0, m1 = s0 / w0, (suma - s0) / (total - w0)
        entre = w0 * (total - w0) * (m0 - m1) ** 2
        if entre > mejor:
            mejor, umbral = entre, t
    binaria = Image.fromarray(((gris > umbral) * 255).astype("uint8"))
    return binaria.filter(ImageFilter.MedianFilter(3))


RECETAS = (("original", None), ("contraste y nitidez", _receta_nitidez), ("brillo y contraste", _receta_brillo),
           ("blanco y negro", _receta_binarizada))


@dataclass
class PaginaOCR:
    lineas: list                                    # lineas fuera de tablas (formato de _lineas_pagina, en pt)
    tablas: list = field(default_factory=list)      # (y0, x0, y1, x1 en pt, filas de texto, xs en pt)
    cajas: list = field(default_factory=list)       # (y0, x0, textos) de un organigrama
    encabezado: list = field(default_factory=list)  # textos de las celdas del encabezado del formato
    confianzas: list = field(default_factory=list)  # confianza de cada palabra leida
    mejora: str = ""                                # tratamiento de imagen con que se obtuvo la lectura
    dpi: int = 0
    orientacion: int = 0                            # grados que se giro la pagina (0, 90, 180, 270)
    espejo: bool = False                            # la pagina estaba reflejada y se leyo ya corregida
    firmas: int = 0                                 # campos de firma manuscrita ignorados (su OCR es ruido)
    disperso: bool = False                          # texto suelto de un diagrama (etiquetas), no parrafos
    descartadas: int = 0                            # palabras leidas con menos de CONF_PALABRA_MIN: ruido de graficos
    etiquetas: list = field(default_factory=list)   # en un diagrama: texto de cada caja, decision o flecha

    @property
    def confianza(self):
        return sum(self.confianzas) / len(self.confianzas) if self.confianzas else 0.0

    @property
    def textos(self):
        """Todos los textos leidos: lineas, celdas de tablas, cajas y encabezado."""
        return ([l["texto"] for l in self.lineas] + [c for t in self.tablas for f in t[4] for c in f]
                + [c[2] for c in self.cajas] + list(self.encabezado))

    @property
    def palabras_utiles(self):
        """Palabras de 4 o mas letras: una pagina con menos de MIN_PALABRAS_TEXTO es una foto, no texto."""
        return sum(1 for t in self.textos for _ in re.findall(r"[^\W\d_]{4,}", t))


# ---------------------------------------------------------------------------
# Lineas de la imagen
# ---------------------------------------------------------------------------

def _corridas(fila_bool):
    """[(inicio, fin)] de los tramos True de un vector booleano (fin exclusivo)."""
    import numpy as np
    d = np.diff(np.concatenate(([0], fila_bool.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def _trazos(tinta, largo):
    """Tramos de al menos ``largo`` pixeles por fila: [(fila, x0, x1)]."""
    import numpy as np
    s = np.cumsum(tinta, axis=1, dtype=np.int32)
    s = np.concatenate((np.zeros((tinta.shape[0], 1), dtype=np.int32), s), axis=1)
    lleno = (s[:, largo:] - s[:, :-largo]) == largo
    res = []
    for y in np.flatnonzero(lleno.any(axis=1)):
        for a, b in _corridas(lleno[y]):
            res.append((int(y), int(a), int(b) + largo))
    return res


def _agrupar(trazos):
    """Agrupa trazos de filas consecutivas que se solapan: [(posicion media, grosor, x0, x1)].

    El grosor es la cantidad media de filas por columna (largo total / ancho): una linea fina algo
    inclinada ocupa varias filas de punta a punta pero solo 2 o 3 en cada columna; un relleno ocupa
    todas.
    """
    grupos = []
    for y, a, b in sorted(trazos):
        for g in grupos:
            if y - g[1] <= 1 and min(b, g[3]) - max(a, g[2]) > 0.5 * min(b - a, g[3] - g[2]):
                g[1], g[2], g[3] = y, min(a, g[2]), max(b, g[3])
                g[4] += b - a
                g[5] += y * (b - a)
                break
        else:
            grupos.append([y, y, a, b, b - a, y * (b - a)])
    return [(g[5] / g[4], g[4] / max(g[3] - g[2], 1), g[2], g[3]) for g in grupos]


def _bordes(gris, eje):
    """Pixeles que contrastan con el pixel a CONTRASTE_DIST de un lado o del otro, a lo largo de ``eje``.

    Detectar por contraste (y no con un umbral fijo) separa las lineas grises del fondo gris claro de
    las filas, y convierte los rellenos de color en sus bordes.
    """
    import numpy as np
    g = gris.astype(np.int16)
    k = CONTRASTE_DIST
    antes = np.full_like(g, 255)
    despues = np.full_like(g, 255)
    if eje == 0:
        antes[k:, :], despues[:-k, :] = g[:-k, :], g[k:, :]
    else:
        antes[:, k:], despues[:, :-k] = g[:, :-k], g[:, k:]
    oscuro = (g < antes - CONTRASTE_MIN) | (g < despues - CONTRASTE_MIN)
    claro = (g > antes + CONTRASTE_MIN) & (g > despues + CONTRASTE_MIN)   # linea clara sobre relleno oscuro
    return oscuro | claro


def lineas_imagen(gris):
    """(horizontales, verticales) detectadas en una imagen en grises (numpy uint8)."""
    import numpy as np
    alto, ancho = gris.shape
    horizontales = [Segmento(pos, a, b)
                    for pos, grosor, a, b in _agrupar(_trazos(_bordes(gris, 0), max(40, int(LARGO_MIN_H * ancho))))
                    if grosor <= GROSOR_MAX_LINEA]
    verticales = [Segmento(pos, a, b)
                  for pos, grosor, a, b in _agrupar(_trazos(np.ascontiguousarray(_bordes(gris, 1).T), LARGO_MIN_V))
                  if grosor <= GROSOR_MAX_LINEA]
    return _unir_colineales(horizontales), _unir_colineales(verticales)


def _unir_colineales(segmentos, hueco=3):
    """Une los tramos de una misma linea que se tocan o se solapan (misma posicion ±3 px).

    Pasa cuando un cruce o una mancha corta la linea en dos. El hueco permitido es minimo: con uno
    mayor se encadenarian los trazos verticales de letras de renglones consecutivos.
    """
    res = []
    for s in sorted(segmentos, key=lambda s: (s.pos, s.ini)):
        unido = False
        for k in range(len(res) - 1, -1, -1):
            u = res[k]
            if s.pos - u.pos > 3:
                break
            if s.ini <= u.fin + hueco and u.ini <= s.fin + hueco:
                res[k] = Segmento((u.pos + s.pos) / 2, min(u.ini, s.ini), max(u.fin, s.fin))
                unido = True
                break
        if not unido:
            res.append(s)
    return res


def _oscura(gris, y0, y1, x0, x1):
    """True si la franja tiene relleno oscuro o de color (las lineas no se ven sobre el)."""
    if gris is None or y1 - y0 < 8 or x1 - x0 < 8:
        return False
    return float(gris[int(y0) + 3:int(y1) - 3, int(x0) + 3:int(x1) - 3].mean()) < FONDO_OSCURO


def _une(h1, h2, verticales, gris):
    """True si dos lineas horizontales consecutivas son el borde de arriba y de abajo de una fila."""
    a, b = max(h1.ini, h2.ini), min(h1.fin, h2.fin)
    if b - a < 0.6 * min(h1.fin - h1.ini, h2.fin - h2.ini):
        return False
    if _oscura(gris, h1.pos, h2.pos, a, b):
        return True
    cruzan = [v for v in verticales if a - TOLERANCIA <= v.pos <= b + TOLERANCIA
              and v.ini <= h1.pos + TOLERANCIA and v.fin >= h2.pos - TOLERANCIA]
    return len(cruzan) >= 2


def tablas_imagen(horizontales, verticales, gris=None, palabras=()):
    """Cuadriculas de celdas formadas por lineas horizontales unidas por verticales o por un relleno.

    ``palabras`` (del OCR, en px) evita partir en columnas una fila con relleno que es un titulo de
    ancho completo: si alguna palabra cruza el limite de una columna, la fila es una sola celda.
    """
    hs = []
    for h in sorted(horizontales, key=lambda s: (s.pos, s.ini)):
        if hs and abs(h.pos - hs[-1].pos) <= GROSOR_MAX_LINEA and h.ini <= hs[-1].fin + 2 * TOLERANCIA \
                and hs[-1].ini <= h.fin + 2 * TOLERANCIA:
            hs[-1] = Segmento((h.pos + hs[-1].pos) / 2, min(h.ini, hs[-1].ini), max(h.fin, hs[-1].fin))
        else:
            hs.append(h)
    usadas, tablas = set(), []
    for i, h in enumerate(hs):
        if i in usadas:
            continue
        cadena, actual = [h], h
        for j in range(i + 1, len(hs)):
            if j in usadas:
                continue
            sig = hs[j]
            if min(sig.fin, actual.fin) - max(sig.ini, actual.ini) <= 0:
                continue
            if _une(actual, sig, verticales, gris):
                cadena.append(sig)
                usadas.add(j)
                actual = sig
            elif sig.fin - sig.ini >= 0.6 * (actual.fin - actual.ini):
                break       # una linea del ancho de la tabla que no continua la cuadricula: termina
            # una linea corta dentro de una celda (subrayado, trazo de una letra) no corta la tabla
        if len(cadena) < 2:
            continue
        usadas.add(i)
        x0 = min(s.ini for s in cadena)
        x1 = max(s.fin for s in cadena)
        bandas = [(arriba, abajo, _oscura(gris, arriba.pos, abajo.pos, x0, x1))
                  for arriba, abajo in zip(cadena, cadena[1:])]

        def separadores(arriba, abajo):
            return [v.pos for v in verticales if x0 + TOLERANCIA < v.pos < x1 - TOLERANCIA
                    and v.ini <= arriba.pos + TOLERANCIA and v.fin >= abajo.pos - TOLERANCIA]

        # en una fila con relleno los bordes de las letras claras parecen lineas verticales: se usan las
        # columnas de las filas sin relleno de la misma tabla
        claras = [separadores(a, b) for a, b, oscura in bandas if not oscura]
        columnas = _sin_cercanos(max(claras, key=len)) if claras else []
        filas = []
        for arriba, abajo, oscura in bandas:
            if oscura:
                cruzan = any(p[1] < c < p[3] for p in palabras
                             if arriba.pos <= (p[2] + p[4]) / 2 <= abajo.pos for c in columnas)
                seps = [] if cruzan else columnas
            else:
                seps = _sin_cercanos(separadores(arriba, abajo))
            xs = [x0] + seps + [x1]
            filas.append([Celda(a, arriba.pos, b, abajo.pos) for a, b in zip(xs, xs[1:]) if b - a > TOLERANCIA])
        tablas.append(TablaImagen([f for f in filas if f]))
    return [t for t in tablas if t.filas]


def _sin_cercanos(xs):
    res = []
    for x in sorted(xs):
        if not res or x - res[-1] > TOLERANCIA:
            res.append(x)
    return res


# ---------------------------------------------------------------------------
# Palabras y celdas
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Pagina completa
# ---------------------------------------------------------------------------

def _ocr(img, idioma, pytesseract, psm=3):
    # pytesseract guarda la imagen en un archivo temporal con su formato: el PNG comprime y tarda ~0,15 s por lectura;
    # un TIFF sin comprimir se escribe al instante y Tesseract lo lee igual (un BMP de 8 bits cambia la lectura)
    if img.mode in ("L", "RGB") and not img.format:
        img.format = "TIFF"
    return palabras_tesseract(pytesseract.image_to_data(
        img, lang=idioma, config=f"--oem 1 --psm {psm}", output_type=pytesseract.Output.DICT))


def _releer_celda(img, gris, celda, idioma, pytesseract):
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
        if celda.palabras and _media(celda.palabras) >= CONFIANZA_RELECTURA:
            return None    # fondo claro y lectura confiable: no hace falta releer
        if not celda.palabras and (zona < 128).sum() < TINTA_MIN_CELDA:
            return None    # celda vacia de verdad
    recorte = img.crop(caja)
    if (zona < 100).mean() > 0.5:      # texto claro sobre fondo oscuro
        recorte = ImageOps.invert(recorte)
    palabras = _ocr(ImageOps.autocontrast(recorte), idioma, pytesseract, psm=6)
    return [(t, caja[0] + x0, caja[1] + y0, caja[0] + x1, caja[1] + y1, conf, k)
            for t, x0, y0, x1, y1, conf, k in palabras]


def texto_de(palabras):
    return " ".join(p[0] for p in palabras)


def _media(palabras):
    return sum(p[5] for p in palabras) / len(palabras) if palabras else 0.0


def _nitidez(img, angulo):
    """Puntaje de lo horizontales que quedan las lineas largas al rotar ``angulo`` grados."""
    import numpy as np
    filas = _bordes(np.asarray(img.rotate(angulo, fillcolor=255)), 0).mean(axis=1)
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


def _giro_por_osd(img, pytesseract):
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
DPI_PRUEBA = 150               # resolucion de las lecturas de prueba de orientacion
LADO_PRUEBA = 1200             # px: la imagen de prueba se reduce a este lado mayor
PROPORCION_RUIDO = 0.8         # en una imagen, descartar tantas palabras como se conservan hace sospechar de la orientacion
CONFIANZA_SOSPECHA = 70        # una pagina mal orientada se lee con basura (alrededor de 55 %); entre 70 y 80 es una mala copia, no una orientacion
MIN_PALABRAS_SOSPECHA = 20     # con menos palabras leidas (una foto, una hoja casi vacia) no se prueban las orientaciones
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
            resultados[(giro, espejo)] = _puntaje_texto(_ocr(banda, idioma, pytesseract, psm=6))
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
            giro_osd = _giro_por_osd(_imagen_pagina(page, dpi), pytesseract)
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
            return _elegir(lecturas)[0]     # la lectura normal y la de contraste y nitidez no sacan texto: es una foto
        if not intentos and dpi == DPI_OCR and not _elegir(lecturas, solo_buenas=True):
            parcial = _elegir(lecturas)
            if parcial is not None and parcial[0].confianza >= CONFIANZA_SIN_ESPERANZA:     # ultimo recurso: 400 dpi
                intentos.append((DPI_OCR_ALTO, parcial[1], parcial[2]))
    return _elegir(lecturas)[0]


def _elegir(lecturas, solo_buenas=False, por_cantidad=False):
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
        palabras = _ocr(img, idioma, pytesseract, psm=11)
        res = PaginaOCR(lineas=[], confianzas=[p[5] for p in palabras])
        for L in _lineas(palabras, 72.0 / dpi):
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
        if not intentos and dpi == DPI_OCR and not _elegir(lecturas, solo_buenas=True):
            parcial = _elegir(lecturas)
            if parcial is not None and parcial[0].confianza >= CONFIANZA_SIN_ESPERANZA:
                intentos.append((DPI_OCR_ALTO, parcial[1], parcial[2]))
    return _elegir(lecturas)[0]


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
            for tx, x0, y0, x1, y1, conf, clave in _ocr(t, idioma, pytesseract, psm=11):
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
    res = PaginaOCR(lineas=_lineas(buenas, esc), confianzas=[p[5] for p in buenas])
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
        return _lectura(_ocr(img, idioma, pytesseract, psm=3), 1.0 / escala, nombre, False)

    def teselas(nombre, receta):
        pal = _por_teselas(gris, idioma, pytesseract, receta)
        return _lectura(pal, 1.0, nombre + ", teselas", True)

    intentos = [(completa, "original", None), (teselas, "nitidez", _receta_nitidez)]
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
        if k >= 1 and _elegir(lecturas, por_cantidad=True)[0].confianza >= CONFIANZA_OBJETIVO:
            break                                            # la lectura con mas texto ya llega a CONFIANZA_OBJETIVO
        if time.monotonic() - inicio > TIEMPO_MAX_MEJORA:
            break
    return _elegir(lecturas, por_cantidad=True)[0]


def _mejor_lectura(nueva, actual):
    """La nueva lectura gana si tiene mas confianza sin perder texto (al menos 90 % de las palabras)."""
    return (nueva.confianza > actual.confianza + 0.5 and len(nueva.confianzas) >= 0.9 * len(actual.confianzas)) or \
        (not actual.confianzas and bool(nueva.confianzas))


def _pixmap_a_gris(pix):
    """Imagen PIL en grises de un pixmap de PyMuPDF, sin pasar por un PNG (codificarlo y leerlo costaba ~0,2 s)."""
    from PIL import Image
    img = Image.frombytes("L" if pix.n == 1 else "RGB", (pix.width, pix.height), pix.samples)
    return img if pix.n == 1 else img.convert("L")


def orientar(img, giro=0, espejo=False):
    """La imagen girada ``giro`` grados (sentido de las agujas del reloj: 0, 90, 180, 270) y, si ``espejo``, reflejada
    de izquierda a derecha (un escaneo hecho «por detras» o con la camara frontal)."""
    from PIL import ImageOps
    if giro:
        img = img.rotate(-giro, expand=True, fillcolor=255)
    return ImageOps.mirror(img) if espejo else img


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
    palabras = _ocr(img, idioma, pytesseract)
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
                    nuevas = _releer_celda(img, gris, c, idioma, pytesseract)
                    # se queda con la lectura de la celda sola si leyo algo y con mas confianza
                    if nuevas and _media(nuevas) >= CONFIANZA_RELECTURA and (
                            not c.palabras or (_media(nuevas) > _media(c.palabras) and
                                               len(texto_de(nuevas)) >= 0.8 * len(texto_celda(c)))):
                        c.palabras = nuevas
    firmas = _quitar_firmas(tablas)
    fuera, firmas_linea = _quitar_firmas_en_lineas(fuera)
    esc = 72.0 / dpi
    res = PaginaOCR(lineas=_lineas(fuera, esc), firmas=firmas + firmas_linea, orientacion=giro, espejo=espejo)
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
                res.tablas.append((t.y0 * esc, t.x0 * esc, t.y1 * esc, t.x1 * esc, _normalizar(filas), xs))
    res.confianzas += [p[5] for p in fuera]
    return res


# Etiqueta de un campo de firma: a su lado hay un trazo manuscrito que el OCR lee como letras sueltas sin sentido.
RE_ETIQUETA_FIRMA = re.compile(r"\b(firma|firmas|firmado|rubrica|sello|(elaborado|revisado|aprobado|autorizado) por|"
                               r"gerente del area|director\s*/?\s*gerente)\b")
CONF_FIRMA_MIN = 75            # en un campo de firma solo se conservan las palabras leidas con al menos esta confianza


def es_etiqueta_de_firma(texto):
    return bool(RE_ETIQUETA_FIRMA.search(norm(texto)))


ROTULOS_DE_FIRMA = ("Firma de Aprobación", "Firma del Colaborador", "Firmas de Aprobación")


def rotulo_de_firma(texto):
    """El rotulo canonico («Firma de Aprobación») si ``texto`` es ese rotulo leido con ruido del OCR («de Firma de
    Aprobación», «Firma de Aj»); si no, el mismo texto."""
    n = norm(texto)
    if "firma" not in n or len(n) > 40:
        return texto
    cerca = difflib.get_close_matches(n, [norm(r) for r in ROTULOS_DE_FIRMA], n=1, cutoff=0.6)
    return next((r for r in ROTULOS_DE_FIRMA if norm(r) == cerca[0]), texto) if cerca else texto


def _quitar_firmas(tablas):
    """Vacia las celdas que acompanan a una etiqueta de firma («Director / Gerente Sr. / Gerente del area:», «Firma de
    Aprobacion») cuando solo traen lecturas de baja confianza: son el trazo de la firma, no texto. Un nombre escrito a
    maquina junto a la firma (confianza alta) se conserva. Devuelve cuantos campos de firma se ignoraron."""
    ignoradas = 0
    for t in tablas:
        for fila in t.filas:
            etiquetas = [j for j, c in enumerate(fila) if es_etiqueta_de_firma(texto_celda(c))]
            if not etiquetas:
                continue
            for j, c in enumerate(fila):
                if j in etiquetas or not c.palabras:
                    continue
                firmes = [p for p in c.palabras if p[5] >= CONF_FIRMA_MIN]
                if sum(1 for p in firmes if len(re.findall(r"[^\W\d_]", p[0])) >= 3) < 2:
                    c.palabras, ignoradas = [], ignoradas + 1
                elif len(firmes) < len(c.palabras):
                    c.palabras = firmes
    return ignoradas


def _quitar_firmas_en_lineas(palabras):
    """(palabras sin el trazo de firma, campos ignorados): en una linea que trae una etiqueta de firma se descartan las
    palabras de baja confianza (el trazo a su lado)."""
    lineas = collections.defaultdict(list)
    for p in palabras:
        lineas[p[6]].append(p)
    quitar, ignoradas = set(), 0
    for ps in lineas.values():
        if es_etiqueta_de_firma(" ".join(p[0] for p in sorted(ps, key=lambda q: q[1]))):
            malas = [id(p) for p in ps if p[5] < CONF_FIRMA_MIN]
            if malas:
                quitar.update(malas)
                ignoradas += 1
    return [p for p in palabras if id(p) not in quitar], ignoradas


def _normalizar(filas):
    """Misma cantidad de columnas en todas las filas (las celdas combinadas se completan vacias)."""
    n = max(len(f) for f in filas)
    return [f + [""] * (n - len(f)) for f in filas]


def _lineas(palabras, esc):
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
