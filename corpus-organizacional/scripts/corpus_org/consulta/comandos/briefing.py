"""Briefing de un area: tablas ya calculadas (el modelo las copia y solo redacta resumen, insights y profundizar)."""

import collections
import re

from ...comun.errores import CorpusError
from ...comun.esquema import NO_ESPECIFICADO
from ...comun.texto import norm, recortar_palabras as recortar
from ...comun.tipos import TIPOS_AREA
from ..extraccion import funciones, perfil
from ..indicadores import kpis_relacionados, sin_medicion
from ..jerarquia import estructura_area
from ..participacion import calcular_participacion
from ..pertinencia import MOTIVO_DEL_AREA, gen_pertinentes
from ..puestos import DetectorPuestos
from ..relaciones import AnalizadorRelaciones
from ..salida import resumir_lista
from .base import Comando
from .normativa import agrupar_por_tipo, citas_de
from .participacion import tabla_resumen_puestos
from .procesos import CABECERA as CABECERA_PROCESOS, filas_procesos
from .relaciones import imprimir_no_resueltas, relaciones_de_area, tabla_resumen

DOCS_POR_PARTE = 15
RE_ITEM = re.compile(r"^\s*(-|\d+\.)\s")
RE_EDUCACION = re.compile(r"educacion|formacion|escolaridad|estudios")
RE_EXPERIENCIA = re.compile(r"experiencia")
ROL_EJECUTA, ROL_APRUEBA = "Ejecuta (responsable del paso)", "Aprueba"
CAMPOS_GOBIERNO = (("version", "Versión"), ("fecha_vigencia", "Vigencia"), ("propietario", "Propietario"),
                   ("responsable", "Responsable"))
TITULOS_NORMATIVOS = {"PRO": "Protocolos (PRO)", "POL": "Políticas (POL)"}


def _o_no_especificado(*valores, sep=" / "):
    return sep.join(v for v in valores if v) or NO_ESPECIFICADO


def _evidencia(linea):
    """Texto literal de la linea del documento (una fila de tabla se muestra con ' · ' entre celdas)."""
    return re.sub(r"\s+", " ", linea.strip().strip("|").replace("|", "·")).strip()


