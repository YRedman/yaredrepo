"""Lector de libros de Excel (.xlsx) con la biblioteca estandar.

Lee, de cada hoja (visible u oculta): el valor de cada celda (con el valor guardado de las formulas), si tiene formula,
si su formato es de fecha u hora, el color de la letra y del relleno, las celdas combinadas y las notas.
"""

import datetime
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
NS_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
RE_REF = re.compile(r"^([A-Z]+)(\d+)$")
ORIGEN_SERIE = datetime.datetime(1899, 12, 30)
FORMATOS_FECHA_INTEGRADOS = set(range(14, 23)) | {27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 45, 46, 47, 50, 51, 52, 53, 54, 55, 56, 57, 58}
FORMATOS_HORA_INTEGRADOS = {18, 19, 20, 21, 45, 46, 47}


def columna_a_numero(letras):
    n = 0
    for c in letras:
        n = n * 26 + ord(c) - 64
    return n


def numero_a_columna(n):
    letras = ""
    while n:
        n, r = divmod(n - 1, 26)
        letras = chr(65 + r) + letras
    return letras


def partir_ref(ref):
    """'C12' -> ('C', 12)."""
    m = RE_REF.match(ref)
    return m.group(1), int(m.group(2))


def _es_formato_fecha(codigo):
    """True si el codigo de formato de numero (personalizado) muestra fechas u horas."""
    limpio = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]', "", codigo or "")
    return bool(re.search(r"[dmyhs]", limpio, re.I)) and not re.search(r"[#0]", limpio)


@dataclass
class Celda:
    ref: str
    valor: object = None            # str, float, bool o None
    formula: str = ""
    estilo: int = 0
    es_fecha: bool = False          # el formato de la celda muestra fecha u hora
    es_hora: bool = False
    color_letra: str = ""           # 'FFFF0000'; '' si es el automatico
    color_relleno: str = ""
    nota: str = ""

    @property
    def vacia(self):
        return self.valor is None or (isinstance(self.valor, str) and not self.valor.strip())


@dataclass
class Hoja:
    nombre: str
    estado: str                     # visible, hidden, veryHidden
    parte: str                      # xl/worksheets/sheetN.xml
    celdas: dict = field(default_factory=dict)         # ref -> Celda
    combinadas: list = field(default_factory=list)     # ['B9:B10', ...]
    _origen_combinada: dict = field(default_factory=dict)

    @property
    def oculta(self):
        return self.estado != "visible"

    def celda(self, ref):
        return self.celdas.get(ref)

    def valor(self, ref):
        c = self.celdas.get(ref)
        return c.valor if c else None

    def valor_combinado(self, ref):
        """Valor de la celda; si esta dentro de una combinada, el de su celda superior izquierda."""
        c = self.celdas.get(ref)
        if c is not None and not c.vacia:
            return c.valor
        origen = self._origen_combinada.get(ref)
        return self.valor(origen) if origen else None

    def filas(self):
        """Numeros de fila con alguna celda, en orden."""
        return sorted({partir_ref(r)[1] for r in self.celdas})

    def fila(self, n):
        """{columna: Celda} de la fila ``n``."""
        return {partir_ref(r)[0]: c for r, c in self.celdas.items() if partir_ref(r)[1] == n}


