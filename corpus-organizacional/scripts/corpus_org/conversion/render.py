"""Markdown publicado de un documento convertido."""

import re

from ..comun.esquema import NO_ESPECIFICADO, TITULO_ENCABEZADO_PIE
from ..comun.tipos import familia, tipo as tipo_documento
from ..comun.markdown import esc_linea, lineas_tabla

_ETIQUETAS_META = (("version", "Versión"), ("estado_documental", "Estado documental"),
                   ("fecha_vigencia", "Fecha de vigencia"), ("propietario", "Propietario"),
                   ("responsable", "Responsable"))


def _metadatos_conversion(doc, analisis, codigo, tipo, departamento, archivo, titulo):
    meta = analisis.metadatos
    td = tipo_documento(tipo)
    lineas = [f"## [{codigo}] {titulo}",
              "> **Metadatos de conversión (no forman parte del documento original)**",
              f"> - Código: {codigo}",
              f"> - Tipo: {td.nombre if td else tipo}"]
    if departamento:
        lineas.append(f"> - Departamento: {departamento}")
    lineas.append(f"> - Archivo origen: {archivo}")
    if meta.area_propietaria:
        lineas.append(f"> - Área propietaria: {meta.area_propietaria}")
    if meta.codigo_interno:
        lineas.append(f"> - Código interno: {meta.codigo_interno}")
    for atributo, etiqueta in _ETIQUETAS_META:
        valor = getattr(meta, atributo)
        if valor:
            lineas.append(f"> - {etiqueta}: {valor}")
    if doc.paginas:
        lineas.append(f"> - {doc.unidad.capitalize()}: {doc.paginas}")
    if familia(tipo) in ("P", "D"):
        if analisis.faltantes:
            lineas += [f"> - {f}: {NO_ESPECIFICADO}" for f in analisis.faltantes]
        else:
            lineas.append("> - Campos clave: completos")
    if analisis.secciones_excluidas:
        lineas.append("> - Secciones no incluidas: " + ", ".join(analisis.secciones_excluidas))
    if doc.paginas_ocr:
        conf = f" (confianza media {doc.confianza_ocr:.0f} %)" if doc.confianza_ocr is not None else ""
        lineas.append(f"> - {doc.unidad.capitalize()} leídas con OCR: " + ", ".join(map(str, doc.paginas_ocr)) + conf)
    lineas.append("")
    return lineas


def _cuerpo(bloques, codigo):
    cuerpo = []
    for b in bloques:
        if b["k"] == "h":
            nivel = max(1, min(b["nivel"], 3))
            t = esc_linea(b["texto"]).lstrip("\\")
            cuerpo += ["", f"### [{codigo}] {t}" if nivel == 1 else "#" * (nivel + 2) + " " + t, ""]
        elif b["k"] == "p":
            cuerpo += ["", esc_linea(b["texto"]), ""]
        elif b["k"] == "li":
            sang = "  " * b.get("nivel", 0)
            marc = b.get("marcador") or "-"
            if marc != "-" and not re.match(r"^\d+\.$", marc):
                cuerpo.append(f"{sang}- {marc} {b['texto']}")
            else:
                cuerpo.append(f"{sang}{marc} {b['texto']}")
        elif b["k"] == "tabla":
            cuerpo += [""] + lineas_tabla(b["filas"]) + [""]
        elif b["k"] == "marca":
            cuerpo += ["", b["texto"], ""]
    return cuerpo


def render_documento(doc, bloques, analisis, codigo, tipo, departamento, archivo, titulo):
    """Devuelve (lineas del documento publicado, texto del cuerpo para verificar)."""
    meta = _metadatos_conversion(doc, analisis, codigo, tipo, departamento, archivo, titulo)
    cuerpo = _cuerpo(bloques, codigo)
    enc = []
    if doc.encabezado:
        enc = ["", f"### [{codigo}] {TITULO_ENCABEZADO_PIE}", ""] + [esc_linea(l) + "  " for l in doc.encabezado]
    return normalizar_blancos(meta + cuerpo + enc + ["", "---", ""]), "\n".join(cuerpo)


def normalizar_blancos(lineas):
    """Una linea en blanco entre bloques, ninguna dentro de una lista o tabla, y nunca dos seguidas."""
    salida = []

    def es_item(l):
        return bool(re.match(r"^\s*(?:-\s|\d+\.\s)", l))

    def es_tabla(l):
        return l.startswith("|")

    for l in lineas:
        if salida and l != "" and salida[-1] != "":
            prev = salida[-1]
            if (es_item(prev) and not es_item(l)) or (es_tabla(prev) != es_tabla(l)) or l.startswith("#") \
                    or l == "---":
                if not prev.startswith(">") or not l.startswith(">"):
                    salida.append("")
        if l == "" and (not salida or salida[-1] == ""):
            continue
        salida.append(l)
    while salida and salida[-1] == "":
        salida.pop()
    return salida + [""]
