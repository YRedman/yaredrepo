"""Informe HTML de la construccion: el mismo log de la consola, pero para revisarlo con la vista.

Un solo archivo (``salida_corpus/INFORME_CONSTRUCCION.html``) sin dependencias ni red: estilos y filtros en linea,
claro y oscuro segun el sistema, que se abre con doble clic. Resume el resultado, las alertas, la cobertura por area, la
revision visual pendiente (con enlace a cada original), la calidad de lectura (OCR), los tiempos y todos los
documentos con busqueda y orden. Lee lo que ya escribio ``construir`` (indice, ``control/``) y el log de la consola
guardado en ``control/log_construccion.txt``.
"""

import collections
import datetime
import html
import json
import re
from pathlib import Path
from urllib.parse import quote

from ..comun.archivos import leer_csv
from ..comun.esquema import ARCHIVO_REVISION, ARCHIVO_RESUMEN
from ..comun.estructura import CARPETA_PUBLICADA, rutas_publicadas
from ..comun.tipos import POR_CODIGO, TIPOS_AREA

ARCHIVO_INFORME = "INFORME_CONSTRUCCION.html"
ARCHIVO_LOG = "log_construccion.txt"
ARCHIVO_DATOS = "construccion.json"
ARCHIVO_TIEMPOS = "tiempos_conversion.csv"
CONFIANZA_OBJETIVO = 80.0

ESTADOS = {
    "LISTO PARA PUBLICAR": ("ok", "Listo para publicar"),
    "PENDIENTE DE REVISIÓN VISUAL": ("aviso", "Pendiente de revisión visual"),
    "REQUIERE REVISIÓN": ("error", "Requiere revisión"),
}

CSS = """
:root{--fondo:#f6f7f9;--tarjeta:#fff;--texto:#1c2430;--suave:#5b6675;--borde:#dfe3e8;--ok:#1a7f4b;--okbg:#e4f5ec;
--aviso:#9a6700;--avisobg:#fff4d6;--error:#b3261e;--errorbg:#fde8e6;--acento:#1f4e78;--barra:#cfe0f1;--barraok:#8fd0ad}
@media (prefers-color-scheme:dark){:root{--fondo:#12161c;--tarjeta:#1b212a;--texto:#e6eaf0;--suave:#9aa6b6;--borde:#2c3541;
--ok:#59d08c;--okbg:#17332a;--aviso:#e8b94a;--avisobg:#3a2f12;--error:#ff8a80;--errorbg:#3b1d1b;--acento:#7fb6ea;--barra:#27415c;--barraok:#2f6b4f}}
*{box-sizing:border-box}body{margin:0;background:var(--fondo);color:var(--texto);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:28px 20px 8px;max-width:1280px;margin:0 auto}h1{margin:0 0 4px;font-size:26px}h2{font-size:19px;margin:34px 0 12px}
h3{font-size:16px;margin:18px 0 8px}main{max-width:1280px;margin:0 auto;padding:0 20px 60px}.suave{color:var(--suave)}
.estado{display:inline-block;padding:4px 12px;border-radius:999px;font-weight:700;font-size:14px}
.ok{background:var(--okbg);color:var(--ok)}.aviso{background:var(--avisobg);color:var(--aviso)}.error{background:var(--errorbg);color:var(--error)}
.tarjetas{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:18px 0}
.tarjeta{background:var(--tarjeta);border:1px solid var(--borde);border-radius:12px;padding:14px 16px}
.tarjeta b{display:block;font-size:26px;line-height:1.1}.tarjeta span{color:var(--suave);font-size:13px}
.tarjeta.error{border-color:var(--error)}.tarjeta.aviso{border-color:var(--aviso)}
.caja{background:var(--tarjeta);border:1px solid var(--borde);border-radius:12px;padding:14px 18px;margin:12px 0}
.alerta{border-left:5px solid;padding:8px 14px;margin:8px 0;border-radius:6px;word-break:break-word}
.alerta.error{border-color:var(--error);background:var(--errorbg);color:var(--texto)}.alerta.aviso{border-color:var(--aviso);background:var(--avisobg);color:var(--texto)}
.alerta.ok{border-color:var(--ok);background:var(--okbg);color:var(--texto)}
.tabla-caja{overflow-x:auto;background:var(--tarjeta);border:1px solid var(--borde);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--borde);vertical-align:top}
th{position:sticky;top:0;background:var(--tarjeta);font-weight:600;cursor:pointer;white-space:nowrap}th:hover{color:var(--acento)}
tr:last-child td{border-bottom:0}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:1px 9px;border-radius:999px;font-size:12px;font-weight:600}
.barra{background:var(--barra);border-radius:6px;height:10px;min-width:80px;overflow:hidden}.barra i{display:block;height:100%;background:var(--barraok)}
.barra.baja i{background:var(--aviso)}.barra.mala i{background:var(--error)}
.filtros{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0}.filtros input,.filtros select{padding:7px 10px;border:1px solid var(--borde);
border-radius:8px;background:var(--tarjeta);color:var(--texto);font-size:14px;min-width:200px}
a{color:var(--acento)}details{margin:10px 0}summary{cursor:pointer;font-weight:600}
pre.log{background:var(--tarjeta);border:1px solid var(--borde);border-radius:10px;padding:12px;overflow:auto;max-height:520px;font-size:12.5px;line-height:1.45}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12.5px}.ruta{color:var(--suave);font-size:12.5px}
nav{position:sticky;top:0;background:var(--fondo);padding:8px 0;z-index:5;display:flex;gap:14px;flex-wrap:wrap;border-bottom:1px solid var(--borde);font-size:14px}
@media print{nav,.filtros{display:none}body{background:#fff}}
"""

