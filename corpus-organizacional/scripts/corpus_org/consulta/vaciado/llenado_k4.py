"""Llena el K4 en blanco con los datos de una entrevista sin tocar la estructura del formulario.

El agente entrega los datos (JSON); este modulo los escribe en las celdas de respuesta de cada tabla, debajo de su fila gris de
encabezados, y nada mas: los encabezados, las combinadas, los bordes, los anchos, las listas desplegables, los comentarios y las
formulas quedan como en el archivo base. Todo texto en rojo (los ejemplos y las notas «la informacion en rojo es un ejemplo») se
borra; los datos se escriben en negro y lo pendiente («VALIDAR: …») en morado.
"""

import re
from dataclasses import dataclass, field

from ...comun.texto import norm
from .estilos import MORADO, NEGRO, Estilos
from .hoja_xml import CeldaConFormula, RE_RANGO
from .k4 import CAMPOS_COLABORADOR, HOJAS, ROJOS, _columnas, _fila_exposicion, _hoja_de
from .paquete import Paquete
from .valores import PREFIJO_VALIDAR, es_validar
from .xlsx import columna_a_numero, numero_a_columna, partir_ref

HOJA_INSTRUCCIONES = "instrucciones"
CLAVES_ESPECIALES = ("colaborador", "exposicion")
UN_SOLO_REGISTRO = {"general"}
CON_VALIDAR_AUTOMATICO = {"general", "herramientas"}       # un campo requerido sin dato queda como «VALIDAR: …», no vacio
ETIQUETAS_VALIDAR = {("general", "matricial"): "VALIDAR: confirmar si existe reporte matricial o regional",
                     ("general", "ubicacion"): "VALIDAR: ubicación o sucursal"}


class DatosInvalidos(ValueError):
    def __init__(self, errores):
        super().__init__("; ".join(errores[:3]))
        self.errores = list(errores)


@dataclass
class Tabla:
    clave: str
    hoja: str
    fila_encabezado: int
    columnas: dict                  # campo -> letra
    encabezados: dict               # campo -> texto del encabezado
    inicio: int                     # primera fila de respuesta
    fin_marco: int                  # ultima fila con el formato de la tabla (inicio - 1 si no hay ninguna)
    tope: int = 0                   # ultima fila que se puede usar sin pasar sobre otro contenido (0 = sin limite)

    @property
    def capacidad(self):
        return (self.tope - self.inicio + 1) if self.tope else None


@dataclass
class ResultadoK4:
    destino: str = ""
    escritas: dict = field(default_factory=dict)              # (hoja, ref) -> valor
    colores: dict = field(default_factory=dict)               # (hoja, ref) -> color de letra esperado
    borradas: dict = field(default_factory=dict)              # (hoja, ref) -> texto rojo que se quito
    por_hoja: dict = field(default_factory=dict)              # hoja -> celdas escritas
    filas: dict = field(default_factory=dict)                 # clave -> registros escritos
    validar: list = field(default_factory=list)               # (hoja, ref, texto)
    advertencias: list = field(default_factory=list)
    tablas: dict = field(default_factory=dict)                # clave -> Tabla
    combinadas_quitadas: dict = field(default_factory=dict)   # hoja -> [rangos]
    combinadas_nuevas: dict = field(default_factory=dict)


def _etiqueta(texto):
    """Encabezado sin la aclaracion entre parentesis ni los signos de pregunta."""
    texto = re.sub(r"\(.*", "", texto or "").replace("¿", "").replace("?", "").strip(" :\n")
    return " ".join(texto.split())


def _rango(ref_o_rango):
    a, _, b = ref_o_rango.partition(":")
    (c1, f1), (c2, f2) = partir_ref(a), partir_ref(b or a)
    return columna_a_numero(c1), f1, columna_a_numero(c2), f2


def _interseca(rango, columnas, desde, hasta):
    c1, f1, c2, f2 = _rango(rango)
    return f2 >= desde and f1 <= hasta and any(c1 <= columna_a_numero(c) <= c2 for c in columnas)


