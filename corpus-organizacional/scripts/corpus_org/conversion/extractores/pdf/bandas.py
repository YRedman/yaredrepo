"""Cajas con titulo en banda de color, cajas de organigrama y formas con texto."""

from .lineas import dentro


def formas_con_texto(page, lineas, rect_tablas, w, h):
    """Lineas de texto dentro de formas vectoriales (cajas, rombos, elipses) que no son tablas.

    Indica un diagrama dibujado con formas: su texto se extrae como lineas sueltas sin orden.
    Devuelve 0 si hay menos de 3 formas con texto.
    """
    formas = []
    try:
        dibujos = page.get_drawings()
    except Exception:
        return 0
    for dr in dibujos:
        r = dr.get("rect")
        if r is None:
            continue
        area = abs(r)
        if area < 400 or area > 0.5 * w * h or r.width < 15 or r.height < 10:
            continue
        items = dr.get("items", [])
        if not ({it[0] for it in items} & {"re", "qu", "c"}) and len(items) < 3:
            continue
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        if any(t.x0 - 1 <= cx <= t.x1 + 1 and t.y0 - 1 <= cy <= t.y1 + 1 for t in rect_tablas):
            continue
        formas.append(r)
    if len(formas) < 3:
        return 0
    dentro, con_texto = 0, set()
    for l in lineas:
        cx, cy = (l["x0"] + l["x1"]) / 2, (l["y0"] + l["y1"]) / 2
        for k, r in enumerate(formas):
            if r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1 and (r.x1 - r.x0) < 0.9 * w:
                dentro += 1
                con_texto.add(k)
                break
    return dentro if len(con_texto) >= 3 else 0


ALTO_BANDA = (18, 45)


ALTO_BANDA_DELGADA = 10      # la plantilla GECA-ATTA-FOR-034 usa bandas de ~13 pt: solo cuentan con un titulo centrado en negrita


MAX_SEPARACION_PRIMERA_FILA = 30   # puntos entre el encabezado de la pagina y la fila de continuacion de una caja


MAX_SEPARACION_FILAS = 10


MARGEN_SEPARADOR = 8


def _sin_anidadas(rects):
    """Quita los rectangulos contenidos en otro mas grande (la banda dibuja un rectangulo interior para el titulo)."""
    return [b for b in rects
            if not any(o is not b and abs(o) > abs(b) and o.x0 - 6 <= b.x0 and b.x1 <= o.x1 + 6
                       and o.y0 - 6 <= b.y0 and b.y1 <= o.y1 + 6 for o in rects)]


def _es_alto_de_banda(r, lineas):
    """Altura de una banda de titulo: 18-45 pt, o 10-18 pt si trae un titulo en negrita centrado (asi una fila con
    relleno de color de la misma altura no se confunde con una banda)."""
    if ALTO_BANDA[0] <= r.height <= ALTO_BANDA[1]:
        return True
    if not ALTO_BANDA_DELGADA <= r.height < ALTO_BANDA[0]:
        return False
    centro = (r.x0 + r.x1) / 2
    return any(l.get("bold") and dentro(l, r, 0) and abs((l["x0"] + l["x1"]) / 2 - centro) <= 0.08 * r.width
               for l in lineas)


def rects_banda(page, w, lineas=()):
    """Rectangulos de color de una pagina con forma de banda de titulo (ancho, alto y relleno de las cajas)."""
    try:
        dibujos = page.get_drawings()
    except Exception:
        return []
    return _sin_anidadas([dr["rect"] for dr in dibujos
                          if dr.get("rect") is not None and 0.4 * w <= dr["rect"].width <= 0.95 * w
                          and _es_alto_de_banda(dr["rect"], lineas)
                          and dr.get("fill") not in (None, (0.0, 0.0, 0.0))])


class FilasBanda(list):
    """Filas de una caja de una columna (banda con titulo). ``continuacion``: filas sin banda que siguen a la
    caja con que termina la pagina anterior."""
    continuacion = False


def _filas_de_continuacion(fitz, page, lineas, rect_tablas, separadores, corte_sup, w):
    """Filas con borde fino al comienzo de la pagina, sin banda de titulo: continuan la caja de la pagina anterior."""
    en_tabla = lambda l: any(t.contains(fitz.Point((l["x0"] + l["x1"]) / 2, (l["y0"] + l["y1"]) / 2))
                             for t in rect_tablas)
    candidatas = sorted((l for l in lineas if l["texto"].strip() and not en_tabla(l)), key=lambda l: (l["y0"], l["x0"]))
    filas, fila, previo, fin, x0, x1 = [], [], corte_sup, corte_sup, None, None
    for l in candidatas:
        limite = MAX_SEPARACION_PRIMERA_FILA if not filas and not fila else MAX_SEPARACION_FILAS
        if l["y0"] - previo > limite or l.get("bold"):
            break
        fila.append(l["texto"].strip())
        previo = l["y1"]
        sep = next((s for s in separadores if l["y1"] - 1 <= s.y0 <= l["y1"] + MARGEN_SEPARADOR
                    and s.x0 <= l["x0"] + 3 and s.x1 >= l["x1"] - 3 and (x0 is None or abs(s.x0 - x0) < 3)), None)
        if sep is None:
            continue
        x0, x1 = sep.x0, sep.x1
        filas.append([" ".join(fila)])
        fila, fin = [], sep.y1
        previo = sep.y1
    if not filas:
        return None
    resultado = FilasBanda(filas)
    resultado.continuacion = True
    return fitz.Rect(x0, corte_sup, x1, fin + 1), resultado, [round(x0)]


