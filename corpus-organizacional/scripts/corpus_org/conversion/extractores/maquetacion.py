"""Reconstruccion de la estructura (titulos, parrafos, listas, tablas) a partir de lineas posicionadas.

Lo usa el extractor de PDF (y el OCR): recibe lineas con coordenadas y devuelve
bloques del modelo intermedio. No depende de PyMuPDF.
"""

import collections
import re

from ...comun.texto import unir
from ..modelo import bloque_h
from ..secciones import (buscar_alias, clave_titulo, es_excluida, es_seccion_conocida, es_titulo_corto,
                         profundidad_numeracion)
from ..configuracion import SECCIONES_D, SECCIONES_P

BULLETS = set("•●○◦▪■□–—-*·►➢➤✓✔◆◇") | {"", "", "", "", "", "", "",
                                       "", "", ""}
RE_VINETA_INICIAL = re.compile(r"^([•●○◦▪■□►➢➤✓✔◆◇])\s*(\S.*)$")
RE_MARCADOR_NUM = re.compile(r"^(?:\d{1,3}(?:\.\d{1,3})*[\.\)]?|[a-zA-Z][\.\)]|[ivxlcdmIVXLCDM]{1,6}[\.\)])$")
RE_NUM_INICIO = re.compile(r"^\s*((?:\d{1,3}(?:\.\d{1,3})*\.?)|(?:[IVXLC]{1,6}\.)|(?:[a-z]\)))\s+(\S.*)$")
RE_ROMANO = re.compile(r"^[IVXLC]{1,6}\.\s")


# ---------------------------------------------------------------------------
# Lineas -> filas
# ---------------------------------------------------------------------------

def _es_simbolo_vineta(parte):
    t = parte["texto"].strip()
    fuente = parte["font"].lower()
    return t in BULLETS or (len(t) == 1 and ("symbol" in fuente or "wingding" in fuente))


def agrupar_filas(lineas):
    """Agrupa lineas que estan a la misma altura (vineta + texto, celdas sueltas)."""
    lineas = sorted(lineas, key=lambda l: (round(l["y0"], 0), l["x0"]))
    filas = []
    for l in lineas:
        cy = (l["y0"] + l["y1"]) / 2
        if filas:
            f = filas[-1]
            fcy = (f["y0"] + f["y1"]) / 2
            alto = min(l["y1"] - l["y0"], f["y1"] - f["y0"])
            if abs(cy - fcy) < 0.45 * max(alto, 4) and l["x0"] >= f["partes"][-1]["x1"] - 2:
                f["partes"].append(l)
                f["x1"] = max(f["x1"], l["x1"])
                f["y0"] = min(f["y0"], l["y0"])
                f["y1"] = max(f["y1"], l["y1"])
                continue
        filas.append({"partes": [l], "x0": l["x0"], "x1": l["x1"], "y0": l["y0"], "y1": l["y1"]})
    return [_fila_desde_partes(f) for f in filas]


def _fila_desde_partes(f):
    partes = f["partes"]
    vineta = marcador = vineta_x = None
    p0 = partes[0]
    t0 = p0["texto"].strip()
    if len(partes) > 1 and _es_simbolo_vineta(p0):
        vineta = p0["x0"]
        partes = partes[1:]
    elif len(partes) > 1 and RE_MARCADOR_NUM.match(t0) and partes[1]["x0"] - p0["x1"] > 3:
        marcador = t0
        vineta_x = p0["x0"]
        partes = partes[1:]
    else:
        m = RE_VINETA_INICIAL.match(t0)
        if m:
            vineta = p0["x0"]
            p0 = dict(p0, texto=m.group(2))
            partes = [p0] + partes[1:]
    texto = ""
    for p in partes:
        texto = (texto + " " + p["texto"]).strip() if texto else p["texto"]
    celdas = []
    for p in partes:
        if celdas and p["x0"] - celdas[-1]["x1"] < 15:
            celdas[-1]["texto"] += " " + p["texto"]
            celdas[-1]["x1"] = p["x1"]
        else:
            celdas.append({"x0": p["x0"], "x1": p["x1"], "texto": p["texto"]})
    return {
        "texto": texto, "x0": partes[0]["x0"], "x1": f["x1"], "y0": f["y0"], "y1": f["y1"],
        "tam": max(partes, key=lambda p: p["chars"])["tam"], "bold": all(p["bold"] for p in partes),
        "chars": sum(p["chars"] for p in partes), "vineta": vineta, "marcador": marcador,
        "x_marcador": vineta_x, "tipo": "fila", "celdas": celdas, "ocr": any(p.get("ocr") for p in partes),
    }


# ---------------------------------------------------------------------------
# Tablas sin bordes
# ---------------------------------------------------------------------------

def _es_fila_multicolumna(f):
    return f["tipo"] == "fila" and len(f.get("celdas", [])) >= 2 and f.get("vineta") is None and not f.get("marcador")


