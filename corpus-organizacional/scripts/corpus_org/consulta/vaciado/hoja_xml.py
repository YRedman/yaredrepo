"""Edicion de una hoja de Excel directamente en su XML: cambia solo las celdas que se le piden.

No se reserializa el XML (eso cambiaria prefijos de espacios de nombres y perderia extensiones como las listas
desplegables x14): se localizan las filas y celdas por texto y se reemplazan solo las que cambian.
"""

import re
from xml.sax.saxutils import escape

from .xlsx import columna_a_numero, numero_a_columna, partir_ref

RE_FILA = re.compile(r"<row\b([^>]*?)(/>|>(.*?)</row>)", re.S)
RE_CELDA = re.compile(r"<c\b([^>]*?)(/>|>(.*?)</c>)", re.S)
RE_ATRIBUTO = re.compile(r'([\w:]+)="([^"]*)"')
RE_COMBINADAS = re.compile(r"<mergeCells\b[^>]*?(?:/>|>.*?</mergeCells>)", re.S)
RE_RANGO = re.compile(r"^([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?$")
RE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
LIMITE_TEXTO = 32000


class CeldaConFormula(ValueError):
    """Se intento escribir en una celda que tiene formula."""


def limpiar_texto(texto):
    texto = RE_CONTROL.sub("", str(texto)).replace("\r\n", "\n").replace("\r", "\n")
    return texto


