"""Registro de extractores por formato de archivo (el real, no solo la extension)."""

import zipfile
from pathlib import Path

DESCRIPCION_FORMATOS = {".zip": "un archivo comprimido",
                        ".ole": "un archivo de Office antiguo (.doc, .xls, .ppt)"}


def formato_real(path):
    """Extension que corresponde al CONTENIDO del archivo (.pdf, .docx, .xlsx, .pptx, .zip, .ole), o None si parece
    texto. Un Excel guardado con extension .csv es un zip: leerlo como texto da letras sin sentido."""
    try:
        with open(path, "rb") as f:
            cabecera = f.read(8)
    except OSError:
        return None
    if cabecera.startswith(b"%PDF"):
        return ".pdf"
    if cabecera.startswith(b"\xd0\xcf\x11\xe0"):
        return ".ole"
    if cabecera.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(path) as z:
                nombres = set(z.namelist())
        except (zipfile.BadZipFile, OSError):
            return None
        if "xl/workbook.xml" in nombres:
            return ".xlsx"
        if "word/document.xml" in nombres:
            return ".docx"
        if "ppt/presentation.xml" in nombres:
            return ".pptx"
        return ".zip"
    return None


def extractor_para(path, verificacion_cruzada=True):
    """Extractor adecuado para ``path``. Las dependencias de cada formato se importan solo si se usan."""
    ext = Path(path).suffix.lower()
    real = formato_real(path)
    if real and real != ext and not (ext == ".xlsm" and real == ".xlsx"):
        if real in DESCRIPCION_FORMATOS:
            raise RuntimeError(f"El archivo se llama «{Path(path).name}» pero es {DESCRIPCION_FORMATOS[real]}: "
                               "guárdelo como PDF, Word o Excel (.xlsx).")
        ext = real
    if ext == ".pdf":
        from .pdf import ExtractorPDF
        return ExtractorPDF(verificacion_cruzada)
    if ext == ".docx":
        from .word import ExtractorDocx
        return ExtractorDocx()
    if ext == ".pptx":
        from .pptx import ExtractorPptx
        return ExtractorPptx()
    if ext in (".xlsx", ".xlsm"):
        from .excel import ExtractorExcel
        return ExtractorExcel()
    if ext in (".md", ".csv", ".txt"):
        from .texto import ExtractorTexto
        return ExtractorTexto()
    raise RuntimeError("Formato no soportado (.doc). Guárdelo como .docx o PDF.")
