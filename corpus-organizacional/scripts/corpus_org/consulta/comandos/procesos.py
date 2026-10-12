from ...comun.esquema import SEPARADOR_LISTA
from ...comun.texto import recortar_palabras as recortar
from .base import Comando


class Procesos(Comando):
    nombre = "procesos"
    ayuda = "Macroproceso, proceso, procedimiento y actividades."

    def configurar(self, parser):
        parser.add_argument("--area", default=None)

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        cods = ctx.filtrar_area(sorted(c for c in cp.meta if c.startswith("P-")), args.area)
        filas = []
        for c in cods:
            f = cp.meta[c]
            acts = [x.strip() for x in (f.get("actividades") or "").split(SEPARADOR_LISTA.strip()) if x.strip()]
            filas.append([f.get("macroproceso", ""), f.get("proceso", ""), c, cp.nombre(c), len(acts),
                          recortar("; ".join(acts), 25)])
        s.linea(f"JERARQUÍA DE PROCESOS · {len(filas)} procedimientos")
        s.linea("Actividades = items y filas de la sección de desarrollo de cada procedimiento (confirmar con doc).")
        s.tabla(["Macroproceso", "Proceso", "Código", "Procedimiento", "Actividades", "Muestra"], filas)
