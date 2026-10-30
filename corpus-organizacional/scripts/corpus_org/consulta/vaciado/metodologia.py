"""Pasa los datos del K4 a la plantilla metodologica y deja lo que no encaja en la hoja Puntos_a_validar."""

import difflib
import re
from dataclasses import dataclass, field

from ...comun.texto import norm
from . import calculo, valores
from .hoja_xml import CeldaConFormula
from .k4 import K4
from .paquete import Paquete
from .plantilla import PRIMERA_FILA_TABLA, Plantilla, clave

HOJA_PUNTOS = "Puntos_a_validar"
NOMBRE_TABLA_PUNTOS = "tblPuntosValidar"
FILAS_PUNTOS_MINIMAS = 100
TIPOS_PUNTO = ["Dato sin destino", "Valor fuera de lista", "Diferencia K4/Reunión", "Dato faltante", "Supuesto",
               "Interpretación", "Recomendación"]
ESTADOS_PUNTO = ["Pendiente", "En proceso", "Completo", "No aplica"]
FUENTE_K4 = "Estimación experta"          # lo que el ocupante estima en el K4
FUENTE_ENTREVISTA = "Entrevista"
CALIDAD_K4 = "Estimación"
MESES_ACTIVOS_POR_DEFECTO = 12
ESTADO_DE_DISENO = "As-Is"
FUENTE_EVIDENCIA_K4 = "Documento"
MAX_CARACTERES_PUNTO = 1500
RE_CODIGO_PUESTO = re.compile(r"^(?=.*\d)[A-Za-z0-9][A-Za-z0-9._\-/]{1,29}$")

# Rotulos de la plantilla -> (hoja, direccion): Control tiene el valor a la derecha; Perfil_Puesto, debajo.
DIRECCION = {"Control": "derecha", "Perfil_Puesto": "abajo"}


@dataclass
class Resultado:
    destino: str = ""
    escritas: dict = field(default_factory=dict)         # (hoja, ref) -> valor
    por_hoja: dict = field(default_factory=dict)         # hoja -> cantidad de celdas escritas
    puntos: list = field(default_factory=list)
    advertencias: list = field(default_factory=list)
    horas_mes: float = 0.0
    fte: float = 0.0
    sin_horas: list = field(default_factory=list)        # actividades que la plantilla calcularia en 0 h
    desbordes: dict = field(default_factory=dict)        # hoja -> filas que no cupieron
    horas_por_actividad: list = field(default_factory=list)


def _txt(valor):
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).replace("\xa0", " ").strip() or None


def _unir(*partes, sep="\n"):
    return sep.join(p for p in partes if p)


def _recortar_punto(texto):
    texto = _txt(texto) or ""
    return texto if len(texto) <= MAX_CARACTERES_PUNTO else texto[:MAX_CARACTERES_PUNTO].rstrip() + " …"


