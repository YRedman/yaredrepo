"""Textos que el comando ``vaciar`` muestra: lo leido del K4 y el resultado del vaciado."""

import collections

from . import calculo, valores
from .checklist import NA


def _min(x):
    return "—" if x is None else (str(int(x)) if float(x).is_integer() else f"{x:g}")


def texto_k4(k4):
    """Lo que se leyo del K4, para que el agente lo revise y lo cruce con la transcripcion y la minuta."""
    lineas = [f"Colaborador: {' '.join(v for v in (k4.colaborador.get('nombre'), k4.colaborador.get('apellido')) if v) or '—'}"]
    lineas.append("Filas leídas: " + " · ".join(f"{c} {len(f)}" for c, f in k4.tablas.items()))
    if k4.hojas_faltantes:
        lineas.append("Hojas que no encontré: " + ", ".join(k4.hojas_faltantes))
    lineas += [f"Aviso: {a}" for a in k4.avisos]
    inv = {f.texto("actividad"): (f.texto("proceso"), f.texto("tipo")) for f in k4.filas("inventario")}
    lineas += ["", "| Actividad | Proceso | Tiempo (min) | Volumen | Período | Retrabajo | Origen |", "|---|---|---|---|---|---|---|"]
    for f in k4.filas("actividades"):
        t = valores.minutos(f.celda("tiempo"))[0] if f.celda("tiempo") else None
        v = valores.volumen(f.celda("volumen"))[0] if f.celda("volumen") else None
        r = valores.retrabajo(f.celda("retrabajo"))[0] if f.celda("retrabajo") else None
        lineas.append(f"| {(f.texto('actividad') or '')[:70]} | {((inv.get(f.texto('actividad')) or ('',))[0] or '')[:40]} | {_min(t)} | "
                      f"{_min(v)} | {f.texto('periodo') or '—'} | {_min(r)} | {f.origen('tiempo')} |")
    return lineas


def texto_resultado(resultado, k4, nombre_k4, plantilla, celdas_verificadas):
    r = resultado
    lineas = [f"K4: {nombre_k4}", f"Plantilla: {plantilla}", f"Archivo generado: {r.destino}",
              f"Verificación: correcta ({celdas_verificadas} celdas releídas y comparadas; fórmulas, listas desplegables, "
              "formatos y gráficos de la plantilla sin cambios)", "",
              "Celdas escritas por hoja: " + " · ".join(f"{h} {n}" for h, n in r.por_hoja.items())]
    actividades = len(r.horas_por_actividad)
    capacidad = calculo.HORAS_POR_DIA * calculo.DIAS_POR_MES
    lineas.append(f"Actividades: {actividades} · carga estimada {r.horas_mes:.1f} h/mes · FTE preliminar {r.horas_mes / capacidad:.2f} "
                  f"(capacidad {capacidad:.1f} h/mes con vacaciones, ausentismo y pausas en 0 %)")
    if r.sin_horas:
        lineas.append(f"Actividades que la plantilla calcula en 0 h: {', '.join(n[:50] for n in r.sin_horas)}")
    if r.propuestas:
        lineas.append("Propuestas del agente en letra morada (validar a mano): " + " · ".join(f"{h} {n}" for h, n in r.propuestas.items()))
    tipos = collections.Counter(p["tipo"] for p in r.puntos)
    lineas.append(f"Puntos a validar: {len(r.puntos)} (" + ", ".join(f"{t}: {n}" for t, n in tipos.most_common()) + ")")
    if r.checklist is not None:
        lineas.append(f"Checklist del formulario: {r.checklist.veredicto} · completitud {r.checklist.porcentaje:.0%} · calidad {r.checklist.promedio:.1f}/5 · {r.checklist.alerta}")
    for hoja, filas in r.desbordes.items():
        lineas.append(f"AVISO: {len(filas)} fila(s) no cupieron en «{hoja}».")
    lineas += [f"AVISO: {a}" for a in r.advertencias]
    lineas += ["", "| # | Hoja | Campo | Tipo | Valor del K4 | Qué validar |", "|---|---|---|---|---|---|"]
    for i, p in enumerate(r.puntos, 1):
        lineas.append(f"| PV-{i:03d} | {p['hoja']} | {p['campo'][:60]} | {p['tipo']} | "
                      f"{(p['valor_formato'] or '—')[:50].replace(chr(10), ' / ').replace('|', '/')} | {p['que_validar'][:110]} |")
    return lineas