def listas_de_la_hoja(texto_hoja):
    """{columna: [opciones]} de las listas desplegables con opciones escritas en la hoja (las de un rango con nombre no)."""
    listas = {}
    for m in re.finditer(r'<dataValidation\b([^>]*)>\s*<formula1>"([^"]*)"</formula1>', texto_hoja):
        sqref = re.search(r'\bsqref="([^"]*)"', m.group(1))
        if sqref and 'type="list"' in m.group(1):
            for ficha in sqref.group(1).split():
                r = RE_RANGO.match(ficha)
                if r:
                    listas.setdefault(r.group(1), [o.replace("&amp;", "&") for o in m.group(2).split(",")])
    return listas


class LlenadoK4:
    def __init__(self, ruta_base, datos):
        self.paquete = Paquete(ruta_base)
        self.paquete.conservar_valores_calculados()
        self.libro = self.paquete.libro
        self.estilos = Estilos(self.paquete.partes["xl/styles.xml"].decode("utf-8"))
        self.datos = datos or {}
        self.r = ResultadoK4()
        self._listas = {}
        self._errores = []

    # -- analisis de la base -----------------------------------------------------------------------------------

    def _es_rojo(self, celda):
        return celda is not None and celda.color_letra in ROJOS

    def _con_dato(self, celda):
        return celda is not None and not celda.vacia and not self._es_rojo(celda)

    def analizar(self, clave):
        """Donde estan los encabezados, las columnas y las filas de respuesta de una tabla; None si la hoja no esta."""
        prefijo, campos = HOJAS[clave]
        hoja = _hoja_de(self.libro, prefijo)
        if hoja is None:
            return None
        fila_enc, columnas = _columnas(hoja, campos)
        faltan = [c for c in campos if c not in columnas]
        if faltan:
            raise DatosInvalidos([f"«{hoja.nombre}»: en la base no encuentro la fila de encabezados ({', '.join(faltan)}). "
                                  "Usa el archivo base vacío original del usuario, sin cambios."])
        cols = list(columnas.values())
        encabezados = {campo: str(hoja.valor(f"{col}{fila_enc}")) for campo, col in columnas.items()}
        inicio, fin, tope = fila_enc + 1, fila_enc, 0
        continuo = True
        for n in range(inicio, (max(hoja.filas()) if hoja.filas() else fila_enc) + 1):
            celdas = [hoja.celda(f"{c}{n}") for c in cols]
            if any(self._con_dato(c) for c in celdas):
                tope = n - 1
                break
            estilados = sum(1 for c in celdas if c is not None and c.estilo)
            if continuo and estilados * 2 >= len(cols):
                fin = n
            else:
                continuo = False
        t = Tabla(clave, hoja.nombre, fila_enc, columnas, encabezados, inicio, fin, tope)
        if t.capacidad is not None and t.capacidad <= 0:
            raise DatosInvalidos([f"«{hoja.nombre}»: la base ya tiene datos bajo los encabezados; usa el archivo base vacío."])
        return t

    # -- escritura ---------------------------------------------------------------------------------------------

    def _hoja_xml(self, nombre):
        return self.paquete.hoja_xml(nombre)

    def _estilo_para(self, hoja, ref_modelo, color):
        base = self._hoja_xml(hoja).estilo(ref_modelo)
        xf = int(base) if base not in (None, "") else 0
        if color == NEGRO and not self.estilos.es_rojo(xf):
            return xf
        return self.estilos.con_color(xf, color)

    def _poner(self, hoja, ref, valor, ref_modelo=None, referencia=""):
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            return False
        if isinstance(valor, bool) or not isinstance(valor, (str, int, float)):
            self._errores.append(f"{hoja}!{ref}: el valor debe ser texto o número ({referencia}).")
            return False
        color = MORADO if es_validar(valor) else NEGRO
        estilo = self._estilo_para(hoja, ref_modelo or ref, color)
        try:
            if self._hoja_xml(hoja).escribir(ref, valor, estilo=str(estilo), forzar=True):
                self.r.advertencias.append(f"{hoja}!{ref}: el texto superaba el límite de Excel y se recortó.")
        except CeldaConFormula:
            self._errores.append(f"{hoja}!{ref}: tiene fórmula; no se escribe.")
            return False
        self.r.escritas[(hoja, ref)] = valor
        self.r.colores[(hoja, ref)] = color
        self.r.por_hoja[hoja] = self.r.por_hoja.get(hoja, 0) + 1
        if color == MORADO:
            self.r.validar.append((hoja, ref, valor))
        return True

    def borrar_texto_rojo(self):
        """Todo texto en rojo (ejemplos de las tablas y notas «la informacion en rojo es un ejemplo») se quita; el formato queda."""
        for h in self.libro.hojas:
            for ref, c in sorted(h.celdas.items(), key=lambda kv: (partir_ref(kv[0])[1], columna_a_numero(partir_ref(kv[0])[0]))):
                if self._es_rojo(c) and not c.vacia and not c.formula:
                    self._hoja_xml(h.nombre).escribir(ref, None)
                    self.r.borradas[(h.nombre, ref)] = c.valor

    # -- tablas ------------------------------------------------------------------------------------------------

    def _validar_registros(self, t, registros):
        prefijo, campos = HOJAS[t.clave]
        if not isinstance(registros, list) or any(not isinstance(x, dict) for x in registros):
            self._errores.append(f"«{t.clave}»: debe ser una lista de registros (objetos con los campos {', '.join(campos)}).")
            return []
        for i, reg in enumerate(registros, 1):
            for campo in reg:
                if campo not in campos:
                    self._errores.append(f"«{t.clave}» registro {i}: el campo «{campo}» no existe (campos: {', '.join(campos)}).")
        if t.clave in UN_SOLO_REGISTRO and len(registros) > 1:
            self._errores.append(f"«{t.clave}» (hoja «{t.hoja}») es una tabla horizontal de un solo registro: recibí {len(registros)}.")
        if t.capacidad is not None and len(registros) > t.capacidad:
            self._errores.append(f"«{t.hoja}» admite {t.capacidad} fila(s) sin pasar sobre otro contenido del formulario y recibí {len(registros)}: "
                                 "reparte el resto en la entrevista o consulta al usuario.")
        return registros

    def _normalizar_listas(self, t, registros):
        """Los campos con lista desplegable solo aceptan sus opciones (se corrige mayusculas y acentos)."""
        if t.hoja not in self._listas:
            self._listas[t.hoja] = listas_de_la_hoja(self.paquete.partes[self.libro.hoja(t.hoja).parte].decode("utf-8"))
        listas = self._listas[t.hoja]
        for i, reg in enumerate(registros, 1):
            for campo, valor in list(reg.items()):
                opciones = listas.get(t.columnas.get(campo))
                if not opciones or valor in (None, "") or es_validar(valor):
                    continue
                coincide = next((o for o in opciones if norm(o) == norm(str(valor))), None)
                if coincide is None:
                    self._errores.append(f"«{t.hoja}» registro {i}: «{valor}» no está en la lista de «{_etiqueta(t.encabezados[campo])}» "
                                         f"({', '.join(opciones)}).")
                else:
                    reg[campo] = coincide

    def _completar_validar(self, t, registros):
        for reg in registros:
            for campo in HOJAS[t.clave][1]:
                if reg.get(campo) in (None, ""):
                    reg[campo] = ETIQUETAS_VALIDAR.get((t.clave, campo)) or f"{PREFIJO_VALIDAR}: {_etiqueta(t.encabezados[campo]).lower()}"
                    self.r.advertencias.append(f"«{t.hoja}»: sin dato de «{_etiqueta(t.encabezados[campo])}»; se escribió «{reg[campo]}».")

    def _fila_modelo(self, t, fila, n_registros, indice):
        """Fila del formulario de la que se copia el formato de la fila ``fila`` (la propia dentro del marco; una intermedia fuera)."""
        largo = t.fin_marco - t.inicio + 1
        intermedia = t.inicio + 1 if largo >= 3 else t.inicio
        if largo <= 0:
            return None
        if n_registros <= largo:
            return fila
        if indice == n_registros - 1:
            return t.fin_marco                                           # el borde inferior pasa a la ultima fila
        return fila if fila < t.fin_marco else intermedia

    def _escribir_tabla(self, t, registros):
        h = self._hoja_xml(t.hoja)
        n = len(registros)
        ultima = t.inicio + n - 1
        if t.clave == "inventario":
            registros = self._agrupar_inventario(t, registros)
        else:
            self._preparar_combinadas(t, n)
        for i, reg in enumerate(registros):
            fila = t.inicio + i
            modelo = self._fila_modelo(t, fila, n, i)
            for campo, col in t.columnas.items():
                valor = reg.get(campo)
                if self._interior_de_combinada(t.hoja, f"{col}{fila}"):
                    continue
                ref_modelo = f"{col}{modelo}" if modelo else f"{col}{fila}"
                self._poner(t.hoja, f"{col}{fila}", valor, ref_modelo, f"{t.clave} #{i + 1} {campo}")
            h.quitar_alto_fijo(fila)
        if n and ultima > t.fin_marco >= t.inicio:
            h.ampliar_validaciones(set(t.columnas.values()), t.fin_marco, ultima)
        self.r.filas[t.clave] = n

    def _interior_de_combinada(self, hoja, ref):
        """True si ``ref`` esta dentro de una combinada sin ser su celda superior izquierda (solo ahi no se puede escribir)."""
        col, fila = partir_ref(ref)
        k = columna_a_numero(col)
        for rango in self._hoja_xml(hoja).combinadas():
            c1, f1, c2, f2 = _rango(rango)
            if c1 <= k <= c2 and f1 <= fila <= f2 and (k, fila) != (c1, f1):
                return True
        return False

    def _combinadas_del_cuerpo(self, t, ultima):
        """Combinadas bajo los encabezados, dentro de las columnas de la tabla, que estorban a las filas que se escriben."""
        cols = list(t.columnas.values())
        return [m for m in self._hoja_xml(t.hoja).combinadas()
                if _rango(m)[1] > t.fila_encabezado and _interseca(m, cols, t.inicio, max(ultima, t.fin_marco))]

    def _preparar_combinadas(self, t, n, nuevas=()):
        ultima = t.inicio + n - 1
        quitar = self._combinadas_del_cuerpo(t, ultima) if n else []
        if quitar or nuevas:
            self._hoja_xml(t.hoja).cambiar_combinadas(quitar, nuevas)
            self.r.combinadas_quitadas.setdefault(t.hoja, []).extend(quitar)
            self.r.combinadas_nuevas.setdefault(t.hoja, []).extend(nuevas)

    def _agrupar_inventario(self, t, registros):
        """El proceso (y su tipo) se escribe en la primera fila de cada grupo y la celda se combina sobre sus actividades."""
        grupos, actual = [], None
        for i, reg in enumerate(registros):
            proceso = (reg.get("proceso") or "").strip() if isinstance(reg.get("proceso"), str) else reg.get("proceso")
            if actual is None or (proceso and norm(str(proceso)) != actual["clave"]):
                actual = {"clave": norm(str(proceso)) if proceso else "", "filas": []}
                grupos.append(actual)
            actual["filas"].append(i)
        salida = [dict(r) for r in registros]
        nuevas = []
        for g in grupos:
            primera, ultima = g["filas"][0], g["filas"][-1]
            tipos = {norm(str(registros[i].get("tipo"))) for i in g["filas"] if registros[i].get("tipo")}
            if len(tipos) > 1:
                self.r.advertencias.append(f"Inventario: el proceso «{registros[primera].get('proceso')}» tiene actividades con tipos distintos; "
                                           "se usó el de la primera.")
            tipo = next((registros[i].get("tipo") for i in g["filas"] if registros[i].get("tipo")), None)
            for i in g["filas"]:
                salida[i]["proceso"] = registros[primera].get("proceso") if i == primera else None
                salida[i]["tipo"] = tipo if i == primera else None
            if len(g["filas"]) > 1:
                for campo in ("proceso", "tipo"):
                    col = t.columnas[campo]
                    nuevas.append(f"{col}{t.inicio + primera}:{col}{t.inicio + ultima}")
        self._preparar_combinadas(t, len(registros), nuevas)
        return salida

    def tabla(self, clave, registros):
        t = self.analizar(clave)
        if t is None:
            self._errores.append(f"El K4 base no tiene la hoja «{HOJAS[clave][0]}…».")
            return
        self.r.tablas[clave] = t
        registros = self._validar_registros(t, registros)
        if clave in CON_VALIDAR_AUTOMATICO and registros:
            self._completar_validar(t, registros)
        self._normalizar_listas(t, registros)
        self._validar_actividades(t, registros)
        if not self._errores:
            self._escribir_tabla(t, registros)

    def _validar_actividades(self, t, registros):
        """Las actividades de las hojas 2, 2.1 y 11 salen de una lista que viene del inventario: deben estar en el inventario."""
        if t.clave not in ("actividades", "transicionales", "optimizacion"):
            return
        inventario = self.datos.get("inventario")
        if not inventario:
            self.r.advertencias.append(f"«{t.hoja}»: no se recibió el inventario; no se comprobó que sus actividades estén en la hoja 1.")
            return
        conocidas = {norm(str(r.get("actividad"))) for r in inventario if isinstance(r, dict) and r.get("actividad")}
        for i, reg in enumerate(registros, 1):
            a = reg.get("actividad")
            if a and not es_validar(a) and norm(str(a)) not in conocidas:
                self._errores.append(f"«{t.hoja}» registro {i}: la actividad «{a}» no está en el inventario (hoja 1); agrégala primero allí.")

    # -- colaborador y exposicion --------------------------------------------------------------------------------

    def colaborador(self, datos):
        hoja = _hoja_de(self.libro, HOJA_INSTRUCCIONES)
        if hoja is None:
            self.r.advertencias.append("El K4 base no tiene la hoja «Instrucciones»: no se escribieron los datos del colaborador.")
            return
        for clave, valor in datos.items():
            if clave not in CAMPOS_COLABORADOR:
                self._errores.append(f"colaborador: el campo «{clave}» no existe (campos: {', '.join(CAMPOS_COLABORADOR)}).")
                continue
            rotulo = CAMPOS_COLABORADOR[clave]
            ref_rotulo = next((ref for ref, c in hoja.celdas.items() if isinstance(c.valor, str)
                               and norm(c.valor).rstrip(": ").startswith(rotulo)), None)
            if ref_rotulo is None:
                self.r.advertencias.append(f"Instrucciones: no encuentro el rótulo del {clave}.")
                continue
            col, fila = partir_ref(ref_rotulo)
            self._poner(hoja.nombre, f"{numero_a_columna(columna_a_numero(col) + 1)}{fila}", valor, referencia=f"colaborador {clave}")

    def exposicion(self, textos):
        hoja = _hoja_de(self.libro, HOJAS["condiciones"][0])
        fila_rotulo = _fila_exposicion(hoja) if hoja else None
        if hoja is None or fila_rotulo is None:
            self._errores.append("El K4 base no trae el bloque «Exposición del puesto a riesgos laborales y disponibilidad».")
            return
        h = self._hoja_xml(hoja.nombre)
        filas = []
        n = fila_rotulo + 1
        while hoja.celda(f"B{n}") is not None and any(_rango(m)[:2] == (2, n) for m in h.combinadas()):
            filas.append(n)
            n += 1
        if not isinstance(textos, list) or len(textos) > len(filas):
            self._errores.append(f"«{hoja.nombre}»: el bloque de exposición admite {len(filas)} texto(s).")
            return
        for fila, texto in zip(filas, textos):
            self._poner(hoja.nombre, f"B{fila}", texto, referencia="exposicion")
            h.quitar_alto_fijo(fila)
        self.r.filas["exposicion"] = len(textos)

    # -- orquestacion ------------------------------------------------------------------------------------------

    def ejecutar(self, destino):
        desconocidas = [k for k in self.datos if k not in HOJAS and k not in CLAVES_ESPECIALES]
        if desconocidas:
            raise DatosInvalidos([f"Claves desconocidas en los datos: {', '.join(desconocidas)}. Válidas: "
                                  f"{', '.join(list(HOJAS) + list(CLAVES_ESPECIALES))}."])
        self.borrar_texto_rojo()
        if "colaborador" in self.datos:
            self.colaborador(self.datos["colaborador"] or {})
        for clave in HOJAS:
            if clave in self.datos:
                self.tabla(clave, self.datos[clave])
                continue
            t = self.analizar(clave)
            if t is not None:
                self.r.tablas[clave] = t
                self.r.advertencias.append(f"Sin datos para «{t.hoja}»: quedó sin respuestas.")
        if "exposicion" in self.datos:
            self.exposicion(self.datos["exposicion"])
        for clave in ("general", "herramientas"):
            if clave not in self.datos:
                self.r.advertencias.append(f"No se recibió «{clave}»: la hoja «{HOJAS[clave][0]}…» quedó sin respuestas "
                                           "(un campo requerido no debería quedar vacío: usa «VALIDAR: …»).")
        if self._errores:
            raise DatosInvalidos(self._errores)
        if self.estilos.modificado:
            self.paquete.reemplazar_parte("xl/styles.xml", self.estilos.texto())
        self.paquete.guardar(destino)
        self.r.destino = str(destino)
        return self.r


