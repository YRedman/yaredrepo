"""Extractor de imagenes sueltas (.png, .jpg...) usadas como material de contexto: capturas de tableros, fotos de
documentos, esquemas. El texto se lee con OCR y queda bajo una marca; sin OCR o sin texto legible solo queda la marca."""

from pathlib import Path

from ..modelo import DocumentoExtraido
from .base import Extractor
from .imagenes import texto_de_imagen

EXTENSIONES_IMAGEN = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")


class ExtractorImagen(Extractor):
    extensiones = EXTENSIONES_IMAGEN

    def extraer(self, path):
        d = DocumentoExtraido()
        d.paginas = 1
        bloques = []
        texto_de_imagen(d, bloques, "EL ARCHIVO", 1, Path(path).read_bytes())
        d.bloques = bloques
        if Path(path).suffix.lower() not in self.extensiones:
            d.notas.append(f"El archivo se llama «{Path(path).name}» pero es una imagen: se leyó con OCR.")
        return d
