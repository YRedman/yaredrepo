"""Extractor de PDF (PyMuPDF; pdfplumber y Tesseract son opcionales)."""

import collections
import io
import math
import os
import re
import statistics

from ...comun.esquema import MARCA_COMBINADA
from ...comun.texto import limpiar_celda, nfc, norm, numeros, tokens, unir
from ..modelo import DocumentoExtraido
from .base import Extractor
from ..secciones import clave_titulo, es_seccion_conocida
from .ocr import configurar_pytesseract, idioma_ocr
from .maquetacion import RE_NUM_INICIO, agrupar_filas, bloques_desde_items

RE_PATRON_ENC = re.compile(r"(p[aá]gina\s*\d+\s*(de|/)\s*\d+|\bversi[oó]n\s*:|\brevisi[oó]n\s*:|c[oó]digo\s*:|"
                           r"fecha de (emisi[oó]n|vigencia|elaboraci[oó]n)\s*:)", re.I)
RE_PATRON_PIE = re.compile(r"(p[aá]gina\s*\d+|confidencial|uso interno|documento controlado|copia no controlada)", re.I)
# pdfplumber escribe "(cid:123)" cuando no puede traducir un glifo (vinetas, simbolos); no es texto del documento.
RE_CID = re.compile(r"\(cid:\d+\)")

ZONA_SUPERIOR = 0.22      # fraccion de la altura donde se buscan encabezados repetidos
ZONA_INFERIOR = 0.84      # fraccion de la altura a partir de la cual se buscan pies repetidos
MIN_REPETICION = 0.6      # fraccion de paginas en que debe repetirse un encabezado, pie o logo
TOLERANCIA_ALTURA = 4.0   # puntos: un encabezado o pie repetido esta siempre a la misma altura
SEPARACION_VALOR_ENCABEZADO = 6.0   # puntos entre una etiqueta del encabezado y su valor en la linea de abajo
COBERTURA_BORDE = 0.9     # fraccion del ancho de una tabla que debe cubrir una linea para ser borde de fila
DPI_OCR = 300


def _importar_fitz():
    os.environ.setdefault("PYMUPDF_SUGGEST_LAYOUT_ANALYZER", "0")
    try:
        import pymupdf as fitz
    except ImportError:  # versiones antiguas de PyMuPDF solo exponen 'fitz'
        import fitz
    try:
        fitz.no_recommend_layout()
    except Exception:
        pass
    return fitz


# ---------------------------------------------------------------------------
# Lectura de lineas, bordes y encabezados
# ---------------------------------------------------------------------------

def _es_bold(span):
    fuente = span["font"].lower()
    return bool(span["flags"] & 16) or "bold" in fuente or "black" in fuente


def _lineas_pagina(page, fitz):
    d = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)
    lineas = []
    for b in d["blocks"]:
        for l in b.get("lines", []):
            spans = [s for s in l["spans"] if s["text"].strip()]
            if not spans:
                continue
            texto = "".join(s["text"] for s in l["spans"]).strip()
            x0, y0, x1, y1 = l["bbox"]
            lineas.append({
                "texto": nfc(texto), "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "tam": round(max(spans, key=lambda s: len(s["text"].strip()))["size"], 1),
                "bold": all(_es_bold(s) for s in spans), "font": spans[0]["font"], "spans": spans,
                "chars": sum(len(s["text"].strip()) for s in spans),
            })
    return lineas


def _clave_rep(texto):
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


def _es_clave(k, claves):
    if k in claves:
        return True
    if len(k) < 15:
        return False
    return any(len(c) >= 15 and (k.startswith(c) or c.startswith(k)) for c in claves)


def _corte_superior(page, fondo_texto):
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
        k = _clave_rep(l["texto"])
        if len(re.findall(r"[a-z]", k)) < 3:
            continue  # numeros sueltos (filas de tabla, numeros de pagina sin texto)
        if l["y1"] <= ZONA_SUPERIOR * h:
            sup[k].append(l["y0"])
        elif l["y0"] >= ZONA_INFERIOR * h:
            inf[k].append(h - l["y1"])
    return sup, inf


