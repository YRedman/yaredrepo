"""Excepciones del dominio.

Las capas internas nunca llaman a ``sys.exit`` ni imprimen errores: lanzan
estas excepciones y la capa de linea de comandos decide como mostrarlas.
"""


class CorpusError(Exception):
    """Error esperado que se muestra al usuario como ``ERROR: <mensaje>``."""

    def __init__(self, mensaje, codigo_salida=1):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo_salida = codigo_salida


class AreaAmbigua(CorpusError):
    def __init__(self, texto, candidatos):
        super().__init__(f"'{texto}' coincide con varias áreas.", 2)
        self.texto = texto
        self.candidatos = candidatos  # [(codigo, nombre)]


class AreaNoEncontrada(CorpusError):
    def __init__(self, texto, disponibles, sin_documentos=()):
        super().__init__(f"no hay un área llamada '{texto}'.", 2)
        self.texto = texto
        self.disponibles = disponibles  # [(codigo, nombre)]
        self.sin_documentos = list(sin_documentos)  # areas o entidades conocidas sin documentos propios
