"""Contrato comun de los extractores de documentos."""

from abc import ABC, abstractmethod


class Extractor(ABC):
    """Convierte un archivo en un ``DocumentoExtraido``.

    Para soportar un formato nuevo se crea una subclase y se registra en
    ``extractores.registro``; el resto del pipeline no cambia.
    """

    extensiones = ()

    @abstractmethod
    def extraer(self, path):
        """Devuelve un ``DocumentoExtraido``."""
