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
import io
import re
from dataclasses import dataclass, field
from typing import List, Optional

from ...comun.texto import nfc, norm

DPI_OCR = 300
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


@dataclass
class PaginaOCR:
    lineas: list                                    # lineas fuera de tablas (formato de _lineas_pagina, en pt)
    tablas: list = field(default_factory=list)      # (y0, x0, y1, x1 en pt, filas de texto, xs en pt)
    cajas: list = field(default_factory=list)       # (y0, x0, textos) de un organigrama
    encabezado: list = field(default_factory=list)  # textos de las celdas del encabezado del formato
    confianzas: list = field(default_factory=list)  # confianza de cada palabra leida

    @property
    def confianza(self):
        return sum(self.confianzas) / len(self.confianzas) if self.confianzas else 0.0

    @property
    def dudosas(self):
        return sum(1 for c in self.confianzas if c < CONFIANZA_BAJA)


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


def leer_pagina(page, idioma, pytesseract):
    """OCR de una pagina escaneada con tablas, cajas de organigrama y encabezado separados."""
    from PIL import Image
    pix = page.get_pixmap(dpi=DPI_OCR)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    try:
        angulo = angulo_inclinacion(img)
        if abs(angulo) >= ANGULO_MIN:
            img = img.rotate(angulo, resample=Image.BICUBIC, fillcolor=255)
    except ImportError:
        angulo = 0.0
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
    if gris is not None:
        for t in tablas:
            for f in t.filas:
                for c in f:
                    nuevas = _releer_celda(img, gris, c, idioma, pytesseract)
                    # se queda con la lectura de la celda sola si leyo algo y con mas confianza
                    if nuevas and _media(nuevas) >= CONFIANZA_RELECTURA and (
                            not c.palabras or (_media(nuevas) > _media(c.palabras) and
                                               len(texto_de(nuevas)) >= 0.8 * len(texto_celda(c)))):
                        c.palabras = nuevas
    esc = 72.0 / DPI_OCR
    res = PaginaOCR(lineas=_lineas(fuera, esc))
    for t in tablas:
        res.confianzas += [p[5] for f in t.filas for c in f for p in c.palabras]
        if es_encabezado(t, img.height):
            res.encabezado += textos_encabezado(t)
        elif es_caja(t, img.width):
            texto = texto_celda(t.filas[0][0])
            if texto:
                res.cajas.append((t.y0 * esc, t.x0 * esc, texto))
        else:
            filas = [f for f in t.textos() if any(f)]
            if filas:
                xs = [c.x0 * esc for c in t.filas[0]]
                res.tablas.append((t.y0 * esc, t.x0 * esc, t.y1 * esc, t.x1 * esc, _normalizar(filas), xs))
    res.confianzas += [p[5] for p in fuera]
    return res


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


def confianza_texto(paginas: List[PaginaOCR]) -> Optional[float]:
    confs = [c for p in paginas for c in p.confianzas]
    return sum(confs) / len(confs) if confs else None