def texto_llenado(r, nombre_base, nombre_datos):
    """Resultado de ``llenar-k4``: lo escrito, lo borrado, los pendientes en morado y los avisos."""
    lineas = [f"Base: {nombre_base}", f"Datos: {nombre_datos}", f"Archivo generado: {r.destino}",
              "Verificación: correcta (encabezados, celdas combinadas, formatos, listas desplegables, comentarios y fórmulas del "
              "formulario sin cambios; respuestas releídas; sin texto en rojo)", "",
              "Celdas escritas por hoja: " + (" · ".join(f"{h} {n}" for h, n in r.por_hoja.items()) or "ninguna"),
              "Registros: " + (" · ".join(f"{c} {n}" for c, n in r.filas.items()) or "ninguno"),
              f"Texto rojo borrado: {len(r.borradas)} celda(s) (ejemplos y notas del formulario)"]
    if r.combinadas_quitadas:
        lineas.append("Celdas combinadas del cuerpo ajustadas: " + "; ".join(f"{h} ({', '.join(m)})" for h, m in r.combinadas_quitadas.items()))
    lineas.append(f"Pendientes «VALIDAR» en morado: {len(r.validar)}")
    lineas += [f"AVISO: {a}" for a in r.advertencias]
    if r.validar:
        lineas += ["", "| Hoja | Celda | Pendiente |", "|---|---|---|"]
        lineas += [f"| {h} | {ref} | {texto[:100].replace('|', '/')} |" for h, ref, texto in r.validar]
    return lineas


ENCABEZADOS_CHECKLIST = ("Datos generales", "Propósito", "Funciones", "Frecuencia y tiempo", "Resp. y nivel de decisión", "Relaciones",
                         "Formación y experiencia", "Competencias", "KPIs", "% Completitud", "Horas/mes", "Alerta de carga", "Coherencia (1–5)",
                         "Especificidad (1–5)", "Calidad promedio")


def texto_checklist(checklists):
    """Tabla del checklist (una fila por formulario) y el detalle de lo que no está completo."""
    lineas = ["| Formulario | " + " | ".join(ENCABEZADOS_CHECKLIST) + " | Veredicto |", "|---" * (len(ENCABEZADOS_CHECKLIST) + 2) + "|"]
    for c in checklists:
        nombre = (c.archivo or c.puesto or "—").replace("|", "/")
        lineas.append(f"| {nombre} | " + " | ".join(x.estado for x in c.criterios) + f" | {c.porcentaje:.0%} | {c.horas_mes:.1f} | "
                      f"{c.alerta} | {c.coherencia} | {c.especificidad} | {c.promedio:.1f} | **{c.veredicto}** |")
    for c in checklists:
        lineas += ["", f"{c.archivo or c.puesto}: {c.veredicto} ({c.motivo_veredicto})"]
        lineas += [f"- {x.nombre}: {x.estado}" + (f" ({x.detalle})" if x.detalle else "") for x in c.criterios if x.estado not in ("Sí", NA)]
        lineas += [f"- {x.nombre}: no aplica ({x.detalle})" for x in c.criterios if x.estado == NA]
        lineas += [f"- Calidad (estimación heurística) · {d}" for d in c.detalle_calidad]
        lineas.append(f"- Carga: {c.horas_mes:.1f} h/mes frente a {c.capacidad:.1f} h/mes de capacidad con vacaciones, ausentismo y pausas en 0 % (FTE preliminar {c.horas_mes / c.capacidad:.2f})")
    return lineas
