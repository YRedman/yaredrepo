"""Extractor de Word (.docx) leyendo el XML con lxml."""

import collections
import html
import re
import zipfile

from ...comun.esquema import MARCA_COMBINADA
from ...comun.texto import norm, numeros, tokens
from ..modelo import DocumentoExtraido, bloque_h
from ..secciones import clave_titulo, es_seccion_conocida, es_titulo_corto, profundidad_numeracion
from .base import Extractor

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {
    "w": W,
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
}
NS_APP = "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}"
EMU_CM = 360000
AREA_DIAGRAMA = (6 * EMU_CM) * (4 * EMU_CM)   # imagenes mayores a 6x4 cm se marcan como diagrama
RE_ROMANO = re.compile(r"^[IVXLC]{1,6}\.\s")


def _local(el):
    t = el.tag
    return t.split("}", 1)[1] if isinstance(t, str) and "}" in t else t


def _wattr(el, nombre):
    return el.get("{%s}%s" % (W, nombre))


def _numpr(ppr):
    np_ = ppr.find("w:numPr", NS)
    if np_ is None:
        return None
    numid = np_.find("w:numId", NS)
    ilvl = np_.find("w:ilvl", NS)
    return (_wattr(numid, "val") if numid is not None else None,
            int(_wattr(ilvl, "val")) if ilvl is not None else 0)


def _outline(ppr):
    ol = ppr.find("w:outlineLvl", NS)
    return int(_wattr(ol, "val")) if ol is not None else None


def _numero_formateado(n, formato):
    if formato == "lowerLetter":
        return chr(ord("a") + (n - 1) % 26)
    if formato == "upperLetter":
        return chr(ord("A") + (n - 1) % 26)
    if formato in ("lowerRoman", "upperRoman"):
        r, m = "", n
        for v, s in [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]:
            while m >= v:
                r += s
                m -= v
        return r.upper() if formato == "upperRoman" else r
    return str(n)


