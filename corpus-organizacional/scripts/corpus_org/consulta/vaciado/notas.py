"""Notas de celda (los comentarios de Excel) escritas directamente en el XML del libro, sin tocar las que ya existen.

Cada celda que propone el agente lleva una nota que dice si el valor es «Inferido» (hay una regla o un dato detras) o «A validar»
(no hay base y el consultor debe completarlo). Una hoja que ya tiene comentarios recibe las notas nuevas en su misma parte; si no
tiene, se crean las partes que Excel necesita (comentarios, dibujo VML, relaciones y tipo de contenido).
"""

import re
from xml.sax.saxutils import escape

from .hoja_xml import limpiar_texto
from .xlsx import columna_a_numero, partir_ref

AUTOR = "Claude (inferido)"
RE_COMENTARIO = re.compile(r"<comment\b[^>]*?\bref=\"([A-Z]+\d+)\"[^>]*?(?:/>|>.*?</comment>)", re.S)
RE_ID_FORMA = re.compile(r'id="_x0000_s(\d+)"')
RE_IDMAP = re.compile(r'<o:idmap\b[^>]*\bdata="(\d+)"')
TIPO_COMENTARIOS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
TIPO_VML = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/vmlDrawing"
CT_COMENTARIOS = "application/vnd.openxmlformats-officedocument.spreadsheetml.comments+xml"
CT_VML = "application/vnd.openxmlformats-officedocument.vmlDrawing"
LIMITE_NOTA = 1200

ENCABEZADO_VML = """<xml xmlns:v="urn:schemas-microsoft-com:vml"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel">
 <o:shapelayout v:ext="edit">
  <o:idmap v:ext="edit" data="{bloque}"/>
 </o:shapelayout><v:shapetype id="_x0000_t202" coordsize="21600,21600" o:spt="202"
  path="m,l,21600r21600,l21600,xe">
  <v:stroke joinstyle="miter"/>
  <v:path gradientshapeok="t" o:connecttype="rect"/>
 </v:shapetype></xml>"""

FORMA_VML = """<v:shape id="_x0000_s{id}" type="#_x0000_t202" style='position:absolute;
  margin-left:100pt;margin-top:50pt;width:180pt;height:80pt;z-index:{z};
  visibility:hidden' fillcolor="infoBackground [80]" strokecolor="none [81]"
  o:insetmode="auto">
  <v:fill color2="infoBackground [80]"/>
  <v:shadow color="none [81]" obscured="t"/>
  <v:path o:connecttype="none"/>
  <v:textbox style='mso-direction-alt:auto'>
   <div style='text-align:left'></div>
  </v:textbox>
  <x:ClientData ObjectType="Note">
   <x:MoveWithCells/>
   <x:SizeWithCells/>
   <x:Anchor>
    {col1}, 15, {fila0}, 2, {col2}, 15, {fila1}, 4</x:Anchor>
   <x:AutoFill>False</x:AutoFill>
   <x:Row>{fila}</x:Row>
   <x:Column>{col}</x:Column>
  </x:ClientData>
 </v:shape>"""


def _clave(ref):
    col, fila = partir_ref(ref)
    return fila, columna_a_numero(col)


def _comentario_xml(ref, texto, autor_id):
    texto = limpiar_texto(texto)[:LIMITE_NOTA]
    return (f'<comment ref="{ref}" authorId="{autor_id}" shapeId="0"><text><r><rPr><sz val="9"/><color indexed="81"/>'
            f'<rFont val="Tahoma"/><family val="2"/></rPr><t xml:space="preserve">{escape(texto)}</t></r></text></comment>')


def _forma_xml(ref, id_forma, z):
    fila, col = _clave(ref)
    return FORMA_VML.format(id=id_forma, z=z, fila=fila - 1, col=col - 1, col1=col, col2=col + 2, fila0=max(fila - 2, 0), fila1=fila + 2)


