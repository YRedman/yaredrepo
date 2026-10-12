from ...comun.esquema import tipo_desde_texto
from ...comun.texto import recortar_palabras as recortar
from ..salida import resumir_lista
from .base import Comando


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
        linea = f"Descriptivos: {len(a.descriptivos)} · Procedimientos: {len(a.procedimientos)}"
        if cp.inventario:
            inv = cp.inventario_de_area(cod)
            esperado_d = sum(1 for f in inv if tipo_desde_texto(f.get("tipo")) == "D")
            linea += f" · En inventario: {esperado_d} descriptivos, {len(inv) - esperado_d} procedimientos"
            faltan = cp.faltantes_de_inventario(inv)
            if faltan:
                linea += f" · NO CONVERTIDOS: {resumir_lista(faltan)}"
        excluidos = sorted(c for c in cp.excluidos if c.split("-")[1] == cod)
        if excluidos:
            linea += f" · EXCLUIDOS POR ESTADO: {resumir_lista(excluidos)}"
        s.linea(linea)
        s.linea()
        if a.descriptivos:
            filas = []
            for c in a.descriptivos:
                f, d = cp.meta.get(c, {}), cp.docs.get(c)
                filas.append([c, cp.nombre(c), f.get("reporta_a", ""), f.get("supervisa_a", ""),
                              recortar(f.get("proposito_literal", ""), 25), f.get("campos_no_especificados", ""),
                              d.ubicacion if d else "?:1-0"])
            s.linea("Descriptivos")
            s.tabla(["Código", "Puesto", "Reporta a", "Supervisa a", "Propósito", "No especificado",
                     "Archivo:líneas"], filas)
            s.linea()
        if a.procedimientos:
            filas = []
            for c in a.procedimientos:
                f, d = cp.meta.get(c, {}), cp.docs.get(c)
                filas.append([c, cp.nombre(c), recortar(f.get("macroproceso", ""), 8),
                              recortar(f.get("proposito_literal", ""), 25), recortar(f.get("subprocedimientos", ""), 20),
                              f.get("codigos_citados", ""), f.get("campos_no_especificados", ""),
                              d.ubicacion if d else "?:1-0"])
            s.linea("Procedimientos")
            s.tabla(["Código", "Procedimiento", "Macroproceso", "Objetivo", "Subprocesos", "Códigos citados",
                     "No especificado", "Archivo:líneas"], filas)
        sin_doc = [c for c in a.codigos() if c not in cp.docs]
        if sin_doc:
            s.linea()
            s.linea("AVISO: en el diccionario pero sin texto en los archivos .md: " + ", ".join(sin_doc))
