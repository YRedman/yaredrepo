"""Lineas y tablas dibujadas en una imagen: se detectan los trazos largos y se arma la rejilla de celdas."""

from .constantes import FONDO_OSCURO
from .modelo import Celda, Segmento, TablaImagen


CONTRASTE_DIST = 5          # px: distancia a la que se compara cada pixel con su entorno
CONTRASTE_MIN = 20          # diferencia de gris para considerar un pixel parte de un borde
GROSOR_MAX_LINEA = 8        # px: un trazo mas grueso es un relleno, no una linea
LARGO_MIN_H = 0.05          # fraccion del ancho de la pagina para una linea horizontal (cajas angostas)
LARGO_MIN_V = 30            # px para un trazo vertical
TOLERANCIA = 10             # px para decidir si un trazo toca otro


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


def bordes_de_imagen(gris, eje):
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
                    for pos, grosor, a, b in _agrupar(_trazos(bordes_de_imagen(gris, 0), max(40, int(LARGO_MIN_H * ancho))))
                    if grosor <= GROSOR_MAX_LINEA]
    verticales = [Segmento(pos, a, b)
                  for pos, grosor, a, b in _agrupar(_trazos(np.ascontiguousarray(bordes_de_imagen(gris, 1).T), LARGO_MIN_V))
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