class Notas:
    def __init__(self, paquete):
        self.paquete = paquete
        self.pendientes = {}             # hoja -> {ref: texto}
        self.omitidas = []               # (hoja, ref) que ya tenian una nota propia: no se pisa

    def agregar(self, hoja, ref, texto):
        self.pendientes.setdefault(hoja, {})[ref] = texto

    # -- partes del paquete ------------------------------------------------------------------------------------

    def _parte(self, nombre):
        return (self.paquete._cambios.get(nombre) or self.paquete.partes[nombre]).decode("utf-8")

    def _relacion_de(self, hoja, sufijo):
        h = self.paquete.libro.hoja(hoja)
        for rid, (destino, tipo) in self.paquete.libro._relaciones(h.parte).items():
            if tipo == sufijo:
                return rid, destino
        return None, None

    def aplicar(self):
        """Escribe todas las notas pendientes en el paquete. Devuelve {hoja: [refs escritas]}."""
        escritas = {}
        for hoja, items in self.pendientes.items():
            _, comentarios = self._relacion_de(hoja, TIPO_COMENTARIOS)
            _, vml = self._relacion_de(hoja, TIPO_VML)
            if comentarios and vml and comentarios in self.paquete.partes and vml in self.paquete.partes:
                escritas[hoja] = self._agregar_a_existentes(comentarios, vml, items, hoja)
            else:
                escritas[hoja] = self._crear(hoja, items)
        return escritas

    # -- la hoja ya tiene comentarios ---------------------------------------------------------------------------

    def _agregar_a_existentes(self, parte_comentarios, parte_vml, items, hoja):
        xml = self._parte(parte_comentarios)
        existentes = {m.group(1): m.group(0) for m in RE_COMENTARIO.finditer(xml)}
        autores = re.findall(r"<author>(.*?)</author>", xml, re.S)
        if AUTOR not in autores:
            xml = xml.replace("</authors>", f"<author>{AUTOR}</author></authors>", 1)
            autores.append(AUTOR)
        autor_id = autores.index(AUTOR)
        nuevos = {}
        for ref, texto in items.items():
            if ref in existentes:
                self.omitidas.append((hoja, ref))
                continue
            nuevos[ref] = _comentario_xml(ref, texto, autor_id)
        todos = {**existentes, **nuevos}
        lista = "".join(todos[r] for r in sorted(todos, key=_clave))
        xml = re.sub(r"<commentList>.*?</commentList>|<commentList/>", lambda _m: f"<commentList>{lista}</commentList>", xml, count=1, flags=re.S)
        self.paquete.reemplazar_parte(parte_comentarios, xml)
        vml = self._parte(parte_vml)
        siguiente = max([int(x) for x in RE_ID_FORMA.findall(vml)] or [self._base_ids(vml)]) + 1
        formas = "".join(_forma_xml(ref, siguiente + i, 1000 + i) for i, ref in enumerate(nuevos))
        self.paquete.reemplazar_parte(parte_vml, vml.replace("</xml>", formas + "</xml>") if "</xml>" in vml else vml + formas)
        return sorted(nuevos, key=_clave)

    @staticmethod
    def _base_ids(vml):
        m = RE_IDMAP.search(vml)
        return (int(m.group(1)) if m else 1) * 1024

    # -- la hoja no tiene comentarios: se crean sus partes -----------------------------------------------------------

    def _numero_libre(self, patron):
        usados = [int(m.group(1)) for n in self.paquete.partes for m in [re.search(patron, n)] if m]
        return max(usados or [0]) + 1

    def _crear(self, hoja, items):
        paquete = self.paquete
        h = paquete.libro.hoja(hoja)
        n_com = self._numero_libre(r"^xl/comments(\d+)\.xml$")
        n_vml = self._numero_libre(r"^xl/drawings/vmlDrawing(\d+)\.vml$")
        bloque = max([int(m.group(1)) for n in paquete.partes if n.endswith(".vml") for m in [RE_IDMAP.search(self._parte(n))] if m] or [0]) + 1
        autor_id = 0
        comentarios = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<comments xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                       f"<authors><author>{AUTOR}</author></authors><commentList>"
                       + "".join(_comentario_xml(ref, items[ref], autor_id) for ref in sorted(items, key=_clave)) + "</commentList></comments>")
        base = bloque * 1024
        formas = "".join(_forma_xml(ref, base + 1 + i, 1 + i) for i, ref in enumerate(sorted(items, key=_clave)))
        vml = ENCABEZADO_VML.format(bloque=bloque).replace("</xml>", formas + "</xml>")
        nombre_com, nombre_vml = f"xl/comments{n_com}.xml", f"xl/drawings/vmlDrawing{n_vml}.vml"
        paquete.agregar_parte(nombre_com, comentarios)
        paquete.agregar_parte(nombre_vml, vml)
        # relaciones de la hoja
        carpeta, _, archivo = h.parte.rpartition("/")
        rels = f"{carpeta}/_rels/{archivo}.rels"
        existentes = self._parte(rels) if rels in paquete.partes else \
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'
        siguiente = max([int(x) for x in re.findall(r'Id="rId(\d+)"', existentes)] or [0]) + 1
        rid_vml, rid_com = f"rId{siguiente}", f"rId{siguiente + 1}"
        nuevas = (f'<Relationship Id="{rid_vml}" Type="{TIPO_VML}" Target="../drawings/vmlDrawing{n_vml}.vml"/>'
                  f'<Relationship Id="{rid_com}" Type="{TIPO_COMENTARIOS}" Target="../comments{n_com}.xml"/>')
        existentes = existentes.replace("</Relationships>", nuevas + "</Relationships>")
        if rels in paquete.partes:
            paquete.reemplazar_parte(rels, existentes)
        else:
            paquete.agregar_parte(rels, existentes)
        # tipos de contenido
        tipos = self._parte("[Content_Types].xml")
        if 'Extension="vml"' not in tipos:
            tipos = tipos.replace("<Override", f'<Default Extension="vml" ContentType="{CT_VML}"/><Override', 1)
        tipos = tipos.replace("</Types>", f'<Override PartName="/{nombre_com}" ContentType="{CT_COMENTARIOS}"/></Types>')
        paquete.reemplazar_parte("[Content_Types].xml", tipos)
        paquete.hoja_xml(hoja).agregar_dibujo_de_notas(rid_vml)
        return sorted(items, key=_clave)