def _repetidas(zonas, ref, minimo):
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
            if len(ys) >= minimo and k in zonas[ref] and max(ys) - min(ys) <= TOLERANCIA_ALTURA}


def _detectar_encabezados(paginas_lineas, alturas):
    """Claves de las lineas repetidas en la parte superior e inferior (encabezado y pie)."""
    n = len(paginas_lineas)
    if n < 2:
        return set(), set()
    minimo = max(2, math.ceil(MIN_REPETICION * n))
    ref = next((i for i, ls in enumerate(paginas_lineas) if sum(l["chars"] for l in ls) >= 25), 0)
    zonas = [_posiciones_por_zona(lineas, alturas[i]) for i, lineas in enumerate(paginas_lineas)]
    return (_repetidas([z[0] for z in zonas], ref, minimo), _repetidas([z[1] for z in zonas], ref, minimo))


def _encabezado_por_patron(lineas, h):
    """Si no hay encabezado repetido, reconoce uno tipico (Codigo:, Version:, Pagina x de y)."""
    sup = [l for l in lineas if l["y1"] <= 0.18 * h and RE_PATRON_ENC.search(l["texto"])]
    inf = [l for l in lineas if l["y0"] >= 0.88 * h and RE_PATRON_PIE.search(l["texto"])]
    return sup, inf


# ---------------------------------------------------------------------------
# Tablas, zonas y OCR
# ---------------------------------------------------------------------------

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


def _palabras_celda(palabras, bbox):
    """Texto de una celda armado con las palabras de ``get_text("words")`` cuyo centro cae en la celda."""
    x0, y0, x1, y1 = bbox
    sel = sorted((w for w in palabras
                  if x0 - 1 <= (w[0] + w[2]) / 2 <= x1 + 1 and y0 - 1 <= (w[1] + w[3]) / 2 <= y1 + 1),
                 key=lambda w: (w[5], w[6], w[7]))
    lineas, clave = [], None
    for w in sel:
        if (w[5], w[6]) != clave:
            lineas.append([])
            clave = (w[5], w[6])
        lineas[-1].append(w[4])
    return "\n".join(" ".join(l) for l in lineas)


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


def _unir_celdas(textos):
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
            fila.append(_unir_celdas(limpiar_celda(x) for x in textos if x.strip()) if textos else None)
            caja = next((filas_bbox[i][j] for i in idx if j < len(filas_bbox[i]) and filas_bbox[i][j] is not None), None)
            cajas.append(caja)
        nuevos.append(fila)
        bbox_nuevos.append(cajas)
    return nuevos, bbox_nuevos, (bordes[0], bordes[-1])


def _tabla_desde_fitz(t, palabras=None, bordes=None):
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
    filas = _quitar_vacias(filas, ncol)
    primera = next((r for r in filas_bbox if r), None)
    xs = [round(c[0]) for c in primera if c is not None] if primera else []
    return filas, xs, limites


def _formas_con_texto(page, lineas, rect_tablas, w, h):
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


def _cajas_con_texto(page, lineas, rect_tablas, w, h):
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


def _es_organigrama(t, filas, rect, ancho_pagina):
    """Una "tabla" angosta de una columna cuyas cajas estan separadas por una fila vacia (la linea que
    las une) es un organigrama, no una tabla de datos."""
    if len(filas) < 2 or any(len(f) != 1 for f in filas) or rect.width > 0.35 * ancho_pagina:
        return False
    crudas = t.extract()
    vacias = [k for k, f in enumerate(crudas) if not any((c or "").strip() for c in f)]
    return any(0 < k < len(crudas) - 1 for k in vacias)


def _dentro(l, r, margen=1):
    cx, cy = (l["x0"] + l["x1"]) / 2, (l["y0"] + l["y1"]) / 2
    return r.x0 - margen <= cx <= r.x1 + margen and r.y0 - margen <= cy <= r.y1 + margen