JS = """
function normaliza(t){return (t||'').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'')}
function filtra(id){var t=document.getElementById(id),q=normaliza(document.getElementById(id+'-q').value),
 s=document.getElementById(id+'-s'),v=s?s.value:'',n=0;
 for(var i=1;i<t.rows.length;i++){var r=t.rows[i],ok=normaliza(r.innerText).indexOf(q)>=0&&(!v||r.getAttribute('data-f')===v);
  r.style.display=ok?'':'none';if(ok)n++}
 var c=document.getElementById(id+'-n');if(c)c.textContent=n+' de '+(t.rows.length-1)}
function ordena(id,col,num){var t=document.getElementById(id),f=Array.prototype.slice.call(t.rows,1),
 asc=t.getAttribute('data-o')!==String(col);t.setAttribute('data-o',asc?col:'');
 f.sort(function(a,b){var x=a.cells[col].getAttribute('data-v')||a.cells[col].innerText,y=b.cells[col].getAttribute('data-v')||b.cells[col].innerText;
  if(num){x=parseFloat(x)||0;y=parseFloat(y)||0;return asc?x-y:y-x}return asc?x.localeCompare(y,'es'):y.localeCompare(x,'es')});
 f.forEach(function(r){t.tBodies[0].appendChild(r)})}
"""


def _e(x):
    return html.escape(str(x if x is not None else ""))


def _num(x, defecto=0.0):
    try:
        return float(str(x).replace("%", "").replace(",", ".").strip())
    except ValueError:
        return defecto


def _enlace(ruta_relativa, datos):
    """URL file:// del original: ``entrada/<ruta>`` o ``contexto/<ruta>`` bajo las carpetas guardadas en construccion.json."""
    if not ruta_relativa:
        return ""
    primero, _, resto = ruta_relativa.partition("/")
    base = datos.get(primero) if primero in ("entrada", "contexto") else None
    if not base or not resto:
        return ""
    ruta = Path(base) / resto
    return "file:///" + quote(str(ruta).replace("\\", "/").lstrip("/"), safe="/:")


def _celda_ruta(ruta, datos):
    """Origen (entrada o contexto) y las dos ultimas partes de la ruta; la ruta completa en el texto emergente y el enlace."""
    if not ruta:
        return ""
    origen, _, resto = ruta.partition("/")
    partes = [x for x in resto.split("/") if x]
    nombre = partes[-1] if partes else ruta
    carpeta = partes[-2] if len(partes) > 1 else ""
    corto = (carpeta[:28] + ("…" if len(carpeta) > 28 else "") + "/" if carpeta else "") + nombre[:60] + ("…" if len(nombre) > 60 else "")
    pill = f'<span class="pill {"aviso" if origen == "contexto" else "ok"}">{_e(origen)}</span> ' if origen in ("entrada", "contexto") else ""
    url = _enlace(ruta, datos)
    texto = f'{pill}<span class="ruta">{_e(corto)}</span>'
    return f'<a href="{_e(url)}" title="{_e(ruta)}">{texto}</a>' if url else f'<span title="{_e(ruta)}">{texto}</span>'


