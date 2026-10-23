from ...comun.esquema import tipo_desde_texto
from ...comun.tipos import TIPOS_AREA, tipo as tipo_documento
from ...comun.texto import recortar_palabras as recortar
from ..salida import resumir_lista
from .base import Comando

SIN_UBICACION = "?:1-0"
TIPOS_CON_TABLA_PROPIA = ("DES", "PRD")


def _ubicacion(cp, codigo):
    d = cp.docs.get(codigo)
    return d.ubicacion if d else SIN_UBICACION


def _fila_descriptivo(cp, c):
    f = cp.meta.get(c, {})
    return [c, cp.nombre(c), f.get("reporta_a", ""), f.get("supervisa_a", ""), recortar(f.get("proposito_literal", ""), 25),
            f.get("campos_no_especificados", ""), _ubicacion(cp, c)]


def _fila_procedimiento(cp, c):
    f = cp.meta.get(c, {})
    return [c, cp.nombre(c), recortar(f.get("macroproceso", ""), 8), recortar(f.get("proposito_literal", ""), 25),
            recortar(f.get("subprocedimientos", ""), 20), f.get("codigos_citados", ""),
            f.get("campos_no_especificados", ""), _ubicacion(cp, c)]


def _fila_normativa(cp, c):
    f = cp.meta.get(c, {})
    return [c, cp.nombre(c), f.get("area_propietaria", ""), recortar(f.get("proposito_literal", ""), 25),
            f.get("codigos_citados", ""), f.get("campos_no_especificados", ""), _ubicacion(cp, c)]


CABECERA_DESCRIPTIVOS = ["Código", "Puesto", "Reporta a", "Supervisa a", "Propósito", "No especificado", "Archivo:líneas"]
CABECERA_PROCEDIMIENTOS = ["Código", "Procedimiento", "Macroproceso", "Objetivo", "Subprocesos", "Códigos citados",
                           "No especificado", "Archivo:líneas"]
CABECERA_NORMATIVA = ["Código", "Documento", "Área propietaria", "Objetivo", "Códigos citados", "No especificado",
                      "Archivo:líneas"]


def _resumen_del_area(cp, a, cod):
    tipos = [t for t in TIPOS_AREA if t in TIPOS_CON_TABLA_PROPIA or a.codigos(t)]
    linea = " · ".join(f"{tipo_documento(t).plural}: {len(a.codigos(t))}" for t in tipos)
    if cp.inventario:
        inv = cp.inventario_de_area(cod)
        por_tipo = [(t, sum(1 for f in inv if tipo_desde_texto(f.get("tipo")) == t)) for t in TIPOS_AREA]
        linea += " · En inventario: " + ", ".join(f"{n} {tipo_documento(t).plural.lower()}"
                                                 for t, n in por_tipo if n or t in TIPOS_CON_TABLA_PROPIA)
        faltan = cp.faltantes_de_inventario(inv)
        if faltan:
            linea += f" · NO CONVERTIDOS: {resumir_lista(faltan)}"
    excluidos = sorted(c for c in cp.excluidos if c.split("-")[1] == cod)
    if excluidos:
        linea += f" · EXCLUIDOS POR ESTADO: {resumir_lista(excluidos)}"
    return linea


class IndiceArea(Comando):
    nombre = "area"
    ayuda = "Indice completo de un area: todos sus codigos con sus datos clave."

    def configurar(self, parser):
        parser.add_argument("area")

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        cod = ctx.area(args.area)
        a = cp.areas[cod]
        s.linea(f"ÁREA · {a.nombre} ({cod})")
        s.linea(_resumen_del_area(cp, a, cod))
        s.linea()
        if a.descriptivos:
            s.linea("Descriptivos")
            s.tabla(CABECERA_DESCRIPTIVOS, [_fila_descriptivo(cp, c) for c in a.descriptivos])
            s.linea()
        if a.procedimientos:
            s.linea("Procedimientos")
            s.tabla(CABECERA_PROCEDIMIENTOS, [_fila_procedimiento(cp, c) for c in a.procedimientos])
        for t in TIPOS_AREA:
            if t in TIPOS_CON_TABLA_PROPIA or not a.codigos(t):
                continue
            s.linea()
            s.linea(tipo_documento(t).plural)
            s.tabla(CABECERA_NORMATIVA, [_fila_normativa(cp, c) for c in a.codigos(t)])
        sin_doc = [c for c in a.codigos() if c not in cp.docs]
        if sin_doc:
            s.linea()
            s.linea("AVISO: en el diccionario pero sin texto en los archivos .md: " + ", ".join(sin_doc))
