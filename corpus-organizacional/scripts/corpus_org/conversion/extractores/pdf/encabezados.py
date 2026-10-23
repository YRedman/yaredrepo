"""Encabezados y pies que se repiten en las paginas: deteccion, corte de la zona y votacion entre paginas."""

import collections
import math
import re

from ....comun.texto import norm


RE_PATRON_ENC = re.compile(r"(p[aá]gina\s*\d+\s*(de|/)\s*\d+|\bversi[oó]n\s*:|\brevisi[oó]n\s*:|c[oó]digo\s*:|"
                           r"fecha de (emisi[oó]n|vigencia|elaboraci[oó]n)\s*:)", re.I)
RE_PATRON_PIE = re.compile(r"(p[aá]gina\s*\d+|confidencial|uso interno|documento controlado|copia no controlada)", re.I)
ZONA_SUPERIOR = 0.22      # fraccion de la altura donde se buscan encabezados repetidos
ZONA_INFERIOR = 0.84      # fraccion de la altura a partir de la cual se buscan pies repetidos
MIN_REPETICION_SIN_REF = 0.75   # fraccion de paginas con texto que basta aunque la pagina de referencia no lo tenga
MIN_REPETICION = 0.6      # fraccion de paginas en que debe repetirse un encabezado, pie o logo
TOLERANCIA_ALTURA = 4.0   # puntos: un encabezado o pie repetido esta siempre a la misma altura
SEPARACION_VALOR_ENCABEZADO = 6.0   # puntos entre una etiqueta del encabezado y su valor en la linea de abajo


def clave_rep(texto):
    return re.sub(r"\d+", "#", norm(texto))


def _bordes_horizontales(page):
    bordes = []
    try:
        for dr in page.get_drawings():
            for it in dr["items"]:
                if it[0] == "re":
                    r = it[1]
                    if r.height <= 2.5 and r.width > 20:
                        bordes.append((r.y0, r.y1))
                    elif "s" in (dr.get("type") or "") and r.width > 20:
                        # rectangulo con contorno (recuadro de una tabla): sus lados superior e inferior son bordes
                        w = dr.get("width") or 0.5
                        bordes += [(r.y0 - w / 2, r.y0 + w / 2), (r.y1 - w / 2, r.y1 + w / 2)]
                elif it[0] == "l":
                    p1, p2 = it[1], it[2]
                    if abs(p1.y - p2.y) < 0.5 and abs(p1.x - p2.x) > 20:
                        w = dr.get("width") or 0.5
                        bordes.append((p1.y - w / 2, p1.y + w / 2))
            r = dr.get("rect")
            if r is not None and dr.get("fill") is not None and r.height <= 2.5 and r.width > 20:
                bordes.append((r.y0, r.y1))
    except Exception:
        pass
    return sorted(set((round(a, 2), round(b, 2)) for a, b in bordes))


def es_clave(k, claves):
    if k in claves:
        return True
    if len(k) < 15:
        return False
    return any(len(c) >= 15 and (k.startswith(c) or c.startswith(k)) for c in claves)


def corte_superior(page, fondo_texto):
    """Punto de corte entre el encabezado de la pagina y el contenido."""
    bordes = [b for b in _bordes_horizontales(page) if fondo_texto - 1.5 <= b[0] <= fondo_texto + 8]
    if not bordes:
        return fondo_texto + 0.5
    enc = bordes[0]
    sig = [b for b in bordes[1:] if b[0] >= enc[1] - 0.05]
    if sig and sig[0][0] - enc[1] < 4:
        return (enc[1] + max(sig[0][0], enc[1])) / 2
    return enc[1] + 0.3


def _posiciones_por_zona(lineas, h):
    """{clave: [posiciones]} de las lineas de la zona superior e inferior de una pagina.

    La posicion es la distancia al borde de su zona (arriba para el encabezado, abajo para el pie),
    asi se compara bien aunque las paginas tengan alturas distintas.
    """
    sup, inf = collections.defaultdict(list), collections.defaultdict(list)
    for l in lineas:
        k = clave_rep(l["texto"])
        if len(re.findall(r"[a-z]", k)) < 3:
            continue  # numeros sueltos (filas de tabla, numeros de pagina sin texto)
        if l["y1"] <= ZONA_SUPERIOR * h:
            sup[k].append(l["y0"])
        elif l["y0"] >= ZONA_INFERIOR * h:
            inf[k].append(h - l["y1"])
    return sup, inf