class HojaXml:
    def __init__(self, texto):
        self._texto = texto
        self._filas = {}                 # numero -> [atributos, {columna: xml de la celda}]
        self.modificada = False
        self._separar()

    # -- lectura / serializacion -------------------------------------------------------------------------------

    def _separar(self):
        m = re.search(r"<sheetData\b[^>]*?>(.*?)</sheetData>", self._texto, re.S)
        self._cuerpo = m.group(1) if m else ""
        self._inicio, self._fin = (m.start(1), m.end(1)) if m else (None, None)
        for f in RE_FILA.finditer(self._cuerpo):
            atributos = dict(RE_ATRIBUTO.findall(f.group(1)))
            celdas = {}
            for c in RE_CELDA.finditer(f.group(3) or ""):
                ref = dict(RE_ATRIBUTO.findall(c.group(1)))["r"]
                celdas[columna_a_numero(partir_ref(ref)[0])] = c.group(0)
            self._filas[int(atributos["r"])] = [f.group(1), celdas]

    def texto(self):
        """El XML de la hoja con los cambios."""
        if not self.modificada:
            return self._texto
        filas = []
        for n in sorted(self._filas):
            atributos, celdas = self._filas[n]
            filas.append(f"<row{atributos}>" + "".join(celdas[k] for k in sorted(celdas)) + "</row>"
                         if celdas else f"<row{atributos}/>")
        nuevo = self._texto[:self._inicio] + "".join(filas) + self._texto[self._fin:]
        return self._actualizar_dimension(nuevo)

    def _actualizar_dimension(self, texto):
        columnas = [k for _, (_, celdas) in self._filas.items() for k in celdas]
        if not columnas or not self._filas:
            return texto
        ref = f"{numero_a_columna(min(columnas))}{min(self._filas)}:{numero_a_columna(max(columnas))}{max(self._filas)}"
        return re.sub(r'<dimension ref="[^"]*"/>', f'<dimension ref="{ref}"/>', texto, count=1)

    # -- consulta ----------------------------------------------------------------------------------------------

    def xml_celda(self, ref):
        col, fila = partir_ref(ref)
        f = self._filas.get(fila)
        return None if f is None else f[1].get(columna_a_numero(col))

    def estilo(self, ref):
        xml = self.xml_celda(ref)
        if xml is None:
            return None
        return dict(RE_ATRIBUTO.findall(RE_CELDA.match(xml).group(1))).get("s")

    def ultima_fila(self):
        return max(self._filas) if self._filas else 0

    # -- escritura ---------------------------------------------------------------------------------------------

    def escribir(self, ref, valor, estilo=None, forzar=False):
        """Escribe un texto o un numero en ``ref`` conservando el estilo de la celda. Devuelve True si el texto se recorto.

        Rechaza las celdas con formula. ``estilo`` se usa solo si la celda no existia, salvo con ``forzar`` (el K4 cambia
        el color de la letra de la celda de respuesta).
        """
        col, fila = partir_ref(ref)
        k = columna_a_numero(col)
        f = self._filas.get(fila)
        if f is None:
            f = self._filas[fila] = [f' r="{fila}"', {}]
        existente = f[1].get(k)
        if existente is not None and "<f" in existente:
            raise CeldaConFormula(ref)
        s = estilo
        if existente is not None and not (forzar and estilo is not None):
            s = dict(RE_ATRIBUTO.findall(RE_CELDA.match(existente).group(1))).get("s", estilo)
        atributos = f' r="{ref}"' + (f' s="{s}"' if s not in (None, "") else "")
        recortado = False
        if valor is None or valor == "":
            xml = f"<c{atributos}/>"
        elif isinstance(valor, bool):
            xml = f'<c{atributos} t="b"><v>{int(valor)}</v></c>'
        elif isinstance(valor, (int, float)):
            xml = f"<c{atributos}><v>{_numero(valor)}</v></c>"
        else:
            texto = limpiar_texto(valor)
            if len(texto) > LIMITE_TEXTO:
                texto, recortado = texto[:LIMITE_TEXTO].rstrip() + " …", True
            xml = f'<c{atributos} t="inlineStr"><is><t xml:space="preserve">{escape(texto)}</t></is></c>'
        f[1][k] = xml
        f[0] = re.sub(r'\s+spans="[^"]*"', "", f[0])
        self.modificada = True
        return recortado

    def quitar_alto_fijo(self, fila):
        """La fila vuelve a ajustar su alto al texto (se quita ``ht`` y ``customHeight``)."""
        f = self._filas.get(fila)
        if f is not None:
            f[0] = re.sub(r'\s+(?:ht|customHeight)="[^"]*"', "", f[0])
            self.modificada = True

    def _editar_fuera_de_los_datos(self, cambio):
        texto = cambio(self.texto())
        self._texto, self.modificada = texto, True
        self._filas.clear()
        self._separar()
        self.modificada = True

    def agregar_dibujo_de_notas(self, rid):
        """Enlaza el dibujo VML de las notas de la hoja (``<legacyDrawing>``), en el lugar que el esquema exige."""
        def cambio(texto):
            if "<legacyDrawing" in texto:
                return texto
            if "xmlns:r=" not in texto.split(">", 2)[1]:
                texto = texto.replace("<worksheet ", '<worksheet xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ', 1)
            etiqueta = f'<legacyDrawing r:id="{rid}"/>'
            for ancla in ("<tableParts", "<extLst", "</worksheet>"):
                i = texto.find(ancla)
                if i >= 0:
                    return texto[:i] + etiqueta + texto[i:]
            return texto
        self._editar_fuera_de_los_datos(cambio)

    def combinadas(self):
        return re.findall(r'<mergeCell\b[^>]*?\bref="([^"]+)"', self.texto())

    def cambiar_combinadas(self, quitar=(), agregar=()):
        """Quita y agrega rangos combinados (solo para el cuerpo de una tabla; los encabezados no se tocan)."""
        quitar = set(quitar)

        def cambio(texto):
            actuales = re.findall(r'<mergeCell\b[^>]*?\bref="([^"]+)"', texto)
            nuevas = [r for r in actuales if r not in quitar] + [r for r in agregar if r not in actuales]
            bloque = (f'<mergeCells count="{len(nuevas)}">' + "".join(f'<mergeCell ref="{r}"/>' for r in nuevas) + "</mergeCells>") if nuevas else ""
            m = RE_COMBINADAS.search(texto)
            if m:
                return texto[:m.start()] + bloque + texto[m.end():]
            return texto.replace("</sheetData>", "</sheetData>" + bloque, 1)
        self._editar_fuera_de_los_datos(cambio)

    def ampliar_validaciones(self, columnas, fila_vieja, fila_nueva):
        """Las listas desplegables de las columnas dadas que terminaban en ``fila_vieja`` llegan hasta ``fila_nueva``."""
        def ampliar(m):
            fichas = []
            for ficha in m.group(2).split():
                r = RE_RANGO.match(ficha)
                if r and r.group(1) in columnas and (r.group(3) is None or r.group(3) == r.group(1)) \
                        and int(r.group(4) or r.group(2)) == fila_vieja:
                    ficha = f"{r.group(1)}{r.group(2)}:{r.group(1)}{fila_nueva}"
                fichas.append(ficha)
            return m.group(1) + " ".join(fichas) + m.group(3)
        self._editar_fuera_de_los_datos(lambda t: re.sub(r'(<dataValidation\b[^>]*?\bsqref=")([^"]*)(")', ampliar, t))

    def agregar_validacion_lista(self, sqref, opciones):
        """Lista desplegable clasica en ``sqref``; se inserta donde el esquema lo exige (antes de los hipervinculos)."""
        item = (f'<dataValidation type="list" allowBlank="1" showInputMessage="1" showErrorMessage="1" sqref="{sqref}">'
                f'<formula1>"{escape(",".join(opciones))}"</formula1></dataValidation>')
        texto = self.texto()
        m = re.search(r'<dataValidations count="(\d+)">', texto)
        if m:
            texto = texto.replace(m.group(0), f'<dataValidations count="{int(m.group(1)) + 1}">', 1)
            texto = texto.replace("</dataValidations>", item + "</dataValidations>", 1)
        else:
            bloque = f'<dataValidations count="1">{item}</dataValidations>'
            for ancla in ("<hyperlinks", "<printOptions", "<pageMargins"):
                i = texto.find(ancla)
                if i >= 0:
                    texto = texto[:i] + bloque + texto[i:]
                    break
            else:
                raise ValueError("no encontré dónde insertar la lista desplegable")
        self._texto, self.modificada = texto, True
        self._filas.clear()
        self._separar()
        self.modificada = True


def _numero(v):
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return str(int(v))
    return repr(float(v)) if isinstance(v, float) else str(v)
