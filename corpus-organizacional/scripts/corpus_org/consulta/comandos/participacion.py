import collections

from ...comun.errores import CorpusError
from ...comun.esquema import area_de
from ...comun.texto import oracion_con, recortar_palabras as recortar
from ..puestos import DetectorPuestos
from ..roles import rol
from .base import Comando

MAX_FILAS = 150


class Participacion(Comando):
    nombre = "participacion"
    ayuda = "Puestos que aparecen en los procedimientos y con que rol."

    def configurar(self, parser):
        parser.add_argument("objetivo", metavar="area_o_codigo")

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        cods = ctx.codigos_objetivo(args.objetivo, "P")
        if not cods:
            raise CorpusError("No hay procedimientos para ese criterio.", 2)
        detector = DetectorPuestos.desde_corpus(cp)
        filas, vistos, con_participacion = [], set(), set()
        sin_desc, ambiguas = collections.OrderedDict(), collections.OrderedDict()
        for c in cods:
            for sec, col, texto, linea in cp.celdas(c):
                for m in detector.detectar(texto):
                    if m.tipo == "sin descriptivo":
                        sin_desc.setdefault(m.frase, set()).add(c)
                        continue
                    if m.tipo == "ambigua":
                        ambiguas.setdefault(m.frase, (set(), m.candidatos))[0].add(c)
                        continue
                    r = rol(col, oracion_con(texto, m.frase), sec)
                    clave = (m.puesto.codigo, c, r)
                    if clave in vistos:
                        continue
                    vistos.add(clave)
                    con_participacion.add(m.puesto.codigo)
                    filas.append([f"{m.puesto.nombre} ({m.puesto.codigo})", f"{c} {cp.nombre(c)}", r,
                                  "exacta" if m.tipo == "exacta" else f"{m.etiqueta}: «{m.frase}»", recortar(sec, 8),
                                  recortar(linea.strip("| ").replace("|", "·"), 30)])
        s.linea(f"PARTICIPACIÓN · {len(cods)} procedimientos · {len(filas)} relaciones puesto–procedimiento")
        s.linea("Rol según la columna de la tabla o las palabras clave de la oración donde aparece el puesto; "
                "'probable' = nombre parecido, no idéntico (tratar como [Inferido]).")
        s.linea()
        if filas:
            s.tabla(["Puesto (descriptivo)", "Procedimiento", "Rol", "Coincidencia", "Sección", "Evidencia"],
                    filas[:MAX_FILAS])
        else:
            s.linea("No se encontraron puestos con descriptivo en estos procedimientos.")
        if len(filas) > MAX_FILAS:
            s.linea(f"Se muestran {MAX_FILAS} de {len(filas)} filas; consulta por procedimiento: participacion <CÓDIGO>.")
        if ambiguas:
            s.linea()
            s.linea("Menciones parecidas a varios puestos (no se asignaron; confirmar con doc):")
            for frase, (cs, candidatos) in ambiguas.items():
                opciones = ", ".join(f"{p.nombre} ({p.codigo})" for p in candidatos)
                s.linea(f"- {frase}: {', '.join(sorted(cs))} · posibles: {opciones}")
        if sin_desc:
            s.linea()
            s.linea("Puestos o roles mencionados que no tienen descriptivo en el corpus:")
            for frase, cs in sin_desc.items():
                s.linea(f"- {frase}: {', '.join(sorted(cs))}")
        areas = {area_de(c) for c in cods}
        if len(areas) == 1:
            sin_part = [d for d in cp.areas[areas.pop()].descriptivos if d not in con_participacion]
            if sin_part:
                s.linea()
                s.linea("Descriptivos del área que no aparecen en sus procedimientos: "
                        + ", ".join(f"{d} {cp.nombre(d)}" for d in sin_part))
