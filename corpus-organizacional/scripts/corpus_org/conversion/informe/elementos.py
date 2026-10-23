"""Piezas de HTML que usan varias secciones del informe: texto escapado, barras, tarjetas, tablas y rutas."""

import html
from pathlib import Path
from urllib.parse import quote

ORIGENES = ("entrada", "contexto")
CARACTERES_CARPETA, CARACTERES_NOMBRE = 28, 60


def esc(x):
    return html.escape(str(x if x is not None else ""))


def numero(x, defecto=0.0):
    """Numero de un texto de CSV (admite '%' y coma decimal); ``defecto`` si no se puede leer."""
    try:
        return float(str(x).replace("%", "").replace(",", ".").strip())
    except ValueError:
        return defecto


def codigo_html(codigo):
    return f'<b class="mono">{esc(codigo)}</b>'


def alerta(clase, contenido_html):
    return f'<div class="alerta {clase}">{contenido_html}</div>'


def tarjeta(valor, texto, clase=""):
    return f'<div class="tarjeta {clase}"><b>{esc(valor)}</b><span>{esc(texto)}</span></div>'


def barra(valor, maximo=100.0, objetivo=None):
    pct = max(0.0, min(100.0, 100.0 * valor / maximo)) if maximo else 0.0
    clase = ""
    if objetivo is not None:
        clase = " mala" if valor < objetivo - 20 else (" baja" if valor < objetivo else "")
    return f'<div class="barra{clase}" title="{valor:.0f}"><i style="width:{pct:.0f}%"></i></div>'


def enlace_original(ruta_relativa, datos):
    """URL file:// del original: ``entrada/<ruta>`` o ``contexto/<ruta>`` bajo las carpetas guardadas en construccion.json."""
    if not ruta_relativa:
        return ""
    primero, _, resto = ruta_relativa.partition("/")
    base = datos.get(primero) if primero in ORIGENES else None
    if not base or not resto:
        return ""
    ruta = Path(base) / resto
    return "file:///" + quote(str(ruta).replace("\\", "/").lstrip("/"), safe="/:")


def _recortar(texto, maximo):
    return texto[:maximo] + ("…" if len(texto) > maximo else "")


def celda_ruta(ruta, datos):
    """Origen (entrada o contexto) y las dos ultimas partes de la ruta; la ruta completa en el texto emergente y el enlace."""
    if not ruta:
        return ""
    origen, _, resto = ruta.partition("/")
    partes = [x for x in resto.split("/") if x]
    nombre = partes[-1] if partes else ruta
    carpeta = partes[-2] if len(partes) > 1 else ""
    corto = (_recortar(carpeta, CARACTERES_CARPETA) + "/" if carpeta else "") + _recortar(nombre, CARACTERES_NOMBRE)
    pill = f'<span class="pill {"aviso" if origen == "contexto" else "ok"}">{esc(origen)}</span> ' \
        if origen in ORIGENES else ""
    url = enlace_original(ruta, datos)
    texto = f'{pill}<span class="ruta">{esc(corto)}</span>'
    return f'<a href="{esc(url)}" title="{esc(ruta)}">{texto}</a>' if url else f'<span title="{esc(ruta)}">{texto}</span>'


def _cuadro_de_filtros(ident, filas, selector):
    partes = ['<div class="filtros">',
              f'<input id="{ident}-q" type="search" placeholder="Buscar…" oninput="filtra(\'{ident}\')">']
    if selector:
        opciones = sorted({f[1] for f in filas if f[1]})
        partes.append(f'<select id="{ident}-s" onchange="filtra(\'{ident}\')"><option value="">{esc(selector)}: todos</option>'
                      + "".join(f'<option value="{esc(o)}">{esc(o)}</option>' for o in opciones) + "</select>")
    partes.append(f'<span class="suave" id="{ident}-n">{len(filas)} de {len(filas)}</span></div>')
    return "".join(partes)


def _celda(k, c, numericas):
    valor, dato = (c if isinstance(c, tuple) else (c, None))
    clase = ' class="num"' if k in numericas else ""
    attr = f' data-v="{esc(dato)}"' if dato is not None else ""
    return f"<td{clase}{attr}>{valor}</td>"


def tabla(ident, cabecera, filas, *, filtros=True, selector=None, numericas=()):
    """Tabla con buscador y orden por columna. ``filas`` = [(celdas HTML o (html, valor), atributo data-f)]."""
    partes = [_cuadro_de_filtros(ident, filas, selector)] if filtros else []
    partes.append(f'<div class="tabla-caja"><table id="{ident}"><thead><tr>')
    for k, c in enumerate(cabecera):
        clase = ' class="num"' if k in numericas else ""
        partes.append(f'<th{clase} onclick="ordena(\'{ident}\',{k},{1 if k in numericas else 0})">{esc(c)}</th>')
    partes.append("</tr></thead><tbody>")
    for celdas, f in filas:
        partes.append(f'<tr data-f="{esc(f)}">' + "".join(_celda(k, c, numericas) for k, c in enumerate(celdas)) + "</tr>")
    partes.append("</tbody></table></div>")
    return "".join(partes)
