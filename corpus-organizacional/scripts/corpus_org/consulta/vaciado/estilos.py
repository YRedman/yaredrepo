"""Estilos de celda nuevos para el K4: el mismo formato con otro color de letra, sin tocar los estilos que ya existen.

Las celdas de respuesta del K4 vienen con letra roja (para los ejemplos). Un dato real debe verse negro y un dato por validar,
morado; para eso se agregan al final de ``fonts`` y de ``cellXfs`` copias con el color cambiado. Lo que ya estaba no se modifica,
de modo que ninguna otra celda del libro cambia de aspecto.
"""

import re

NEGRO = "FF000000"
MORADO = "FF7030A0"

RE_BLOQUE_FUENTES = re.compile(r"(<fonts\b[^>]*>)(.*?)(</fonts>)", re.S)
RE_BLOQUE_XFS = re.compile(r"(<cellXfs\b[^>]*>)(.*?)(</cellXfs>)", re.S)
RE_FUENTE = re.compile(r"<font\b[^>]*?(?:/>|>.*?</font>)", re.S)
RE_XF = re.compile(r"<xf\b[^>]*?(?:/>|>.*?</xf>)", re.S)
RE_COLOR = re.compile(r"<color\b[^>]*?/>")
RE_CUENTA = re.compile(r'\bcount="\d+"')


def _color_de(fuente):
    m = RE_COLOR.search(fuente)
    if m is None:
        return ""
    rgb = re.search(r'\brgb="([0-9A-Fa-f]{8})"', m.group(0))
    return rgb.group(1).upper() if rgb else m.group(0)


def fuentes_y_formatos(texto):
    """([fuentes], [formatos de celda]) de un styles.xml, como texto de cada elemento."""
    f = RE_BLOQUE_FUENTES.search(texto)
    x = RE_BLOQUE_XFS.search(texto)
    return RE_FUENTE.findall(f.group(2)), RE_XF.findall(x.group(2))


class Estilos:
    def __init__(self, texto):
        self._texto = texto
        self.fuentes, self.formatos = fuentes_y_formatos(texto)
        self._n_fuentes, self._n_formatos = len(self.fuentes), len(self.formatos)
        self._cache = {}
        self.modificado = False

    def color_de_letra(self, indice_formato):
        """Color de la letra de un formato: 'FFFF0000', 'theme1' (o el elemento <color>) o '' si no tiene."""
        fuente_id = int(re.search(r'\bfontId="(\d+)"', self.formatos[indice_formato]).group(1))
        return _color_de(self.fuentes[fuente_id])

    def es_rojo(self, indice_formato):
        return self.color_de_letra(indice_formato) in ("FFFF0000", "FFC00000", "00FF0000")

    def con_color(self, indice_formato, color):
        """Indice de un formato igual al dado pero con letra de ``color`` ('FF000000'); se crea la primera vez que se pide."""
        clave = (indice_formato, color)
        if clave in self._cache:
            return self._cache[clave]
        xf = self.formatos[indice_formato]
        fuente_id = int(re.search(r'\bfontId="(\d+)"', xf).group(1))
        fuente = self.fuentes[fuente_id]
        nuevo_color = f'<color rgb="{color}"/>'
        nueva_fuente = RE_COLOR.sub(nuevo_color, fuente, count=1) if RE_COLOR.search(fuente) else \
            re.sub(r"(<sz\b[^>]*/>)", r"\1" + nuevo_color, fuente, count=1)
        if nueva_fuente == fuente:                                     # sin <color> ni <sz>: se agrega al final
            nueva_fuente = fuente.replace("</font>", nuevo_color + "</font>") if "</font>" in fuente else fuente
        if nueva_fuente in self.fuentes:
            nuevo_fuente_id = self.fuentes.index(nueva_fuente)
        else:
            self.fuentes.append(nueva_fuente)
            nuevo_fuente_id = len(self.fuentes) - 1
        nuevo_xf = re.sub(r'\bfontId="\d+"', f'fontId="{nuevo_fuente_id}"', xf, count=1)
        if "applyFont=" not in nuevo_xf:
            nuevo_xf = re.sub(r"<xf\b", '<xf applyFont="1"', nuevo_xf, count=1)
        if nuevo_xf in self.formatos:
            indice = self.formatos.index(nuevo_xf)
        else:
            self.formatos.append(nuevo_xf)
            indice = len(self.formatos) - 1
        self._cache[clave] = indice
        self.modificado = True
        return indice

    def texto(self):
        """El styles.xml con los elementos agregados al final (los anteriores quedan como estaban)."""
        if not self.modificado:
            return self._texto
        texto = self._texto
        nuevas_fuentes = self.fuentes[self._n_fuentes:]
        nuevos_formatos = self.formatos[self._n_formatos:]
        f = RE_BLOQUE_FUENTES.search(texto)
        cabecera = RE_CUENTA.sub(f'count="{len(self.fuentes)}"', f.group(1), count=1)
        texto = texto[:f.start()] + cabecera + f.group(2) + "".join(nuevas_fuentes) + f.group(3) + texto[f.end():]
        x = RE_BLOQUE_XFS.search(texto)
        cabecera = RE_CUENTA.sub(f'count="{len(self.formatos)}"', x.group(1), count=1)
        return texto[:x.start()] + cabecera + x.group(2) + "".join(nuevos_formatos) + x.group(3) + texto[x.end():]


def verificar_estilos_agregados(texto_base, texto_nuevo):
    """Errores si styles.xml cambio en algo mas que fuentes y formatos agregados al final (lo anterior debe quedar igual)."""
    fb, xb = fuentes_y_formatos(texto_base)
    fn, xn = fuentes_y_formatos(texto_nuevo)
    errores = []
    if fn[:len(fb)] != fb or xn[:len(xb)] != xb:
        errores.append("Cambiaron fuentes o formatos que ya existían en el archivo base.")
    sin = lambda t: re.sub(r"<fonts\b.*?</fonts>|<cellXfs\b.*?</cellXfs>", "", t, flags=re.S)           # noqa: E731
    if sin(texto_base) != sin(texto_nuevo):
        errores.append("styles.xml cambió en algo más que fuentes y formatos agregados al final.")
    for nombre, lista in (("fonts", fn), ("cellXfs", xn)):
        m = re.search(rf'<{nombre}\b[^>]*?\bcount="(\d+)"', texto_nuevo)
        if m is None or int(m.group(1)) != len(lista):
            errores.append(f"styles.xml: la cantidad declarada en {nombre} no coincide con sus elementos.")
    return errores


def sin_color_de_letra(elemento):
    """El texto de una fuente o de un formato sin su color ni los indices que cambian al agregar una fuente."""
    t = RE_COLOR.sub("", elemento)
    return re.sub(r'\s(?:fontId|applyFont)="[^"]*"', "", t)