class Briefing(Comando):
    """Tablas del briefing de un area ya calculadas, para que el modelo no las recalcule ni las resuma mal.

    Los documentos del area se reparten de 15 en 15 por parte (DES, PRD, PRO y POL, con los protocolos y
    politicas GEN pertinentes). Las tablas que resumen el area completa van en la parte 1.
    """

    nombre = "briefing"
    ayuda = "Tablas del briefing de un area (puestos, procedimientos, protocolos, politicas, relaciones...), por partes."

    def configurar(self, parser):
        parser.add_argument("area")
        parser.add_argument("--parte", type=int, default=1)

    # -- orquestacion -----------------------------------------------------------------------

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        cod = ctx.area(args.area)
        a = cp.areas[cod]
        detector = DetectorPuestos.desde_corpus(cp)
        analizador = AnalizadorRelaciones(cp, detector)
        propios = {t: [c for c in a.codigos(t) if c in cp.docs] for t in TIPOS_AREA}
        pertinentes = gen_pertinentes(cp, cod, detector)
        motivos = {c: m for t in pertinentes for c, m in pertinentes[t].items()}
        listado = {t: propios[t] + list(pertinentes.get(t, {})) for t in TIPOS_AREA}
        docs = [c for t in TIPOS_AREA for c in listado[t]]
        total = max(1, -(-len(docs) // DOCS_POR_PARTE))
        if not 1 <= args.parte <= total:
            raise CorpusError(f"El área tiene {total} partes.", 2)
        lote = set(docs[(args.parte - 1) * DOCS_POR_PARTE: args.parte * DOCS_POR_PARTE])
        n_gen = sum(len(v) for v in pertinentes.values())

        s.linea(f"Partes: {total}")
        s.linea(self._cobertura(cp, cod, n_gen))
        s.linea(f"# Briefing: {a.nombre} ({cod}) · parte {args.parte} de {total}")
        faltan = cp.faltantes_de_inventario(cp.inventario_de_area(cod))
        if faltan:
            s.linea(f"No convertidos (no se pueden describir): {resumir_lista(faltan)}")
        s.linea(f"Documentos de esta parte: {', '.join(c for c in docs if c in lote) or '—'}"
                + (f" · siguiente: briefing \"{cod}\" --parte {args.parte + 1}" if args.parte < total
                   else " · última parte"))

        procesos = propios["PRD"] + propios["PRO"]
        part = calcular_participacion(cp, procesos, detector) if procesos else None
        puestos_por_doc = collections.defaultdict(set)
        for f in (part.filas if part else []):
            puestos_por_doc[f.procedimiento].add(f.puesto.codigo)

        self._puestos(ctx, [c for c in listado["DES"] if c in lote])
        self._procedimientos(ctx, analizador, cod, [c for c in listado["PRD"] if c in lote], puestos_por_doc)
        for t in ("PRO", "POL"):
            self._normativos(ctx, t, [c for c in listado[t] if c in lote], motivos)
        if args.parte == 1:
            self._toda_el_area(ctx, analizador, detector, cod, propios, part, puestos_por_doc)
        s.linea()
        s.linea("El modelo redacta solo: Resumen del área, Insights ([Inferido], con códigos) y Para profundizar.")

    @staticmethod
    def _cobertura(cp, cod, n_gen):
        por_tipo = cp.cobertura_por_tipo(cod)
        partes = [f"{t} {p}/{e if e is not None else '?'}" for t, (p, e) in por_tipo.items()]
        return ("Cobertura: " + " · ".join(partes) + f" · GEN pertinentes: {n_gen}"
                + ("" if cp.completo else " · CORPUS INCOMPLETO"))

    # -- tablas por documento (se reparten en partes) ------------------------------------------

    @staticmethod
    def _funciones(cp, c):
        return [l.lstrip("-0123456789. ").strip() for t, ls in cp.secciones(c)
                if re.search(r"funcion|responsab|actividad", norm(t)) for l in ls if RE_ITEM.match(l)]

    def _puestos(self, ctx, ds):
        cp, s = ctx.corpus, ctx.salida
        s.linea()
        s.linea("## Puestos (DES)")
        if not ds:
            s.linea("(ninguno en esta parte)")
            return
        filas = []
        for c in ds:
            f, funciones_c = cp.meta.get(c, {}), self._funciones(cp, c)
            filas.append([c, cp.nombre(c), f.get("reporta_a") or NO_ESPECIFICADO,
                          recortar(f.get("proposito_literal", ""), 30) or NO_ESPECIFICADO,
                          f"{len(funciones_c)}: " + "; ".join(recortar(x, 10) for x in funciones_c[:3])
                          if funciones_c else NO_ESPECIFICADO, f.get("supervisa_a", "")])
        s.tabla(["Código", "Puesto", "Reporta a", "Propósito", "Funciones principales (n: primeras)", "Supervisa a"],
                filas)

    def _procedimientos(self, ctx, analizador, cod, ps, puestos_por_doc):
        cp, s = ctx.corpus, ctx.salida
        s.linea()
        s.linea("## Procedimientos (PRD)")
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
                          ", ".join(sorted(areas_por_doc.get(c, []))) or "—", len(puestos_por_doc.get(c, ()))])
        s.tabla(["Código", "Procedimiento", "Macroproceso / proceso", "Objetivo", "Responsable / propietario",
                 "Versión / estado", "Áreas mencionadas", "N.º de puestos que participan"], filas)

    def _normativos(self, ctx, tipo, codigos, motivos):
        """Protocolos (PRO) o politicas (POL) del area y los GEN pertinentes, con el motivo de cada uno."""
        cp, s = ctx.corpus, ctx.salida
        s.linea()
        s.linea(f"## {TITULOS_NORMATIVOS[tipo]}")
        if not codigos:
            s.linea("(ninguno en esta parte)")
            return
        filas = []
        for c in codigos:
            f = cp.meta.get(c, {})
            filas.append([c, cp.nombre(c), f.get("departamento", ""), f.get("area_propietaria") or NO_ESPECIFICADO,
                          recortar(f.get("proposito_literal", ""), 30) or NO_ESPECIFICADO,
                          _o_no_especificado(f.get("responsable"), f.get("propietario")),
                          _o_no_especificado(f.get("version"), f.get("estado_documental")),
                          motivos.get(c, MOTIVO_DEL_AREA)])
        s.tabla(["Código", "Documento", "Área", "Área propietaria", "Objetivo", "Responsable / propietario",
                 "Versión / estado", "Motivo"], filas)

    # -- tablas de toda el area (parte 1) ----------------------------------------------------------

    def _toda_el_area(self, ctx, analizador, detector, cod, propios, part, puestos_por_doc):
        cp, s = ctx.corpus, ctx.salida
        todos = [c for t in TIPOS_AREA for c in propios[t]]
        self._jerarquia(s, cp, propios["PRD"])
        self._relaciones(s, cp, analizador, cod)
        self._participacion(s, part, propios)
        self._un_solo_puesto(s, cp, part)
        self._ejecuta_y_aprueba(s, cp, part)
        self._estructura(s, cp, cod, detector)
        self._indicadores(s, cp, propios, todos)
        self._gobierno(s, cp, todos)
        self._normativa(s, cp, todos)
        self._perfil_y_funciones(s, cp, propios["DES"])
        self._no_documentado(s, cp, cod, todos, part)

    @staticmethod
    def _jerarquia(s, cp, prd):
        s.linea()
        s.linea("## Jerarquía de procesos")
        if prd:
            s.tabla(CABECERA_PROCESOS, filas_procesos(cp, prd))
        else:
            s.linea("(el área no tiene procedimientos)")

    @staticmethod
    def _relaciones(s, cp, analizador, cod):
        s.linea()
        s.linea("## Relaciones")
        _, _, resumen, no_resueltas = relaciones_de_area(analizador, cod)
        if resumen:
            tabla_resumen(s, cp, cod, resumen)
        else:
            s.linea("No hay menciones explícitas de otras áreas del corpus.")
        imprimir_no_resueltas(s, no_resueltas, 20)

    @staticmethod
    def _participacion(s, part, propios):
        s.linea()
        s.linea("## Participación — Resumen por puesto")
        n = len(propios["PRD"]) + len(propios["PRO"])
        if part and part.filas:
            s.linea(f"Toda el área: {n} procedimientos y protocolos, {len(part.filas)} relaciones puesto–documento.")
            tabla_resumen_puestos(s, part, 20)
        else:
            s.linea("(ningún puesto con descriptivo aparece en los procedimientos o protocolos del área)")

    @staticmethod
    def _un_solo_puesto(s, cp, part):
        s.linea()
        s.linea("## Procedimientos con un solo puesto participante")
        por_doc = collections.defaultdict(set)
        for f in (part.filas if part else []):
            por_doc[f.procedimiento].add(f.puesto)
        filas = [[c, cp.nombre(c), ", ".join(f"{p.nombre} ({p.codigo})" for p in sorted(ps, key=lambda p: p.codigo))]
                 for c, ps in sorted(por_doc.items()) if len(ps) == 1]
        if filas:
            s.tabla(["Código", "Procedimiento", "Puesto"], filas)
        else:
            s.linea("(ninguno)")

    @staticmethod
    def _ejecuta_y_aprueba(s, cp, part):
        s.linea()
        s.linea("## Mismo puesto con roles Ejecuta y Aprueba en un procedimiento")
        evidencias = collections.defaultdict(dict)
        for f in (part.filas if part else []):
            if f.rol in (ROL_EJECUTA, ROL_APRUEBA):
                evidencias[(f.procedimiento, f.puesto.codigo)].setdefault(f.rol, (f.puesto.nombre, f.evidencia))
        filas = [[c, cp.nombre(c), f"{roles[ROL_EJECUTA][0]} ({p})", _evidencia(roles[ROL_EJECUTA][1]),
                  _evidencia(roles[ROL_APRUEBA][1])]
                 for (c, p), roles in sorted(evidencias.items()) if len(roles) == 2]
        if filas:
            s.tabla(["Código", "Procedimiento", "Puesto", "Evidencia (Ejecuta)", "Evidencia (Aprueba)"], filas)
        else:
            s.linea("(ninguno)")

    @staticmethod
    def _estructura(s, cp, cod, detector):
        s.linea()
        s.linea("## Estructura")
        filas = [[c, cp.nombre(c), cp.meta[c].get("reporta_a") or NO_ESPECIFICADO, jefe or "—", len(subs),
                  ", ".join(subs) or "—", nivel]
                 for c, jefe, subs, nivel in estructura_area(cp, cod, detector)]
        if not filas:
            s.linea("(el área no tiene descriptivos)")
            return
        s.linea("Subordinados directos según «Supervisa a» y «Reporta a». Nivel 1 = puesto que reporta fuera del "
                "área (o sin jefe identificado en ella).")
        s.tabla(["Código", "Puesto", "Reporta a", "Jefe en el área", "Subordinados directos (n)", "Subordinados",
                 "Nivel jerárquico"], filas)

    @staticmethod
    def _indicadores(s, cp, propios, todos):
        s.linea()
        s.linea("## Indicadores relacionados")
        if not cp.kpis:
            s.linea("(el corpus no tiene kpis.csv)")
            return
        rel = kpis_relacionados(cp, [c for c in todos if c in cp.docs])
        if rel:
            s.linea("Coincidencia de términos con los documentos del área [Inferido]: confirmar con doc.")
            s.tabla(["KPI", "Indicador", "Meta", "Medición", "Documentos"],
                    [[k.get("id", ""), recortar(k.get("indicador", ""), 12),
                      f"{k.get('meta', '')} {k.get('unidad', '')}".strip(),
                      "sin medición" if sin_medicion(k) else f"{k.get('medicion', '')} {k.get('unidad', '')}".strip(),
                      resumir_lista(sorted(cs), 6)] for k, cs in rel])
        else:
            s.linea("(ningún indicador menciona términos de los documentos del área)")
        s.linea()
        s.linea("Indicadores sin medición (de los relacionados con el área)")
        sin_med = [k for k, _ in rel if sin_medicion(k)]
        if sin_med:
            s.tabla(["KPI", "Indicador", "Meta"], [[k.get("id", ""), recortar(k.get("indicador", ""), 12),
                                                    f"{k.get('meta', '')} {k.get('unidad', '')}".strip()]
                                                   for k in sin_med])
        else:
            s.linea("(ninguno)")
        s.linea(f"Sin medición en todo el corpus: {sum(1 for k in cp.kpis if sin_medicion(k))} de {len(cp.kpis)}.")
        s.linea()
        s.linea("Procedimientos del área sin ningún indicador relacionado")
        con_kpi = set().union(*(cs for _, cs in rel)) if rel else set()
        sin_kpi = [c for c in propios["PRD"] if c not in con_kpi]
        if sin_kpi:
            s.tabla(["Código", "Procedimiento"], [[c, cp.nombre(c)] for c in sin_kpi])
        else:
            s.linea("(ninguno)" if propios["PRD"] else "(el área no tiene procedimientos)")

    @staticmethod
    def _gobierno(s, cp, todos):
        s.linea()
        s.linea("## Gobierno documental (resumen)")
        if not todos:
            s.linea("(el área no tiene documentos)")
            return
        filas = []
        for campo, etiqueta in CAMPOS_GOBIERNO:
            faltan = [c for c in todos if not (cp.meta.get(c, {}).get(campo) or "").strip()]
            filas.append([etiqueta, f"{len(faltan)} de {len(todos)}", resumir_lista(faltan, 20) or "—"])
        s.tabla(["Campo", "Documentos que no lo traen", "Códigos"], filas)

    @staticmethod
    def _normativa(s, cp, todos):
        s.linea()
        s.linea("## Normativa citada (resumen)")
        grupos = agrupar_por_tipo(citas_de(cp, todos))
        if not grupos:
            s.linea("(los documentos del área no citan normativa)")
            return
        s.tabla(["Tipo de referencia", "N.º de citas", "Documentos que la citan"],
                [[t, len(v), resumir_lista(sorted({c[0] for c in v}), 20)] for t, v in grupos.items()])
        s.linea("El detalle literal de cada cita se obtiene con: normativa --area \"<área>\".")

    @staticmethod
    def _perfil_y_funciones(s, cp, des):
        s.linea()
        s.linea("## Perfil y funciones (resumen por puesto)")
        if not des:
            s.linea("(el área no tiene descriptivos)")
            return
        filas = []
        for c in des:
            doc = cp.doc(c)
            fn = funciones(doc)
            reqs = perfil(doc)
            educacion = [f"{d or r}" for _, r, d in reqs if RE_EDUCACION.search(norm(r))]
            experiencia = [f"{d or r}" for _, r, d in reqs if RE_EXPERIENCIA.search(norm(r))]
            filas.append([c, cp.nombre(c), len(fn), sum(1 for _, ev in fn if ev.strip()),
                          "; ".join(educacion) or NO_ESPECIFICADO, "; ".join(experiencia) or NO_ESPECIFICADO])
        s.tabla(["Código", "Puesto", "Funciones", "Con evidencia o entregable", "Educación requerida",
                 "Experiencia requerida"], filas)

    @staticmethod
    def _no_documentado(s, cp, cod, todos, part):
        s.linea()
        s.linea("## No documentado")
        ne = [(c, cp.meta[c].get("campos_no_especificados")) for c in todos
              if c in cp.meta and cp.meta[c].get("campos_no_especificados")]
        if ne:
            s.tabla(["Código", f"Campos {NO_ESPECIFICADO}"], ne)
        else:
            s.linea(f"Sin campos {NO_ESPECIFICADO}.")
        if not cp.completo:
            s.linea("Roles sin descriptivo y descriptivos que no aparecen en procedimientos: no se informan porque "
                    "el corpus está incompleto.")
            return
        if part and part.sin_descriptivo:
            s.linea("Roles de procedimientos sin descriptivo: "
                    + "; ".join(f"{r} ({', '.join(sorted(cs))})" for r, cs in part.sin_descriptivo.items()))
        con = part.puestos_con_participacion() if part else set()
        sin_part = [d for d in cp.areas[cod].codigos("DES") if d in cp.docs and d not in con]
        if sin_part:
            s.linea("Descriptivos del área que no aparecen en sus procedimientos: "
                    + ", ".join(f"{d} {cp.nombre(d)}" for d in sin_part))