def _corta_tabla_sin_bordes(fila, anterior):
    """Una fila de una sola celda que parece titulo termina la tabla sin bordes."""
    t1 = fila["celdas"][0]["texto"]
    clave = clave_titulo(t1)
    return ((fila["bold"] and not anterior["bold"]) or re.match(r"^\s*\d+(\.\d+)*\.?\s+\S", t1)
            or buscar_alias(clave, SECCIONES_P + SECCIONES_D) or es_excluida(clave))


def tablas_sin_bordes(items):
    """Reconoce tablas sin bordes: varias filas seguidas con texto en columnas alineadas."""
    salida = []
    k, n = 0, len(items)
    while k < n:
        it = items[k]
        if not _es_fila_multicolumna(it):
            salida.append(it)
            k += 1
            continue
        cols = [c["x0"] for c in it["celdas"]]
        filas = [[c["texto"] for c in it["celdas"]]]
        ult = it
        j = k + 1
        multiples = 1
        while j < n:
            f = items[j]
            if f["tipo"] != "fila" or f.get("pagina") != ult.get("pagina"):
                break
            alto = max(f["y1"] - f["y0"], 1)
            if f["y0"] - ult["y1"] > 1.6 * alto:
                break
            pos = []
            for c in f.get("celdas", []):
                m = [ci for ci, x in enumerate(cols) if abs(c["x0"] - x) <= 8]
                pos.append(m[0] if m else None)
            if None in pos or not pos:
                break
            if _es_fila_multicolumna(f) and len(set(pos)) == len(pos):
                fila = [""] * len(cols)
                for ci, c in zip(pos, f["celdas"]):
                    fila[ci] = c["texto"]
                filas.append(fila)
                multiples += 1
            elif len(pos) == 1:
                if _corta_tabla_sin_bordes(f, ult):
                    break
                ci = pos[0]
                t = f["celdas"][0]["texto"]
                filas[-1][ci] = unir(filas[-1][ci], t) if filas[-1][ci] else t
            else:
                break
            ult = f
            j += 1
        if multiples >= 2:
            filas = [f + [""] * (len(cols) - len(f)) for f in filas]
            salida.append({"tipo": "tabla", "filas": filas, "sin_bordes": True, "pagina": it.get("pagina")})
            k = j
        else:
            salida.append(it)
            k += 1
    return salida


# ---------------------------------------------------------------------------
# Filas -> bloques
# ---------------------------------------------------------------------------

def nivel_titulo(f, tam_cuerpo, tam_titulos):
    """Nivel de titulo (1-3) de una fila, o 0 si es texto normal."""
    texto = f["texto"].strip()
    if f.get("vineta") is not None:
        return 0
    completo = (f.get("marcador") + " " + texto) if f.get("marcador") else texto
    clave = clave_titulo(completo)
    corto = es_titulo_corto(completo)
    m = re.match(r"^\s*(\d{1,3}(?:\.\d{1,3})*)\.?\s+\S", completo)
    profundidad = profundidad_numeracion(completo)
    if es_seccion_conocida(clave) and corto and len(clave.split()) <= 6 and (
            f["bold"] or f["tam"] >= tam_cuerpo + 1 or clave == completo.strip(" :").lower()
            or len(completo.split()) <= 5):
        return profundidad if (profundidad and profundidad > 1) else 1
    if not corto or texto.endswith((",", ";")):
        return 0
    if f.get("ocr"):
        if profundidad and profundidad > 1 and len(texto.split()) <= 8 and not texto.endswith("."):
            return min(profundidad, 3)
        return 0
    if texto.endswith(":") and not f["bold"]:
        return 0
    grande = f["tam"] >= tam_cuerpo + 1.0 and f["tam"] > 0
    if f["bold"] or grande:
        if texto.endswith(".") and len(texto.split()) > 6 and not m:
            return 0
        if texto.endswith(":") and not grande:
            return 0
        if profundidad:
            return min(profundidad, 3)
        if RE_ROMANO.match(completo):
            return 1
        if grande and tam_titulos:
            rango = tam_titulos.index(f["tam"]) if f["tam"] in tam_titulos else len(tam_titulos)
            return min(1 + rango, 3)
        return 2
    return 0


def _tamano_cuerpo(filas):
    cuenta = collections.Counter()
    for f in filas:
        if not f.get("ocr"):
            cuenta[f["tam"]] += f["chars"]
    return cuenta.most_common(1)[0][0] if cuenta else 10.0