class Vaciado:
    def __init__(self, k4: K4, ruta_plantilla, complementos=None, nombre_k4="", fuentes_extra=()):
        self.k4 = k4
        self.paquete = Paquete(ruta_plantilla)
        self.plantilla = Plantilla(self.paquete.libro)
        self.complementos = complementos or {}
        self.nombre_k4 = nombre_k4
        self.fuentes_extra = list(fuentes_extra)
        self.r = Resultado()
        self._tablas = {}
        self.codigo = None
        self.dias_mes = self.plantilla.dias_por_mes(calculo.DIAS_POR_MES)
        self.supuestos = {"meses": 0, "retrabajo": 0, "dedicacion_indirecta": 0, "bimestral": 0, "rangos": 0, "eventual": 0}

    # -- escritura ---------------------------------------------------------------------------------------------

    def poner(self, hoja, ref, valor, estilo=None):
        """Escribe un valor en la plantilla; las celdas con formula y los textos vacios no se tocan."""
        if valor is None or valor == "":
            return False
        try:
            if self.paquete.hoja_xml(hoja).escribir(ref, valor, estilo):
                self.r.advertencias.append(f"{hoja}!{ref}: el texto superaba el límite de Excel y se recortó.")
        except CeldaConFormula:
            self.r.advertencias.append(f"{hoja}!{ref}: tiene fórmula; no se escribió.")
            return False
        self.r.escritas[(hoja, ref)] = valor
        self.r.por_hoja[hoja] = self.r.por_hoja.get(hoja, 0) + 1
        return True

    def punto(self, hoja, campo, tipo, valor_formato="", que_validar="", valor_reunion="", fuente_reunion=""):
        self.r.puntos.append({"hoja": hoja, "campo": campo, "tipo": tipo, "valor_formato": _recortar_punto(valor_formato),
                              "valor_reunion": _recortar_punto(valor_reunion), "fuente_reunion": fuente_reunion or "",
                              "que_validar": que_validar})

    def _tabla(self, hoja):
        if hoja not in self._tablas:
            self._tablas[hoja] = {"columnas": self.plantilla.columnas_de_tabla(hoja), "siguiente": PRIMERA_FILA_TABLA,
                                  "ultima": self.paquete.capacidad_de_tabla(hoja)}
        return self._tablas[hoja]

    def fila_nueva(self, hoja, valores_por_encabezado, referencia=""):
        """Agrega una fila a una tabla de la plantilla. Devuelve su numero o None si la tabla esta llena."""
        t = self._tabla(hoja)
        fila = t["siguiente"]
        if fila > t["ultima"]:
            self.r.desbordes.setdefault(hoja, []).append(referencia or valores_por_encabezado)
            return None
        t["siguiente"] += 1
        for encabezado, valor in valores_por_encabezado.items():
            col = t["columnas"].get(clave(encabezado))
            if col is None:
                self.r.advertencias.append(f"{hoja}: la plantilla no tiene la columna «{encabezado}».")
                continue
            self.poner(hoja, f"{col}{fila}", valor)
        return fila

    def _campo(self, hoja, rotulo, valor, referencia_k4=""):
        """Escribe el valor de un rotulo de Control o Perfil_Puesto (solo si la celda esta vacia en la plantilla)."""
        ref = self.plantilla.valor_de_rotulo(hoja, rotulo, DIRECCION[hoja])
        if ref is None:
            self.r.advertencias.append(f"{hoja}: no encontré el rotulo «{rotulo}».")
            return None
        actual = self.plantilla.libro.hoja(hoja).valor(ref)
        if actual not in (None, "") and not isinstance(actual, float):
            return ref
        self.poner(hoja, ref, valor)
        return ref

    # -- orquestacion ------------------------------------------------------------------------------------------

    def ejecutar(self, destino):
        self._identificacion()
        self._perfil()
        self._responsabilidades()
        self._competencias()
        self._actividades()
        self._interacciones()
        self._herramientas()
        self._riesgos_y_mejoras()
        self._transicionales()
        self._entregables()
        self._complementos()
        self._evidencias()
        self._supuestos()
        self._hoja_de_puntos()
        self.paquete.recalcular_al_abrir()
        self.paquete.guardar(destino)
        self.r.destino = str(destino)
        return self.r

    # -- identificacion ----------------------------------------------------------------------------------------

    def _identificacion(self):
        g = self.k4.filas("general")
        f = g[0] if g else None
        col = self.k4.colaborador
        nombre_completo = _unir(col.get("nombre"), col.get("apellido"), sep=" ")
        puesto, codigo = (f.texto("puesto"), f.texto("codigo")) if f else (None, None)
        if codigo and RE_CODIGO_PUESTO.match(codigo):
            self.codigo = codigo
        elif f is not None:
            self.punto("Control", "Código puesto*", "Dato faltante", codigo or "(vacío)",
                       "El K4 no trae un código de puesto válido: completarlo en Control y en la columna «Código puesto» de cada hoja.")
        if f is None:
            self.punto("Control", "Información general", "Dato faltante", "", "El K4 no trae la hoja «8. Información General».")
            return
        reporta = f.texto("reporta")
        for hoja, rotulo, valor in (("Control", "Área / unidad*", f.texto("area")), ("Control", "Subárea", f.texto("departamento")),
                                    ("Control", "Código puesto*", self.codigo), ("Control", "Nombre del puesto*", puesto),
                                    ("Control", "Colaborador / Entrevistado", nombre_completo or None),
                                    ("Control", "Jefe inmediato", reporta), ("Control", "Ubicación", f.texto("ubicacion"))):
            self._campo(hoja, rotulo, valor)
        cond = self.k4.filas("condiciones")
        if cond:
            mod_texto = cond[0].texto("modalidad")
            mod = valores.modalidad(mod_texto)
            if mod:
                self._campo("Control", "Modalidad", mod)
            elif mod_texto:
                self.punto("Control", "Modalidad", "Valor fuera de lista", mod_texto,
                           "La modalidad no coincide con la lista (Presencial, Híbrido, Remoto, Campo).")
        if f.texto("matricial"):
            self.punto("Perfil_Puesto", "Reporta matricialmente / regionalmente a", "Dato sin destino", f.texto("matricial"),
                       "La plantilla no tiene un campo para el reporte matricial: decidir dónde registrarlo.")
        if col.get("correo") or col.get("telefono"):
            self.r.advertencias.append("El correo y el teléfono del colaborador no se copian a la plantilla (no tiene esos campos).")

    # -- perfil ------------------------------------------------------------------------------------------------

    def _perfil(self):
        g = self.k4.filas("general")
        f = g[0] if g else None
        prop = (self.k4.filas("proposito") or [None])[0]
        edu = self.k4.filas("educacion")
        cond = (self.k4.filas("condiciones") or [None])[0]
        P = "Perfil_Puesto"
        if f:
            personas, cargo = f.texto("personas"), f.texto("puestos_cargo")
            supervisa = _unir(f"{personas} persona(s) a cargo" if personas else None, cargo)
            for rotulo, valor in (("Código puesto*", self.codigo), ("Nombre puesto*", f.texto("puesto")), ("Área / unidad*", f.texto("area")),
                                  ("Subárea", f.texto("departamento")), ("Reporta a*", f.texto("reporta")),
                                  ("Puestos que supervisa", supervisa), ("Ubicación", f.texto("ubicacion")),
                                  ("Estado de diseño", ESTADO_DE_DISENO)):
                self._campo(P, rotulo, valor)
        if prop:
            for rotulo, campo in (("Propósito general del puesto*", "proposito"), ("Contribución a objetivos de calidad", "funcion_clave"),
                                  ("Alcance del rol", "objetivos"), ("Indicadores principales", "resultados")):
                self._campo(P, rotulo, prop.texto(campo))
        entregables = [_txt(e.valor("entregable")) for e in self.k4.filas("entregables")]
        self._campo(P, "Productos / servicios entregables", _unir(*entregables) or None)
        self._educacion(edu)
        tecnicas = [c.texto("competencia") for c in self.k4.filas("competencias") if valores.tipo_competencia(c.texto("tipo")) == "Técnica"]
        self._campo(P, "Conocimientos técnicos*", "; ".join(t for t in tecnicas if t) or None)
        herramientas = [h.texto("nombre") for h in self.k4.filas("herramientas")]
        self._campo(P, "Herramientas / sistemas", "; ".join(h for h in herramientas if h) or None)
        if cond:
            self._condiciones(cond)

    def _educacion(self, filas):
        P = "Perfil_Puesto"
        niveles = [(valores.escolaridad(e.texto("nivel")), e) for e in filas]
        academicos = [(n, e) for n, e in niveles if n]
        if academicos:
            minima = min(academicos, key=lambda x: valores.ESCOLARIDADES.index(x[0]))[0]
            self._campo(P, "Escolaridad mínima*", minima)
        elif filas:
            self.punto(P, "Escolaridad mínima*", "Valor fuera de lista", "; ".join(e.texto("nivel") or "" for e in filas),
                       "El nivel académico no coincide con la lista de escolaridad de la plantilla.")
        disciplina = _unir(*[f"{e.texto('nivel')}: {e.texto('area')}" if e.texto("nivel") and e.texto("area") else (e.texto("area")) for e in filas])
        certificaciones = _unir(*[e.texto("certificaciones") for e in filas])
        self._campo(P, "Disciplina / especialidad", disciplina or None)
        self._campo(P, "Certificaciones / licencias", certificaciones or None)
        for n, e in niveles:
            if n is None and e.texto("nivel"):
                self.punto(P, "Experiencia / requisitos", "Interpretación", _unir(e.texto("nivel"), e.texto("area"), e.texto("certificaciones")),
                           "Fila de la hoja «9. Educación» que no es un nivel académico (p. ej. experiencia): ubicarla en el campo que corresponda.")

    def _condiciones(self, cond):
        P = "Perfil_Puesto"
        disponibilidad = [t for t in self.k4.exposicion if norm(t).startswith("disponibilidad")]
        riesgos = [t for t in self.k4.exposicion if t not in disponibilidad]
        self._campo(P, "Disponibilidad / viajes / turnos", _unir(cond.texto("horario"), *disponibilidad) or None)
        self._campo(P, "Recursos requeridos", cond.texto("equipos"))
        self._campo(P, "Riesgos SST / ergonómicos", _unir(*riesgos) or None)
        mod = cond.texto("modalidad")
        self._campo(P, "Condiciones de trabajo", _unir(mod, cond.texto("observaciones")) or None)

    # -- tablas simples ----------------------------------------------------------------------------------------

    def _responsabilidades(self):
        for fila in self.k4.filas("responsabilidades"):
            freq_txt = fila.texto("frecuencia")
            freq = self._frecuencia_de_lista(freq_txt)
            nivel, obs = fila.texto("nivel"), fila.texto("observaciones")
            autoridad = _unir(f"Nivel de responsabilidad: {nivel}" if nivel else None, obs)
            self.fila_nueva("Responsabilidades", {"Código puesto": self.codigo, "Responsabilidad principal": fila.texto("funcion"),
                                                       "Frecuencia": freq, "Autoridad asociada": autoridad or None},
                                fila.referencia("funcion"))
            if freq_txt and not freq:
                self.punto("Responsabilidades", f"Frecuencia de «{(fila.texto('funcion') or '')[:60]}»", "Valor fuera de lista", freq_txt,
                           "La frecuencia no está en la lista (Diaria, Semanal, Quincenal, Mensual, Trimestral, Semestral, Anual, Eventual).")
        if self.k4.filas("responsabilidades"):
            self.punto("Responsabilidades", "Resultado / entregable*", "Dato faltante", "",
                       "El K4 no pide el resultado de cada responsabilidad (campo obligatorio de la plantilla): completarlo en la entrevista.")

    def _frecuencia_de_lista(self, texto):
        """La frecuencia de una lista de la plantilla (sin Bimestral); None si no calza. Cuenta las lecturas «a demanda»."""
        freq, nota = valores.frecuencia(texto)
        if freq in valores.EVENTOS_POR_ANIO:
            return None
        if nota:
            self.supuestos["eventual"] += 1
        return freq

    def _competencias(self):
        propuestas = 0
        for fila in self.k4.filas("competencias"):
            tipo_txt, nivel_txt = fila.texto("tipo"), fila.texto("nivel")
            tipo, nivel = valores.tipo_competencia(tipo_txt), valores.nivel(nivel_txt)
            self.fila_nueva("Competencias", {"Código puesto": self.codigo, "Tipo": tipo, "Competencia / conocimiento": fila.texto("competencia"),
                                             "Nivel requerido": nivel, "Conducta / evidencia observable": fila.texto("observaciones")},
                            fila.referencia("competencia"))
            nombre = (fila.texto("competencia") or "")[:60]
            if tipo_txt and not tipo:
                self.punto("Competencias", f"Tipo de «{nombre}»", "Valor fuera de lista", tipo_txt, "El tipo no está en la lista de la plantilla.")
            if nivel_txt and not nivel:
                self.punto("Competencias", f"Nivel de «{nombre}»", "Valor fuera de lista", nivel_txt,
                           "El nivel no está en la lista (Básico, Intermedio, Avanzado, Experto).")
            propuestas += fila.origen("competencia") == "propuesto" or fila.origen("tipo") == "propuesto"
        if propuestas:
            self.punto("Competencias", "Competencias propuestas", "Interpretación", f"{propuestas} de {len(self.k4.filas('competencias'))}",
                       "Son propuestas hechas al completar el K4, no confirmadas por el ocupante: validar con Gestión Humana y con el ocupante.")

    def _interacciones(self):
        sin_raci = 0
        for fila in self.k4.filas("relaciones"):
            freq_txt = fila.texto("frecuencia")
            freq = self._frecuencia_de_lista(freq_txt)
            contacto, destino = fila.texto("contacto"), fila.texto("destino")
            actor = fila.texto("area") + (f" ({contacto})" if contacto and fila.texto("area") else "") if fila.texto("area") else contacto
            salida = fila.texto("resultado")
            if destino:
                salida = _unir(salida, f"Hacia: {destino}", sep=". ")
            self.fila_nueva("Interacciones", {"Código puesto": self.codigo, "Proceso / entregable": fila.texto("motivo"),
                                               "Actor / área relacionada": actor, "Tipo de relación": fila.texto("tipo"),
                                               "Entrada recibida": fila.texto("recibida"), "Salida entregada": salida, "Frecuencia": freq},
                            fila.referencia("area"))
            sin_raci += 1
            if freq_txt and not freq:
                self.punto("Interacciones", f"Frecuencia con «{(fila.texto('area') or '')[:60]}»", "Valor fuera de lista", freq_txt,
                           "La frecuencia no está en la lista de la plantilla.")
        if sin_raci:
            self.punto("Interacciones", "Rol RACI*", "Dato faltante", "", f"El K4 no pide el rol RACI (obligatorio): completarlo en {sin_raci} fila(s).")

    def _herramientas(self):
        for fila in self.k4.filas("herramientas"):
            detalle = [("Tipo", fila.texto("tipo")), ("Nivel de dominio", fila.texto("dominio")), ("Frecuencia de uso", fila.texto("frecuencia")),
                       ("Requerido/deseable", fila.texto("requerido"))]
            uso = _unir(fila.texto("uso"), "; ".join(f"{k}: {v}" for k, v in detalle if v), sep=". ")
            self.fila_nueva("Sistemas_Datos", {"Código puesto": self.codigo, "Sistema / herramienta": fila.texto("nombre"), "Uso principal": uso or None},
                            fila.referencia("nombre"))

    # -- actividades -------------------------------------------------------------------------------------------

    def _inventario(self):
        """{actividad normalizada: (proceso, tipo)} del inventario de procesos del K4."""
        return {norm(f.texto("actividad") or ""): (f.texto("proceso"), f.texto("tipo")) for f in self.k4.filas("inventario") if f.texto("actividad")}

    def _proceso_de(self, nombre, inventario):
        k = norm(nombre or "")
        if k in inventario:
            return inventario[k]
        cercano = difflib.get_close_matches(k, list(inventario), n=1, cutoff=0.9)
        return inventario[cercano[0]] if cercano else (None, None)

    def _actividades(self):
        inventario = self._inventario()
        vistos_inv = set()
        for fila in self.k4.filas("actividades"):
            nombre = fila.texto("actividad")
            proceso, tipo_txt = self._proceso_de(nombre, inventario)
            if proceso is None:
                self.punto("Actividades_Carga", f"Proceso de «{(nombre or '')[:60]}»", "Dato faltante", "",
                           "La actividad no está en el inventario de procesos del K4: indicar su proceso.")
            tipo = valores.tipo_proceso(tipo_txt)
            self._fila_actividad(fila, nombre, proceso, tipo, tipo_txt)
            vistos_inv.add(norm(nombre or ""))
        faltan = [f for f in self.k4.filas("inventario") if norm(f.texto("actividad") or "") not in vistos_inv]
        if faltan:
            self.punto("Actividades_Carga", "Actividades del inventario sin detalle", "Dato faltante",
                       "; ".join(f.texto("actividad") for f in faltan)[:1200],
                       f"{len(faltan)} actividad(es) del inventario no tienen fila en «2. Actividades Base»: pedir su tiempo y volumen.")

    def _fila_actividad(self, fila, nombre, proceso, tipo, tipo_txt):
        ref = f"«{(nombre or '')[:60]}»"
        t, nota_t = valores.minutos(fila.celda("tiempo")) if fila.celda("tiempo") else (None, None)
        v, nota_v = valores.volumen(fila.celda("volumen")) if fila.celda("volumen") else (None, None)
        periodo_txt = fila.texto("periodo")
        periodo, _ = valores.frecuencia(periodo_txt)
        retrabajo, nota_r = valores.retrabajo(fila.celda("retrabajo")) if fila.celda("retrabajo") else (None, None)
        indirecto, nota_i = valores.minutos(fila.celda("indirecto")) if fila.celda("indirecto") else (None, None)
        automatizacion_txt = fila.texto("automatizacion")
        automatizacion = valores.automatizacion(automatizacion_txt)
        periodo_final, eventos, nota_p = valores.periodo_para_plantilla(periodo, v)
        if nota_p:
            self.supuestos["bimestral"] += 1
        if periodo_txt and not periodo:
            self.punto("Actividades_Carga", f"Período de {ref}", "Valor fuera de lista", periodo_txt, "El período no está en la lista de frecuencias.")
        for nota, campo, valor in ((nota_t, "Tiempo", fila.texto("tiempo")), (nota_v, "Volumen", fila.texto("volumen")),
                                   (nota_r, "Retrabajo", fila.texto("retrabajo")), (nota_i, "Participación indirecta", fila.texto("indirecto"))):
            if nota and not nota.startswith("tiempo 0"):
                tipo_p = "Interpretación" if (valor and not nota.startswith("no se pudo") and "convirtió" not in nota and "mayor que 1" not in nota) else "Valor fuera de lista"
                self.punto("Actividades_Carga", f"{campo} de {ref}", tipo_p, valor or "", nota)
        if nota_v and "rango" in nota_v or nota_t and "rango" in nota_t:
            self.supuestos["rangos"] += 1
        recurrencia = fila.texto("recurrencia")
        meses = MESES_ACTIVOS_POR_DEFECTO
        if recurrencia and norm(recurrencia) == "estacional":
            meses = None
            self.punto("Actividades_Carga", f"Meses activos de {ref}", "Dato faltante", recurrencia,
                       "Actividad estacional: indicar en cuántos meses del año se realiza (la plantilla usa 12 si se deja el valor por defecto).")
        else:
            self.supuestos["meses"] += 1
        dedicacion = 1.0
        if indirecto:
            dedicacion = min(1.0, indirecto / t) if t else 1.0
            self.supuestos["dedicacion_indirecta"] += 1
        if retrabajo is not None:
            self.supuestos["retrabajo"] += 1
        origen = fila.origen("tiempo")
        if "entrevista" in (fila.origen("volumen"), fila.origen("periodo"), origen):
            fuente = FUENTE_ENTREVISTA
        else:
            fuente = FUENTE_K4
        descripcion = _unir(fila.texto("descripcion"), f"[Recurrencia en el K4: {recurrencia}]" if recurrencia else None, sep=" ")
        n = self.fila_nueva("Actividades_Carga", {
            "Código puesto": self.codigo, "Proceso": proceso, "Actividad": nombre, "Descripción / inicio-fin": descripcion,
            "Tipo proceso": tipo, "Frecuencia": periodo_final, "Eventos por frecuencia": eventos, "Meses/año activos": meses,
            "Tiempo unitario min": t, "% dedicación personal": dedicacion if t is not None else None, "Retrabajo %": retrabajo,
            "Fuente del dato": fuente, "Calidad dato": CALIDAD_K4, "Automatización": automatizacion}, fila.referencia("actividad"))
        if tipo_txt and not tipo:
            self.punto("Actividades_Carga", f"Tipo de proceso de {ref}", "Valor fuera de lista", tipo_txt, "El tipo no está en la lista (Core, Soporte, Gobierno/Control).")
        if automatizacion_txt and not automatizacion:
            self.punto("Actividades_Carga", f"Automatización de {ref}", "Valor fuera de lista", automatizacion_txt,
                       "El nivel no está en la lista (Manual, Semiautomatizada, Automatizada).")
        horas = calculo.horas_mes(t, 0, eventos, periodo_final, retrabajo, dedicacion if t is not None else None, self.dias_mes)
        self.r.horas_por_actividad.append((nombre, horas))
        self.r.horas_mes += horas
        if n is not None and horas == 0:
            self.r.sin_horas.append(nombre)

    def _transicionales(self):
        for fila in self.k4.filas("transicionales"):
            partes = [f"{k}: {fila.texto(c)}" for k, c in (("Descripción", "descripcion"), ("Recurrencia", "recurrencia"), ("Tiempo (min)", "tiempo"),
                                                            ("Volumen", "volumen"), ("Período", "periodo"), ("Participación indirecta", "indirecto"),
                                                            ("Automatización", "automatizacion"), ("Retrabajo", "retrabajo"),
                                                            ("Causa de retrabajo", "causa"), ("Riesgos", "riesgo")) if fila.texto(c)]
            self.punto("Actividades_Carga", f"{fila.texto('transicion') or 'Transición'}: {(fila.texto('actividad') or '')[:70]}", "Recomendación",
                       "\n".join(partes), "Actividad transicional (próximos seis meses): la plantilla describe el estado actual y no tiene dónde registrarla.")

    def _entregables(self):
        for fila in self.k4.filas("entregables"):
            partes = [f"{k}: {fila.texto(c)}" for k, c in (("Recurrencia / período", "recurrencia"), ("Actividades", "actividades"),
                                                             ("Puestos participantes", "puestos")) if fila.texto(c)]
            self.punto("Perfil_Puesto", f"Entregable: {(fila.texto('entregable') or '')[:80]}", "Dato sin destino", "\n".join(partes),
                       "La plantilla no relaciona entregables con actividades ni puestos: el entregable está en «Productos / servicios entregables».")

    # -- riesgos y mejoras -------------------------------------------------------------------------------------

    def _riesgos_y_mejoras(self):
        for fila in self.k4.filas("actividades"):
            if fila.texto("riesgo") or fila.texto("causa"):
                self.fila_nueva("Riesgos_Mejoras", {"Código puesto": self.codigo, "Actividad / proceso": fila.texto("actividad"),
                                                     "Hallazgo / dolor": fila.texto("riesgo") or fila.texto("causa"),
                                                     "Causa raíz": fila.texto("causa") if fila.texto("riesgo") else None,
                                                     "Tipo oportunidad": "Riesgo de la actividad"}, fila.referencia("riesgo"))
        for fila in self.k4.filas("optimizacion"):
            self.fila_nueva("Riesgos_Mejoras", {"Código puesto": self.codigo, "Actividad / proceso": fila.texto("actividad"),
                                                 "Hallazgo / dolor": fila.texto("sugerencia"), "Beneficio esperado": fila.texto("ahorro"),
                                                 "Tipo oportunidad": "Optimización de tiempo"}, fila.referencia("actividad"))
        if self.k4.filas("optimizacion"):
            self.punto("Riesgos_Mejoras", "Ahorro de las optimizaciones", "Dato faltante", "",
                       "El K4 no cuantifica el ahorro: no incorporarlo al caso de negocio hasta medirlo.")

    # -- evidencias --------------------------------------------------------------------------------------------

    def _evidencias(self):
        if self.nombre_k4:
            self.fila_nueva("Evidencias", {"Código puesto": self.codigo, "Tipo": FUENTE_EVIDENCIA_K4,
                                            "Nombre / descripción": f"Formulario K4 completado: {self.nombre_k4}"}, self.nombre_k4)
        for e in self.fuentes_extra + list(self.complementos.get("evidencias", [])):
            e = e if isinstance(e, dict) else {"nombre": str(e)}
            tipo = e.get("tipo") if e.get("tipo") in ("Observación directa", "Muestreo de trabajo", "Sistema transaccional", "Bitácora",
                                                       "Entrevista", "Estimación experta", "Documento") else "Entrevista"
            self.fila_nueva("Evidencias", {"Código puesto": self.codigo, "Tipo": tipo, "Nombre / descripción": e.get("nombre")}, e.get("nombre"))

    # -- complementos de la entrevista -------------------------------------------------------------------------

    def _complementos(self):
        c = self.complementos
        for item in c.get("campos", []):
            hoja, rotulo, valor = item.get("hoja"), item.get("campo"), item.get("valor")
            fuente = item.get("fuente", "Entrevista")
            if hoja not in DIRECCION or not rotulo or valor in (None, ""):
                continue
            ref = self.plantilla.valor_de_rotulo(hoja, rotulo, DIRECCION[hoja])
            if ref is None:
                self.punto(hoja, rotulo, "Dato sin destino", "", f"Complemento sin campo en la plantilla: {valor}", str(valor), fuente)
                continue
            existente = self.r.escritas.get((hoja, ref))
            if item.get("modo") == "diferencia" or (existente not in (None, "") and _txt(existente) != _txt(valor)):
                self.punto(hoja, rotulo, "Diferencia K4/Reunión", _txt(existente) or "", "El K4 y la reunión dicen cosas distintas: confirmar cuál vale.",
                           str(valor), fuente)
                if (hoja, ref) in self.r.escritas:
                    self.paquete.hoja_xml(hoja).escribir(ref, "")
                    del self.r.escritas[(hoja, ref)]
            elif existente in (None, ""):
                self.poner(hoja, ref, valor)
        for a in c.get("actividades_nuevas", []):
            self._actividad_nueva(a)
        for p in c.get("puntos", []):
            self.punto(p.get("hoja", ""), p.get("campo", ""), p.get("tipo") if p.get("tipo") in TIPOS_PUNTO else "Interpretación",
                       p.get("valor_formato", ""), p.get("que_validar", ""), p.get("valor_reunion", ""), p.get("fuente_reunion", ""))

    def _actividad_nueva(self, a):
        periodo, _ = valores.frecuencia(a.get("periodo"))
        volumen, tiempo = a.get("volumen"), a.get("tiempo_min")
        periodo_final, eventos, nota = valores.periodo_para_plantilla(periodo, volumen)
        n = self.fila_nueva("Actividades_Carga", {
            "Código puesto": self.codigo, "Proceso": a.get("proceso"), "Actividad": a.get("actividad"), "Descripción / inicio-fin": a.get("descripcion"),
            "Frecuencia": periodo_final, "Eventos por frecuencia": eventos, "Meses/año activos": MESES_ACTIVOS_POR_DEFECTO,
            "Tiempo unitario min": tiempo, "% dedicación personal": 1.0 if tiempo is not None else None,
            "Fuente del dato": FUENTE_ENTREVISTA, "Calidad dato": CALIDAD_K4}, a.get("actividad"))
        self.punto("Actividades_Carga", f"Actividad nueva: {(a.get('actividad') or '')[:70]}", "Interpretación", "",
                   a.get("motivo") or "Surgió en la entrevista y no estaba en el K4: confirmar que es una actividad del puesto y sus tiempos.",
                   _unir(a.get("descripcion"), nota, sep=" "), a.get("fuente", "Entrevista"))
        horas = calculo.horas_mes(tiempo, 0, eventos, periodo_final, None, 1.0 if tiempo is not None else None, self.dias_mes)
        self.r.horas_mes += horas
        if n is not None and horas == 0:
            self.r.sin_horas.append(a.get("actividad"))

    # -- supuestos y hoja de puntos ----------------------------------------------------------------------------

    def _supuestos(self):
        s = self.supuestos
        if s["meses"]:
            self.punto("Actividades_Carga", "Meses/año activos", "Supuesto", f"{s['meses']} actividad(es)",
                       f"El K4 no trae los meses activos: se usó {MESES_ACTIVOS_POR_DEFECTO} en todas. Ajustar las estacionales.")
        if s["eventual"]:
            self.punto("Responsabilidades", "Frecuencia «Eventual»", "Interpretación", f"{s['eventual']} fila(s)",
                       "«A demanda» y «Por evento» del K4 se registraron como «Eventual», que es lo que ofrece la plantilla.")
        if s["retrabajo"]:
            self.punto("Actividades_Carga", "Retrabajo %", "Interpretación", f"{s['retrabajo']} actividad(es)",
                       "El K4 pide minutos pero se llenó con fracciones (0.1, 0.05): se interpretaron como porcentaje (0.1 = 10 %). Confirmar la unidad.")
        if s["dedicacion_indirecta"]:
            self.punto("Actividades_Carga", "% dedicación personal", "Interpretación", f"{s['dedicacion_indirecta']} actividad(es)",
                       "Con participación indirecta, el % de dedicación se calculó como minutos indirectos ÷ tiempo de la actividad.")
        self.punto("Actividades_Carga", "% dedicación personal", "Supuesto", "",
                   "Sin participación indirecta se usó 100 %: sin ese valor la plantilla calcula 0 horas.")
        self.punto("Capacidad", "Parámetros de capacidad", "Dato faltante", "",
                   "Vacaciones, ausentismo y pausas están en 0 %: el FTE es preliminar hasta que el consultor los complete.")
        if self.r.sin_horas:
            self.punto("Actividades_Carga", "Actividades con 0 horas", "Dato faltante", "; ".join(self.r.sin_horas)[:1200],
                       f"{len(self.r.sin_horas)} actividad(es) quedan con 0 horas por falta de tiempo, volumen o frecuencia válidos.")
        for hoja, filas in self.r.desbordes.items():
            self.punto(hoja, "Filas que no cupieron", "Dato sin destino", _recortar_punto(" | ".join(str(f)[:80] for f in filas)),
                       f"{len(filas)} fila(s) superan la capacidad de la tabla de «{hoja}»; pasarlas manualmente.")
        for aviso in self.k4.avisos:
            self.r.advertencias.append(aviso)

    def _hoja_de_puntos(self):
        puntos = self.r.puntos
        if not puntos:
            return
        hoja = self.paquete.hoja_xml(HOJA_PUNTOS)
        cols = self.plantilla.columnas_de_tabla(HOJA_PUNTOS)
        estilo = self.plantilla.estilo_de_entrada("Actividades_Carga", "G") or "24"
        for i, p in enumerate(puntos, 1):
            fila = PRIMERA_FILA_TABLA + i - 1
            for encabezado, valor in (("ID", f"PV-{i:03d}"), ("Hoja", p["hoja"]), ("Actividad / Campo", p["campo"]), ("Tipo", p["tipo"]),
                                      ("Valor Formato", p["valor_formato"]), ("Valor Reunión", p["valor_reunion"]),
                                      ("Fuente Reunión", p["fuente_reunion"]), ("Qué Validar", p["que_validar"]), ("Estado", "Pendiente")):
                col = cols[clave(encabezado)]
                if valor not in (None, ""):
                    self.poner(HOJA_PUNTOS, f"{col}{fila}", valor, estilo=estilo)
        ultima = max(PRIMERA_FILA_TABLA + len(puntos) - 1, PRIMERA_FILA_TABLA + FILAS_PUNTOS_MINIMAS - 1)
        for fila in range(PRIMERA_FILA_TABLA + len(puntos), ultima + 1):          # filas vacias con el mismo estilo
            for col in cols.values():
                hoja.escribir(f"{col}{fila}", None, estilo=estilo)
        self.paquete.ampliar_tabla(HOJA_PUNTOS, ultima, NOMBRE_TABLA_PUNTOS)
        for encabezado, opciones in (("Tipo", TIPOS_PUNTO), ("Estado", ESTADOS_PUNTO)):
            col = cols[clave(encabezado)]
            hoja.agregar_validacion_lista(f"{col}{PRIMERA_FILA_TABLA}:{col}{ultima}", opciones)


class VerificacionFallida(Exception):
    def __init__(self, errores):
        super().__init__("; ".join(errores[:3]))
        self.errores = errores


def vaciar_k4(ruta_k4, ruta_plantilla, destino, complementos=None, fuentes=()):
    """Lee el K4, llena la plantilla, relee el archivo y lo compara. Si algo no coincide, borra el archivo y lanza
    ``VerificacionFallida``. Devuelve (Resultado, K4, cantidad de celdas verificadas)."""
    import os
    from pathlib import Path

    from .k4 import leer_k4
    from .verificacion import verificar

    k4 = leer_k4(ruta_k4)
    v = Vaciado(k4, ruta_plantilla, complementos, Path(ruta_k4).name, fuentes)
    resultado = v.ejecutar(destino)
    errores = verificar(ruta_plantilla, destino, resultado.escritas, resultado.horas_mes, v.dias_mes)
    if errores:
        if os.path.exists(destino):
            os.unlink(destino)
        raise VerificacionFallida(errores)
    return resultado, k4, len(resultado.escritas)
