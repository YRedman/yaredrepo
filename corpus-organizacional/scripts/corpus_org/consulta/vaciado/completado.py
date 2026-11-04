"""Ninguna celda de entrada queda vacia: lo que el K4 no trae se propone y se rotula «Inferido» o «A validar».

- **Inferido**: hay una regla o un dato detras (por ejemplo, el valor VA / NVA-N / NVA sale de las palabras de la actividad). La celda
  se escribe en letra morada y su nota explica la regla.
- **A validar**: no hay base para proponer nada. En una celda de texto se escribe «A validar: …»; en una celda con lista
  desplegable no se puede escribir texto (solo admite sus opciones), asi que queda vacia y se anota en ``sin_completar``.

En los dos casos el consultor valida a mano. Las fechas no se completan (un texto en una celda de fecha rompe las formulas).
"""

from ...comun.texto import norm
from . import inferencia
from .plantilla import clave

LIMITE_RESPONSABILIDAD = 150
ROTULOS_PERFIL = (
    "Nivel / categoría", "Alcance del rol", "Clientes internos / externos", "Productos / servicios entregables", "Indicadores principales",
    "Decisiones autónomas*", "Decisiones que requieren aprobación", "Autoridades formales*", "Responsabilidades sobre el SGQ",
    "Sustitución / respaldo", "Segregación de funciones crítica", "Disciplina / especialidad", "Experiencia general (años)",
    "Experiencia específica (años)", "Certificaciones / licencias", "Idiomas y nivel", "Conocimientos técnicos*", "Herramientas / sistemas",
    "Requisitos legales / regulatorios", "Disponibilidad / viajes / turnos", "Condiciones de trabajo", "Riesgos SST / ergonómicos",
    "Recursos requeridos", "Información documentada asociada", "Propietario del documento", "Frecuencia de revisión", "Aprobador",
    "Código / versión del descriptivo", "Contribución a objetivos de calidad", "Propósito general del puesto*")
ROTULOS_CONTROL = ("Subárea", "Jefe inmediato", "Ubicación", "Colaborador / Entrevistado", "Entrevistador", "Nombre del puesto*", "Área / unidad*")
INFERIDOS_DE_CONTROL = {"Versión": ("1.0", "es el primer levantamiento de este puesto"),
                        "Tipo de vinculación": ("Empleado fijo", "el K4 no lo indica; se asume un colaborador fijo"),
                        "Estado del levantamiento": ("En proceso", "la plantilla se acaba de llenar y está pendiente de validación")}


