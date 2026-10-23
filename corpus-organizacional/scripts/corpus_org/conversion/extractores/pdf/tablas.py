"""Tablas de una pagina PDF: de PyMuPDF o por palabras, con celdas combinadas y sin bordes."""

import collections

from ....comun.esquema import MARCA_COMBINADA
from ....comun.texto import limpiar_celda, norm, unir


COBERTURA_BORDE = 0.9     # fraccion del ancho de una tabla que debe cubrir una linea para ser borde de fila


def _valor_celda_combinada(i, j, filas, filas_bbox):
    """Valor de una celda vacia de PyMuPDF: repite el de arriba si es combinada en vertical."""
    if i == 0 or not filas or j >= len(filas[-1]):
        return ""
    bb_col = None
    for ii in range(i - 1, -1, -1):
        if j < len(filas_bbox[ii]) and filas_bbox[ii][j] is not None:
            bb_col = filas_bbox[ii][j]
            break
    y_fila = next(((c[1] + c[3]) / 2 for c in filas_bbox[i] if c is not None), None)
    if bb_col is None or y_fila is None or not (bb_col[1] <= y_fila <= bb_col[3] + 0.5):
        return ""
    arriba = filas[-1][j]
    if not arriba or not arriba.strip():
        return ""
    return arriba.replace(MARCA_COMBINADA, "") + MARCA_COMBINADA


MIN_CARACTERES_REPETIDA = 20     # una celda mas corta ("N/A", "Equipo interdisciplinario") puede repetirse de verdad


def _quitar_celdas_repetidas(filas):
    """Vacia la celda que repite el texto de la de su izquierda en la misma fila.

    Una celda con un rectangulo interior (relleno de color con margen) la reconoce PyMuPDF dos veces, la grande
    y la interior, y el texto sale en dos columnas; la columna sobrante queda vacia y ``_unir_columnas_corridas``
    la une con la vecina."""
    for f in filas:
        for j in range(1, len(f)):
            t = norm(f[j].replace(MARCA_COMBINADA, ""))
            if len(t) >= MIN_CARACTERES_REPETIDA and t == norm(f[j - 1].replace(MARCA_COMBINADA, "")):
                f[j] = ""
    return filas


def _quitar_vacias(filas, ncol):
    filas = [f for f in filas if any(c.strip() for c in f)]
    if filas:
        cols = [j for j in range(ncol) if any(f[j].strip() for f in filas)]
        filas = [[f[j] for j in cols] for f in filas]
    return _unir_columnas_corridas(filas)


def _unir_columnas_corridas(filas):
    """Une dos columnas vecinas cuando la cabecera esta en una y los datos en la otra.

    Una cabecera combinada desplaza las celdas: "|   | Área de Interacción |" sobre "| Gerente |   |".
    Se unen solo si una de las dos no tiene cabecera y ninguna fila tiene texto en ambas.
    """
    if len(filas) < 2:
        return filas
    j = 0
    while j < len(filas[0]) - 1:
        a, b = j, j + 1
        sin_cabecera = not filas[0][a].strip() or not filas[0][b].strip()
        disjuntas = all(not (f[a].strip() and f[b].strip()) for f in filas)
        if sin_cabecera and disjuntas:
            filas = [f[:a] + [f[a] if f[a].strip() else f[b]] + f[b + 1:] for f in filas]
            continue
        j += 1
    return filas


def _cajas_de(filas_bbox):
    """Todas las celdas con caja de una tabla de PyMuPDF."""
    return [c for fila in filas_bbox for c in fila if c is not None]


def _palabras_celda(palabras, bbox, excluir=()):
    """Texto de una celda armado con las palabras de ``get_text("words")`` cuyo centro cae en la celda.

    ``excluir``: cajas de otras celdas; sus palabras no se toman (solo para celdas sin borde propio)."""
    x0, y0, x1, y1 = bbox

    def en_otra(w):
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        return any(c[0] - 1 <= cx <= c[2] + 1 and c[1] - 1 <= cy <= c[3] + 1 for c in excluir)
    sel = sorted((w for w in palabras
                  if x0 - 1 <= (w[0] + w[2]) / 2 <= x1 + 1 and y0 - 1 <= (w[1] + w[3]) / 2 <= y1 + 1
                  and not en_otra(w)),
                 key=lambda w: (w[5], w[6], w[7]))
    lineas, clave = [], None
    for w in sel:
        if (w[5], w[6]) != clave:
            lineas.append([])
            clave = (w[5], w[6])
        lineas[-1].append(w[4])
    return "\n".join(" ".join(l) for l in lineas)


ANCHO_MIN_COLUMNA = 25     # puntos: una columna mas angosta es un hueco entre celdas, no una celda


def _celda_sin_borde(filas_bbox, i, j):
    """Caja de una celda que PyMuPDF no reconocio (sin borde propio) en una fila que si tiene otras celdas.

    Ancho: el de la columna ``j`` en otra fila; alto: el de la fila. Si una celda de arriba en esa columna
    cubre la fila, la celda esta combinada en vertical y no se inventa nada.
    """
    fila = [c for c in filas_bbox[i] if c is not None] if i < len(filas_bbox) else []
    if not fila:
        return None
    y0, y1 = min(c[1] for c in fila), max(c[3] for c in fila)
    cy = (y0 + y1) / 2
    for ii in range(i - 1, -1, -1):                      # una celda combinada de arriba cubre esta fila
        if j < len(filas_bbox[ii]) and filas_bbox[ii][j] is not None:
            if filas_bbox[ii][j][1] <= cy <= filas_bbox[ii][j][3] + 0.5:
                return None
            break
    columna = next((filas_bbox[k][j] for k in sorted(range(len(filas_bbox)), key=lambda k: abs(k - i))
                    if j < len(filas_bbox[k]) and filas_bbox[k][j] is not None), None)
    if columna is None:
        return None
    cx = (columna[0] + columna[2]) / 2
    if any(c[0] - 1 <= cx <= c[2] + 1 for c in fila):    # otra celda de la fila cubre la columna: combinada en horizontal
        return None
    if columna[2] - columna[0] < ANCHO_MIN_COLUMNA:
        return None
    return (columna[0], y0, columna[2], y1)