class _ContextoDocx:
    """Estilos, numeracion y notas al pie de un .docx, y lectura de parrafos."""

    def __init__(self, z, etree):
        self.etree = etree
        self.z = z
        self.estilos = {}      # id -> dict(nombre, basado, numpr, outline, bold)
        self.numeracion = {}   # numId -> {ilvl: (fmt, lvlText, start)}
        self.contadores = {}
        self.notas = {}
        self._cargar_estilos()
        self._cargar_numeracion()
        self._cargar_notas()

    def leer(self, nombre):
        try:
            return self.etree.fromstring(self.z.read(nombre))
        except KeyError:
            return None

    def _cargar_estilos(self):
        raiz = self.leer("word/styles.xml")
        if raiz is None:
            return
        for st in raiz.findall("w:style", NS):
            sid = _wattr(st, "styleId")
            nom = st.find("w:name", NS)
            bas = st.find("w:basedOn", NS)
            ppr = st.find("w:pPr", NS)
            rpr = st.find("w:rPr", NS)
            b = rpr.find("w:b", NS) if rpr is not None else None
            self.estilos[sid] = {"nombre": _wattr(nom, "val") if nom is not None else sid,
                                 "basado": _wattr(bas, "val") if bas is not None else None,
                                 "numpr": _numpr(ppr) if ppr is not None else None,
                                 "outline": _outline(ppr) if ppr is not None else None,
                                 "bold": b is not None and _wattr(b, "val") not in ("0", "false")}

    def estilo_prop(self, sid, prop):
        """Propiedad de un estilo, heredada de sus estilos base si no la define."""
        vistos = set()
        while sid and sid not in vistos:
            vistos.add(sid)
            st = self.estilos.get(sid)
            if not st:
                return None
            if st.get(prop) is not None and st.get(prop) is not False:
                return st[prop]
            sid = st["basado"]
        return None

    def _cargar_numeracion(self):
        raiz = self.leer("word/numbering.xml")
        if raiz is None:
            return
        abstractos = {}
        for an in raiz.findall("w:abstractNum", NS):
            niveles = {}
            for lvl in an.findall("w:lvl", NS):
                fmt = lvl.find("w:numFmt", NS)
                txt = lvl.find("w:lvlText", NS)
                ini = lvl.find("w:start", NS)
                niveles[int(_wattr(lvl, "ilvl"))] = (_wattr(fmt, "val") if fmt is not None else "decimal",
                                                     _wattr(txt, "val") if txt is not None else "%1.",
                                                     int(_wattr(ini, "val")) if ini is not None else 1)
            abstractos[_wattr(an, "abstractNumId")] = niveles
        for num in raiz.findall("w:num", NS):
            an = num.find("w:abstractNumId", NS)
            if an is not None:
                self.numeracion[_wattr(num, "numId")] = abstractos.get(_wattr(an, "val"), {})

    def _cargar_notas(self):
        raiz = self.leer("word/footnotes.xml")
        if raiz is None:
            return
        for fn in raiz.findall("w:footnote", NS):
            if _wattr(fn, "type") in ("separator", "continuationSeparator"):
                continue
            textos = [self.texto_parrafo(p)[0] for p in fn.findall(".//w:p", NS)]
            self.notas[_wattr(fn, "id")] = " ".join(t for t in textos if t).strip()

    def marcador_lista(self, numid, ilvl):
        niveles = self.numeracion.get(numid)
        if not niveles:
            return "-"
        fmt, lvltext, inicio = niveles.get(ilvl, ("decimal", "%1.", 1))
        if fmt in ("bullet", "none"):
            return "-"
        cont = self.contadores.setdefault(numid, {})
        cont[ilvl] = cont.get(ilvl, inicio - 1) + 1
        for k in list(cont):
            if k > ilvl:
                del cont[k]

        def repl(m):
            k = int(m.group(1)) - 1
            f = niveles.get(k, ("decimal", "", 1))[0]
            return _numero_formateado(cont.get(k, niveles.get(k, ("", "", 1))[2]), f)

        return re.sub(r"%(\d)", repl, lvltext).strip() or "-"

    def texto_parrafo(self, p):
        """(texto, tamanos de imagenes, cuadros de texto, ids de notas) de un parrafo.

        Omite texto eliminado, codigos de campo y duplicados de compatibilidad (mc:Fallback).
        """
        partes, imagenes, cuadros, notas = [], [], [], []

        def visitar(el):
            for h in el:
                nom = _local(h)
                if nom in ("del", "instrText", "delText", "Fallback", "rPr", "pPr"):
                    continue
                if nom == "txbxContent":
                    cuadros.append(h)
                elif nom == "t":
                    partes.append(h.text or "")
                elif nom in ("tab", "br", "cr"):
                    partes.append(" ")
                elif nom == "noBreakHyphen":
                    partes.append("-")
                elif nom == "footnoteReference":
                    fid = _wattr(h, "id")
                    notas.append(fid)
                    partes.append(f" [NOTA AL PIE {fid}]")
                elif nom in ("drawing", "pict", "object"):
                    if h.find(".//a:blip", NS) is not None or h.find(".//v:imagedata", NS) is not None:
                        imagenes.append(self._area_imagen(h))
                    visitar(h)
                else:
                    visitar(h)

        visitar(p)
        texto = re.sub(r"[ \t]+", " ", "".join(partes)).strip()
        return texto, imagenes, cuadros, notas

    @staticmethod
    def _area_imagen(el):
        ext = el.find(".//wp:extent", NS)
        if ext is None:
            return 0
        try:
            return int(ext.get("cx")) * int(ext.get("cy"))
        except (TypeError, ValueError):
            return 0

    def props_parrafo(self, p):
        """(nombre de estilo, numeracion, nivel de esquema, negrita) de un parrafo."""
        ppr = p.find("w:pPr", NS)
        sid = numpr = outline = None
        if ppr is not None:
            ps = ppr.find("w:pStyle", NS)
            if ps is not None:
                sid = _wattr(ps, "val")
            numpr = _numpr(ppr)
            outline = _outline(ppr)
        if numpr is None and sid:
            numpr = self.estilo_prop(sid, "numpr")
        if outline is None and sid:
            outline = self.estilo_prop(sid, "outline")
        nombre = self.estilos.get(sid, {}).get("nombre", "") if sid else ""
        if numpr is not None and numpr[0] in (None, "0"):
            numpr = None
        return nombre, numpr, outline, self._es_negrita(p, sid)

    def _es_negrita(self, p, sid):
        """True si todas las corridas con texto estan en negrita (directa o por estilo)."""
        runs = [r for r in p.iter("{%s}r" % W) if any(_local(x) == "t" and (x.text or "").strip() for x in r)]
        estilo_bold = bool(sid and self.estilo_prop(sid, "bold"))
        bold = bool(runs)
        for r in runs:
            rpr = r.find("w:rPr", NS)
            b = rpr.find("w:b", NS) if rpr is not None else None
            if b is not None:
                if _wattr(b, "val") in ("0", "false"):
                    bold = False
            elif not estilo_bold:
                bold = False
        return bold