def bloques_desde_items(items):
    """Convierte filas de texto, tablas y marcas en bloques (titulos, parrafos, listas)."""
    items = tablas_sin_bordes(items)
    filas = [it for it in items if it["tipo"] == "fila"]
    tam_cuerpo = _tamano_cuerpo(filas)
    borde_der = {}
    for f in filas:
        borde_der[f["pagina"]] = max(borde_der.get(f["pagina"], 0), f["x1"])
    tam_titulos = sorted({f["tam"] for f in filas if f["tam"] >= tam_cuerpo + 1.0 and not f.get("ocr")},
                         reverse=True)

    bloques = []
    actual = None  # bloque en construccion
    previo = None  # fila anterior

    def cerrar():
        nonlocal actual
        if actual is not None:
            bloques.append(actual)
            actual = None

    for it in items:
        if it["tipo"] != "fila":
            cerrar()
            previo = None
            if it["tipo"] == "tabla":
                bloques.append({"k": "tabla", "filas": it["filas"], "pagina": it.get("pagina")})
            else:
                bloques.append({"k": "marca", "texto": it["texto"], "pagina": it.get("pagina")})
            continue
        texto = it["texto"].strip()
        if not texto:
            continue
        nivel = nivel_titulo(it, tam_cuerpo, tam_titulos)
        if nivel:
            # titulo partido en dos lineas
            if (actual is not None and actual["k"] == "h" and previo is not None and previo.get("es_titulo")
                    and it["y0"] - previo["y1"] < 0.6 * (it["y1"] - it["y0"]) and abs(it["tam"] - previo["tam"]) < 0.3
                    and not RE_NUM_INICIO.match(texto) and not actual["texto"].endswith((".", ":"))):
                actual["texto"] = unir(actual["texto"], texto)
                previo = dict(it, es_titulo=True)
                continue
            cerrar()
            if it.get("marcador"):
                texto = it["marcador"] + " " + texto
            actual = bloque_h(nivel, texto)
            actual["ocr"] = it.get("ocr", False)
            actual["pagina"] = it.get("pagina")
            previo = dict(it, es_titulo=True)
            continue
        if it.get("vineta") is not None or it.get("marcador"):
            cerrar()
            marcador = "-" if it.get("vineta") is not None else it["marcador"]
            xv = it.get("vineta") if it.get("vineta") is not None else (it.get("x_marcador") or it["x0"])
            actual = {"k": "li", "marcador": marcador, "texto": texto, "x_texto": it["x0"], "x_vineta": xv,
                      "ocr": it.get("ocr", False), "pagina": it.get("pagina")}
            previo = it
            continue
        m = RE_NUM_INICIO.match(texto)
        if m and re.match(r"^\d{1,2}[\.\)]$|^[a-z]\)$", m.group(1)) and not it["bold"]:
            cerrar()
            actual = {"k": "li", "marcador": m.group(1), "texto": m.group(2), "x_texto": it["x0"],
                      "x_vineta": it["x0"], "ocr": it.get("ocr", False), "pagina": it.get("pagina")}
            previo = it
            continue
        if actual is not None and actual["k"] in ("p", "li") and previo is not None \
                and previo.get("pagina") is not None and _continua(actual, previo, it, borde_der):
            actual["texto"] = unir(actual["texto"], texto)
            actual["ocr"] = actual.get("ocr") or it.get("ocr", False)
            previo = it
            continue
        cerrar()
        actual = {"k": "p", "texto": texto, "ocr": it.get("ocr", False), "pagina": it.get("pagina")}
        previo = it
    cerrar()
    _asignar_niveles_lista(bloques)
    return bloques


def _continua(actual, previo, it, borde_der):
    """True si la fila ``it`` continua el parrafo o item ``actual``."""
    alto = max(it["y1"] - it["y0"], 1)
    mismo_pag = previo.get("pagina") == it.get("pagina")
    hueco = it["y0"] - previo["y1"] if mismo_pag else 0
    der = borde_der.get(previo.get("pagina"), previo["x1"])
    termina = previo["texto"].rstrip().endswith((".", ":", ";", "!", "?"))
    fin_parrafo = termina and (not mismo_pag or previo["x1"] < der - 25)
    if actual["k"] == "li":
        alineado = (abs(it["x0"] - actual["x_texto"]) <= 4 or
                    actual["x_vineta"] + 4 < it["x0"] <= actual["x_texto"] + 30)
    else:
        alineado = abs(it["x0"] - previo["x0"]) <= 4 or it["x0"] < previo["x0"]
    return (((mismo_pag and 0 <= hueco < 0.6 * alto) or not mismo_pag) and alineado and not fin_parrafo
            and abs(it["tam"] - previo["tam"]) < 1.0)


def _asignar_niveles_lista(bloques):
    """Nivel de cada item de lista segun su sangria."""
    xs = sorted({round(b["x_vineta"]) for b in bloques if b["k"] == "li"})
    base = xs[0] if xs else 0
    for b in bloques:
        if b["k"] == "li":
            b["nivel"] = min(3, max(0, int(round((b["x_vineta"] - base) / 16.0))))
