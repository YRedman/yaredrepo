"""Lo que comparten las partes de la extraccion de un PDF: el documento leido, sus elementos y los datos de cada pagina."""

from ...modelo import DocumentoExtraido
from .lineas import lineas_pagina


class ContextoPDF:
    """Estado comun de la extraccion de un PDF concreto (una instancia por archivo)."""

    def __init__(self, fitz, doc_pdf):
        self.fitz = fitz
        self.pdf = doc_pdf
        self.d = DocumentoExtraido(paginas=len(doc_pdf))
        self.items = []            # (pagina, y0, x0, item)
        self.paginas_lineas = [lineas_pagina(p, fitz) for p in doc_pdf]
        self.alturas = [p.rect.height for p in doc_pdf]
        self.anchos = [p.rect.width for p in doc_pdf]
        self.cortes = []           # (corte_sup, corte_inf) de paginas con encabezado
        self.encabezado_guardado = False
        self._idioma = None

    def marca(self, pagina, y, x, texto):
        self.items.append((pagina, y, x, {"tipo": "marca", "texto": texto, "pagina": pagina}))

    def idioma_ocr(self):
        """Idioma de Tesseract ('' si no hay OCR disponible); se consulta una sola vez por documento."""
        if self._idioma is None:
            from ..ocr import idioma_ocr
            self._idioma = idioma_ocr() or ""
        return self._idioma
