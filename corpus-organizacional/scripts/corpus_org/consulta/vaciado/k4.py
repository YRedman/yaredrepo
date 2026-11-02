"""Lee el formulario K4 (levantamiento del puesto) y entrega sus datos por hoja, con la procedencia de cada celda.

Reconoce cada hoja por su nombre y cada columna por su encabezado (no por su posicion), lee tambien las hojas ocultas,
descarta las filas de ejemplo (letra roja), hereda el proceso y el tipo en los grupos de filas, y resuelve las
formulas sencillas (``=(8*60)``) cuando el archivo no trae su valor guardado.
"""

import ast
import operator
import re
from dataclasses import dataclass, field

from ...comun.texto import norm
from .xlsx import Libro, partir_ref

ROJOS = ("FFFF0000", "FFC00000", "00FF0000")
AMARILLO = "FFFFFF00"

# hoja -> (prefijo del nombre normalizado, {campo: (modo, texto del encabezado normalizado)})
# modo: 'empieza' (el encabezado empieza con el texto), 'igual' o 'contiene'.
HOJAS = {
    "inventario": ("1. inventario", {"proceso": ("empieza", "proceso"), "actividad": ("empieza", "actividad / subproceso"),
                                     "tipo": ("empieza", "tipo")}),
    "actividades": ("2. actividades", {
        "actividad": ("empieza", "actividad / subproceso"), "descripcion": ("empieza", "descripcion de la actividad"),
        "recurrencia": ("empieza", "recurrencia"), "tiempo": ("empieza", "tiempo que le toma"),
        "volumen": ("empieza", "volumen"), "periodo": ("empieza", "periodo del volumen"),
        "indirecto": ("empieza", "tiempo de participacion indirecta"), "automatizacion": ("empieza", "nivel de automatizacion"),
        "retrabajo": ("empieza", "tiempo de retrabajo"), "causa": ("empieza", "causa"), "riesgo": ("empieza", "riesgo")}),
    "transicionales": ("2.1 actividades", {
        "actividad": ("empieza", "actividad / subproceso"), "descripcion": ("empieza", "descripcion de la actividad"),
        "transicion": ("empieza", "transicion"), "recurrencia": ("empieza", "recurrencia"),
        "tiempo": ("empieza", "tiempo que le toma"), "volumen": ("empieza", "volumen"),
        "periodo": ("empieza", "periodo del volumen"), "indirecto": ("empieza", "tiempo de participacion indirecta"),
        "automatizacion": ("empieza", "nivel de automatizacion"), "retrabajo": ("empieza", "tiempo de retrabajo"),
        "causa": ("empieza", "causa"), "riesgo": ("empieza", "riesgo")}),
    "entregables": ("3. entregables", {"entregable": ("empieza", "entregables"), "recurrencia": ("empieza", "recurrencia"),
                                       "actividades": ("empieza", "actividades necesarias"),
                                       "puestos": ("empieza", "puestos participantes")}),
    "relaciones": ("4. relaciones", {
        "tipo": ("empieza", "tipo de relacion"), "area": ("empieza", "area / empresa"), "contacto": ("empieza", "puesto o rol"),
        "recibida": ("empieza", "informacion recibida"), "motivo": ("empieza", "motivo de la relacion"),
        "frecuencia": ("empieza", "frecuencia de interaccion"), "resultado": ("empieza", "resultado obtenido"),
        "destino": ("empieza", "area de destino")}),
    "herramientas": ("5. herramientas", {
        "nombre": ("empieza", "nombre de la herramienta"), "tipo": ("empieza", "tipo de herramienta"),
        "uso": ("empieza", "para que se utiliza"), "dominio": ("empieza", "nivel de dominio"),
        "frecuencia": ("empieza", "frecuencia de uso"), "requerido": ("contiene", "requerido o deseable")}),
    "responsabilidades": ("6. responsabilidades", {
        "funcion": ("empieza", "funcion / tarea"), "frecuencia": ("empieza", "frecuencia"),
        "nivel": ("empieza", "nivel de responsabilidad"), "observaciones": ("empieza", "observaciones")}),
    "proposito": ("7. proposito", {
        "proposito": ("empieza", "proposito principal"), "funcion_clave": ("empieza", "funcion clave"),
        "objetivos": ("empieza", "objetivos principales"), "resultados": ("empieza", "resultados esperados")}),
    "general": ("8. informacion", {
        "puesto": ("empieza", "nombre del puesto"), "codigo": ("empieza", "codigo interno"), "area": ("igual", "area"),
        "departamento": ("empieza", "departamento"), "reporta": ("empieza", "reporta directamente"),
        "matricial": ("empieza", "reporta matricialmente"), "personas": ("empieza", "numero de personas"),
        "puestos_cargo": ("empieza", "puestos bajo su cargo"), "ubicacion": ("empieza", "ubicacion")}),
    "competencias": ("9. competencias", {
        "tipo": ("empieza", "tipo de competencia"), "competencia": ("igual", "competencia"),
        "nivel": ("empieza", "nivel requerido"), "observaciones": ("empieza", "observaciones")}),
    "educacion": ("9. educacion", {"nivel": ("empieza", "nivel academico"), "area": ("empieza", "area de formacion"),
                                    "certificaciones": ("empieza", "certificaciones")}),
    "condiciones": ("10. condiciones", {
        "horario": ("empieza", "horario de trabajo"), "modalidad": ("igual", "modalidad"),
        "equipos": ("empieza", "equipos utilizados"), "observaciones": ("empieza", "observaciones")}),
    "optimizacion": ("11. optimizacion", {"actividad": ("empieza", "actividad / subproceso"),
                                           "sugerencia": ("empieza", "sugerencia"), "ahorro": ("empieza", "tiempo estimado de ahorro")}),
}
# campo sin el cual una fila no es un registro de la tabla (las notas y los calculos auxiliares que la gente deja debajo
# de la tabla no tienen actividad, funcion, etc.)
CLAVES = {"inventario": ("actividad",), "actividades": ("actividad",), "transicionales": ("actividad",),
          "entregables": ("entregable",), "relaciones": ("area", "contacto"), "herramientas": ("nombre",),
          "responsabilidades": ("funcion",), "proposito": ("proposito", "funcion_clave", "objetivos", "resultados"),
          "general": ("puesto", "codigo"), "competencias": ("competencia",), "educacion": ("nivel", "area", "certificaciones"),
          "condiciones": ("horario", "modalidad", "equipos", "observaciones"), "optimizacion": ("actividad", "sugerencia")}