def _barra(valor, maximo=100.0, objetivo=None):
    pct = max(0.0, min(100.0, 100.0 * valor / maximo)) if maximo else 0.0
    clase = ""
    if objetivo is not None:
        clase = " mala" if valor < objetivo - 20 else (" baja" if valor < objetivo else "")
    return f'<div class="barra{clase}" title="{valor:.0f}"><i style="width:{pct:.0f}%"></i></div>'


def _tabla(ident, cabecera, filas, filtros=True, selector=None, numericas=(), maximo_visible=None):
    """Tabla con buscador y orden por columna. ``filas`` = [(celdas HTML o (html, valor), atributo data-f)]."""
    partes = []
    if filtros:
        partes.append('<div class="filtros">')
        partes.append(f'<input id="{ident}-q" type="search" placeholder="Buscar…" oninput="filtra(\'{ident}\')">')
        if selector:
            opciones = sorted({f[1] for f in filas if f[1]})
            partes.append(f'<select id="{ident}-s" onchange="filtra(\'{ident}\')"><option value="">{_e(selector)}: todos</option>'
                          + "".join(f'<option value="{_e(o)}">{_e(o)}</option>' for o in opciones) + "</select>")
        partes.append(f'<span class="suave" id="{ident}-n">{len(filas)} de {len(filas)}</span></div>')
    partes.append(f'<div class="tabla-caja"><table id="{ident}"><thead><tr>')
    for k, c in enumerate(cabecera):
        clase = ' class="num"' if k in numericas else ""
        partes.append(f'<th{clase} onclick="ordena(\'{ident}\',{k},{1 if k in numericas else 0})">{_e(c)}</th>')
    partes.append("</tr></thead><tbody>")
    for celdas, f in filas:
        partes.append(f'<tr data-f="{_e(f)}">')
        for k, c in enumerate(celdas):
            valor, dato = (c if isinstance(c, tuple) else (c, None))
            clase = ' class="num"' if k in numericas else ""
            attr = f' data-v="{_e(dato)}"' if dato is not None else ""
            partes.append(f"<td{clase}{attr}>{valor}</td>")
        partes.append("</tr>")
    partes.append("</tbody></table></div>")
    return "".join(partes)


def _leer(ruta):
    try:
        return leer_csv(ruta) if Path(ruta).is_file() else []
    except (OSError, ValueError):
        return []


def _estado_de(texto):
    m = re.search(r"Resultado:\s*\**\s*([A-ZÁÉÍÓÚÑ ]+?)\s*\**\s*$", texto or "", re.M)
    return m.group(1).strip() if m else ""


def _lineas_de(texto, prefijo):
    return [l[len(prefijo):].strip() for l in (texto or "").splitlines() if l.startswith(prefijo)]


def _log_a_html(texto):
    """El log de la consola con color: ERROR en rojo, AVISO / REVISIÓN en ambar y las tablas markdown como tablas."""
    salida, tabla = [], []

    def cerrar():
        if not tabla:
            return
        filas = [[c.strip() for c in l.strip().strip("|").split("|")] for l in tabla if not re.match(r"^\|[\s\-|:]+\|$", l.strip())]
        if filas:
            salida.append('<div class="tabla-caja"><table><thead><tr>' + "".join(f"<th>{_e(c)}</th>" for c in filas[0])
                          + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in f) + "</tr>"
                                                              for f in filas[1:]) + "</tbody></table></div>")
        tabla.clear()

    for linea in (texto or "").splitlines():
        if linea.startswith("|"):
            tabla.append(linea)
            continue
        cerrar()
        if not linea.strip():
            continue
        clase = ""
        if linea.startswith(("ERROR", "- PROBLEMA", "PROBLEMA")):
            clase = "error"
        elif linea.startswith(("AVISO", "REVISIÓN VISUAL", "Revisar en", "AVISOS")):
            clase = "aviso"
        if re.match(r"^[A-ZÁÉÍÓÚÑ ]{5,} ·", linea) or linea.startswith("CONSTRUIR CORPUS"):
            salida.append(f"<h3>{_e(linea)}</h3>")
        elif clase:
            salida.append(f'<div class="alerta {clase}">{_e(linea)}</div>')
        else:
            salida.append(f'<div class="mono">{_e(linea)}</div>')
    cerrar()
    return "".join(salida)