class Completador:
    def __init__(self, vaciado):
        self.v = vaciado

    # -- primitivas ----------------------------------------------------------------------------------------------

    def _libre(self, hoja, ref):
        v = self.v
        if (hoja, ref) in v.r.escritas:
            return False
        if v.plantilla.libro.hoja(hoja).valor(ref) not in (None, ""):
            return False
        xml = v.paquete.hoja_xml(hoja).xml_celda(ref)
        return not (xml and "<f" in xml)

    def _ref(self, hoja, fila, encabezado):
        col = self.v._tabla(hoja)["columnas"].get(clave(encabezado))
        return f"{col}{fila}" if col else None

    def _inferido(self, hoja, ref, valor, motivo, etiqueta="Inferido"):
        if not self._libre(hoja, ref):
            return False
        return self.v.poner(hoja, ref, valor, morado=True, nota=f"{etiqueta}: {motivo}. Validar con el consultor.")

    def _a_validar(self, hoja, ref, que, motivo=None):
        """Texto «A validar: …» en una celda libre; si la celda es una lista o una fecha no se puede, y se anota."""
        if not self._libre(hoja, ref):
            return False
        if self.v.plantilla.es_lista(hoja, ref) or self.v.plantilla.es_fecha(hoja, ref):
            self.v.r.sin_completar.append((hoja, ref, que))
            return False
        return self.v.poner(hoja, ref, f"A validar: {que}", morado=True,
                            nota=f"A validar: {motivo or 'el K4, la transcripción y la minuta no traen este dato'}. Validar con el consultor.")

    def _en_fila(self, hoja, fila, encabezado, valor, motivo=None, que=None, etiqueta="Inferido"):
        """Escribe ``valor`` (inferido) o, si es None, «A validar: que» en la celda de una fila de tabla."""
        ref = self._ref(hoja, fila, encabezado)
        if ref is None:
            return
        if valor is not None:
            self._inferido(hoja, ref, valor, motivo, etiqueta)
        else:
            self._a_validar(hoja, ref, que or encabezado.replace("*", "").lower())

    def _valor_de(self, hoja, fila, encabezado):
        ref = self._ref(hoja, fila, encabezado)
        return self.v.r.escritas.get((hoja, ref)) if ref else None

    # -- tablas --------------------------------------------------------------------------------------------------

    def ejecutar(self):
        self._codigos()
        self._actividades()
        self._riesgos()
        self._responsabilidades()
        self._tablas_de_texto()
        self._control()
        self._perfil()

    def _codigos(self):
        """Sin un codigo de puesto valido en el K4, la columna «Código puesto» de cada tabla queda como «A validar»."""
        v = self.v
        if v.codigo:
            return
        for hoja, filas in v._filas_tabla.items():
            for fila in filas:
                ref = self._ref(hoja, fila, "Código puesto")
                if ref:
                    self._a_validar(hoja, ref, "código del puesto", "el K4 no trae un código de puesto válido")

    def _actividades(self):
        v, h = self.v, "Actividades_Carga"
        funciones = list(v._datos_responsabilidad.values())
        for fila, d in v._datos_actividad.items():
            texto = f"{d['nombre']} {d['descripcion'] or ''}"
            tipo = d["tipo"] or self._valor_de(h, fila, "Tipo proceso")
            if tipo is None:
                tipo, motivo = inferencia.tipo_de_proceso(texto)
                self._en_fila(h, fila, "Tipo proceso", tipo, motivo)
            valor = self._valor_de(h, fila, "Valor")
            if valor is None:
                valor, motivo = inferencia.valor_de_actividad(texto, tipo, d["retrabajo"])
                self._en_fila(h, fila, "Valor", valor, motivo + ". VA = el cliente lo pagaría; NVA-N = necesaria sin agregar valor; NVA = desperdicio")
            cliente, motivo = inferencia.cliente_de(texto)
            self._en_fila(h, fila, "Cliente", cliente, motivo)
            if d["automatizacion"] is None and self._valor_de(h, fila, "Automatización") is None:
                self._en_fila(h, fila, "Automatización", "Manual", "el K4 no indica el nivel de automatización; se asume manual")
            self._en_fila(h, fila, "Participantes por evento", 1, "el K4 no pide el número de participantes; se asume una persona")
            self._en_fila(h, fila, "Espera min", 0, "el K4 no registra tiempos de espera; se asume 0 min")
            self._en_fila(h, fila, "Meses/año activos", 12, "el K4 dice que la actividad es estacional y no cuántos meses dura; 12 es un valor provisional",
                          etiqueta="A validar")
            self._en_fila(h, fila, "Subproceso", None, que=f"subproceso de «{d['proceso']}»" if d["proceso"] else "subproceso")
            coincide = inferencia.coincidencia(d["nombre"], funciones)
            if coincide:
                self._en_fila(h, fila, "Responsabilidad vinculada", coincide[0][:LIMITE_RESPONSABILIDAD],
                              f"la actividad y la responsabilidad comparten las palabras: {', '.join(coincide[1])}")
            else:
                self._en_fila(h, fila, "Responsabilidad vinculada", None, que="responsabilidad vinculada")
            if not d["descripcion"]:
                self._en_fila(h, fila, "Descripción / inicio-fin", None, que="descripción, inicio y fin de la actividad")
            d["valor"], d["tipo"] = valor, tipo
            d["automatizacion"] = d["automatizacion"] or self._valor_de(h, fila, "Automatización")

    def _riesgos(self):
        v, h = self.v, "Riesgos_Mejoras"
        por_nombre = {norm(d["nombre"]): d for d in v._datos_actividad.values()}
        total = v.r.horas_mes
        for fila in v._filas_tabla.get(h, []):
            info = v._datos_riesgo.get(fila, {})
            act = por_nombre.get(norm(info.get("actividad", "")), {})
            ref_evidencia = self._ref(h, fila, "Evidencia")
            if ref_evidencia and self._libre(h, ref_evidencia):
                if info.get("evidencia"):
                    v.poner(h, ref_evidencia, info["evidencia"])              # referencia al K4: es un dato, no una propuesta
                else:
                    self._a_validar(h, ref_evidencia, "evidencia (dato o documento que respalda el hallazgo)")
            horas, retrabajo = act.get("horas", 0.0), act.get("retrabajo")
            impacto = self._valor_de(h, fila, "Impacto")
            if impacto is None:
                impacto, motivo = inferencia.impacto_de(horas, total)
                self._en_fila(h, fila, "Impacto", impacto, motivo)
            probabilidad = self._valor_de(h, fila, "Probabilidad")
            if probabilidad is None:
                probabilidad, motivo = inferencia.probabilidad_de(retrabajo)
                self._en_fila(h, fila, "Probabilidad", probabilidad, motivo)
            accion = self._valor_de(h, fila, "Acción sugerida")
            if accion is None:
                accion, motivo = inferencia.accion_de(act.get("valor"), act.get("automatizacion"), horas, retrabajo)
                self._en_fila(h, fila, "Acción sugerida", accion, motivo)
            if self._valor_de(h, fila, "Esfuerzo") is None:
                nivel, motivo = inferencia.esfuerzo_de(accion)
                self._en_fila(h, fila, "Esfuerzo", nivel, motivo)
            if self._valor_de(h, fila, "Prioridad") is None:
                nivel, motivo = inferencia.prioridad_de(impacto, probabilidad)
                self._en_fila(h, fila, "Prioridad", nivel, motivo)
            self._en_fila(h, fila, "Causa raíz", None, que="causa raíz del hallazgo")
            self._en_fila(h, fila, "Beneficio esperado", None, que="beneficio esperado (ahorro por medir)")
            self._en_fila(h, fila, "Tipo oportunidad", None, que="tipo de oportunidad")

    def _responsabilidades(self):
        v, h = self.v, "Responsabilidades"
        for fila, texto in v._datos_responsabilidad.items():
            self._en_fila(h, fila, "Resultado / entregable", None, que="resultado o entregable de la responsabilidad")
            self._en_fila(h, fila, "Indicador / criterio de éxito", None, que="indicador o criterio de éxito")
            coincide = inferencia.coincidencia(texto, v.procesos, minimo=1)
            if coincide:
                self._en_fila(h, fila, "Proceso relacionado", coincide[0], f"la responsabilidad comparte las palabras con el proceso: {', '.join(coincide[1])}")
            else:
                self._en_fila(h, fila, "Proceso relacionado", None, que="proceso relacionado")
            self._en_fila(h, fila, "As-Is / To-Be", "As-Is", "el K4 describe cómo se trabaja hoy")
            self._en_fila(h, fila, "Peso %", round(1 / len(v._datos_responsabilidad), 4),
                          f"el K4 no pide pesos; se repartió por igual entre las {len(v._datos_responsabilidad)} responsabilidades")

    def _tablas_de_texto(self):
        """Columnas de texto de Competencias, Interacciones y Sistemas_Datos que el K4 no trae."""
        v = self.v
        for fila in v._filas_tabla.get("Competencias", []):
            tipo, motivo = inferencia.tipo_de_competencia(v._datos_competencia.get(fila, ""))
            self._en_fila("Competencias", fila, "Tipo", tipo, motivo)
            self._en_fila("Competencias", fila, "Nivel requerido", "Intermedio", "el K4 no indica el nivel requerido; «Intermedio» es el valor central")
            for enc in ("Método de evaluación", "Evidencia disponible", "Brecha / desarrollo", "Conducta / evidencia observable"):
                self._en_fila("Competencias", fila, enc, None)
        for fila in v._filas_tabla.get("Interacciones", []):
            self._en_fila("Interacciones", fila, "Rol RACI", "Consulta", "el K4 no pide el rol RACI; «Consulta» es el valor más neutro")
            for enc in ("Dolor / duplicidad", "Entrada recibida", "Salida entregada", "Proceso / entregable"):
                self._en_fila("Interacciones", fila, enc, None)
        actividades = [d["nombre"] for d in v._datos_actividad.values()]
        for fila in v._filas_tabla.get("Sistemas_Datos", []):
            uso = self._valor_de("Sistemas_Datos", fila, "Uso principal") or ""
            coincide = inferencia.coincidencia(str(uso), actividades)
            if coincide:
                self._en_fila("Sistemas_Datos", fila, "Proceso / actividad", coincide[0], f"el uso de la herramienta y la actividad comparten las palabras: {', '.join(coincide[1])}")
            else:
                self._en_fila("Sistemas_Datos", fila, "Proceso / actividad", None)
            for enc in ("Uso principal", "Dato de entrada", "Dato de salida", "Dueño del dato", "Nivel de acceso", "Control / validación", "Dolor / oportunidad"):
                self._en_fila("Sistemas_Datos", fila, enc, None)

    # -- identificacion -------------------------------------------------------------------------------------------

    def _control(self):
        v, h = self.v, "Control"
        for rotulo in ROTULOS_CONTROL + (() if v.codigo else ("Código puesto*",)):
            ref = v.plantilla.valor_de_rotulo(h, rotulo, "derecha")
            if ref:
                self._a_validar(h, ref, rotulo.replace("*", "").lower())
        for rotulo, (valor, motivo) in INFERIDOS_DE_CONTROL.items():
            ref = v.plantilla.valor_de_rotulo(h, rotulo, "derecha")
            if ref:
                self._inferido(h, ref, valor, motivo)

    def _perfil(self):
        v, h = self.v, "Perfil_Puesto"
        general = (v.k4.filas("general") or [None])[0]
        cargo = general.texto("puesto") if general else ""
        for rotulo in ROTULOS_PERFIL + (() if v.codigo else ("Código puesto*",)) + ("Nombre puesto*", "Área / unidad*", "Subárea", "Reporta a*", "Puestos que supervisa"):
            ref = v.plantilla.valor_de_rotulo(h, rotulo, "abajo")
            if not ref or not self._libre(h, ref):
                continue
            if rotulo == "Nivel / categoría":
                categoria = inferencia.nivel_del_cargo(cargo)
                if categoria:
                    self._inferido(h, ref, categoria[0], categoria[1])
                    continue
            if rotulo == "Clientes internos / externos" and v._datos_actividad:
                clientes = sorted({v.r.escritas.get(("Actividades_Carga", f"{col}{fila}"), "") for fila in v._datos_actividad
                                   for col in [v._tabla("Actividades_Carga")["columnas"].get(clave("Cliente"))] if col} - {""})
                if clientes:
                    self._inferido(h, ref, ", ".join(clientes), "son los clientes que se infirieron para las actividades del puesto")
                    continue
            self._a_validar(h, ref, rotulo.replace("*", "").lower())