def bandas_apiladas(fitz, page, lineas, rect_tablas, w, corte_sup=0.0, continua=False):
    """Cajas de una columna dibujadas como una banda de color con el titulo y, debajo, filas con borde fino.

    Son tablas («Accesos a Sistemas», «Herramientas de Trabajo»...) que ``find_tables`` no reconoce: sin esto
    su texto quedaba como lineas sueltas o titulos y el documento se marcaba como «posible diagrama
    vectorial». Una fila solo cuenta si tiene una linea de separacion debajo, asi un parrafo bajo un titulo
    en una banda no se parte en filas. Devuelve [(rect, filas, xs)] como ``_tablas``.
    """
    try:
        dibujos = page.get_drawings()
    except Exception:
        return []
    bandas, separadores = [], []
    for dr in dibujos:
        r = dr.get("rect")
        if r is None or r.width < 0.4 * w:
            continue
        if r.height <= 2:
            separadores.append(r)
        elif _es_alto_de_banda(r, lineas) and dr.get("fill") not in (None, (0.0, 0.0, 0.0)) \
                and r.width <= 0.95 * w:
            if not any(abs(b.y0 - r.y0) < 2 and abs(b.x0 - r.x0) < 2 for b in bandas):
                bandas.append(r)
    bandas = _sin_anidadas(bandas)
    bandas.sort(key=lambda r: r.y0)
    res = []
    for k, b in enumerate(bandas):
        centro = fitz.Point((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2)
        if any(t.contains(centro) for t in rect_tablas):
            continue
        titulo = [l for l in lineas if l["texto"].strip() and dentro(l, b, 0)]
        if not titulo:
            continue
        limite = bandas[k + 1].y0 if k + 1 < len(bandas) else page.rect.height
        candidatas = sorted((l for l in lineas if l["texto"].strip() and l["y0"] >= b.y1 - 2 and l["y1"] <= limite
                             and l["x0"] >= b.x0 - 2 and l["x1"] <= b.x1 + 2
                             and not any(t.contains(fitz.Point((l["x0"] + l["x1"]) / 2, (l["y0"] + l["y1"]) / 2))
                                         for t in rect_tablas)), key=lambda l: l["y0"])
        filas, fila, previo, fin = [], [], b.y1, b.y1
        for l in candidatas:
            if l["y0"] - previo > MAX_SEPARACION_FILAS or l.get("bold"):
                break
            fila.append(l["texto"].strip())
            previo = l["y1"]
            sep = next((s for s in separadores if l["y1"] - 1 <= s.y0 <= l["y1"] + MARGEN_SEPARADOR
                        and s.x0 <= b.x0 + 3 and s.x1 >= b.x1 - 3), None)
            if sep is not None:
                filas.append([" ".join(fila)])
                fila, fin = [], sep.y1
        if not filas:
            continue
        cabecera = " ".join(l["texto"].strip() for l in sorted(titulo, key=lambda l: (l["y0"], l["x0"])))
        res.append((fitz.Rect(b.x0, b.y0, b.x1, fin + 1), FilasBanda([[cabecera]] + filas), [round(b.x0)]))
    if continua:
        sobrantes = [l for l in lineas if not any(dentro(l, r) for r, _, _ in res)]
        cont = _filas_de_continuacion(fitz, page, sobrantes, rect_tablas + [r for r, _, _ in res], separadores,
                                      corte_sup, w)
        if cont is not None:
            res.insert(0, cont)
    return res


def cajas_con_texto(page, lineas, rect_tablas, w, h):
    """Cajas dibujadas (rectangulos chicos) que contienen texto y no son tablas: [(rect, [lineas])].

    Un organigrama o diagrama de cajas se extrae como lineas sueltas que se mezclan con el parrafo de
    al lado; agrupandolas por caja se conserva cada nombre completo y fuera del texto corrido.
    """
    try:
        dibujos = page.get_drawings()
    except Exception:
        return []
    candidatas = []
    for dr in dibujos:
        r = dr.get("rect")
        if r is None or r.width < 30 or r.height < 12 or r.width > 0.6 * w or r.height > 0.25 * h:
            continue
        if any(t.intersects(r) and t.contains(r.tl) for t in rect_tablas):
            continue
        candidatas.append(r)
    # una caja que contiene a otras es el marco del grupo, no una caja del diagrama
    cajas = [r for r in candidatas
             if not any(o != r and r.contains(o) and abs(o) < abs(r) for o in candidatas)]
    resultado = []
    for r in sorted({(c.x0, c.y0, c.x1, c.y1) for c in cajas}, key=lambda c: (c[1], c[0])):
        rect = page.rect.__class__(*r)
        dentro = [l for l in lineas if rect.x0 - 1 <= (l["x0"] + l["x1"]) / 2 <= rect.x1 + 1
                  and rect.y0 - 1 <= (l["y0"] + l["y1"]) / 2 <= rect.y1 + 1]
        if dentro:
            resultado.append((rect, dentro))
    return resultado if len(resultado) >= 2 else []


def es_organigrama(t, filas, rect, ancho_pagina):
    """Una "tabla" angosta de una columna cuyas cajas estan separadas por una fila vacia (la linea que
    las une) es un organigrama, no una tabla de datos."""
    if len(filas) < 2 or any(len(f) != 1 for f in filas) or rect.width > 0.35 * ancho_pagina:
        return False
    crudas = t.extract()
    vacias = [k for k, f in enumerate(crudas) if not any((c or "").strip() for c in f)]
    return any(0 < k < len(crudas) - 1 for k in vacias)