def _texto_zona(page, fitz, lineas, rect):
    """Texto de una zona de encabezado o pie: celdas de tabla completas y luego lineas sueltas."""
    textos, rects = [], []
    try:
        for t in page.find_tables(clip=rect).tables:
            rects.append(fitz.Rect(t.bbox))
            for fila in t.extract():
                for c in fila:
                    c = limpiar_celda(c) if c else ""
                    if c and c not in textos:
                        textos.append(c)
    except Exception:
        pass
    resto = [l for l in lineas if not any(_dentro(l, r) for r in rects)]
    for f in agrupar_filas(resto):
        if f["texto"] not in textos:
            textos.append(f["texto"])
    return textos


def palabras_ocr(lineas):
    """Palabras de las lineas OCR, incluidas las que se unen al quitar el guion de fin de linea ("ambien-" + "tal")."""
    lineas = list(lineas)
    palabras = set()
    for k, texto in enumerate(lineas):
        palabras.update(tokens(texto))
        if texto.rstrip().endswith("-") and k + 1 < len(lineas):
            antes, despues = tokens(texto), tokens(lineas[k + 1])
            if antes and despues:
                palabras.add(antes[-1] + despues[0])
    return palabras


def _ocr_lineas(page, idioma):
    """OCR de una pagina escaneada; devuelve lineas con posicion (en puntos PDF)."""
    pytesseract = configurar_pytesseract()
    from PIL import Image
    pix = page.get_pixmap(dpi=DPI_OCR)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    datos = pytesseract.image_to_data(img, lang=idioma, output_type=pytesseract.Output.DICT)
    esc = 72.0 / DPI_OCR
    lineas = collections.OrderedDict()
    for k in range(len(datos["text"])):
        t = (datos["text"][k] or "").strip()
        try:
            conf = float(datos["conf"][k])
        except (TypeError, ValueError):
            conf = -1
        if not t or conf < 0:
            continue
        clave = (datos["block_num"][k], datos["par_num"][k], datos["line_num"][k])
        x, y = datos["left"][k] * esc, datos["top"][k] * esc
        w, h = datos["width"][k] * esc, datos["height"][k] * esc
        L = lineas.setdefault(clave, {"palabras": [], "x0": x, "y0": y, "x1": x + w, "y1": y + h})
        L["palabras"].append(t)
        L["x0"], L["y0"] = min(L["x0"], x), min(L["y0"], y)
        L["x1"], L["y1"] = max(L["x1"], x + w), max(L["y1"], y + h)
    salida = []
    for L in lineas.values():
        texto = nfc(" ".join(L["palabras"]))
        texto = re.sub(r"^[e¢«°•*»©]\s+(?=[A-ZÁÉÍÓÚÑ])", "• ", texto)
        salida.append({"texto": texto, "x0": L["x0"], "y0": L["y0"], "x1": L["x1"], "y1": L["y1"],
                       "tam": 0.0, "bold": False, "font": "ocr", "spans": [],
                       "chars": len(texto.replace(" ", "")), "ocr": True})
    return salida


def _idioma_ocr():
    return idioma_ocr()


MAX_SUELTAS_ENTRE_TABLAS = 3


def _es_suelta_entre_tablas(it):
    """Linea corta que puede quedar entre dos trozos de una tabla partida (fragmento de fila, no un titulo)."""
    if it["tipo"] != "fila":
        return False
    t = it["texto"].strip()
    if not t or len(t.split()) > 15 or (RE_NUM_INICIO.match(t) and it.get("bold")):
        return False
    return not es_seccion_conocida(clave_titulo(t))


def _columnas_compatibles(a, b):
    na = len(a["filas"][0]) if a["filas"] else 0
    nb = len(b["filas"][0]) if b["filas"] else 0
    xs_ok = (not a["xs"] or not b["xs"] or len(a["xs"]) != len(b["xs"]) or
             all(abs(x - y) <= 6 for x, y in zip(a["xs"], b["xs"])))
    return na == nb and na > 0 and xs_ok