FILAS_BUSCANDO_ENCABEZADO = 14
CAMPOS_COLABORADOR = {"nombre": "nombre", "apellido": "apellido", "correo": "correo", "telefono": "numero de telefono"}


@dataclass
class Fila:
    hoja: str                       # nombre de la hoja en el K4
    numero: int
    celdas: dict = field(default_factory=dict)      # campo -> Celda

    def celda(self, campo):
        return self.celdas.get(campo)

    def valor(self, campo):
        c = self.celdas.get(campo)
        return None if c is None or c.vacia else c.valor

    def texto(self, campo):
        """Texto del campo (None si esta vacio); los numeros enteros sin '.0'."""
        v = self.valor(campo)
        if v is None:
            return None
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v).replace("\xa0", " ").strip() or None

    def origen(self, campo):
        return origen_de(self.celdas.get(campo))

    def referencia(self, campo=None):
        c = self.celdas.get(campo) if campo else None
        return f"{self.hoja}!{c.ref if c else self.numero}"


@dataclass
class K4:
    colaborador: dict = field(default_factory=dict)
    tablas: dict = field(default_factory=dict)        # clave -> [Fila]
    exposicion: list = field(default_factory=list)    # textos del bloque «Exposición del puesto…»
    avisos: list = field(default_factory=list)
    hojas_ocultas_leidas: list = field(default_factory=list)
    hojas_faltantes: list = field(default_factory=list)

    def filas(self, clave):
        return self.tablas.get(clave, [])


