"""Extractor de presentaciones de PowerPoint (.pptx) usadas como material de contexto.

Cada diapositiva es una seccion: su titulo, los textos de sus formas en orden de lectura (listas con su nivel),
las tablas, el texto de los diagramas SmartArt y las notas del orador. Los pies de diapositiva, la fecha y el numero
de diapositiva no son contenido y se omiten. Las imagenes con contenido (una captura, un esquema) se leen con OCR.
Solo usa la biblioteca estandar (zipfile y xml) mas, para las imagenes, Pillow y Tesseract.
"""

import collections
import posixpath
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from ...comun.esquema import RE_MARCAS
from ...comun.texto import numeros, tokens
from ..modelo import DocumentoExtraido, bloque_h
from .base import Extractor
from .imagenes import es_imagen_de_contenido, hash_imagen, texto_de_imagen

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "dgm": "http://schemas.openxmlformats.org/drawingml/2006/diagram"}
REL = "{" + NS["r"] + "}"
PLACEHOLDERS_DE_PIE = {"sldNum", "ftr", "dt", "hdr"}
PLACEHOLDERS_DE_TITULO = {"title", "ctrTitle"}
MAX_IMAGENES = 30
MIN_REPETICION_LOGO = 3        # una imagen que sale en 3 o mas diapositivas es un logo o un fondo
BUCKET_Y = 300000              # EMU (~0.33 in): formas a esta altura se leen de izquierda a derecha


def _local(el):
    return el.tag.rsplit("}", 1)[-1]


def _texto_parrafo(p):
    partes = []
    for el in p.iter():
        n = _local(el)
        if n == "t" and el.text:
            partes.append(el.text)
        elif n == "br":
            partes.append(" ")
    return " ".join("".join(partes).split())


def _parrafos(txbody, cuerpo=False):
    """[(texto, nivel, es_lista)] de un cuerpo de texto. En un marcador de cuerpo (``cuerpo``) las vinetas vienen
    del diseno de la diapositiva: todo parrafo es de lista salvo que diga ``buNone``."""
    res = []
    for p in txbody.findall("a:p", NS):
        t = _texto_parrafo(p)
        if not t:
            continue
        ppr = p.find("a:pPr", NS)
        nivel = int(ppr.get("lvl", 0)) if ppr is not None else 0
        sin_vineta = ppr is not None and ppr.find("a:buNone", NS) is not None
        lista = not sin_vineta and (cuerpo or (ppr is not None and (ppr.find("a:buChar", NS) is not None
                                                                   or ppr.find("a:buAutoNum", NS) is not None)))
        res.append((t, min(nivel, 3), lista))
    return res


def _posicion(sp):
    off = sp.find("p:spPr/a:xfrm/a:off", NS)
    if off is None:
        off = sp.find("p:xfrm/a:off", NS)           # graphicFrame
    if off is None:
        return None
    try:
        return int(off.get("y")), int(off.get("x"))
    except (TypeError, ValueError):
        return None


def _tipo_placeholder(sp):
    ph = sp.find("p:nvSpPr/p:nvPr/p:ph", NS)
    return ph.get("type", "body") if ph is not None else None


class _Lector:
    """Lee un .pptx abierto como zip."""

    def __init__(self, z):
        self.z = z
        self.nombres = set(z.namelist())

    def xml(self, nombre):
        return ET.fromstring(self.z.read(nombre))

    def rels(self, parte):
        """{id: ruta absoluta dentro del zip} de las relaciones de una parte."""
        carpeta, archivo = posixpath.split(parte)
        ruta = posixpath.join(carpeta, "_rels", archivo + ".rels")
        if ruta not in self.nombres:
            return {}
        res = {}
        for r in self.xml(ruta):
            destino = r.get("Target", "")
            if r.get("TargetMode") == "External":
                continue
            res[r.get("Id")] = posixpath.normpath(posixpath.join(carpeta, destino)) if not destino.startswith("/") \
                else destino.lstrip("/")
        return res

    def diapositivas(self):
        """[ruta de cada diapositiva] en el orden de la presentacion."""
        pres = self.xml("ppt/presentation.xml")
        rels = self.rels("ppt/presentation.xml")
        orden = []
        for sld in pres.iterfind("p:sldIdLst/p:sldId", NS):
            ruta = rels.get(sld.get(REL + "id"))
            if ruta in self.nombres:
                orden.append(ruta)
        return orden or sorted((n for n in self.nombres if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                               key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))