def _agregar_continuacion(a, b, d, pagina):
    """Agrega las filas de ``b`` a la tabla ``a`` (sin la cabecera repetida; uniendo una fila partida)."""
    filas_b = b["filas"]
    if filas_b and [norm(c) for c in filas_b[0]] == [norm(c) for c in a["filas"][0]]:
        for c in filas_b[0]:
            d.retirados.update(tokens(c))
        filas_b = filas_b[1:]
    if filas_b and not filas_b[0][0].strip() and any(c.strip() for c in filas_b[0][1:]):
        a["filas"][-1] = [
            (unir(x, y.replace(MARCA_COMBINADA, "")) if y.strip() and not y.endswith(MARCA_COMBINADA) else x)
            for x, y in zip(a["filas"][-1], filas_b[0])]
        filas_b = filas_b[1:]
        d.notas.append(f"Página {pagina + 1}: fila de tabla partida entre páginas; se unió con la anterior.")
    a["filas"].extend(filas_b)
    a["pagina_fin"] = pagina


def _unir_tablas_continuas(items, d):
    """Une una tabla que continua en la pagina siguiente con la de la pagina anterior.

    Tambien si entre ambos trozos quedaron hasta 3 lineas sueltas cortas (fragmentos de una fila que
    no quedaron en celdas): la tabla se une, las lineas se conservan despues de ella y se emite un
    aviso de estructura para revisarla.
    """
    k = 1
    while k < len(items):
        pb, _, _, b = items[k]
        if b["tipo"] != "tabla":
            k += 1
            continue
        j, medio = k - 1, []
        while j >= 0 and len(medio) < MAX_SUELTAS_ENTRE_TABLAS and _es_suelta_entre_tablas(items[j][3]):
            medio.insert(0, j)
            j -= 1
        if j < 0 or items[j][3]["tipo"] != "tabla":
            k += 1
            continue
        a = items[j][3]
        pa = a.get("pagina_fin", items[j][0])
        if pb != pa + 1 or any(items[m][0] not in (pa, pb) for m in medio) or not _columnas_compatibles(a, b):
            k += 1
            continue
        _agregar_continuacion(a, b, d, pb)
        sueltas = [items[m] for m in medio]
        del items[k]
        for m in reversed(medio):
            del items[m]
        for desplazamiento, it in enumerate(sueltas):
            items.insert(j + 1 + desplazamiento, it)
        if sueltas:
            d.avisos.append(f"p.{pb + 1}: tabla partida entre páginas con {len(sueltas)} líneas sueltas en medio; "
                            "se unió la tabla y las líneas quedaron después de ella")
        k = j + 1 + len(sueltas)


# ---------------------------------------------------------------------------
# Extraccion de un documento
# ---------------------------------------------------------------------------