def origen_de(celda):
    """'k4' (lo escribio el ocupante), 'entrevista' (complemento de la entrevista) o 'propuesto' (propuesta por validar)."""
    if celda is None:
        return "k4"
    nota = norm(celda.nota or "")
    if nota.startswith(("requisito o condicion propuesta", "propuesta", "propuesto")):
        return "propuesto"
    if nota.startswith(("complementado", "fuente: minuta", "la entrevista", "se complemento")) or celda.color_relleno == AMARILLO:
        return "entrevista"
    return "k4"


def es_rojo(celda):
    return celda is not None and celda.color_letra in ROJOS


_OPERADORES = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
               ast.USub: operator.neg, ast.UAdd: operator.pos}


def evaluar_aritmetica(formula):
    """Valor de una formula de solo numeros y + - * / ( ) (p. ej. '(8*60)'); None si es otra cosa."""
    texto = formula.lstrip("=").strip()
    if not texto or not re.fullmatch(r"[\d\s.+\-*/()]+", texto):
        return None

    def calcular(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPERADORES:
            return _OPERADORES[type(n.op)](calcular(n.left), calcular(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPERADORES:
            return _OPERADORES[type(n.op)](calcular(n.operand))
        raise ValueError
    try:
        return float(calcular(ast.parse(texto, mode="eval").body))
    except (ValueError, SyntaxError, ZeroDivisionError):
        return None


def _hoja_de(libro, prefijo):
    for h in libro.hojas:
        if norm(h.nombre).startswith(prefijo):
            return h
    return None


def _columnas(hoja, campos):
    """(fila del encabezado, {campo: columna}) buscando la fila donde mas encabezados esperados aparecen."""
    mejor = (0, {}, 0)
    for n in range(1, FILAS_BUSCANDO_ENCABEZADO + 1):
        encontrados = {}
        for col, c in hoja.fila(n).items():
            if c.vacia or not isinstance(c.valor, str):
                continue
            t = norm(c.valor)
            for campo, (modo, clave) in campos.items():
                if campo in encontrados:
                    continue
                if (modo == "empieza" and t.startswith(clave)) or (modo == "igual" and t == clave) or (modo == "contiene" and clave in t):
                    encontrados[campo] = col
                    break
        if len(encontrados) > len(mejor[1]):
            mejor = (n, encontrados, len(encontrados))
    return mejor[0], mejor[1]


def _valor_calculado(celda):
    if celda.formula and celda.valor is None:
        return evaluar_aritmetica(celda.formula)
    return celda.valor


def _leer_tabla(hoja, campos, claves, avisos, hasta=None):
    fila_enc, columnas = _columnas(hoja, campos)
    if not columnas:
        avisos.append(f"No encontré los encabezados de «{hoja.nombre}»: se omite.")
        return []
    ejemplos, sin_clave = 0, []
    filas = []
    for n in hoja.filas():
        if n <= fila_enc or (hasta is not None and n >= hasta):
            continue
        celdas = {}
        for campo, col in columnas.items():
            c = hoja.celda(f"{col}{n}")
            if c is not None and c.formula and c.valor is None:       # formula sin valor guardado: se resuelve si es aritmetica
                c = _con_valor(c, _valor_calculado(c))
            valor = hoja.valor_combinado(f"{col}{n}") if c is None or c.vacia else c.valor
            if c is None and valor is None:
                continue
            if c is None or c.vacia:
                # celda combinada: se toma el valor de la superior izquierda, con su procedencia
                origen = hoja.celda(hoja._origen_combinada.get(f"{col}{n}", ""))
                if valor is None or origen is None:
                    continue
                c = origen
            celdas[campo] = c
        con_dato = {k: c for k, c in celdas.items() if not c.vacia}
        if not con_dato:
            continue
        if all(es_rojo(c) for c in con_dato.values()):
            ejemplos += 1
            continue
        if not any(k in con_dato for k in claves):
            sin_clave.append(n)
            continue
        filas.append(Fila(hoja.nombre, n, celdas))
    if ejemplos:
        avisos.append(f"«{hoja.nombre}»: {ejemplos} fila(s) de ejemplo en rojo descartadas.")
    if sin_clave:
        avisos.append(f"«{hoja.nombre}»: {len(sin_clave)} fila(s) con datos pero sin {' ni '.join(claves)} (notas o cálculos "
                      f"auxiliares debajo de la tabla; filas {sin_clave[0]} a {sin_clave[-1]}) no se tomaron como registros.")
    return filas


def _con_valor(celda, valor):
    if valor is celda.valor:
        return celda
    copia = type(celda)(**{**celda.__dict__, "valor": valor})
    return copia


def _heredar(filas, campos):
    """Los grupos de filas escriben el proceso (y su tipo) solo en la primera: las siguientes lo heredan."""
    previo = {}
    for f in filas:
        for campo in campos:
            c = f.celdas.get(campo)
            if c is not None and not c.vacia:
                previo[campo] = c
            elif campo in previo and (f.valor("actividad") is not None):
                f.celdas[campo] = previo[campo]


def _colaborador(libro):
    hoja = _hoja_de(libro, "instrucciones")
    datos = {}
    if hoja is None:
        return datos
    for ref, c in hoja.celdas.items():
        if isinstance(c.valor, str):
            t = norm(c.valor).rstrip(":").strip()
            col, fila = partir_ref(ref)
            for clave, rotulo in CAMPOS_COLABORADOR.items():
                if t.startswith(rotulo) and clave not in datos:
                    siguiente = hoja.celda(f"{chr(ord(col) + 1)}{fila}")
                    if siguiente is not None and not siguiente.vacia:
                        datos[clave] = str(siguiente.valor).strip()
    return datos


def _fila_exposicion(hoja):
    """Fila del rotulo «Exposición del puesto a riesgos laborales y disponibilidad» (None si no esta)."""
    for n in hoja.filas():
        c = hoja.celda(f"B{n}")
        if c is not None and isinstance(c.valor, str) and norm(c.valor).startswith("exposicion del puesto"):
            return n
    return None


def _exposicion(hoja, desde):
    """Textos que siguen al rotulo de exposicion y disponibilidad."""
    textos = []
    for n in hoja.filas():
        c = hoja.celda(f"B{n}")
        if n > desde and c is not None and not c.vacia and not es_rojo(c) and isinstance(c.valor, str):
            textos.append(c.valor.strip())
    return textos


def leer_k4(ruta):
    libro = Libro(ruta)
    k4 = K4(colaborador=_colaborador(libro))
    for clave, (prefijo, campos) in HOJAS.items():
        hoja = _hoja_de(libro, prefijo)
        if hoja is None:
            k4.hojas_faltantes.append(prefijo)
            continue
        if hoja.oculta:
            k4.hojas_ocultas_leidas.append(hoja.nombre)
        fila_exposicion = _fila_exposicion(hoja) if clave == "condiciones" else None
        filas = _leer_tabla(hoja, campos, CLAVES[clave], k4.avisos, hasta=fila_exposicion)
        if clave == "inventario":
            _heredar(filas, ("proceso", "tipo"))
        k4.tablas[clave] = filas
        if fila_exposicion is not None:
            k4.exposicion = _exposicion(hoja, fila_exposicion)
    if k4.hojas_ocultas_leidas:
        k4.avisos.append("Hojas ocultas del K4 que sí se leyeron: " + ", ".join(k4.hojas_ocultas_leidas) + ".")
    return k4
