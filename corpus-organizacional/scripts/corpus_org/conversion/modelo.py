"""Modelo intermedio de la conversion.

``DocumentoExtraido`` es lo que produce un extractor (PDF, Word...). ``Analisis``
es lo que se deduce de el. Separarlos evita que el analisis agregue atributos
sueltos al documento y que el resto del codigo tenga que adivinar con ``getattr``.
"""

import collections
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from ..comun.esquema import AVISO_ESCANEADO, CONFIANZA_OCR_REVISION, RE_MARCAS
from ..comun.texto import numeros, tokens


def bloque_h(nivel, texto):
    return {"k": "h", "nivel": nivel, "texto": texto}


@dataclass
class DocumentoExtraido:
    bloques: List[dict] = field(default_factory=list)       # dicts: h, p, li, tabla, marca
    encabezado: List[str] = field(default_factory=list)     # lineas de encabezado/pie (una sola vez)
    paginas: int = 0
    paginas_ocr: List[int] = field(default_factory=list)
    paginas_escaneadas_sin_ocr: List[int] = field(default_factory=list)
    diagramas: List[int] = field(default_factory=list)      # paginas con imagenes grandes
    imagenes_omitidas: int = 0
    tablas: int = 0
    crudo: collections.Counter = field(default_factory=collections.Counter)      # tokens del original
    crudo_encabezado: Set[str] = field(default_factory=set)
    crudo_ocr: Set[str] = field(default_factory=set)        # palabras leidas por OCR (su "original" es el OCR)
    retirados: collections.Counter = field(default_factory=collections.Counter)  # duplicados retirados a proposito
    notas: List[str] = field(default_factory=list)          # informacion para el reporte
    avisos: List[str] = field(default_factory=list)         # avisos de ESTRUCTURA: exigen revision visual
    numeros: collections.Counter = field(default_factory=collections.Counter)   # numeros completos del original
    texto_cruzado: Optional[Set[str]] = None                # tokens de un segundo motor (pdfplumber)
    idioma_ocr: Optional[str] = None
    confianzas_ocr: List[float] = field(default_factory=list)   # confianza de cada palabra leida por OCR
    unidad: str = "páginas"                                 # "hojas" (Excel) o "diapositivas" (PowerPoint) si no es un PDF/Word
    hoja_de_calculo: bool = False                           # Excel o CSV: una celda vacia es un dato, no una fila partida
    lineas_diag: List[tuple] = field(default_factory=list)  # (pagina, zona, texto) para ubicar faltantes

    @property
    def confianza_ocr(self):
        """Confianza media del OCR (0-100) o None si no hubo OCR."""
        return sum(self.confianzas_ocr) / len(self.confianzas_ocr) if self.confianzas_ocr else None

    @property
    def ocr_dudoso(self):
        """True si el OCR del documento necesita revision visual (confianza baja o desconocida)."""
        c = self.confianza_ocr
        return bool(self.paginas_ocr) and (c is None or c < CONFIANZA_OCR_REVISION)

    def registrar_original(self, texto, descontar_marcas=True):
        """Guarda las palabras y los numeros del texto del original, con los que se verifica el Markdown.

        Las marcas ([NO ESPECIFICADO], [D-XXX-01]...) se descuentan igual que en el Markdown generado."""
        self.crudo = collections.Counter(tokens(RE_MARCAS.sub(" ", texto) if descontar_marcas else texto))
        self.numeros = numeros(texto)


@dataclass
class Metadatos:
    """Gobierno documental. Solo contiene valores que aparecen literalmente con su etiqueta."""
    codigo_interno: str = ""
    version: str = ""
    estado_documental: str = ""
    fecha_vigencia: str = ""
    propietario: str = ""
    responsable: str = ""
    proceso: str = ""
    area_propietaria: str = ""     # area que emite una politica o protocolo


@dataclass
class Analisis:
    campos: Dict[str, str] = field(default_factory=dict)
    titulos: List[str] = field(default_factory=list)
    subprocedimientos: List[str] = field(default_factory=list)
    faltantes: List[str] = field(default_factory=list)
    actividades: List[str] = field(default_factory=list)
    codigos_citados: List[str] = field(default_factory=list)
    secciones_excluidas: List[str] = field(default_factory=list)
    secciones_diagrama: List[str] = field(default_factory=list)
    notas: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    excluidos: collections.Counter = field(default_factory=collections.Counter)
    excluidos_numeros: collections.Counter = field(default_factory=collections.Counter)
    metadatos: Metadatos = field(default_factory=Metadatos)