def _nivel_estilo(nombre, outline):
    n = norm(nombre)
    m = re.match(r"^(heading|titulo|título|encabezado)\s*(\d)$", n)
    if m:
        return int(m.group(2))
    if n in ("title", "titulo"):
        return 1
    if outline is not None and 0 <= outline <= 5:
        return outline + 1
    return 0


def _tabla_docx(tbl, ctx):
    filas = []
    for tr in tbl.findall("w:tr", NS):
        fila = []
        for tc in tr.findall("w:tc", NS):
            tcpr = tc.find("w:tcPr", NS)
            span, vmerge = 1, None
            if tcpr is not None:
                gs = tcpr.find("w:gridSpan", NS)
                if gs is not None:
                    span = int(_wattr(gs, "val") or 1)
                vm = tcpr.find("w:vMerge", NS)
                if vm is not None:
                    vmerge = _wattr(vm, "val") or "continue"
            texto = " ".join(_textos_celda(tc, ctx)).strip()
            if vmerge == "continue":
                col = len(fila)
                if filas and col < len(filas[-1]) and filas[-1][col].strip():
                    texto = filas[-1][col].replace(MARCA_COMBINADA, "") + MARCA_COMBINADA
                else:
                    texto = ""
            fila.append(texto)
            fila.extend([""] * (span - 1))
        filas.append(fila)
    ncol = max((len(f) for f in filas), default=0)
    filas = [f + [""] * (ncol - len(f)) for f in filas]
    filas = [f for f in filas if any(c.strip() for c in f)]
    filas = _unir_filas_partidas(filas)
    if filas:
        cols = [j for j in range(ncol) if any(f[j].strip() for f in filas)]
        filas = [[f[j] for j in cols] for f in filas]
    return filas


def _unir_filas_partidas(filas):
    """Une a la fila anterior las filas sin primera celda que continuan una frase cortada (el autor partio el texto de
    una celda en dos filas): cada celda llena debe seguir a una celda anterior que no cierra la frase y empezar en
    minuscula. Una fila que no cumple se deja (puede ser una fila nueva, como «Fin del proceso»)."""
    salida = []
    for f in filas:
        previa = salida[-1] if salida else None
        llenas = [j for j, c in enumerate(f) if c.strip()]
        if (previa is not None and llenas and not f[0].strip() and len(salida) > 1 and all(
                previa[j].strip() and previa[j].rstrip()[-1] not in ".:;?!)" and f[j].lstrip()[0].islower()
                for j in llenas)):
            for j in llenas:
                previa[j] = previa[j].rstrip() + " " + f[j].strip()
            continue
        salida.append(list(f))
    return salida