def estructura_de(ruta_base):
    """Lineas que describen donde se escribe en cada hoja del K4 base (para que el agente arme los datos)."""
    llenado = LlenadoK4(ruta_base, {})
    lineas = []
    for clave, (prefijo, campos) in HOJAS.items():
        try:
            t = llenado.analizar(clave)
        except DatosInvalidos as e:
            lineas.append(f"- {clave}: {e.errores[0]}")
            continue
        if t is None:
            lineas.append(f"- {clave}: la hoja «{prefijo}…» no está en el archivo.")
            continue
        capacidad = "un solo registro" if clave in UN_SOLO_REGISTRO else (f"{t.capacidad} fila(s)" if t.capacidad else "sin límite (se agregan filas)")
        lineas.append(f"- {clave} · hoja «{t.hoja}» · encabezados en la fila {t.fila_encabezado}, respuestas desde la fila {t.inicio} · {capacidad}")
        lineas.append("    campos: " + "; ".join(f"{c} = «{_etiqueta(t.encabezados[c])}» (col. {t.columnas[c]})" for c in campos))
        listas = listas_de_la_hoja(llenado.paquete.partes[llenado.libro.hoja(t.hoja).parte].decode("utf-8"))
        for campo in campos:
            if t.columnas[campo] in listas:
                lineas.append(f"    valores de {campo}: {', '.join(listas[t.columnas[campo]])}")
    return lineas


def llenar_k4(ruta_base, datos, destino):
    """Llena el K4, relee el archivo y lo compara con la base. Si algo no coincide, borra la salida y lanza
    ``VerificacionFallida``. Devuelve el ``ResultadoK4``."""
    from pathlib import Path

    from .metodologia import VerificacionFallida
    from .verificacion_k4 import verificar_k4

    resultado = LlenadoK4(ruta_base, datos).ejecutar(destino)
    errores = verificar_k4(ruta_base, destino, resultado)
    if errores:
        Path(destino).unlink(missing_ok=True)
        raise VerificacionFallida(errores)
    return resultado