class Libro:
    def __init__(self, ruta):
        self.ruta = Path(ruta)
        with zipfile.ZipFile(self.ruta) as z:
            self._z = {n: z.read(n) for n in z.namelist()}
        self._cadenas = self._leer_cadenas()
        self._estilos = self._leer_estilos()
        self.hojas = self._leer_hojas()

    # -- paquete -----------------------------------------------------------------------------------------------

    def _xml(self, parte):
        return ET.fromstring(self._z[parte])

    def _relaciones(self, parte):
        """{id: destino absoluto} de las relaciones de una parte."""
        carpeta = PurePosixPath(parte).parent
        nombre = f"{carpeta}/_rels/{PurePosixPath(parte).name}.rels"
        if nombre not in self._z:
            return {}
        rels = {}
        for r in self._xml(nombre):
            destino = r.get("Target")
            ruta = PurePosixPath(destino[1:]) if destino.startswith("/") else PurePosixPath(carpeta, destino)
            partes = []
            for p in ruta.parts:
                if p == "..":
                    partes.pop()
                else:
                    partes.append(p)
            rels[r.get("Id")] = ("/".join(partes), r.get("Type", ""))
        return rels

    def _leer_cadenas(self):
        if "xl/sharedStrings.xml" not in self._z:
            return []
        cadenas = []
        for si in self._xml("xl/sharedStrings.xml").iter(NS + "si"):
            cadenas.append("".join(t.text or "" for t in si.iter(NS + "t") if not _en_fonetico(si, t)))
        return cadenas

    def _leer_estilos(self):
        """Por indice de estilo: (es_fecha, es_hora, color de letra, color de relleno)."""
        if "xl/styles.xml" not in self._z:
            return []
        raiz = self._xml("xl/styles.xml")
        formatos = {int(n.get("numFmtId")): n.get("formatCode") for n in raiz.iter(NS + "numFmt")}
        fuentes = [_color(f.find(NS + "color")) for f in raiz.find(NS + "fonts")]
        rellenos = []
        for r in raiz.find(NS + "fills"):
            pf = r.find(NS + "patternFill")
            rellenos.append(_color(pf.find(NS + "fgColor")) if pf is not None and pf.get("patternType") == "solid" else "")
        estilos = []
        for xf in raiz.find(NS + "cellXfs"):
            fid = int(xf.get("numFmtId", 0))
            codigo = formatos.get(fid, "")
            fecha = fid in FORMATOS_FECHA_INTEGRADOS or (fid >= 164 and _es_formato_fecha(codigo))
            hora = fid in FORMATOS_HORA_INTEGRADOS or (fid >= 164 and _es_formato_fecha(codigo) and bool(re.search(r"[hs]", codigo)) and not re.search(r"[dy]", codigo))
            estilos.append((fecha, hora, fuentes[int(xf.get("fontId", 0))], rellenos[int(xf.get("fillId", 0))]))
        return estilos

    def _leer_hojas(self):
        raiz = self._xml("xl/workbook.xml")
        rels = self._relaciones("xl/workbook.xml")
        hojas = []
        for h in raiz.find(NS + "sheets"):
            parte = rels[h.get(NS_REL + "id")][0]
            hoja = Hoja(h.get("name"), h.get("state", "visible"), parte)
            self._leer_hoja(hoja)
            hojas.append(hoja)
        return hojas

    def _leer_hoja(self, hoja):
        raiz = self._xml(hoja.parte)
        for fila in raiz.iter(NS + "row"):
            for c in fila.iter(NS + "c"):
                celda = self._leer_celda(c)
                if celda is not None:
                    hoja.celdas[celda.ref] = celda
        for m in raiz.iter(NS + "mergeCell"):
            hoja.combinadas.append(m.get("ref"))
            a, b = m.get("ref").split(":")
            (c1, f1), (c2, f2) = partir_ref(a), partir_ref(b)
            for f in range(f1, f2 + 1):
                for col in range(columna_a_numero(c1), columna_a_numero(c2) + 1):
                    ref = f"{numero_a_columna(col)}{f}"
                    if ref != a:
                        hoja._origen_combinada[ref] = a
        for ref, texto in self._notas(hoja).items():
            celda = hoja.celdas.get(ref)
            if celda is None:
                celda = hoja.celdas[ref] = Celda(ref)
            celda.nota = texto

    def _leer_celda(self, c):
        ref, tipo = c.get("r"), c.get("t")
        formula = c.find(NS + "f")
        v = c.find(NS + "v")
        valor = None
        if tipo == "s" and v is not None:
            valor = self._cadenas[int(v.text)]
        elif tipo == "inlineStr":
            valor = "".join(t.text or "" for t in c.iter(NS + "t"))
        elif tipo in ("str", "e") and v is not None:
            valor = v.text or ""
        elif tipo == "b" and v is not None:
            valor = v.text == "1"
        elif v is not None and v.text not in (None, ""):
            try:
                valor = float(v.text)
            except ValueError:
                valor = v.text
        estilo = int(c.get("s", 0))
        fecha, hora, letra, relleno = self._estilos[estilo] if estilo < len(self._estilos) else (False, False, "", "")
        if valor is None and formula is None and not estilo:
            return None
        if tipo == "e":
            valor = None                           # #N/A, #REF!...: no es un dato
        return Celda(ref, valor, _texto_formula(formula), estilo, fecha, hora, letra, relleno)

    def _notas(self, hoja):
        """{ref: texto} de las notas (comentarios clasicos) de la hoja."""
        notas = {}
        for _id, (destino, tipo) in self._relaciones(hoja.parte).items():
            if tipo.endswith("/comments") and destino in self._z:
                for c in self._xml(destino).iter(NS + "comment"):
                    notas[c.get("ref")] = "".join(t.text or "" for t in c.iter(NS + "t")).strip()
        return notas

    # -- consulta ----------------------------------------------------------------------------------------------

    def hoja(self, nombre):
        return next((h for h in self.hojas if h.nombre == nombre), None)

    @property
    def nombres(self):
        return [h.nombre for h in self.hojas]


def _texto_formula(f):
    """Texto de la formula; las celdas que comparten la de otra no la repiten, asi que se marcan con su grupo."""
    if f is None:
        return ""
    return f.text or f"<compartida {f.get('si', '')}>"


def _en_fonetico(si, t):
    """True si el texto ``t`` esta dentro de una ayuda fonetica (<rPh>), que no es parte de la celda."""
    return any(t in ph.iter(NS + "t") for ph in si.iter(NS + "rPh"))


def _color(nodo):
    """'FFFF0000' (rgb), 'theme0' o 'theme0/-0.05' (tema con tinte); '' si no hay color."""
    if nodo is None:
        return ""
    if nodo.get("rgb"):
        return nodo.get("rgb").upper()
    if nodo.get("theme") is not None:
        tinte = float(nodo.get("tint", 0))
        return f"theme{nodo.get('theme')}" + (f"/{tinte:.2f}" if tinte else "")
    return ""


def serie_a_fecha(numero):
    return ORIGEN_SERIE + datetime.timedelta(days=float(numero))
