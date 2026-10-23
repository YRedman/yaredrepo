"""PDF en pliegos: paginas apaisadas con dos paginas de libro lado a lado, que se leen como dos."""

from .lineas import lineas_pagina


RAZON_PLIEGO = (1.38, 1.75)     # ancho/alto de dos paginas de libro lado a lado (A4: 1.41, carta: 1.55)


ANCHO_CANAL = 4.0               # puntos a cada lado del centro donde no debe cruzar texto


MAX_CRUZAN_CANAL = 0.03         # fraccion de lineas que pueden cruzar el centro


MIN_PLIEGOS = 0.6               # fraccion de las paginas apaisadas que deben ser pliegos


MIN_PLIEGOS_CON_AMBOS = 3       # pliegos con texto en las dos mitades para tratar el PDF como folleto


def _perfil_pliego(page, fitz):
    """(canal limpio, texto en ambos lados) de una pagina apaisada con razon de pliego; None si no la tiene."""
    w, h = page.rect.width, page.rect.height
    if not h or not RAZON_PLIEGO[0] <= w / h <= RAZON_PLIEGO[1]:
        return None
    lineas = lineas_pagina(page, fitz)
    centro = w / 2
    izq = sum(1 for l in lineas if l["x1"] <= centro + ANCHO_CANAL)
    der = sum(1 for l in lineas if l["x0"] >= centro - ANCHO_CANAL)
    cruzan = sum(1 for l in lineas if l["x0"] < centro - ANCHO_CANAL and l["x1"] > centro + ANCHO_CANAL)
    return cruzan <= MAX_CRUZAN_CANAL * len(lineas), bool(izq and der)


def separar_pliegos(fitz, doc):
    """(documento, origen): si el PDF es un folleto en pliegos, otro documento con cada pliego partido en sus dos
    paginas (izquierda, derecha) para que el orden de lectura no mezcle ambas; ``origen[k]`` es la pagina
    original de la pagina ``k``. Las paginas sueltas (portada, contraportada) quedan igual. Es un folleto en
    pliegos si la mayoria de las paginas apaisadas tienen el centro sin texto cruzado y varias tienen texto
    en las dos mitades; si no, devuelve el mismo documento."""
    perfiles = {i: _perfil_pliego(pg, fitz) for i, pg in enumerate(doc)}
    apaisadas = {i: p for i, p in perfiles.items() if p is not None}
    pliegos = {i for i, (limpio, _) in apaisadas.items() if limpio}
    con_ambos = sum(1 for i in pliegos if apaisadas[i][1])
    if con_ambos < MIN_PLIEGOS_CON_AMBOS or len(pliegos) < MIN_PLIEGOS * len(apaisadas):
        return doc, list(range(len(doc)))
    nuevo, origen = fitz.open(), []
    for i, pg in enumerate(doc):
        r = pg.rect
        mitades = [fitz.Rect(r.x0, r.y0, (r.x0 + r.x1) / 2, r.y1),
                   fitz.Rect((r.x0 + r.x1) / 2, r.y0, r.x1, r.y1)] if i in pliegos else [r]
        for clip in mitades:
            hoja = nuevo.new_page(width=clip.width, height=clip.height)
            hoja.show_pdf_page(hoja.rect, doc, i, clip=clip)
            origen.append(i)
    return nuevo, origen
