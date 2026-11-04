"""Compara el K4 llenado con el archivo base: si la estructura cambio o falta algo, el archivo no se entrega."""

import re
import xml.etree.ElementTree as ET
import zipfile

from ...comun.texto import norm
from .estilos import MORADO, NEGRO, verificar_estilos_agregados
from .hoja_xml import RE_ATRIBUTO, RE_COMBINADAS, RE_FILA, limpiar_texto
from .k4 import ROJOS
from .valores import es_validar
from .xlsx import Libro, columna_a_numero, partir_ref

ATRIBUTOS_DE_FILA_LIBRES = ("spans", "ht", "customHeight")
PARTES_QUE_PUEDEN_CAMBIAR = ("xl/styles.xml",)


def _esqueleto(texto):
    """El XML de la hoja sin datos, dimension, combinadas ni los rangos de las listas: lo demas no debe cambiar."""
    t = re.sub(r"<sheetData\b.*?</sheetData>|<sheetData\b[^>]*/>", "<sheetData/>", texto, flags=re.S)
    t = re.sub(r'<dimension ref="[^"]*"/>', "", t)
    t = RE_COMBINADAS.sub("", t)
    return re.sub(r'(<dataValidation\b[^>]*?\bsqref=")[^"]*(")', r"\1\2", t)


def _atributos_de_filas(texto):
    filas = {}
    for m in RE_FILA.finditer(texto):
        a = dict(RE_ATRIBUTO.findall(m.group(1)))
        filas[int(a["r"])] = {k: v for k, v in a.items() if k not in ATRIBUTOS_DE_FILA_LIBRES}
    return filas


def _combinadas(texto):
    return set(re.findall(r'<mergeCell\b[^>]*?\bref="([^"]+)"', texto))


def _celdas(rango):
    a, _, b = rango.partition(":")
    (c1, f1), (c2, f2) = partir_ref(a), partir_ref(b or a)
    return {(c, f) for c in range(columna_a_numero(c1), columna_a_numero(c2) + 1) for f in range(f1, f2 + 1)}


def _cubre(sqref_base, sqref_nuevo):
    """True si todas las celdas de las listas de la base siguen cubiertas."""
    nuevas = set().union(*(_celdas(f) for f in sqref_nuevo.split())) if sqref_nuevo.split() else set()
    base = set().union(*(_celdas(f) for f in sqref_base.split())) if sqref_base.split() else set()
    return base <= nuevas


def _listas(texto):
    return re.findall(r'<dataValidation\b[^>]*?\bsqref="([^"]*)"', texto)


def verificar_k4(base, salida, resultado):
    """Lista de errores (vacia si el archivo esta bien)."""
    errores = []
    with zipfile.ZipFile(base) as zb, zipfile.ZipFile(salida) as zs:
        if zb.namelist() != zs.namelist():
            return ["El archivo de salida tiene partes distintas a las del archivo base."]
        for parte in (n for n in zb.namelist() if n.startswith("xl/worksheets/sheet") or n == "xl/styles.xml"):
            try:
                ET.fromstring(zs.read(parte))
            except ET.ParseError as e:
                return [f"{parte}: el XML no es válido ({e}); Excel no abriría el archivo."]
        lb, ls = Libro(base), Libro(salida)
        if [(h.nombre, h.estado) for h in lb.hojas] != [(h.nombre, h.estado) for h in ls.hojas]:
            errores.append("Cambiaron los nombres, el orden o la visibilidad de las hojas.")
            return errores
        partes_hoja = {h.parte for h in lb.hojas}
        for n in zb.namelist():
            if zb.read(n) != zs.read(n) and n not in partes_hoja and n not in PARTES_QUE_PUEDEN_CAMBIAR:
                errores.append(f"Cambió la parte {n}, que no debía tocarse.")
        errores += verificar_estilos_agregados(zb.read("xl/styles.xml").decode("utf-8"), zs.read("xl/styles.xml").decode("utf-8"))
        for h in lb.hojas:
            tb, ts = zb.read(h.parte).decode("utf-8"), zs.read(h.parte).decode("utf-8")
            errores += _verificar_hoja(h, ls.hoja(h.nombre), tb, ts, resultado)
    errores += _verificar_celdas(lb, ls, resultado)
    errores += _verificar_semantica(ls, resultado)
    return errores


def _verificar_hoja(h, hs, tb, ts, resultado):
    errores = []
    if _esqueleto(tb) != _esqueleto(ts):
        errores.append(f"«{h.nombre}»: cambió algo además de las celdas (formatos, listas desplegables, vistas o columnas).")
    quitadas = set(resultado.combinadas_quitadas.get(h.nombre, []))
    nuevas = set(resultado.combinadas_nuevas.get(h.nombre, []))
    if (_combinadas(tb) - quitadas) | nuevas != _combinadas(ts):
        errores.append(f"«{h.nombre}»: cambiaron las celdas combinadas más allá de las del cuerpo de la tabla.")
    ocupadas = set()
    for m in _combinadas(ts):
        celdas = _celdas(m)
        if celdas & ocupadas:
            errores.append(f"«{h.nombre}»: hay celdas combinadas superpuestas ({m}); Excel lo marcaría como dañado.")
        ocupadas |= celdas
    for sqref_b, sqref_n in zip(_listas(tb), _listas(ts)):
        if not _cubre(sqref_b, sqref_n):
            errores.append(f"«{h.nombre}»: una lista desplegable dejó de cubrir sus celdas ({sqref_b}).")
    if len(_listas(tb)) != len(_listas(ts)):
        errores.append(f"«{h.nombre}»: cambió la cantidad de listas desplegables.")
    t = next((x for x in resultado.tablas.values() if x.hoja == h.nombre), None)
    ab, as_ = _atributos_de_filas(tb), _atributos_de_filas(ts)
    primera_libre = (t.inicio if t else 10 ** 9)
    for n in set(ab) | set(as_):
        if n < primera_libre and ab.get(n) != as_.get(n):
            errores.append(f"«{h.nombre}»: cambió la fila {n} (alto, visibilidad u otros atributos), que está sobre las respuestas.")
        elif n >= primera_libre and n in ab and ab[n] != as_.get(n):
            errores.append(f"«{h.nombre}»: cambió el atributo de la fila {n}.")
    return errores