def generar_informe(raiz_salida, texto_log=None, destino=None):
    """Escribe el informe HTML de la ultima construccion y devuelve su ruta."""
    raiz = Path(raiz_salida)
    control = raiz / "control"
    rutas = rutas_publicadas(raiz / CARPETA_PUBLICADA)
    datos = {}
    if (control / ARCHIVO_DATOS).is_file():
        try:
            datos = json.loads((control / ARCHIVO_DATOS).read_text(encoding="utf-8"))
        except ValueError:
            datos = {}
    if texto_log is None and (control / ARCHIVO_LOG).is_file():
        texto_log = (control / ARCHIVO_LOG).read_text(encoding="utf-8", errors="replace")
    resumen = (raiz / ARCHIVO_RESUMEN).read_text(encoding="utf-8", errors="replace") if (raiz / ARCHIVO_RESUMEN).is_file() else ""
    indice = _leer(rutas.indice / "indice_corpus.csv")
    inventario = _leer(control / "inventario_maestro.csv")
    revision = _leer(control / ARCHIVO_REVISION)
    tiempos = {f["codigo"]: _num(f.get("segundos")) for f in _leer(control / ARCHIVO_TIEMPOS)}
    estado_txt = _estado_de(texto_log) or _estado_de(resumen) or "DESCONOCIDO"
    clase_estado, etiqueta_estado = ESTADOS.get(estado_txt, ("aviso", estado_txt.capitalize()))

    errores = [x for x in _lineas_de(texto_log, "ERROR: ")] or _lineas_de(resumen, "- ERROR: ")
    avisos = _lineas_de(texto_log, "AVISO: ")
    if not avisos:
        avisos = [l.strip("- ").strip() for l in resumen.splitlines() if l.startswith("- ") and "aviso" in l.lower()]
    por_tipo = collections.Counter(f["codigo"].split("-")[0] for f in indice)
    areas = sorted({(f["codigo_departamento"], f["departamento"]) for f in indice if f["codigo"].split("-")[0] in TIPOS_AREA})
    ocr = [f for f in indice if (f.get("paginas_ocr") or "").strip()]
    pendientes = [f for f in revision if not (f.get("revisado") or "").strip()]
    cob_min = min((_num(f.get("cobertura"), 100.0) for f in indice), default=100.0)
    segundos_total = datos.get("segundos_total") or sum(tiempos.values())

    p = []
    p.append(f'<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
             f"<title>Informe de construcción del corpus</title><style>{CSS}</style></head><body>")
    p.append("<header><h1>Informe de construcción del corpus</h1>")
    fecha = datos.get("fecha") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    p.append(f'<div class="suave">convertir.py v{_e(datos.get("version", ""))} · {_e(fecha)} · '
             f'<span class="estado {clase_estado}">{_e(etiqueta_estado)}</span></div></header><main>')
    p.append('<nav><a href="#alertas">Alertas</a><a href="#cobertura">Cobertura</a><a href="#revision">Revisión visual</a>'
             '<a href="#lectura">Calidad de lectura</a><a href="#tiempos">Tiempos</a><a href="#documentos">Documentos</a>'
             '<a href="#log">Log</a></nav>')

    # tarjetas
    def tarjeta(valor, texto, clase=""):
        return f'<div class="tarjeta {clase}"><b>{_e(valor)}</b><span>{_e(texto)}</span></div>'
    t = [tarjeta(len(indice), "documentos en el corpus"),
         *[tarjeta(por_tipo[k], POR_CODIGO[k].plural) for k in ("DES", "PRD", "PRO", "POL")],
         tarjeta(sum(v for k, v in por_tipo.items() if k not in TIPOS_AREA), "de contexto (ORG, MPR, CTX…)"),
         tarjeta(len(areas), "áreas"),
         tarjeta(f"{cob_min:.1f} %", "texto presente (mínimo)", "" if cob_min >= 100 else "aviso"),
         tarjeta(len(ocr), "leídos con OCR"),
         tarjeta(len(errores), "errores", "error" if errores else ""),
         tarjeta(len(pendientes), "revisiones visuales pendientes", "aviso" if pendientes else ""),
         tarjeta(f"{segundos_total / 60:.1f} min" if segundos_total else "—", "tiempo de conversión (suma)")]
    p.append('<div class="tarjetas">' + "".join(t) + "</div>")

    # alertas
    p.append('<h2 id="alertas">Alertas</h2>')
    if not errores and not avisos and not pendientes:
        p.append('<div class="alerta ok">Sin errores, avisos ni revisiones pendientes.</div>')
    for x in errores:
        p.append(f'<div class="alerta error"><b>Error:</b> {_e(x)}</div>')
    if pendientes:
        p.append(f'<div class="alerta aviso"><b>Revisión visual pendiente:</b> {len(pendientes)} documentos (ver la sección '
                 '<a href="#revision">Revisión visual</a>).</div>')
    for x in avisos:
        p.append(f'<div class="alerta aviso"><b>Aviso:</b> {_e(x)}</div>')

    # cobertura por area
    p.append('<h2 id="cobertura">Cobertura por área</h2>')
    inv_por = collections.Counter()
    for f in inventario:
        if (f.get("estado_inventario") or "ACTIVO").upper() == "ACTIVO":
            inv_por[(f.get("codigo_departamento", ""), f["codigo"].split("-")[0])] += 1
    pub_por = collections.Counter((f["codigo_departamento"], f["codigo"].split("-")[0]) for f in indice)
    filas = []
    for cod, nombre in areas:
        celdas = [f"<b>{_e(nombre)}</b> <span class='suave'>{_e(cod)}</span>"]
        for tipo in ("DES", "PRD", "PRO", "POL"):
            pub, inv = pub_por[(cod, tipo)], inv_por[(cod, tipo)]
            celdas.append((f"{pub}" + (f" / {inv}" if inv != pub else ""), pub))
        total = sum(pub_por[(cod, t_)] for t_ in TIPOS_AREA)
        celdas.append((_barra(min(100.0, 100.0 * total / max(1, sum(inv_por[(cod, t_)] for t_ in TIPOS_AREA) or total))), total))
        filas.append((celdas, ""))
    p.append(_tabla("t-areas", ["Área", "DES", "PRD", "PRO", "POL", "Convertidos"], filas, numericas=(1, 2, 3, 4)))
    p.append('<div class="suave">«n / m»: convertidos / en el inventario cuando difieren.</div>')

    # revision visual
    p.append(f'<h2 id="revision">Revisión visual pendiente ({len(pendientes)})</h2>')
    if pendientes:
        p.append('<p class="suave">Compare cada documento con su original y anote su código en <span class="mono">revision_visual_ok.txt</span> '
                 "(uno por línea); luego vuelva a ejecutar <span class=\"mono\">construir</span>. Un clic en la ruta abre el original.</p>")
        info = {f["codigo"]: f for f in indice}
        filas = []
        for f in pendientes:
            motivo = f.get("motivo", "")
            tipo = "muestra aleatoria" if motivo.startswith("muestra") else "aviso de estructura / OCR"
            d = info.get(f["codigo"], {})
            filas.append(([f'<b class="mono">{_e(f["codigo"])}</b>', _e(d.get("departamento", "")), _e(motivo),
                           _celda_ruta(f.get("ruta_original", ""), datos)], tipo))
        p.append(_tabla("t-rev", ["Código", "Área", "Motivo", "Original"], filas, selector="Motivo"))
    else:
        p.append('<div class="alerta ok">No hay documentos pendientes de revisión visual.</div>')

    # calidad de lectura
    p.append(f'<h2 id="lectura">Calidad de lectura (OCR: {len(ocr)} documentos)</h2>')
    if ocr:
        filas = []
        for f in sorted(ocr, key=lambda x: _num(x.get("confianza_ocr"), 100.0)):
            c = _num(f.get("confianza_ocr"), 0.0)
            filas.append(([f'<b class="mono">{_e(f["codigo"])}</b>', _e(f["nombre"][:80]), _e(f.get("paginas_ocr", "")),
                           (f"{c:.1f} %", c), (_barra(c, 100, CONFIANZA_OBJETIVO), c), _celda_ruta(f.get("ruta_original", ""), datos)],
                          "bajo 80 %" if c < CONFIANZA_OBJETIVO else "80 % o más"))
        p.append('<p class="suave">Confianza media de Tesseract por documento (objetivo ≥ 80 %). Los documentos con texto digital no pasan por OCR.</p>')
        p.append(_tabla("t-ocr", ["Código", "Documento", "Páginas OCR", "Confianza", "", "Original"], filas, selector="Confianza",
                        numericas=(3,)))
    else:
        p.append('<div class="alerta ok">Ningún documento necesitó OCR.</div>')

    # tiempos
    p.append('<h2 id="tiempos">Tiempos</h2>')
    if tiempos:
        por_codigo = {f["codigo"]: f for f in indice}
        lentos = sorted(tiempos.items(), key=lambda kv: -kv[1])[:15]
        mayor = lentos[0][1] or 1
        filas = []
        for codigo, seg in lentos:
            f = por_codigo.get(codigo, {})
            filas.append(([f'<b class="mono">{_e(codigo)}</b>', _e(f.get("nombre", "")[:80]), (f"{seg:.0f} s", seg),
                           (_barra(seg, mayor), seg), _e(f.get("paginas", ""))], ""))
        p.append(f'<p class="suave">Suma de los tiempos de conversión: {sum(tiempos.values()):.0f} s en {len(tiempos)} documentos '
                 f"({sum(tiempos.values()) / len(tiempos):.1f} s en promedio). Los documentos se convierten en paralelo, así que el "
                 "tiempo real es menor. Los 15 más lentos:</p>")
        p.append(_tabla("t-tiempos", ["Código", "Documento", "Segundos", "", "Páginas"], filas, filtros=False, numericas=(2, 4)))
        por_t = collections.defaultdict(float)
        for codigo, seg in tiempos.items():
            por_t[codigo.split("-")[0]] += seg
        p.append("<p class='suave'>Por tipo: " + " · ".join(f"{k} {v:.0f} s" for k, v in sorted(por_t.items(), key=lambda kv: -kv[1])) + "</p>")
    else:
        p.append('<div class="alerta aviso">Esta construcción no guardó tiempos por documento (<span class="mono">control/tiempos_conversion.csv</span>).</div>')

    # documentos
    p.append(f'<h2 id="documentos">Documentos ({len(indice)})</h2>')
    filas = []
    for f in indice:
        tipo = f["codigo"].split("-")[0]
        c = (f.get("confianza_ocr") or "").strip()
        lectura = f"OCR {_num(c):.0f} %" if c else "Digital"
        avisos_n = _num(f.get("avisos_estructura"), 0)
        celdas = [f'<b class="mono">{_e(f["codigo"])}</b>', _e(POR_CODIGO[tipo].nombre if tipo in POR_CODIGO else tipo),
                  _e(f.get("departamento", "")), _e(f["nombre"][:90]), (_e(f.get("paginas", "")), _num(f.get("paginas"))),
                  (_e(f.get("palabras", "")), _num(f.get("palabras"))), (_e(f.get("cobertura", "")), _num(f.get("cobertura"))),
                  lectura, (f'<span class="pill {"aviso" if avisos_n else "ok"}">{int(avisos_n)}</span>', avisos_n),
                  (f"{tiempos.get(f['codigo'], 0):.0f}", tiempos.get(f["codigo"], 0)), _celda_ruta(f.get("ruta_original", ""), datos)]
        filas.append((celdas, POR_CODIGO[tipo].nombre if tipo in POR_CODIGO else tipo))
    p.append(_tabla("t-docs", ["Código", "Tipo", "Área", "Documento", "Págs.", "Palabras", "Texto presente", "Lectura", "Avisos", "Seg.",
                               "Original"], filas, selector="Tipo", numericas=(4, 5, 6, 8, 9)))

    # log
    p.append('<h2 id="log">Log de la consola</h2>')
    if texto_log:
        p.append("<details><summary>Ver el log completo con color</summary>" + _log_a_html(texto_log) + "</details>")
        p.append("<details><summary>Texto original del log</summary><pre class=\"log\">" + _e(texto_log) + "</pre></details>")
    else:
        p.append('<div class="alerta aviso">No hay log guardado (<span class="mono">control/log_construccion.txt</span>).</div>')
    p.append(f"</main><script>{JS}</script></body></html>")

    destino = Path(destino) if destino else raiz / ARCHIVO_INFORME
    destino.write_text("".join(p), encoding="utf-8")
    return destino