def _textos_celda(tc, ctx):
    textos = []
    for el in tc:
        nom = _local(el)
        if nom == "p":
            t = ctx.texto_parrafo(el)[0]
            if t:
                textos.append(t)
        elif nom == "tbl":
            sub = _tabla_docx(el, ctx)
            textos.append(" ".join(" ".join(c for c in f if c) for f in sub))
        elif nom == "sdt":
            for p in el.iter("{%s}p" % W):
                t = ctx.texto_parrafo(p)[0]
                if t:
                    textos.append(t)
    return textos


def _crudo_docx_xml(datos):
    """Texto del XML con expresiones regulares: lectura independiente para verificar la conversion."""
    txt = datos.decode("utf-8", errors="replace")
    txt = re.sub(r"<mc:Fallback>.*?</mc:Fallback>", " ", txt, flags=re.S)
    # solo <w:del ...>...</w:del> con contenido: la marca de parrafo borrado <w:del .../> es autocontenida
    txt = re.sub(r"<w:del\b[^>]*(?<!/)>.*?</w:del>", " ", txt, flags=re.S)
    salida = []        # <m:t> es el texto de una ecuacion de Word (Office Math), que el extractor tambien lee
    for m in re.finditer(r"<[wm]:t(?:\s[^>]*)?>(.*?)</[wm]:t>|(<w:tab/>|<w:br/>|</w:p>|</w:tc>)", txt, flags=re.S):
        salida.append(html.unescape(m.group(1)) if m.group(1) is not None else " ")
    return "".join(salida)


class _ConversionDocx:
    """Recorre el cuerpo del documento y produce bloques."""

    def __init__(self, ctx, d):
        self.ctx = ctx
        self.d = d
        self.bloques = []

    def procesar(self, contenedor):
        for el in contenedor:
            nom = _local(el)
            if nom == "p":
                self._parrafo(el)
            elif nom == "tbl":
                self._tabla(el)
            elif nom in ("sdt", "customXml", "smartTag"):
                cont = el.find("w:sdtContent", NS) if nom == "sdt" else el
                if cont is not None:
                    self.procesar(cont)

    def _parrafo(self, el):
        ctx = self.ctx
        texto, imagenes, cuadros, notas = ctx.texto_parrafo(el)
        nombre, numpr, outline, bold = ctx.props_parrafo(el)
        if texto:
            self.bloques.append(self._bloque_texto(texto, nombre, numpr, outline, bold))
        for tam in imagenes:
            if tam > AREA_DIAGRAMA:
                self.bloques.append({"k": "marca", "texto": "[DIAGRAMA O IMAGEN: ver documento original]"})
                self.d.diagramas.append(0)
            else:
                self.d.imagenes_omitidas += 1
                self.bloques.append({"k": "marca", "texto": "[IMAGEN OMITIDA]"})
        for cb in cuadros:
            self._cuadro(cb)
        for fid in notas:
            if fid in ctx.notas:
                self.bloques.append({"k": "p", "texto": f"[NOTA AL PIE {fid}] {ctx.notas[fid]}"})

    def _cuadro(self, cb):
        """Contenido de un cuadro de texto: parrafos, tablas (los diagramas de flujo de Word son tablas dentro de
        cuadros) y cuadros anidados."""
        for el in cb:
            nom = _local(el)
            if nom == "p":
                texto, _imgs, anidados, _notas = self.ctx.texto_parrafo(el)
                if texto:
                    self.bloques.append({"k": "p", "texto": "[CUADRO DE TEXTO] " + texto})
                for a in anidados:
                    self._cuadro(a)
            elif nom == "tbl":
                self._tabla(el)

    def _bloque_texto(self, texto, nombre, numpr, outline, bold):
        nivel = _nivel_estilo(nombre, outline)
        # El numero automatico de Word no esta en el texto del parrafo: se calcula con la numeracion
        # del documento (tambien para los titulos, para que "2. Alcance" no quede como "Alcance").
        marcador = self.ctx.marcador_lista(numpr[0], numpr[1]) if numpr is not None else None
        if nivel:
            return bloque_h(min(nivel, 3), (marcador + " " + texto) if marcador and marcador != "-" else texto)
        clave = clave_titulo(texto)
        corto = es_titulo_corto(texto)
        if es_seccion_conocida(clave) and corto and len(clave.split()) <= 6 and (
                bold or numpr is not None or len(texto.split()) <= 5):
            t = (marcador + " " + texto) if marcador and marcador != "-" else texto
            return bloque_h(min(profundidad_numeracion(t) or 1, 3), t)
        if numpr is not None:
            nivel_l = numpr[1]
            ms = re.match(r"^(list|lista).*?(\d)$", norm(nombre))
            if ms and nivel_l == 0:
                nivel_l = int(ms.group(2)) - 1
            return {"k": "li", "marcador": marcador, "texto": texto, "nivel": min(nivel_l, 3)}
        if bold and corto and not texto.endswith((".", ",", ";", ":")):
            prof = profundidad_numeracion(texto) or 2
            if RE_ROMANO.match(texto):
                prof = 1
            return bloque_h(min(prof, 3), texto)
        return {"k": "p", "texto": texto}

    def _tabla(self, el):
        filas = _tabla_docx(el, self.ctx)
        if not filas:
            return
        if len(filas) == 1 and len(filas[0]) == 1:
            self.bloques.append({"k": "p", "texto": filas[0][0]})
        else:
            self.bloques.append({"k": "tabla", "filas": filas})
            self.d.tablas += 1