def _datos_por_palabras(datos, filas_bbox, palabras):
    """Rehace cada celda con ``get_text("words")``.

    ``Table.extract()`` puede romper ligaduras ("eficiencia" -> "efci encia"); las palabras de la pagina
    no. Si una celda queda vacia se conserva el texto de ``extract()``.
    """
    nuevos = []
    for i, fila in enumerate(datos):
        nueva = []
        for j, v in enumerate(fila):
            bb = filas_bbox[i][j] if i < len(filas_bbox) and j < len(filas_bbox[i]) else None
            if v is None and bb is None:
                bb = _celda_sin_borde(filas_bbox, i, j)
                texto = _palabras_celda(palabras, bb, excluir=_cajas_de(filas_bbox)) if bb is not None else ""
                nueva.append(texto if texto.strip() else v)
                continue
            texto = _palabras_celda(palabras, bb) if v is not None and bb is not None else ""
            nueva.append(texto if texto.strip() else v)
        nuevos.append(nueva)
    return nuevos


def bordes_horizontales_completos(page, rect):
    """Alturas de las lineas horizontales que cruzan casi todo el ancho de ``rect`` (bordes de fila)."""
    ancho = rect.x1 - rect.x0
    if ancho <= 0:
        return []
    cobertura = collections.defaultdict(float)
    try:
        dibujos = page.get_drawings()
    except Exception:
        return []
    for dr in dibujos:
        for it in dr["items"]:
            if it[0] == "l" and abs(it[1].y - it[2].y) < 0.5:
                y, a, b = it[1].y, min(it[1].x, it[2].x), max(it[1].x, it[2].x)
            elif it[0] == "re" and it[1].height <= 2.5:
                y, a, b = (it[1].y0 + it[1].y1) / 2, it[1].x0, it[1].x1
            else:
                continue
            if rect.y0 - 2 <= y <= rect.y1 + 2:
                cobertura[round(y)] += max(0.0, min(b, rect.x1) - max(a, rect.x0))
    return sorted(y for y, c in cobertura.items() if c >= COBERTURA_BORDE * ancho)


def unir_celdas(textos):
    out = ""
    for t in textos:
        out = unir(out, t)
    return out


def _filas_por_bordes(datos, filas_bbox, bordes):
    """Agrupa en una sola fila las filas de PyMuPDF que caen entre dos bordes reales consecutivos.

    PyMuPDF puede cortar una fila por cada renglon de texto cuando una celda tiene varias lineas; los
    bordes dibujados indican donde termina de verdad cada fila. Las filas fuera del primer y el ultimo
    borde no son de la tabla (p. ej. un organigrama o un parrafo que quedo dentro del rectangulo).
    Devuelve (datos, filas_bbox, (y_inicio, y_fin)).
    """
    grupos = collections.OrderedDict()
    for i, cells in enumerate(filas_bbox):
        ys = [(c[1] + c[3]) / 2 for c in cells if c is not None]
        if not ys:
            continue
        cy = sum(ys) / len(ys)
        k = next((k for k in range(len(bordes) - 1) if bordes[k] - 1 <= cy <= bordes[k + 1] + 1), None)
        if k is not None:
            grupos.setdefault(k, []).append(i)
    nuevos, bbox_nuevos = [], []
    for k, idx in grupos.items():
        ncol = max(len(datos[i]) for i in idx)
        fila, cajas = [], []
        for j in range(ncol):
            textos = [datos[i][j] for i in idx if j < len(datos[i]) and datos[i][j] is not None]
            fila.append(unir_celdas(limpiar_celda(x) for x in textos if x.strip()) if textos else None)
            caja = next((filas_bbox[i][j] for i in idx if j < len(filas_bbox[i]) and filas_bbox[i][j] is not None), None)
            cajas.append(caja)
        nuevos.append(fila)
        bbox_nuevos.append(cajas)
    return nuevos, bbox_nuevos, (bordes[0], bordes[-1])


def tabla_desde_fitz(t, palabras=None, bordes=None):
    """(filas, xs, (y_inicio, y_fin) o None). Con ``bordes`` reales, las filas se rehacen por bordes."""
    datos = t.extract()
    filas_bbox = [r.cells for r in t.rows]
    if palabras is not None:
        datos = _datos_por_palabras(datos, filas_bbox, palabras)
    limites = None
    if bordes and len(bordes) >= 3 and len(bordes) - 1 < len(datos):
        datos, filas_bbox, limites = _filas_por_bordes(datos, filas_bbox, bordes)
    ncol = max((len(r) for r in datos), default=0)
    filas = []
    for i, fila in enumerate(datos):
        nueva = []
        for j in range(ncol):
            v = fila[j] if j < len(fila) else None
            nueva.append(_valor_celda_combinada(i, j, filas, filas_bbox) if v is None else limpiar_celda(v))
        filas.append(nueva)
    filas = _quitar_vacias(_quitar_celdas_repetidas(filas), ncol)
    primera = next((r for r in filas_bbox if r), None)
    xs = [round(c[0]) for c in primera if c is not None] if primera else []
    return filas, xs, limites
