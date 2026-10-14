from ...comun.errores import CorpusError
from ...comun.esquema import area_de
from ...comun.tipos import TIPOS_PROCESO, tipo_de_codigo
from ...comun.texto import recortar_palabras as recortar
from ..participacion import calcular_participacion
from ..salida import resumir_lista
from .base import Comando

DETALLE_POR_DEFECTO = 60


def _detalle(valor):
    """'todo' -> sin limite; un numero -> ese limite."""
    if valor is None:
        return DETALLE_POR_DEFECTO
    if str(valor).lower() == "todo":
        return None
    if str(valor).isdigit():
        return int(valor)
    raise CorpusError(f"--detalle acepta un número o 'todo' (recibido: '{valor}').")


def tabla_resumen_puestos(s, participaciones, maximo=None):
    resumen = participaciones.resumen_por_puesto()
    s.tabla(["Código", "Puesto", "Procedimientos distintos", "Roles", "Procedimientos"],
            [[p.codigo, p.nombre, len(procs), ", ".join(f"{k} ({n})" for k, n in roles.most_common()),
              resumir_lista(sorted(procs), 12)] for p, procs, roles in resumen[:maximo]])


def imprimir_ausencias(s, cp, participaciones, codigos):
    """Roles sin descriptivo y descriptivos sin participacion: solo se afirman con el corpus completo."""
    if participaciones.sin_descriptivo:
        s.linea()
        if cp.completo:
            s.linea("Puestos o roles mencionados que no tienen descriptivo en el corpus (corpus completo):")
        else:
            s.linea("Puestos o roles mencionados que no coinciden con ningún descriptivo CARGADO. El corpus está "
                    "incompleto: no concluyas que no tienen descriptivo.")
        for frase, cs in participaciones.sin_descriptivo.items():
            s.linea(f"- {frase}: {', '.join(sorted(cs))}")
    areas = {area_de(c) for c in codigos}
    if len(areas) == 1 and len(codigos) > 1:
        cod = areas.pop()
        sin_part = [d for d in cp.areas[cod].descriptivos
                    if d in cp.docs and d not in participaciones.puestos_con_participacion()]
        if sin_part:
            s.linea()
            if cp.completo:
                s.linea("Descriptivos del área que no aparecen en sus procedimientos: "
                        + ", ".join(f"{d} {cp.nombre(d)}" for d in sin_part))
            else:
                s.linea("(Se omite 'descriptivos que no aparecen en procedimientos': el corpus está incompleto.)")


class Participacion(Comando):
    nombre = "participacion"
    ayuda = "Puestos que aparecen en los procedimientos y con que rol (resumen completo y detalle)."

    def configurar(self, parser):
        parser.add_argument("objetivo", metavar="area_o_codigo")
        parser.add_argument("--detalle", default=None, help="Filas de detalle: un número o 'todo'.")

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        maximo = _detalle(args.detalle)
        # procedimientos (PRD) y protocolos (PRO); las politicas no tienen responsables por paso
        cods = [c for c in ctx.codigos_objetivo(args.objetivo, "P") if tipo_de_codigo(c) in TIPOS_PROCESO]
        if not cods:
            raise CorpusError("No hay procedimientos ni protocolos para ese criterio.", 2)
        p = calcular_participacion(cp, cods)
        con_filas = len({f.procedimiento for f in p.filas})
        s.linea(f"PARTICIPACIÓN · {len(cods)} procedimientos y protocolos ({con_filas} con puestos identificados) · "
                f"{len(p.filas)} relaciones puesto–procedimiento · calculado sobre TODAS las filas")
        s.linea("Rol según la columna de la tabla o las palabras clave de la oración donde aparece el puesto; "
                "'probable' = nombre parecido, no idéntico (tratar como [Inferido]).")
        s.linea()
        if not p.filas:
            s.linea("No se encontraron puestos con descriptivo en estos procedimientos.")
        else:
            s.linea("Resumen por puesto (completo; úsalo para contar quién concentra más procedimientos)")
            tabla_resumen_puestos(s, p)
            mostradas = p.filas if maximo is None else p.filas[:maximo]
            s.linea()
            s.linea(f"Detalle: filas 1–{len(mostradas)} de {len(p.filas)}"
                    + ("" if len(mostradas) == len(p.filas) else " (más: --detalle todo, o participacion <CÓDIGO>)"))
            s.tabla(["Puesto (descriptivo)", "Procedimiento", "Rol", "Coincidencia", "Sección", "Evidencia"],
                    [[f"{f.puesto.nombre} ({f.puesto.codigo})", f"{f.procedimiento} {cp.nombre(f.procedimiento)}",
                      f.rol, f.coincidencia, recortar(f.seccion, 8),
                      recortar(f.evidencia.strip("| ").replace("|", "·"), 30)] for f in mostradas])
        if p.ambiguas:
            s.linea()
            s.linea("Menciones parecidas a varios puestos (no se asignaron; confirmar con doc):")
            for frase, (cs, candidatos) in p.ambiguas.items():
                opciones = ", ".join(f"{x.nombre} ({x.codigo})" for x in candidatos)
                s.linea(f"- {frase}: {', '.join(sorted(cs))} · posibles: {opciones}")
        imprimir_ausencias(s, cp, p, cods)
