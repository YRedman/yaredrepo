from ...comun.esquema import SEPARADOR_LISTA
from ...comun.tipos import tipo_de_codigo
from ...comun.texto import recortar_palabras as recortar
from .base import Comando


CABECERA = ["Macroproceso", "Proceso", "Código", "Procedimiento", "Actividades", "Muestra"]


def filas_procesos(cp, codigos):
    """Filas de la jerarquia macroproceso -> proceso -> procedimiento -> actividades de los procedimientos dados."""
    filas = []
    for c in codigos:
        f = cp.meta[c]
        acts = [x.strip() for x in (f.get("actividades") or "").split(SEPARADOR_LISTA.strip()) if x.strip()]
        filas.append([f.get("macroproceso", ""), f.get("proceso", ""), c, cp.nombre(c), len(acts),
                      recortar("; ".join(acts), 25)])
    return filas


class Procesos(Comando):
    nombre = "procesos"
    ayuda = "Macroproceso, proceso, procedimiento y actividades."

    def configurar(self, parser):
        parser.add_argument("--area", default=None)

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        cods = ctx.filtrar_area(sorted(c for c in cp.meta if tipo_de_codigo(c) == "PRD"), args.area)
        filas = filas_procesos(cp, cods)
        s.linea(f"JERARQUÍA DE PROCESOS · {len(filas)} procedimientos")
        s.linea("Actividades = items y filas de la sección de desarrollo de cada procedimiento (confirmar con doc).")
        s.tabla(CABECERA, filas)
