"""Localizacion de Tesseract (OCR de paginas escaneadas) y diagnostico de la instalacion.

En Windows el instalador no siempre agrega Tesseract al PATH (por ejemplo, sin permisos de
administrador). Se busca, en este orden: la variable TESSERACT_CMD, el PATH y las carpetas de
instalacion habituales.
"""

import os
import shutil
from pathlib import Path

IDIOMAS_OCR = ("spa", "eng")   # preferencia: espanol; ingles solo si no hay espanol


def rutas_candidatas():
    rutas = []
    if os.environ.get("TESSERACT_CMD"):
        rutas.append(os.environ["TESSERACT_CMD"])
    en_path = shutil.which("tesseract")
    if en_path:
        rutas.append(en_path)
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs") if os.environ.get("LOCALAPPDATA")
                 else None, r"C:\Program Files", r"C:\Program Files (x86)"):
        if base:
            rutas.append(os.path.join(base, "Tesseract-OCR", "tesseract.exe"))
    vistas = []
    for r in rutas:
        if r and r not in vistas:
            vistas.append(r)
    return vistas


def ejecutable_tesseract():
    """Ruta del ejecutable de Tesseract o None."""
    for r in rutas_candidatas():
        if Path(r).is_file():
            return r
    return None


def configurar_pytesseract():
    """Importa pytesseract apuntando al ejecutable encontrado. Devuelve el modulo o None."""
    try:
        import pytesseract
    except ImportError:
        return None
    exe = ejecutable_tesseract()
    if exe:
        pytesseract.pytesseract.tesseract_cmd = exe
    return pytesseract


def idioma_ocr():
    """'spa' o 'eng' si el OCR esta disponible; None si no."""
    pytesseract = configurar_pytesseract()
    if pytesseract is None:
        return None
    try:
        idiomas = pytesseract.get_languages(config="")
    except Exception:
        return None
    for idioma in IDIOMAS_OCR:
        if idioma in idiomas:
            return idioma
    return None


def diagnostico():
    """Lineas (ok, texto) con el estado de cada pieza necesaria para leer PDF y paginas escaneadas."""
    lineas = []
    try:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        lineas.append((True, f"PyMuPDF {getattr(fitz, 'VersionBind', '')}: lee los PDF digitales"))
    except ImportError:
        lineas.append((False, "Falta PyMuPDF: python -m pip install pymupdf"))
    for modulo, paquete in (("pytesseract", "pytesseract"), ("PIL", "pillow")):
        try:
            __import__(modulo)
            lineas.append((True, f"{paquete} instalado"))
        except ImportError:
            lineas.append((False, f"Falta {paquete}: python -m pip install {paquete}"))
    exe = ejecutable_tesseract()
    if not exe:
        lineas.append((False, "No encontré Tesseract. Instálelo (Windows: instalador de UB Mannheim) o indique su "
                              "ruta en la variable TESSERACT_CMD. Busqué en: " + "; ".join(rutas_candidatas())))
        return lineas
    lineas.append((True, f"Tesseract: {exe}"))
    pytesseract = configurar_pytesseract()
    if pytesseract is not None:
        try:
            idiomas = pytesseract.get_languages(config="")
            if "spa" in idiomas:
                lineas.append((True, "Idioma español (spa) instalado: el OCR está listo"))
            else:
                lineas.append((False, "Tesseract no tiene el idioma español (spa). Reinstálelo marcando "
                                      "'Additional language data' → Spanish, o copie spa.traineddata a su carpeta "
                                      "tessdata. Idiomas instalados: " + ", ".join(sorted(idiomas))))
        except Exception as e:
            lineas.append((False, f"Tesseract no responde: {e}"))
    return lineas