def _verificar_celdas(lb, ls, resultado):
    errores = []
    for h in lb.hojas:
        hs = ls.hoja(h.nombre)
        for ref in sorted(set(h.celdas) | set(hs.celdas), key=lambda r: (partir_ref(r)[1], columna_a_numero(partir_ref(r)[0]))):
            co, cs = h.celdas.get(ref), hs.celdas.get(ref)
            clave = (h.nombre, ref)
            if clave in resultado.escritas:
                esperado = resultado.escritas[clave]
                if cs is None or not _iguales(esperado, cs.valor):
                    errores.append(f"{h.nombre}!{ref}: se esperaba «{str(esperado)[:40]}» y se leyó «{str(cs.valor if cs else None)[:40]}».")
                    continue
                color = resultado.colores[clave]
                if color == MORADO and cs.color_letra != MORADO:
                    errores.append(f"{h.nombre}!{ref}: el pendiente «VALIDAR» no quedó en morado.")
                if color == NEGRO and cs.color_letra in ROJOS:
                    errores.append(f"{h.nombre}!{ref}: el dato quedó en letra roja.")
                if cs.formula:
                    errores.append(f"{h.nombre}!{ref}: se escribió sobre una fórmula.")
            elif clave in resultado.borradas:
                if cs is not None and not cs.vacia:
                    errores.append(f"{h.nombre}!{ref}: el texto rojo no se borró.")
            else:
                if (co.valor if co else None) != (cs.valor if cs else None) or (co.formula if co else "") != (cs.formula if cs else ""):
                    errores.append(f"{h.nombre}!{ref}: cambió sin haberse pedido.")
                if co is not None and cs is not None and co.estilo != cs.estilo:
                    errores.append(f"{h.nombre}!{ref}: cambió el formato de la celda.")
            if cs is not None and not cs.vacia and cs.color_letra in ROJOS and clave not in resultado.escritas:
                errores.append(f"{h.nombre}!{ref}: queda texto en letra roja.")
    return errores


def _iguales(esperado, leido):
    if isinstance(esperado, (int, float)) and not isinstance(esperado, bool):
        return isinstance(leido, (int, float)) and abs(float(esperado) - float(leido)) <= 1e-9 * max(1.0, abs(float(esperado)))
    return isinstance(leido, str) and leido == limpiar_texto(esperado)


def _verificar_semantica(ls, resultado):
    """Lo que el formulario exige: encabezados completos, un solo registro horizontal, sin nombres de campo en las respuestas."""
    errores = []
    for clave, t in resultado.tablas.items():
        hoja = ls.hoja(t.hoja)
        for campo, col in t.columnas.items():
            leido = hoja.valor(f"{col}{t.fila_encabezado}")
            if not isinstance(leido, str) or norm(leido) != norm(t.encabezados[campo]):
                errores.append(f"«{t.hoja}»: falta o cambió el encabezado «{t.encabezados[campo][:40]}» ({col}{t.fila_encabezado}).")
        textos = {norm(v) for v in t.encabezados.values()}
        en_tabla = [(partir_ref(ref), valor) for (h, ref), valor in resultado.escritas.items()
                    if h == t.hoja and partir_ref(ref)[1] >= t.inicio and partir_ref(ref)[0] in t.columnas.values()]
        filas_escritas = {fila for (_, fila), _valor in en_tabla}
        for (col, fila), valor in en_tabla:
            if isinstance(valor, str) and norm(valor) in textos:
                errores.append(f"{t.hoja}!{col}{fila}: una respuesta repite el nombre de un campo («{valor[:30]}»).")
        if clave == "general":
            if filas_escritas - {t.inicio}:
                errores.append(f"«{t.hoja}» debe tener un solo registro, en la fila {t.inicio}; hay respuestas en {sorted(filas_escritas - {t.inicio})}.")
            vacios = [c for c in t.columnas.values() if hoja.valor(f"{c}{t.inicio}") in (None, "")]
            if vacios and resultado.filas.get("general"):
                errores.append(f"«{t.hoja}»: quedaron vacías las columnas {', '.join(vacios)} del registro.")
    for (h, ref), valor in resultado.escritas.items():
        if es_validar(valor) and resultado.colores[(h, ref)] != MORADO:
            errores.append(f"{h}!{ref}: un «VALIDAR» no está en morado.")
    return errores

