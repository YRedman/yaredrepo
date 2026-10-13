"""Reporte de conversion en Markdown (evidencia de QA en control/)."""

import datetime

from .. import VERSION
from ..comun.markdown import esc_celda
from .huella import huella


def _resumen(documentos):
    def contar(pred):
        return sum(1 for r in documentos if pred(r.estado))
    return (f"Documentos esperados: {len(documentos)} · convertidos: {contar(lambda e: e == 'OK')} · "
            f"no adjuntos: {contar(lambda e: e == 'NO ADJUNTO')} · errores: {contar(lambda e: e == 'ERROR')} · "
            f"pendientes por tiempo: {contar(lambda e: e.startswith('PENDIENTE'))}")


def _tabla(documentos):
    l = ["| Código | Archivo | Estado | Páginas | Palabras | Texto presente | Revisar |",
         "|---|---|---|---|---|---|---|"]
    revisar = 0
    for r in documentos:
        if not r.ok:
            l.append(f"| {r.codigo} | {esc_celda(r.archivo)} | {r.estado} |  |  |  | {esc_celda(r.error)} |")
            continue
        motivos = r.motivos_revision()
        revisar += bool(motivos)
        l.append(f"| {r.codigo} | {esc_celda(r.archivo)} | OK | {r.doc.paginas or ''} | {r.palabras} | "
                 f"{r.verificacion.cobertura:.1f} % | {esc_celda('; '.join(motivos)) or '—'} |")
    return l, revisar


def _detalle(r):
    l = ["", f"### {r.codigo} · {r.archivo}"]
    if not r.ok:
        l.append(f"- Estado: {r.estado}")
        if r.error:
            l += [f"- Error: {r.error}", "```", r.traza.strip(), "```"]
        return l
    d, v, a = r.doc, r.verificacion, r.analisis
    l.append(f"- Texto del original presente en el Markdown: {v.cobertura:.2f} % "
             f"({v.total - v.palabras_faltantes} de {v.total} palabras)")
    if v.faltan:
        muestra = ", ".join(f"{t} (×{n})" if n > 1 else t for t, n in v.faltan.most_common(25))
        l.append(f"- Palabras del original que no aparecen: {muestra}")
        ubic = "; ".join(f"página {p} · {z} ({n})" if p else f"{z} ({n})" for (p, z), n in v.origen.most_common(12))
        l.append(f"- Dónde están en el original: {ubic}")
        for (p, z), _n in v.origen.most_common(5):
            if (p, z) in v.ejemplos:
                l.append(f"  - Ejemplo (página {p}, {z}): \"{v.ejemplos[(p, z)]}\"")
    if v.agregadas:
        l.append(f"- Palabras que no están en el original: {', '.join(v.agregadas[:25])}")
    if v.numeros_faltan:
        l.append(f"- Números del original que no aparecen completos: {', '.join(list(v.numeros_faltan)[:15])}")
    if r.avisos:
        l.append(f"- AVISOS DE ESTRUCTURA (revisar visualmente): {len(r.avisos)}")
        l += [f"  - {x}" for x in r.avisos]
    if v.cruz:
        l.append(f"- Palabras que solo detectó el segundo motor (pdfplumber): {', '.join(v.cruz[:25])}")
    l.append(f"- Títulos de sección detectados: {' | '.join(a.titulos) or '(ninguno)'}")
    if a.subprocedimientos:
        l.append(f"- Subsecciones del desarrollo: {' | '.join(a.subprocedimientos)}")
    if a.secciones_excluidas:
        l.append(f"- Secciones no incluidas por configuración: {', '.join(a.secciones_excluidas)} "
                 f"({sum(a.excluidos.values())} palabras)")
    if a.secciones_diagrama:
        l.append(f"- Secciones de diagrama no transcritas: {', '.join(a.secciones_diagrama)}")
    l.append(f"- Tablas: {d.tablas} · diagramas o imágenes grandes: {len(d.diagramas)} · "
             f"imágenes pequeñas omitidas: {d.imagenes_omitidas}")
    if d.paginas_ocr:
        conf = f"; confianza media {d.confianza_ocr:.1f} %" if d.confianza_ocr is not None else ""
        l.append(f"- OCR aplicado en páginas: {', '.join(map(str, d.paginas_ocr))} (idioma: {d.idioma_ocr}{conf}); "
                 "ese texto no se puede verificar automáticamente.")
    if d.paginas_escaneadas_sin_ocr:
        l.append(f"- Páginas escaneadas sin texto y sin OCR: {', '.join(map(str, d.paginas_escaneadas_sin_ocr))}")
    if d.encabezado:
        l.append(f"- Encabezado y pie (se dejan una sola vez al final): {' · '.join(d.encabezado)[:300]}")
    campos = {k: x for k, x in a.campos.items() if k in ("nombre_puesto", "reporta_a", "supervisa_a", "area")}
    if campos:
        l.append("- Datos del puesto: " + " · ".join(f"{k}: {x}" for k, x in campos.items()))
    if a.faltantes:
        l.append(f"- Campos clave no especificados: {', '.join(a.faltantes)}")
    l += [f"- Nota: {n}" for n in d.notas + a.notas]
    return l


def escribir_reporte(path, grupo, documentos):
    l = [f"# Reporte de conversión · {grupo.titulo}", "",
         f"convertir.py v{VERSION} · huella {huella()} · {datetime.datetime.now():%Y-%m-%d %H:%M}", "",
         _resumen(documentos)]
    if not grupo.completo:
        l += ["", "**Archivo parcial:** faltan documentos de este grupo. Conviértalos en otra corrida."]
    tabla, revisar = _tabla(documentos)
    l += [""] + tabla + ["", f"Documentos con algo que revisar: {revisar}", "", "## Detalle por documento"]
    for r in documentos:
        l += _detalle(r)
    path.write_text("\n".join(l) + "\n", encoding="utf-8")
    return path
