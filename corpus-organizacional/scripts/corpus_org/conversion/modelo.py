"""Modelo intermedio de la conversion.

``DocumentoExtraido`` es lo que produce un extractor (PDF, Word...). ``Analisis``
es lo que se deduce de el. Separarlos evita que el analisis agregue atributos
sueltos al documento y que el resto del codigo tenga que adivinar con ``getattr``.
"""

import collections
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


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
    retirados: collections.Counter = field(default_factory=collections.Counter)  # duplicados retirados a proposito
    notas: List[str] = field(default_factory=list)          # avisos para el reporte
    texto_cruzado: Optional[Set[str]] = None                # tokens de un segundo motor (pdfplumber)
    idioma_ocr: Optional[str] = None
    lineas_diag: List[tuple] = field(default_factory=list)  # (pagina, zona, texto) para ubicar faltantes


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


@dataclass
class Analisis:
    campos: Dict[str, str] = field(default_factory=dict)
    titulos: List[str] = field(default_factory=list)
    subprocedimientos: List[str] = field(default_factory=list)
    faltantes: List[str] = field(default_factory=list)
    actividades: List[str] = field(default_factory=list)
    codigos_citados: List[str] = field(default_factory=list)
    secciones_excluidas: List[str] = field(default_factory=list)
    excluidos: collections.Counter = field(default_factory=collections.Counter)
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

    @property
    def ok(self):
        return self.estado == "OK"

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
        if d.paginas_ocr:
            extra.append("OCR en páginas " + ", ".join(map(str, d.paginas_ocr)))
        if d.paginas_escaneadas_sin_ocr:
            extra.append("páginas escaneadas sin texto")
        if self.palabras == 0:
            extra.append("el documento no tiene texto")
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
            motivos.append(f"OCR en páginas {', '.join(map(str, d.paginas_ocr))}")
        if d.paginas_escaneadas_sin_ocr:
            motivos.append(f"páginas escaneadas sin texto: {', '.join(map(str, d.paginas_escaneadas_sin_ocr))}")
        if self.palabras == 0:
            motivos.append("el documento no tiene texto")
        if self.analisis.faltantes:
            motivos.append("no especificado: " + ", ".join(self.analisis.faltantes))
        return motivos