class ExtractorPptx(Extractor):
    extensiones = (".pptx",)

    def extraer(self, path):
        path = Path(path)
        try:
            z = zipfile.ZipFile(path)
        except zipfile.BadZipFile:
            raise RuntimeError("El archivo no es una presentación de PowerPoint válida (¿dañado?).")
        with z:
            lector = _Lector(z)
            if "ppt/presentation.xml" not in lector.nombres:
                raise RuntimeError("El archivo no es una presentación de PowerPoint (.pptx).")
            return self._extraer(lector, path)

    def _extraer(self, lector, path):
        d = DocumentoExtraido()
        bloques, textos = [], []
        diapositivas = lector.diapositivas()
        d.paginas = len(diapositivas)
        repeticion = self._imagenes_repetidas(lector, diapositivas)
        leidas, ocultas = 0, 0
        for n, ruta in enumerate(diapositivas, 1):
            raiz = lector.xml(ruta)
            if raiz.get("show") == "0":
                ocultas += 1
                continue
            titulo, cuerpo, imagenes = self._contenido(lector, ruta, raiz, d)
            encabezado = f"Diapositiva {n}" + (f": {titulo}" if titulo else "")
            bloques.append(bloque_h(1, encabezado))
            textos.append(encabezado)
            for b in cuerpo:
                bloques.append(b)
                textos += [b["texto"]] if "texto" in b else [c for f in b.get("filas", []) for c in f]
            for datos in imagenes:
                if repeticion[hash_imagen(datos)] >= MIN_REPETICION_LOGO or not es_imagen_de_contenido(datos):
                    continue
                if leidas >= MAX_IMAGENES:
                    d.imagenes_omitidas += 1
                    continue
                leidas += 1
                texto_de_imagen(d, bloques, f"LA DIAPOSITIVA {n}", n, datos)
            notas = self._notas(lector, ruta)
            if notas:
                bloques.append({"k": "p", "texto": "Notas del orador: " + " ".join(notas)})
                textos.append("Notas del orador: " + " ".join(notas))
        if ocultas:
            d.notas.append(f"{ocultas} diapositivas ocultas no se leyeron.")
        d.notas.append("Se omiten los pies de diapositiva, la fecha y el número de diapositiva.")
        d.bloques = bloques
        d.tablas = sum(1 for b in bloques if b["k"] == "tabla")
        todo = " ".join(textos)
        d.crudo = collections.Counter(tokens(RE_MARCAS.sub(" ", todo)))
        d.numeros = numeros(todo)
        if path.suffix.lower() != ".pptx":
            d.notas.append(f"El archivo se llama «{path.name}» pero es una presentación de PowerPoint: se leyó como tal.")
        return d

    # -- una diapositiva ------------------------------------------------------

    def _contenido(self, lector, ruta, raiz, d):
        """(titulo, [bloques], [bytes de imagenes]) de una diapositiva."""
        arbol = raiz.find("p:cSld/p:spTree", NS)
        rels = lector.rels(ruta)
        formas = []
        self._recorrer(arbol, formas)
        titulo, items, imagenes = "", [], []
        for sp in formas:
            n = _local(sp)
            ph = _tipo_placeholder(sp) if n == "sp" else None
            if ph in PLACEHOLDERS_DE_PIE:
                continue
            if n == "sp":
                tx = sp.find("p:txBody", NS)
                if tx is None:
                    continue
                parrafos = _parrafos(tx, cuerpo=ph in ("body", "obj"))
                if not parrafos:
                    continue
                if ph in PLACEHOLDERS_DE_TITULO and not titulo:
                    titulo = " ".join(t for t, _, _ in parrafos)
                    continue
                items.append((_posicion(sp), self._bloques_de_texto(parrafos)))
            elif n == "graphicFrame":
                items.append((_posicion(sp), self._bloques_de_grafico(lector, sp, rels, d)))
            elif n == "pic":
                emb = sp.find("p:blipFill/a:blip", NS)
                destino = rels.get(emb.get(REL + "embed")) if emb is not None else None
                if destino and destino in lector.nombres:
                    imagenes.append(lector.z.read(destino))
        if items and all(pos is not None for pos, _ in items):
            items.sort(key=lambda it: (it[0][0] // BUCKET_Y, it[0][1]))
        cuerpo = [b for _, bs in items for b in bs]
        return titulo, cuerpo, imagenes

    def _recorrer(self, nodo, salida):
        """Formas de un arbol en orden de documento, entrando a los grupos."""
        for hijo in nodo:
            n = _local(hijo)
            if n == "grpSp":
                self._recorrer(hijo, salida)
            elif n in ("sp", "graphicFrame", "pic"):
                salida.append(hijo)

    @staticmethod
    def _bloques_de_texto(parrafos):
        bloques = []
        for texto, nivel, lista in parrafos:
            if lista or nivel > 0:
                bloques.append({"k": "li", "marcador": "-", "texto": texto, "nivel": nivel})
            else:
                bloques.append({"k": "p", "texto": texto})
        return bloques

    def _bloques_de_grafico(self, lector, gf, rels, d):
        tabla = gf.find(".//a:tbl", NS)
        if tabla is not None:
            filas = [[_texto_parrafo(tc) for tc in tr.findall("a:tc", NS)] for tr in tabla.findall("a:tr", NS)]
            filas = [f for f in filas if any(f)]
            if filas:
                ancho = max(len(f) for f in filas)
                return [{"k": "tabla", "filas": [f + [""] * (ancho - len(f)) for f in filas]}]
            return []
        rel_ids = gf.find(".//dgm:relIds", NS)                        # SmartArt: el texto esta en la parte de datos
        if rel_ids is not None:
            datos = rels.get(rel_ids.get(REL + "dm"))
            if datos and datos in lector.nombres:
                frases = [_texto_parrafo(p) for p in lector.xml(datos).iter("{%s}p" % NS["a"])]
                frases = [f for f in frases if f]
                return [{"k": "li", "marcador": "-", "texto": f, "nivel": 0} for f in frases]
        if gf.find(".//{http://schemas.openxmlformats.org/drawingml/2006/chart}chart") is not None:
            d.diagramas.append(0)
            return [{"k": "marca", "texto": "[DIAGRAMA O IMAGEN: gráfico de la diapositiva; ver la presentación original]"}]
        return []

    @staticmethod
    def _notas(lector, ruta):
        for destino in lector.rels(ruta).values():
            if "notesSlides/" in destino and destino in lector.nombres:
                tx = [_texto_parrafo(p) for p in lector.xml(destino).iter("{%s}p" % NS["a"])]
                # el cuerpo de la nota es el marcador de texto, no el numero de diapositiva
                return [t for t in tx if t and not t.isdigit()]
        return []

    @staticmethod
    def _imagenes_repetidas(lector, diapositivas):
        """{hash: en cuantas diapositivas sale}: un logo o fondo repetido no es contenido."""
        cuenta = collections.Counter()
        for ruta in diapositivas:
            vistos = set()
            rels = lector.rels(ruta)
            for emb in lector.xml(ruta).iter("{%s}blip" % NS["a"]):
                destino = rels.get(emb.get(REL + "embed"))
                if destino and destino in lector.nombres:
                    vistos.add(hash_imagen(lector.z.read(destino)))
            cuenta.update(vistos)
        return collections.defaultdict(int, cuenta)