class ExtractorDocx(Extractor):
    extensiones = (".docx",)

    def extraer(self, path):
        from lxml import etree
        with zipfile.ZipFile(path) as z:
            ctx = _ContextoDocx(z, etree)
            d = DocumentoExtraido()
            conv = _ConversionDocx(ctx, d)
            conv.procesar(etree.fromstring(z.read("word/document.xml")).find("w:body", NS))
            d.bloques = conv.bloques
            d.encabezado = self._encabezados_y_pies(z, ctx, d)
            # texto crudo independiente (regex sobre el XML)
            crudo = _crudo_docx_xml(z.read("word/document.xml"))
            if "word/footnotes.xml" in z.namelist():
                crudo += " " + _crudo_docx_xml(z.read("word/footnotes.xml"))
            d.crudo = collections.Counter(tokens(crudo))
            d.numeros = numeros(crudo)
            d.paginas = self._paginas(ctx)
        return d

    @staticmethod
    def _encabezados_y_pies(z, ctx, d):
        """Lineas de encabezados y pies (una sola vez cada texto distinto)."""
        vistos = []
        nombres = [n for n in z.namelist() if re.match(r"word/(header|footer)\d*\.xml$", n)]
        for n in sorted(nombres, key=lambda x: (0 if "header" in x else 1, x)):
            r = ctx.etree.fromstring(z.read(n))
            lineas = []
            for el in r:
                if _local(el) == "p":
                    t, _, cuadros, _ = ctx.texto_parrafo(el)
                    if t:
                        lineas.append(t)
                    for cb in cuadros:
                        for p in cb.findall("w:p", NS):
                            tt = ctx.texto_parrafo(p)[0]
                            if tt:
                                lineas.append(tt)
                elif _local(el) == "tbl":
                    for f in _tabla_docx(el, ctx):
                        lineas.append(" · ".join(c for c in f if c))
            for l in lineas:
                if l not in vistos:
                    vistos.append(l)
            d.crudo_encabezado.update(tokens(_crudo_docx_xml(z.read(n))))
        return vistos

    @staticmethod
    def _paginas(ctx):
        try:
            pg = ctx.leer("docProps/app.xml").find(NS_APP + "Pages")
            return int(pg.text) if pg is not None and pg.text else 0
        except Exception:
            return 0