class _ExtraccionPDF:
    """Estado de la extraccion de un PDF concreto (una instancia por archivo)."""

    def __init__(self, fitz, doc_pdf):
        self.fitz = fitz
        self.pdf = doc_pdf
        self.d = DocumentoExtraido(paginas=len(doc_pdf))
        self.items = []            # (pagina, y0, x0, item)
        self.ocr_pendiente = []    # (pagina, lineas, altura)
        self.cortes = []           # (corte_sup, corte_inf) de paginas con encabezado
        self.encabezado_guardado = False
        self.claves_guardadas = set()
        self.rects_organigrama = []    # (pagina, rect) de organigramas ya agregados como marca
        self.ocr_idioma = None
        self.paginas_lineas = [_lineas_pagina(p, fitz) for p in doc_pdf]
        self.alturas = [p.rect.height for p in doc_pdf]
        self.anchos = [p.rect.width for p in doc_pdf]
        self.claves_sup, self.claves_inf = _detectar_encabezados(self.paginas_lineas, self.alturas)
        self.info_img, self.logos = self._imagenes()

    def _imagenes(self):
        """Imagenes por pagina y huellas de logos (imagenes repetidas en varias paginas)."""
        info_img = []
        cuenta = collections.Counter()
        for page in self.pdf:
            try:
                info = page.get_image_info(hashes=True)
            except Exception:
                info = []
            info_img.append(info)
            cuenta.update({i.get("digest") for i in info if i.get("digest")})
        n = self.d.paginas
        min_rep = max(2, math.ceil(MIN_REPETICION * n))
        logos = {k for k, c in cuenta.items() if n >= 2 and c >= min_rep}
        return info_img, logos

    def ejecutar(self):
        for i, page in enumerate(self.pdf):
            if self._es_escaneada(i):
                self._pagina_escaneada(i, page)
            else:
                self._pagina_con_texto(i, page)
        self._aplicar_ocr_pendiente()
        d = self.d
        d.crudo = +d.crudo
        d.numeros = +d.numeros
        self.items.sort(key=lambda t: (t[0], t[1], t[2]))
        _unir_tablas_continuas(self.items, d)
        d.tablas = sum(1 for it in self.items if it[3]["tipo"] == "tabla")
        d.bloques = bloques_desde_items([it[3] for it in self.items])
        return d

    # -- paginas escaneadas --------------------------------------------------

    def _es_escaneada(self, i):
        """Casi sin texto y con una imagen que cubre la pagina."""
        chars = sum(l["chars"] for l in self.paginas_lineas[i])
        area_img = sum(abs(self.fitz.Rect(im["bbox"])) for im in self.info_img[i])
        return chars < 25 and area_img > 0.4 * self.anchos[i] * self.alturas[i]

    def _pagina_escaneada(self, i, page):
        if self.ocr_idioma is None:
            self.ocr_idioma = _idioma_ocr() or ""
        if not self.ocr_idioma:
            self.d.paginas_escaneadas_sin_ocr.append(i + 1)
            self._marca(i, 0, 0, f"[PÁGINA ESCANEADA SIN TEXTO: página {i + 1}; no se pudo aplicar OCR]")
            return
        try:
            ocr = _ocr_lineas(page, self.ocr_idioma)
        except Exception as e:
            ocr = []
            self.d.notas.append(f"OCR falló en la página {i + 1}: {e}")
        self.d.paginas_ocr.append(i + 1)
        self.d.crudo_ocr |= palabras_ocr(l["texto"] for l in ocr)
        self.d.idioma_ocr = self.ocr_idioma
        self._marca(i, -1, 0, f"[TEXTO OCR: página {i + 1} escaneada; revisar contra el original]")
        self.ocr_pendiente.append((i, ocr, self.alturas[i]))

    def _aplicar_ocr_pendiente(self):
        """Agrega el texto OCR quitando el encabezado y pie, ubicados con la mediana de las otras paginas."""
        if not self.ocr_pendiente:
            return
        sups = [c[0] for c in self.cortes if c[0] is not None]
        infs = [c[1] for c in self.cortes if c[1] is not None]
        lim_sup = statistics.median(sups) if sups else None
        lim_inf = statistics.median(infs) if infs else None
        for i, ocr, _h in self.ocr_pendiente:
            quitadas = [l for l in ocr if (lim_sup is not None and l["y1"] <= lim_sup + 2) or
                        (lim_inf is not None and l["y0"] >= lim_inf - 2)]
            if quitadas:
                self.d.notas.append(f"Página {i + 1} (OCR): se quitaron {len(quitadas)} líneas de encabezado o pie.")
            for f in agrupar_filas([l for l in ocr if l not in quitadas]):
                f["pagina"] = i
                f["ocr"] = True
                self.items.append((i, f["y0"], f["x0"], f))

    def _marca(self, pagina, y, x, texto):
        self.items.append((pagina, y, x, {"tipo": "marca", "texto": texto, "pagina": pagina}))

    # -- paginas con texto ----------------------------------------------------

    def _pagina_con_texto(self, i, page):
        lineas = self.paginas_lineas[i]
        h, w = self.alturas[i], self.anchos[i]
        corte_sup, corte_inf, enc_lineas = self._encabezado_y_pie(i, page, lineas, h, w)
        tablas = self._tablas(i, page, self.fitz.Rect(0, corte_sup, w, corte_inf))
        lineas = self._organigrama(i, page, lineas, enc_lineas, tablas, w, h)
        self._contenido(i, lineas, enc_lineas, tablas)
        ids_enc = {id(l) for l in enc_lineas}
        en_formas = _formas_con_texto(page, [l for l in lineas if id(l) not in ids_enc], [r for r, _, _ in tablas], w, h)
        if en_formas:
            self.d.avisos.append(f"p.{i + 1}: posible diagrama vectorial ({en_formas} líneas de texto dentro de "
                                 "formas); su texto quedó como líneas sueltas")
        self._imagenes_contenido(i, corte_sup, corte_inf, w, h)
        # texto crudo de verificacion (motor principal, pagina completa, sin encabezado ni pie)
        crudo = re.sub(r"(\w)-\n(?=[a-záéíóúüñ])", r"\1", page.get_text("text"))
        self.d.crudo.update(tokens(crudo))
        self.d.numeros.update(numeros(crudo))
        for l in enc_lineas:
            self.d.crudo.subtract(tokens(l["texto"]))
            self.d.numeros.subtract(numeros(l["texto"]))

    def _encabezado_y_pie(self, i, page, lineas, h, w):
        sup = [l for l in lineas if l["y1"] <= ZONA_SUPERIOR * h and _es_clave(_clave_rep(l["texto"]), self.claves_sup)]
        inf = [l for l in lineas if l["y0"] >= ZONA_INFERIOR * h and _es_clave(_clave_rep(l["texto"]), self.claves_inf)]
        if not self.claves_sup and not self.claves_inf:
            sup, inf = _encabezado_por_patron(lineas, h)
        corte_sup, corte_inf = 0.0, h
        enc_lineas = []
        if sup:
            fondo = self._fondo_encabezado(sup, lineas, h, w)
            corte_sup = _corte_superior(page, fondo)
            enc_lineas += [l for l in lineas if l["y1"] <= fondo + 0.5]
        if inf:
            inf = sorted(inf, key=lambda l: -l["y1"])
            tope = inf[0]["y0"]
            for l in inf[1:]:
                if l["y1"] < tope - 14:
                    break
                tope = min(tope, l["y0"])
            corte_inf = tope - 0.5
            enc_lineas += [l for l in lineas if l["y0"] >= tope - 0.5]
        if enc_lineas:
            if not self.encabezado_guardado:
                self._guardar_encabezado(page, enc_lineas, corte_sup, corte_inf, w, h)
                self.claves_guardadas = {_clave_rep(l["texto"]) for l in enc_lineas}
            else:
                enc_lineas = self._sin_texto_unico(i, enc_lineas)
            for l in enc_lineas:
                self.d.crudo_encabezado.update(tokens(l["texto"]))
        if sup or inf:
            self.cortes.append((corte_sup if sup else None, corte_inf if inf else None))
        return corte_sup, corte_inf, enc_lineas

    def _sin_texto_unico(self, i, enc_lineas):
        """Deja como contenido las lineas de la zona de encabezado o pie que no estan en el encabezado guardado.

        El encabezado se guarda una sola vez (el de la primera pagina) y en las demas paginas se descarta.
        Una linea que no se parece a ninguna de las guardadas no es un encabezado repetido: si se
        descartara, su texto desapareceria del corpus sin que la verificacion lo notara.
        """
        unicas = [l for l in enc_lineas if len(re.findall(r"[a-z]", _clave_rep(l["texto"]))) >= 3
                  and _clave_rep(l["texto"]) not in self.claves_guardadas]
        if unicas:
            ids = {id(l) for l in unicas}
            self.d.avisos.append(f"p.{i + 1}: {len(unicas)} líneas en la zona de encabezado o pie no coinciden "
                                 "con el encabezado de la primera página; se conservaron como contenido")
            return [l for l in enc_lineas if id(l) not in ids]
        return enc_lineas

    @staticmethod
    def _fondo_encabezado(sup, lineas, h, w):
        """Zona continua desde arriba: se detiene en el primer salto grande entre lineas repetidas."""
        sup = sorted(sup, key=lambda l: l["y0"])
        fondo = sup[0]["y1"]
        for l in sup[1:]:
            if l["y0"] > fondo + 14:
                break
            fondo = max(fondo, l["y1"])
        # lineas sueltas pegadas al encabezado: el final de una linea partida o el valor numerico que esta
        # debajo de su etiqueta en la misma celda ("Vigencia:" / "01/02/2024", "Página:" / "1 de 3")
        for l in sorted(lineas, key=lambda l: l["y0"]):
            if l["y1"] <= fondo + 0.5:
                continue
            if l["y0"] > fondo + SEPARACION_VALOR_ENCABEZADO or l["y1"] > ZONA_SUPERIOR * h:
                break
            if len(re.findall(r"[A-Za-z]", l["texto"])) < 3 and l["y1"] - fondo < 14:
                fondo = l["y1"]
        return fondo

    def _guardar_encabezado(self, page, enc_lineas, corte_sup, corte_inf, w, h):
        fitz = self.fitz
        zona_sup = [l for l in enc_lineas if l["y1"] <= corte_sup + 0.5]
        zona_inf = [l for l in enc_lineas if l["y1"] > corte_sup + 0.5]
        self.d.encabezado = (
            (_texto_zona(page, fitz, zona_sup, fitz.Rect(0, 0, w, corte_sup)) if zona_sup else [])
            + (_texto_zona(page, fitz, zona_inf, fitz.Rect(0, corte_inf, w, h)) if zona_inf else []))
        self.encabezado_guardado = True

    def _organigrama(self, i, page, lineas, enc_lineas, tablas, w, h):
        """Saca del texto corrido las lineas que estan dentro de cajas de un organigrama y las agrega
        como una marca seguida de las cajas en orden (de arriba hacia abajo). Devuelve las lineas restantes."""
        ids_enc = {id(l) for l in enc_lineas}
        # las cajas ya leidas como organigrama desde una tabla de una columna no se agregan otra vez
        ocupadas = [r for r, _, _ in tablas] + [r for p, r in self.rects_organigrama if p == i]
        libres = [l for l in lineas if id(l) not in ids_enc and not any(_dentro(l, r) for r in ocupadas)]
        cajas = _cajas_con_texto(page, libres, [r for r, _, _ in tablas], w, h)
        if not cajas:
            return lineas
        usadas = {id(l) for _, ls in cajas for l in ls}
        textos = [_unir_celdas(l["texto"].strip() for l in sorted(ls, key=lambda l: (l["y0"], l["x0"])))
                  for _, ls in cajas]
        self._agregar_organigrama(i, cajas[0][0], textos)
        for _, ls in cajas:
            for l in ls:
                self.d.lineas_diag.append((i + 1, "organigrama", l["texto"]))
        return [l for l in lineas if id(l) not in usadas]

    def _agregar_organigrama(self, i, rect, cajas):
        """Marca de organigrama seguida de sus cajas en orden (de arriba hacia abajo)."""
        self._marca(i, rect.y0, rect.x0, f"[ORGANIGRAMA: cajas de arriba hacia abajo; ver página {i + 1} del original]")
        self.items.append((i, rect.y0 + 0.01, rect.x0, {"tipo": "marca", "texto": " → ".join(cajas), "pagina": i}))
        self.rects_organigrama.append((i, rect))

    def _tablas(self, i, page, clip):
        tablas = []
        try:
            palabras = page.get_text("words")
            for t in page.find_tables(clip=clip).tables:
                rect = self.fitz.Rect(t.bbox)
                filas, xs, limites = _tabla_desde_fitz(t, palabras, bordes_horizontales_completos(page, rect))
                if not filas or (len(filas) == 1 and len(filas[0]) == 1):
                    continue  # vacia o recuadro simple: se trata como texto
                if limites:
                    # lo que queda fuera de los bordes reales (organigrama, parrafo) se lee como texto
                    rect = self.fitz.Rect(rect.x0, limites[0], rect.x1, limites[1])
                if _es_organigrama(t, filas, rect, page.rect.width):
                    self._agregar_organigrama(i, rect, [f[0] for f in filas])
                    continue
                tablas.append((rect, filas, xs))
        except Exception as e:
            self.d.notas.append(f"No se pudieron leer tablas en la página {i + 1}: {e}")
        return tablas

    def _contenido(self, i, lineas, enc_lineas, tablas):
        """Reparte las lineas entre tablas y texto. Nunca descarta una linea que no sea encabezado o pie."""
        d = self.d
        ids_enc = {id(l) for l in enc_lineas}
        contenido = []
        en_tabla = collections.defaultdict(list)
        for l in lineas:
            if id(l) in ids_enc:
                d.lineas_diag.append((i + 1, "encabezado o pie", l["texto"]))
                continue
            if any(p == i and _dentro(l, r) for p, r in self.rects_organigrama):
                d.lineas_diag.append((i + 1, "organigrama", l["texto"]))
                continue
            k = next((k for k, (r, _, _) in enumerate(tablas) if _dentro(l, r)), None)
            if k is not None:
                en_tabla[k].append(l)
            else:
                contenido.append(l)
                d.lineas_diag.append((i + 1, "texto", l["texto"]))
        # cada tabla debe contener el texto de las lineas que cubre; lo que no, se conserva como texto
        for k, (r, filas, xs) in enumerate(tablas):
            disponibles = collections.Counter(tokens(" ".join(" ".join(c.replace(MARCA_COMBINADA, "") for c in f)
                                                              for f in filas)))
            propias = sorted(en_tabla.get(k, []), key=lambda l: (l["y0"], l["x0"]))
            sueltas = []
            for l in propias:
                tk = collections.Counter(tokens(l["texto"]))
                if tk - disponibles:
                    sueltas.append(l)
                else:
                    disponibles -= tk
            total = sum(len(tokens(l["texto"])) for l in propias)
            perdidas = sum(len(tokens(l["texto"])) for l in sueltas)
            if total and perdidas > 0.3 * total:
                contenido.extend(propias)
                d.lineas_diag += [(i + 1, "posible tabla tratada como texto", l["texto"]) for l in propias]
                d.avisos.append(f"p.{i + 1}: posible tabla tratada como texto ({perdidas} de {total} palabras "
                                "fuera de celdas)")
                continue
            if sueltas:
                contenido.extend(sueltas)
                d.avisos.append(f"p.{i + 1}: {len(sueltas)} líneas de una tabla fuera de sus celdas; se agregaron "
                                "como texto junto a la tabla")
            d.lineas_diag += [(i + 1, "tabla", l["texto"]) for l in propias]
            self.items.append((i, r.y0, r.x0, {"tipo": "tabla", "filas": filas, "xs": xs, "y0": r.y0, "y1": r.y1,
                                               "pagina": i}))
        for f in agrupar_filas(contenido):
            f["pagina"] = i
            self.items.append((i, f["y0"], f["x0"], f))

    def _imagenes_contenido(self, i, corte_sup, corte_inf, w, h):
        for im in self.info_img[i]:
            r = self.fitz.Rect(im["bbox"])
            if im.get("digest") in self.logos:
                continue
            cy = (r.y0 + r.y1) / 2
            if cy < corte_sup or cy > corte_inf:
                continue
            if abs(r) > 0.06 * w * h:
                self.d.diagramas.append(i + 1)
                self._marca(i, r.y0, r.x0, f"[DIAGRAMA O IMAGEN: ver página {i + 1} del documento original]")
            elif abs(r) > 400:
                self.d.imagenes_omitidas += 1
                self._marca(i, r.y0, r.x0, "[IMAGEN OMITIDA]")


