import collections
import re

from ...comun.errores import CorpusError
from ...comun.esquema import NO_ESPECIFICADO, SEPARADOR_LISTA
from ...comun.texto import norm, recortar_palabras as recortar
from ..indicadores import kpis_relacionados, sin_medicion
from ..participacion import calcular_participacion
from ..relaciones import AnalizadorRelaciones
from ..salida import resumir_lista
from .base import Comando
from .participacion import tabla_resumen_puestos
from .relaciones import imprimir_no_resueltas, relaciones_de_area, tabla_resumen

DOCS_POR_PARTE = 15
RE_ITEM = re.compile(r"^\s*(-|\d+\.)\s")


def _o_no_especificado(*valores, sep=" / "):
    return sep.join(v for v in valores if v) or NO_ESPECIFICADO


class Briefing(Comando):
    """Tablas del briefing de un area ya calculadas, para que el modelo no las recalcule ni las resuma mal."""

    nombre = "briefing"
    ayuda = "Tablas del briefing de un area (puestos, procedimientos, relaciones, participacion), por partes."

    def configurar(self, parser):
        parser.add_argument("area")
        parser.add_argument("--parte", type=int, default=1)

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        cod = ctx.area(args.area)
        a = cp.areas[cod]
        docs = [c for c in a.codigos() if c in cp.docs]
        total = max(1, -(-len(docs) // DOCS_POR_PARTE))
        if not 1 <= args.parte <= total:
            raise CorpusError(f"El área tiene {total} partes.", 2)
        lote = docs[(args.parte - 1) * DOCS_POR_PARTE: args.parte * DOCS_POR_PARTE]
        s.linea(f"# Briefing: {a.nombre} ({cod}) · parte {args.parte} de {total}")
        s.linea(f"Cobertura: {cp.cobertura(cod)}" + ("" if cp.completo else " · CORPUS INCOMPLETO"))
        faltan = cp.faltantes_de_inventario(cp.inventario_de_area(cod))
        if faltan:
            s.linea(f"No convertidos (no se pueden describir): {resumir_lista(faltan)}")
        s.linea(f"Documentos de esta parte: {', '.join(lote) or '—'}"
                + (f" · siguiente: briefing \"{cod}\" --parte {args.parte + 1}" if args.parte < total
                   else " · última parte"))
        analizador = AnalizadorRelaciones(cp)
        self._puestos(ctx, [c for c in lote if c.startswith("D-")])
        self._procedimientos(ctx, analizador, cod, [c for c in lote if c.startswith("P-")])
        if args.parte == 1:
            self._toda_el_area(ctx, analizador, cod)
        s.linea()
        s.linea("El modelo redacta: 1. Resumen del área, 6. Insights ([Inferido] con códigos), 8. Para profundizar.")

    @staticmethod
    def _funciones(cp, c):
        return [l.lstrip("-0123456789. ").strip() for t, ls in cp.secciones(c)
                if re.search(r"funcion|responsab|actividad", norm(t)) for l in ls if RE_ITEM.match(l)]

    def _puestos(self, ctx, ds):
        cp, s = ctx.corpus, ctx.salida
        s.linea()
        s.linea("## 2. Puestos")
        if not ds:
            s.linea("(ninguno en esta parte)")
            return
        filas = []
        for c in ds:
            f, funciones = cp.meta.get(c, {}), self._funciones(cp, c)
            filas.append([c, cp.nombre(c), f.get("reporta_a") or NO_ESPECIFICADO,
                          recortar(f.get("proposito_literal", ""), 30) or NO_ESPECIFICADO,
                          f"{len(funciones)}: " + "; ".join(recortar(x, 10) for x in funciones[:3])
                          if funciones else NO_ESPECIFICADO, f.get("supervisa_a", "")])
        s.tabla(["Código", "Puesto", "Reporta a", "Propósito", "Funciones principales (n: primeras)", "Supervisa a"],
                filas)

    def _procedimientos(self, ctx, analizador, cod, ps):
        cp, s = ctx.corpus, ctx.salida
        s.linea()
        s.linea("## 3. Procedimientos")
        if not ps:
            s.linea("(ninguno en esta parte)")
            return
        areas_por_doc = collections.defaultdict(set)
        for m in analizador.menciones(cod, list(cp.areas)):
            areas_por_doc[m.codigo].add(m.destino)
        filas = []
        for c in ps:
            f = cp.meta.get(c, {})
            filas.append([c, cp.nombre(c), _o_no_especificado(f.get("macroproceso"), f.get("proceso")),
                          recortar(f.get("proposito_literal", ""), 30) or NO_ESPECIFICADO,
                          _o_no_especificado(f.get("responsable"), f.get("propietario")),
                          _o_no_especificado(f.get("version"), f.get("estado_documental")),
                          ", ".join(sorted(areas_por_doc.get(c, []))) or "—"])
        s.tabla(["Código", "Procedimiento", "Macroproceso / proceso", "Objetivo", "Responsable / propietario",
                 "Versión / estado", "Áreas mencionadas"], filas)
        s.linea()
        s.linea("## 4. Jerarquía de procesos (solo lo documentado)")
        s.tabla(["Macroproceso", "Proceso", "Código", "Actividades (n)"],
                [[cp.meta.get(c, {}).get("macroproceso") or NO_ESPECIFICADO,
                  cp.meta.get(c, {}).get("proceso") or NO_ESPECIFICADO, c,
                  len([x for x in (cp.meta.get(c, {}).get("actividades") or "").split(SEPARADOR_LISTA.strip())
                       if x.strip()])] for c in ps])

    def _toda_el_area(self, ctx, analizador, cod):
        cp, s = ctx.corpus, ctx.salida
        a = cp.areas[cod]
        s.linea()
        s.linea("## 5. Relaciones con otras áreas (toda el área)")
        _, _, resumen, no_resueltas = relaciones_de_area(analizador, cod)
        if resumen:
            tabla_resumen(s, cp, cod, resumen)
        else:
            s.linea("No hay menciones explícitas de otras áreas del corpus.")
        imprimir_no_resueltas(s, no_resueltas, 20)
        procedimientos = [c for c in a.procedimientos if c in cp.docs]
        participaciones = calcular_participacion(cp, procedimientos) if procedimientos else None
        if participaciones and participaciones.filas:
            s.linea()
            s.linea(f"## Participación de puestos (toda el área: {len(procedimientos)} procedimientos, "
                    f"{len(participaciones.filas)} relaciones)")
            tabla_resumen_puestos(s, participaciones, 20)
        s.linea()
        s.linea("## 7. Información no documentada (toda el área)")
        ne = [(c, cp.meta[c].get("campos_no_especificados")) for c in a.codigos()
              if c in cp.meta and cp.meta[c].get("campos_no_especificados")]
        if ne:
            s.tabla(["Código", f"Campos {NO_ESPECIFICADO}"], ne)
        else:
            s.linea(f"Sin campos {NO_ESPECIFICADO}.")
        if participaciones and participaciones.sin_descriptivo:
            if cp.completo:
                s.linea("Roles de procedimientos sin descriptivo: "
                        + "; ".join(f"{r} ({', '.join(sorted(cs))})" for r, cs in participaciones.sin_descriptivo.items()))
            else:
                s.linea("Roles sin descriptivo: no se informan porque el corpus está incompleto.")
        if cp.kpis:
            rel = kpis_relacionados(cp, [c for c in a.codigos() if c in cp.docs])
            if rel:
                s.linea()
                s.linea("## Indicadores cuyos términos aparecen en documentos del área [Inferido]")
                s.tabla(["KPI", "Indicador", "Meta", "Medición", "Documentos"],
                        [[k.get("id", ""), recortar(k.get("indicador", ""), 12),
                          f"{k.get('meta', '')} {k.get('unidad', '')}".strip(),
                          "sin medición" if sin_medicion(k) else f"{k.get('medicion', '')} {k.get('unidad', '')}".strip(),
                          resumir_lista(sorted(cs), 6)] for k, cs in rel])
