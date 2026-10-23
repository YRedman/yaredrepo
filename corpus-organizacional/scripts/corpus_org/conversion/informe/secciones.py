"""Las secciones del informe: cada funcion recibe los ``DatosInforme`` y devuelve su HTML."""

import collections

from ...comun.tipos import POR_CODIGO, TIPOS_AREA
from .datos import DatosInforme, tipo_de
from .elementos import alerta, barra, celda_ruta, codigo_html, esc, numero, tabla, tarjeta
from .log import log_a_html

CONFIANZA_OBJETIVO = 80.0
TIPOS_DE_DOCUMENTO = ("DES", "PRD", "PRO", "POL")
TIEMPOS_MOSTRADOS = 15
NAVEGACION = (("alertas", "Alertas"), ("cobertura", "Cobertura"), ("revision", "Revisión visual"),
              ("lectura", "Calidad de lectura"), ("tiempos", "Tiempos"), ("documentos", "Documentos"), ("log", "Log"))


def _nombre_de_tipo(tipo):
    return POR_CODIGO[tipo].nombre if tipo in POR_CODIGO else tipo


def navegacion(_d):
    return "<nav>" + "".join(f'<a href="#{ancla}">{texto}</a>' for ancla, texto in NAVEGACION) + "</nav>"


def tarjetas(d: DatosInforme):
    por_tipo, cobertura = d.por_tipo, d.cobertura_minima
    tarjetas_ = [tarjeta(len(d.indice), "documentos en el corpus"),
                 *[tarjeta(por_tipo[k], POR_CODIGO[k].plural) for k in TIPOS_DE_DOCUMENTO],
                 tarjeta(sum(v for k, v in por_tipo.items() if k not in TIPOS_AREA), "de contexto (ORG, MPR, CTX…)"),
                 tarjeta(len(d.areas), "áreas"),
                 tarjeta(f"{cobertura:.1f} %", "texto presente (mínimo)", "" if cobertura >= 100 else "aviso"),
                 tarjeta(len(d.con_ocr), "leídos con OCR"),
                 tarjeta(len(d.errores), "errores", "error" if d.errores else ""),
                 tarjeta(len(d.pendientes), "revisiones visuales pendientes", "aviso" if d.pendientes else ""),
                 tarjeta(f"{d.segundos_total / 60:.1f} min" if d.segundos_total else "—", "tiempo de conversión (suma)")]
    return '<div class="tarjetas">' + "".join(tarjetas_) + "</div>"


def alertas(d: DatosInforme):
    p = ['<h2 id="alertas">Alertas</h2>']
    if not d.errores and not d.avisos and not d.pendientes:
        p.append(alerta("ok", "Sin errores, avisos ni revisiones pendientes."))
    p += [alerta("error", f"<b>Error:</b> {esc(x)}") for x in d.errores]
    if d.pendientes:
        p.append(alerta("aviso", f'<b>Revisión visual pendiente:</b> {len(d.pendientes)} documentos (ver la sección '
                                 '<a href="#revision">Revisión visual</a>).'))
    p += [alerta("aviso", f"<b>Aviso:</b> {esc(x)}") for x in d.avisos]
    return "".join(p)


def _conteo_por_area_y_tipo(filas, activas_solo=False):
    conteo = collections.Counter()
    for f in filas:
        if activas_solo and (f.get("estado_inventario") or "ACTIVO").upper() != "ACTIVO":
            continue
        conteo[(f.get("codigo_departamento", ""), tipo_de(f))] += 1
    return conteo


def cobertura(d: DatosInforme):
    inventariados = _conteo_por_area_y_tipo(d.inventario, activas_solo=True)
    publicados = _conteo_por_area_y_tipo(d.indice)
    filas = []
    for cod, nombre in d.areas:
        celdas = [f"<b>{esc(nombre)}</b> <span class='suave'>{esc(cod)}</span>"]
        for tipo in TIPOS_DE_DOCUMENTO:
            pub, inv = publicados[(cod, tipo)], inventariados[(cod, tipo)]
            celdas.append((f"{pub}" + (f" / {inv}" if inv != pub else ""), pub))
        total = sum(publicados[(cod, t)] for t in TIPOS_AREA)
        esperados = sum(inventariados[(cod, t)] for t in TIPOS_AREA) or total
        celdas.append((barra(min(100.0, 100.0 * total / max(1, esperados))), total))
        filas.append((celdas, ""))
    return ('<h2 id="cobertura">Cobertura por área</h2>'
            + tabla("t-areas", ["Área", "DES", "PRD", "PRO", "POL", "Convertidos"], filas, numericas=(1, 2, 3, 4))
            + '<div class="suave">«n / m»: convertidos / en el inventario cuando difieren.</div>')


def revision_visual(d: DatosInforme):
    titulo = f'<h2 id="revision">Revisión visual pendiente ({len(d.pendientes)})</h2>'
    if not d.pendientes:
        return titulo + alerta("ok", "No hay documentos pendientes de revisión visual.")
    filas = []
    for f in d.pendientes:
        motivo = f.get("motivo", "")
        origen = "muestra aleatoria" if motivo.startswith("muestra") else "aviso de estructura / OCR"
        doc = d.por_codigo.get(f["codigo"], {})
        filas.append(([codigo_html(f["codigo"]), esc(doc.get("departamento", "")), esc(motivo),
                       celda_ruta(f.get("ruta_original", ""), d.datos)], origen))
    ayuda = ('<p class="suave">Compare cada documento con su original y anote su código en '
             '<span class="mono">revision_visual_ok.txt</span> (uno por línea); luego vuelva a ejecutar '
             '<span class="mono">construir</span>. Un clic en la ruta abre el original.</p>')
    return titulo + ayuda + tabla("t-rev", ["Código", "Área", "Motivo", "Original"], filas, selector="Motivo")


