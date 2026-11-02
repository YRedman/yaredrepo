"""Relee el archivo escrito y lo compara con la plantilla: si algo no coincide, el archivo no se entrega."""

import re
import zipfile

from . import calculo
from .hoja_xml import RE_FILA, RE_ATRIBUTO, limpiar_texto
from .xlsx import Libro

HOJA_PUNTOS = "Puntos_a_validar"
RELLENO_ENTRADA = "theme0/-"            # gris claro de las celdas de entrada de la plantilla
TOLERANCIA = 1e-9


def _esqueleto(texto, quitar_validaciones_nuevas=False):
    """El XML de la hoja sin sus datos: lo demas (estructura, formatos, listas, tablas) no debe cambiar."""
    t = re.sub(r"<sheetData\b.*?</sheetData>|<sheetData\b[^>]*/>", "<sheetData/>", texto, flags=re.S)
    t = re.sub(r'<dimension ref="[^"]*"/>', "", t)
    if quitar_validaciones_nuevas:
        t = re.sub(r"<dataValidations count=.*?</dataValidations>", "", t, flags=re.S)
    return t


def _atributos_de_filas(texto):
    filas = {}
    for m in RE_FILA.finditer(texto):
        a = dict(RE_ATRIBUTO.findall(m.group(1)))
        a.pop("spans", None)
        filas[a["r"]] = a
    return filas


def _iguales(esperado, leido):
    if isinstance(esperado, (int, float)) and not isinstance(esperado, bool):
        return isinstance(leido, (int, float)) and abs(float(esperado) - float(leido)) <= TOLERANCIA * max(1.0, abs(float(esperado)))
    return isinstance(leido, str) and leido == limpiar_texto(esperado)


def verificar(origen, salida, esperadas, horas_esperadas=None, dias_mes=calculo.DIAS_POR_MES):
    """Lista de errores (vacia si el archivo esta bien). ``esperadas``: {(hoja, ref): valor escrito}."""
    errores = []
    with zipfile.ZipFile(origen) as zo, zipfile.ZipFile(salida) as zs:
        if zo.namelist() != zs.namelist():
            return ["El archivo de salida tiene partes distintas a la plantilla."]
        permitidas = {"xl/workbook.xml"}
        for n in zo.namelist():
            o, s = zo.read(n), zs.read(n)
            if o == s:
                continue
            if n.startswith("xl/worksheets/sheet") or n in permitidas or n.startswith("xl/tables/"):
                continue
            errores.append(f"Cambió la parte {n}, que no debía tocarse.")
        lo, ls = Libro(origen), Libro(salida)
        for h in lo.hojas:
            hs = ls.hoja(h.nombre)
            if hs is None:
                errores.append(f"Falta la hoja «{h.nombre}».")
                continue
            to, ts = zo.read(h.parte).decode("utf-8"), zs.read(h.parte).decode("utf-8")
            if _esqueleto(to) != _esqueleto(ts, quitar_validaciones_nuevas=h.nombre == HOJA_PUNTOS):
                errores.append(f"«{h.nombre}»: cambió algo además de las celdas (formatos, listas desplegables, combinadas o tablas).")
            if h.nombre != HOJA_PUNTOS:
                ao, as_ = _atributos_de_filas(to), _atributos_de_filas(ts)
                if ao != as_:
                    errores.append(f"«{h.nombre}»: cambiaron las filas (alto, visibilidad u otros atributos).")
            errores += _comparar_celdas(h, hs, esperadas)
        errores += _comparar_libro(zo, zs)
    if horas_esperadas is not None:
        leidas = _horas_leidas(ls, dias_mes)
        if abs(leidas - horas_esperadas) > 0.01:
            errores.append(f"Las horas por mes releídas ({leidas:.2f}) no coinciden con las calculadas ({horas_esperadas:.2f}).")
    return errores


def _comparar_celdas(h, hs, esperadas):
    errores = []
    for ref in sorted(set(h.celdas) | set(hs.celdas), key=lambda r: (len(r), r)):
        co, cs = h.celdas.get(ref), hs.celdas.get(ref)
        esperado = esperadas.get((h.nombre, ref))
        formula_o, formula_s = (co.formula if co else ""), (cs.formula if cs else "")
        if formula_o != formula_s:
            errores.append(f"{h.nombre}!{ref}: cambió una fórmula.")
            continue
        if formula_o:
            if (h.nombre, ref) in esperadas:
                errores.append(f"{h.nombre}!{ref}: se escribió sobre una fórmula.")
            continue
        if (h.nombre, ref) in esperadas:
            if cs is None or not _iguales(esperado, cs.valor):
                errores.append(f"{h.nombre}!{ref}: se esperaba «{str(esperado)[:40]}» y se leyó «{str(cs.valor if cs else None)[:40]}».")
            if h.nombre != HOJA_PUNTOS and co is not None and not (co.color_relleno or "").startswith(RELLENO_ENTRADA):
                errores.append(f"{h.nombre}!{ref}: no es una celda de entrada (gris).")
            if co is not None and cs is not None and co.estilo != cs.estilo:
                errores.append(f"{h.nombre}!{ref}: cambió el formato de la celda.")
        else:
            vo, vs = (co.valor if co else None), (cs.valor if cs else None)
            if vo != vs and not (_vacio(vo) and _vacio(vs)):
                errores.append(f"{h.nombre}!{ref}: cambió sin haberse pedido.")
    return errores


def _vacio(v):
    return v is None or (isinstance(v, str) and not v.strip())


def _comparar_libro(zo, zs):
    errores = []
    o, s = zo.read("xl/workbook.xml").decode("utf-8"), zs.read("xl/workbook.xml").decode("utf-8")
    if re.sub(r' fullCalcOnLoad="1"', "", s) != o:
        errores.append("El libro cambió en algo más que el recálculo al abrir.")
    return errores


def _horas_leidas(libro, dias_mes):
    """Suma de horas por mes recalculada con lo que quedo escrito en Actividades_Carga."""
    hoja = libro.hoja("Actividades_Carga")
    columnas = {}
    for col, c in hoja.fila(7).items():
        if isinstance(c.valor, str):
            columnas[re.sub(r"\*", "", c.valor).strip().lower()] = col
    total = 0.0
    for n in hoja.filas():
        if n < 8 or hoja.valor(f"{columnas['actividad']}{n}") in (None, ""):
            continue
        g = lambda k: hoja.valor(f"{columnas[k]}{n}")          # noqa: E731
        total += calculo.horas_mes(g("tiempo unitario min"), g("espera min"), g("eventos por frecuencia"), g("frecuencia"),
                                   g("retrabajo %"), g("% dedicación personal"), dias_mes)
    return total
