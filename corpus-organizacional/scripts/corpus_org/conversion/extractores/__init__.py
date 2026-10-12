"""Registro de extractores por extension de archivo."""

from pathlib import Path


def extractor_para(path, verificacion_cruzada=True):
    """Extractor adecuado para ``path``. Las dependencias de cada formato se importan solo si se usan."""
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        from .pdf import ExtractorPDF
        return ExtractorPDF(verificacion_cruzada)
    if ext == ".docx":
        from .word import ExtractorDocx
        return ExtractorDocx()
    if ext in (".md", ".csv", ".txt"):
        from .texto import ExtractorTexto
        return ExtractorTexto()
    raise RuntimeError("Formato no soportado (.doc). Guárdelo como .docx o PDF.")