def calidad_de_lectura(d: DatosInforme):
    titulo = f'<h2 id="lectura">Calidad de lectura (OCR: {len(d.con_ocr)} documentos)</h2>'
    if not d.con_ocr:
        return titulo + alerta("ok", "Ningún documento necesitó OCR.")
    filas = []
    for f in sorted(d.con_ocr, key=lambda x: numero(x.get("confianza_ocr"), 100.0)):
        c = numero(f.get("confianza_ocr"), 0.0)
        filas.append(([codigo_html(f["codigo"]), esc(f["nombre"][:80]), esc(f.get("paginas_ocr", "")), (f"{c:.1f} %", c),
                       (barra(c, 100, CONFIANZA_OBJETIVO), c), celda_ruta(f.get("ruta_original", ""), d.datos)],
                      "bajo 80 %" if c < CONFIANZA_OBJETIVO else "80 % o más"))
    ayuda = ('<p class="suave">Confianza media de Tesseract por documento (objetivo ≥ 80 %). Los documentos con texto '
             'digital no pasan por OCR.</p>')
    return titulo + ayuda + tabla("t-ocr", ["Código", "Documento", "Páginas OCR", "Confianza", "", "Original"], filas,
                                  selector="Confianza", numericas=(3,))


def tiempos(d: DatosInforme):
    titulo = '<h2 id="tiempos">Tiempos</h2>'
    if not d.tiempos:
        return titulo + alerta("aviso", 'Esta construcción no guardó tiempos por documento '
                                        '(<span class="mono">control/tiempos_conversion.csv</span>).')
    lentos = sorted(d.tiempos.items(), key=lambda kv: -kv[1])[:TIEMPOS_MOSTRADOS]
    mayor = lentos[0][1] or 1
    filas = []
    for codigo, seg in lentos:
        f = d.por_codigo.get(codigo, {})
        filas.append(([codigo_html(codigo), esc(f.get("nombre", "")[:80]), (f"{seg:.0f} s", seg),
                       (barra(seg, mayor), seg), esc(f.get("paginas", ""))], ""))
    total = sum(d.tiempos.values())
    por_tipo = collections.defaultdict(float)
    for codigo, seg in d.tiempos.items():
        por_tipo[codigo.split("-")[0]] += seg
    resumen = (f'<p class="suave">Suma de los tiempos de conversión: {total:.0f} s en {len(d.tiempos)} documentos '
               f"({total / len(d.tiempos):.1f} s en promedio). Los documentos se convierten en paralelo, así que el "
               f"tiempo real es menor. Los {TIEMPOS_MOSTRADOS} más lentos:</p>")
    por_tipo_html = ("<p class='suave'>Por tipo: "
                     + " · ".join(f"{k} {v:.0f} s" for k, v in sorted(por_tipo.items(), key=lambda kv: -kv[1])) + "</p>")
    return (titulo + resumen
            + tabla("t-tiempos", ["Código", "Documento", "Segundos", "", "Páginas"], filas, filtros=False, numericas=(2, 4))
            + por_tipo_html)


def _fila_de_documento(f, d):
    tipo = tipo_de(f)
    confianza = (f.get("confianza_ocr") or "").strip()
    avisos = numero(f.get("avisos_estructura"), 0)
    segundos = d.tiempos.get(f["codigo"], 0)
    celdas = [codigo_html(f["codigo"]), esc(_nombre_de_tipo(tipo)), esc(f.get("departamento", "")), esc(f["nombre"][:90]),
              (esc(f.get("paginas", "")), numero(f.get("paginas"))), (esc(f.get("palabras", "")), numero(f.get("palabras"))),
              (esc(f.get("cobertura", "")), numero(f.get("cobertura"))),
              f"OCR {numero(confianza):.0f} %" if confianza else "Digital",
              (f'<span class="pill {"aviso" if avisos else "ok"}">{int(avisos)}</span>', avisos),
              (f"{segundos:.0f}", segundos), celda_ruta(f.get("ruta_original", ""), d.datos)]
    return celdas, _nombre_de_tipo(tipo)


def documentos(d: DatosInforme):
    filas = [_fila_de_documento(f, d) for f in d.indice]
    return (f'<h2 id="documentos">Documentos ({len(d.indice)})</h2>'
            + tabla("t-docs", ["Código", "Tipo", "Área", "Documento", "Págs.", "Palabras", "Texto presente", "Lectura", "Avisos",
                               "Seg.", "Original"], filas, selector="Tipo", numericas=(4, 5, 6, 8, 9)))


def log(d: DatosInforme):
    titulo = '<h2 id="log">Log de la consola</h2>'
    if not d.texto_log:
        return titulo + alerta("aviso", 'No hay log guardado (<span class="mono">control/log_construccion.txt</span>).')
    return (titulo + "<details><summary>Ver el log completo con color</summary>" + log_a_html(d.texto_log) + "</details>"
            + '<details><summary>Texto original del log</summary><pre class="log">' + esc(d.texto_log) + "</pre></details>")