def _tokens_pdfplumber(path, omitir_paginas):
    """Tokens que lee un segundo motor (pdfplumber), sin paginas escaneadas ni glifos sin traducir."""
    import pdfplumber
    cruz = set()
    with pdfplumber.open(path) as pl:
        for k, pg in enumerate(pl.pages):
            if (k + 1) in omitir_paginas:
                continue
            cruz.update(tokens(RE_CID.sub(" ", pg.extract_text() or "")))
    return cruz


class ExtractorPDF(Extractor):
    extensiones = (".pdf",)

    def __init__(self, verificacion_cruzada=True):
        self.verificacion_cruzada = verificacion_cruzada

    def extraer(self, path):
        fitz = _importar_fitz()
        doc_pdf = fitz.open(str(path))
        try:
            if doc_pdf.needs_pass:
                raise RuntimeError("El PDF está protegido con contraseña.")
            d = _ExtraccionPDF(fitz, doc_pdf).ejecutar()
        finally:
            doc_pdf.close()
        if self.verificacion_cruzada:
            try:
                d.texto_cruzado = _tokens_pdfplumber(str(path), set(d.paginas_ocr) | set(d.paginas_escaneadas_sin_ocr))
            except Exception as e:
                d.notas.append(f"Verificación cruzada con pdfplumber no disponible: {e}")
        return d