@dataclass
class Verificacion:
    total: int
    faltan: collections.Counter
    cobertura: float
    agregadas: List[str]
    cruz: List[str]
    origen: collections.Counter
    ejemplos: Dict[tuple, str]
    numeros_faltan: collections.Counter = field(default_factory=collections.Counter)

    @property
    def palabras_faltantes(self):
        return sum(self.faltan.values())


@dataclass
class DocumentoConvertido:
    """Resultado de convertir un archivo del inventario."""
    codigo: str
    archivo: str
    estado: str                        # OK, ERROR, NO ADJUNTO, PENDIENTE (tiempo)
    error: str = ""
    traza: str = ""
    doc: Optional[DocumentoExtraido] = None
    analisis: Optional[Analisis] = None
    verificacion: Optional[Verificacion] = None
    palabras: int = 0
    ruta: str = ""                     # ubicacion del original: "entrada/<ruta>" o "contexto/<ruta>"
    segundos: float = 0.0              # lo que tardo en convertirse (en su proceso)

    @property
    def ok(self):
        return self.estado == "OK"

    @property
    def avisos(self):
        """Avisos de estructura del documento: si hay alguno, se exige revision visual antes de publicar."""
        if not self.ok:
            return []
        d, v = self.doc, self.verificacion
        avisos = list(d.avisos) + list(self.analisis.avisos)
        if v.numeros_faltan:
            avisos.append("números del original que no aparecen completos: " + ", ".join(list(v.numeros_faltan)[:8]))
        if d.ocr_dudoso:
            conf = f"confianza {d.confianza_ocr:.0f} %" if d.confianza_ocr is not None else "confianza desconocida"
            avisos.append(f"OCR en {d.unidad} " + ", ".join(map(str, d.paginas_ocr)) + f" ({conf}): revisar contra el original")
        if d.paginas_escaneadas_sin_ocr:
            avisos.append(AVISO_ESCANEADO + ": " + ", ".join(map(str, d.paginas_escaneadas_sin_ocr)))
        return avisos

    def motivos_consola(self):
        """Razones de revision que se muestran en la consola al terminar la conversion."""
        if not self.ok:
            return [f"{self.estado} {self.error}".strip()]
        d, v, extra = self.doc, self.verificacion, []
        if v.cobertura < 100:
            ubic = ", ".join(f"p.{p} {z}" if p else z for (p, z), _n in v.origen.most_common(4))
            extra.append(f"texto presente {v.cobertura:.1f} % (faltan en: {ubic})")
        if v.agregadas:
            extra.append(f"{len(v.agregadas)} palabras que no están en el original")
        if d.ocr_dudoso:   # el OCR con confianza alta no necesita revision: no se lista
            conf = f" (confianza {d.confianza_ocr:.0f} %)" if d.confianza_ocr is not None else ""
            extra.append(f"OCR en {d.unidad} " + ", ".join(map(str, d.paginas_ocr)) + conf)
        if d.paginas_escaneadas_sin_ocr:
            extra.append("páginas escaneadas sin texto")
        if self.palabras == 0:
            extra.append("el documento no tiene texto")
        extra += [f"ESTRUCTURA: {a}" for a in self.avisos if not a.startswith(("OCR en", "páginas escaneadas"))]
        return extra

    def motivos_revision(self):
        """Lista de razones por las que conviene revisar el documento convertido."""
        if not self.ok:
            return [f"{self.estado} {self.error}".strip()]
        d, v, motivos = self.doc, self.verificacion, []
        if v.cobertura < 100:
            motivos.append(f"{v.palabras_faltantes} palabras del original no aparecen")
        if v.agregadas:
            motivos.append(f"{len(v.agregadas)} palabras que no están en el original")
        if v.cruz:
            motivos.append(f"{len(v.cruz)} palabras solo detectadas por el segundo motor")
        if d.paginas_ocr:
            motivos.append(f"OCR en {d.unidad} {', '.join(map(str, d.paginas_ocr))}")
        if d.paginas_escaneadas_sin_ocr:
            motivos.append(f"páginas escaneadas sin texto: {', '.join(map(str, d.paginas_escaneadas_sin_ocr))}")
        if self.palabras == 0:
            motivos.append("el documento no tiene texto")
        if self.analisis.faltantes:
            motivos.append("no especificado: " + ", ".join(self.analisis.faltantes))
        if self.avisos:
            motivos.append(f"{len(self.avisos)} avisos de estructura")
        return motivos
