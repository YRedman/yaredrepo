"""Areas y entidades sin documentos propios (areas_extra.csv) y frases que no son menciones de un area.

Formato de areas_extra.csv (separado por ';'):

    nombre;alias;tipo;nota
    Finanzas;Gerencia Financiera|Director Financiero;interna;
    ARS;Administradora de Riesgos de Salud;externa;
    Seguridad Social;;excluir;No es el area Seguridad

- ``interna``: area de la organizacion sin documentos en el corpus (o alias de un area que si tiene).
- ``externa``: proveedor, cliente, regulador...
- ``excluir``: frase que contiene el nombre de un area pero no la menciona.
"""

import re
from dataclasses import dataclass, field
from typing import List

from ..comun.archivos import leer_csv
from ..comun.texto import norm, patron_frase, sin_acentos

# Frases comunes que contienen el nombre de un area sin mencionarla ("Seguridad Social" no es el area Seguridad).
EXCLUSIONES_BASE = ("seguridad social", "seguridad y salud en el trabajo", "recursos naturales", "calidad de vida",
                    "tecnologia de punta", "servicio al cliente externo")
TIPOS_ENTIDAD = ("interna", "externa")


@dataclass
class EntidadExtra:
    nombre: str
    tipo: str                                   # interna | externa
    alias: List[str] = field(default_factory=list)

    @property
    def nombres(self):
        return [self.nombre] + self.alias

    def patrones(self):
        """Siglas y nombres de una palabra se buscan tal como estan escritos; los compuestos sin mayusculas."""
        pats = []
        for nombre in self.nombres:
            base = sin_acentos(nombre).strip()
            flags = 0 if (base.isupper() or len(base.split()) == 1) else re.I
            pats.append(patron_frase(base, flags))
        return pats


def leer_areas_extra(path):
    """(entidades, exclusiones) desde areas_extra.csv; sin archivo, solo las exclusiones base."""
    entidades, exclusiones = [], list(EXCLUSIONES_BASE)
    if path is None or not path.is_file():
        return entidades, exclusiones
    for f in leer_csv(path):
        nombre = (f.get("nombre") or "").strip()
        if not nombre:
            continue
        tipo = norm(f.get("tipo") or "interna")
        alias = [x.strip() for x in (f.get("alias") or "").split("|") if x.strip()]
        if tipo.startswith("exclu"):
            exclusiones += [norm(nombre)] + [norm(x) for x in alias]
        else:
            entidades.append(EntidadExtra(nombre, tipo if tipo in TIPOS_ENTIDAD else "interna", alias))
    return entidades, exclusiones


def quitar_exclusiones(texto, exclusiones):
    """Texto sin acentos y sin las frases excluidas (para que no cuenten como mencion de un area)."""
    t = sin_acentos(texto)
    for frase in exclusiones:
        t = patron_frase(sin_acentos(frase), re.I).sub(" ", t)
    return t
