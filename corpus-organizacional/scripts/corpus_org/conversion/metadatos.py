"""Extraccion estricta de metadatos de gobierno documental (codigo, version, estado...).

Regla para evitar falsos positivos: un valor solo se acepta si aparece junto a
su etiqueta ("Estado: Vigente", o una celda "Estado" seguida de la celda
"Vigente") y si su forma es la esperada para ese campo. Nunca se deduce un
valor a partir de texto corrido ("el estado de cuenta..." no es un estado
documental) y un dato ausente queda vacio.
"""

import re
from dataclasses import dataclass

from ..comun.texto import norm
from .modelo import Metadatos

_LETRAS = "A-Za-zÁÉÍÓÚÜÑáéíóúüñ"


@dataclass(frozen=True)
class CampoMetadato:
    campo: str
    etiquetas: tuple
    valor: str                       # expresion que debe cumplir el valor completo
    max_palabras: int
    una_palabra: bool = False        # el valor es un solo token (codigo, version)
    sin_dos_puntos: str = ""         # expresion alternativa si la etiqueta no lleva ':'

    def acepta(self, valor, con_dos_puntos):
        if not valor or len(valor.split()) > self.max_palabras:
            return False
        if con_dos_puntos:
            return re.fullmatch(self.valor, valor) is not None
        return bool(self.sin_dos_puntos) and re.fullmatch(self.sin_dos_puntos, valor) is not None


CAMPOS = (
    CampoMetadato("codigo_interno", ("Código del documento", "Codigo del documento", "Código", "Codigo"),
                  r"[A-Z0-9][A-Z0-9\-_./]{2,30}", 1, una_palabra=True,
                  sin_dos_puntos=r"(?=[A-Z0-9\-_./]*\d)[A-Z0-9][A-Z0-9\-_./]{2,30}"),
    CampoMetadato("version", ("Versión", "Version", "Revisión", "Revision"),
                  r"(?=[\w.\-]*\d)[\w.\-]{1,20}|[A-Z]{1,2}", 1, una_palabra=True,
                  sin_dos_puntos=r"(?=[\w.\-]*\d)[\w.\-]{1,20}"),
    CampoMetadato("estado_documental", ("Estado documental", "Estado del documento", "Estado", "Estatus", "Status"),
                  rf"[{_LETRAS} ]{{2,40}}", 4),
    CampoMetadato("fecha_vigencia", ("Fecha de vigencia", "Vigente a partir de", "Vigente desde", "Vigencia"),
                  rf"[0-9{_LETRAS}/ .\-]{{4,40}}", 5),
    CampoMetadato("propietario", ("Propietario del proceso", "Propietario", "Dueño del proceso", "Dueño de proceso"),
                  r"[^·|]{2,80}", 10),
    CampoMetadato("responsable", ("Responsable del documento", "Responsable", "Elaborado por"),
                  r"[^·|]{2,80}", 10),
    CampoMetadato("proceso", ("Proceso",), r"[^·|]{2,120}", 12),
    CampoMetadato("area_propietaria", ("Área propietaria", "Area propietaria", "Área emisora", "Area emisora",
                                       "Área responsable", "Area responsable", "Área dueña", "Area duena"),
                  r"[^·|]{2,80}", 10),
)

# Etiquetas que no se extraen pero que delimitan el valor de la etiqueta anterior.
ETIQUETAS_DE_CORTE = (
    "Página", "Pagina", "Pág", "Hoja", "Fecha de emisión", "Fecha de elaboración", "Fecha de revisión",
    "Fecha de actualización", "Fecha", "Revisado por", "Aprobado por", "Autorizado por", "Departamento",
    "Área", "Area", "Gerencia", "Macroproceso", "Subproceso", "Título", "Nombre del documento", "Tipo de documento",
    "Próxima revisión", "Proxima revision", "Sustituye a", "Alcance",
)
RE_SEPARADOR_VALOR = re.compile(r"\s{2,}|\s*[·|]\s*|\n")


def _regex_etiquetas():
    todas = {e for c in CAMPOS for e in c.etiquetas} | set(ETIQUETAS_DE_CORTE)
    alternativas = "|".join(re.escape(e) for e in sorted(todas, key=len, reverse=True))
    return re.compile(rf"(?<![\w-])({alternativas})(?![\w-])\s*(:)?", re.I)


RE_ETIQUETA = _regex_etiquetas()
_CAMPO_POR_ETIQUETA = {norm(e): c for c in CAMPOS for e in c.etiquetas}


def _limpiar(valor):
    return valor.strip().strip(" .;,:").strip()


def _pares_en_linea(linea):
    """(campo, valor, con_dos_puntos) para cada etiqueta conocida en una linea de texto."""
    marcas = []
    for m in RE_ETIQUETA.finditer(linea):
        campo = _CAMPO_POR_ETIQUETA.get(norm(m.group(1)))
        con_dos_puntos = m.group(2) is not None
        # una etiqueta sin ':' solo cuenta si su campo admite esa forma (p. ej. "Versión 2")
        if con_dos_puntos or (campo and campo.sin_dos_puntos):
            marcas.append((m, campo, con_dos_puntos))
    for k, (m, campo, con_dos_puntos) in enumerate(marcas):
        if campo is None:
            continue
        fin = marcas[k + 1][0].start() if k + 1 < len(marcas) else len(linea)
        valor = RE_SEPARADOR_VALOR.split(linea[m.end():fin].strip(), maxsplit=1)[0]
        if campo.una_palabra:
            valor = (valor.split() or [""])[0]
        yield campo, _limpiar(valor), con_dos_puntos


def _pares_en_tabla(filas):
    """(campo, valor, True) para celdas 'Etiqueta' seguidas de su celda de valor."""
    for f in filas:
        for j in range(len(f) - 1):
            campo = _CAMPO_POR_ETIQUETA.get(norm(f[j]).rstrip(" :"))
            if campo is not None:
                valor = _limpiar(f[j + 1])
                if campo.una_palabra:
                    valor = (valor.split() or [""])[0]
                yield campo, valor, True
        for c in f:
            yield from _pares_en_linea(c)


def extraer_metadatos(encabezado, bloques_iniciales):
    """Metadatos tomados del encabezado/pie y de los primeros bloques del documento.

    El encabezado tiene prioridad. Para cada campo se usa la primera aparicion valida.
    """
    pares = []
    for linea in encabezado:
        pares.extend(_pares_en_linea(linea))
    for b in bloques_iniciales:
        if b["k"] == "tabla":
            pares.extend(_pares_en_tabla(b["filas"]))
        elif b.get("texto"):
            pares.extend(_pares_en_linea(b["texto"]))
    valores = {}
    for campo, valor, con_dos_puntos in pares:
        if campo.campo not in valores and campo.acepta(valor, con_dos_puntos):
            valores[campo.campo] = valor
    return Metadatos(**valores)
