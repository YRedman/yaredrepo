"""Edicion de una hoja de Excel directamente en su XML: cambia solo las celdas que se le piden.

No se reserializa el XML (eso cambiaria prefijos de espacios de nombres y perderia extensiones como las listas
desplegables x14): se localizan las filas y celdas por texto y se reemplazan solo las que cambian.
"""

import re
from xml.sax.saxutils import escape

from .xlsx import columna_a_numero, numero_a_columna, partir_ref

RE_SHEETDATA = re.compile(r"(<sheetData\b[^>]*?(?:/>|>)).*?(</sheetData>)|<sheetData\b[^>]*?/>", re.S)
RE_FILA = re.compile(r"<row\b([^>]*?)(/>|>(.*?)</row>)", re.S)
RE_CELDA = re.compile(r"<c\b([^>]*?)(/>|>(.*?)</c>)", re.S)
RE_ATRIBUTO = re.compile(r'([\w:]+)="([^"]*)"')
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
        self._orden_original = []
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

    def tiene_formula(self, ref):
        xml = self.xml_celda(ref)
        return xml is not None and "<f" in xml

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

    def escribir(self, ref, valor, estilo=None):
        """Escribe un texto o un numero en ``ref`` conservando el estilo de la celda. Devuelve True si el texto se recorto.

        Rechaza las celdas con formula. ``estilo`` se usa solo si la celda no existia.
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
        if existente is not None:
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