def _repetidas(zonas, ref, minimo, sin_ref=None):
    """Claves que se repiten como encabezado o pie: en ``minimo`` paginas, una sola vez por pagina,
    siempre a la misma altura y presentes en la pagina de referencia.

    Una fila de tabla que continua en la pagina siguiente tambien se repite ("Analista de Procesos",
    "Actividad numero #"), pero aparece varias veces por pagina o a otra altura; un encabezado real no.
    """
    posiciones = collections.defaultdict(list)
    for zona in zonas:
        for k, ys in zona.items():
            if len(ys) == 1:
                posiciones[k].append(ys[0])
    return {k for k, ys in posiciones.items()
            if len(ys) >= minimo and (k in zonas[ref] or len(ys) >= (sin_ref or minimo + 1))
            and max(ys) - min(ys) <= TOLERANCIA_ALTURA}


def detectar_encabezados(paginas_lineas, alturas):
    """Claves de las lineas repetidas en la parte superior e inferior (encabezado y pie)."""
    n = len(paginas_lineas)
    if n < 2:
        return set(), set()
    con_texto = sum(1 for ls in paginas_lineas if sum(l["chars"] for l in ls) >= 25) or n   # las de solo imagen no cuentan
    minimo = max(2, math.ceil(MIN_REPETICION * con_texto))
    ref = next((i for i, ls in enumerate(paginas_lineas) if sum(l["chars"] for l in ls) >= 25), 0)
    zonas = [_posiciones_por_zona(lineas, alturas[i]) for i, lineas in enumerate(paginas_lineas)]
    sin_ref = math.ceil(MIN_REPETICION_SIN_REF * con_texto)     # la pagina de referencia puede no llevar el pie
    return (_repetidas([z[0] for z in zonas], ref, minimo, sin_ref),
            _repetidas([z[1] for z in zonas], ref, minimo, sin_ref))


def encabezado_por_patron(lineas, h):
    """Si no hay encabezado repetido, reconoce uno tipico (Codigo:, Version:, Pagina x de y)."""
    sup = [l for l in lineas if l["y1"] <= 0.18 * h and RE_PATRON_ENC.search(l["texto"])]
    inf = [l for l in lineas if l["y0"] >= 0.88 * h and RE_PATRON_PIE.search(l["texto"])]
    return sup, inf


RE_CAMPO_ENCABEZADO = re.compile(r"^\s*(C[oó]digo|Versi[oó]n|Vigente a partir de|Pr[oó]xima revisi[oó]n|Sustituye a)\s*:\s*(.+?)\s*$", re.I)


def consenso_de_encabezados(encabezado, encabezados_por_pagina, notas=None):
    """El encabezado del documento con cada campo fijo (Código, Versión, Vigencia, Próxima revisión, Sustituye a)
    corregido por voto: el formato repite el mismo encabezado en todas las páginas y el OCR se equivoca en cada una de
    forma distinta («SECA-ATTA» en una de cinco páginas). Gana el valor que se lee igual en al menos dos páginas."""
    if len(encabezados_por_pagina) < 3:
        return encabezado
    votos = collections.defaultdict(collections.Counter)
    for lineas in encabezados_por_pagina:
        for t in lineas:
            m = RE_CAMPO_ENCABEZADO.match(t)
            if m:
                votos[norm(m.group(1))][m.group(2)] += 1
    res = []
    for t in encabezado:
        m = RE_CAMPO_ENCABEZADO.match(t)
        if m and votos.get(norm(m.group(1))):
            valor, n = votos[norm(m.group(1))].most_common(1)[0]
            if n >= 2 and valor != m.group(2):
                if notas is not None:
                    notas.append(f"Encabezado (OCR): «{m.group(1)}: {m.group(2)}» se corrigió a «{valor}» "
                                 f"(así se lee en {n} páginas).")
                t = f"{m.group(1)}: {valor}"
        res.append(t)
    return res
