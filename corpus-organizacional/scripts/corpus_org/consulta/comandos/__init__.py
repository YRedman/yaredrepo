"""Registro de comandos de ``corpus.py`` (en el orden en que se muestran en la ayuda)."""

from .area import IndiceArea
from .briefing import Briefing
from .buscar import Buscar
from .catalogo import Catalogo
from .doc import Documento
from .ficha import Ficha
from .gobierno import Gobierno
from .kpis import Indicadores
from .normativa import Normativa
from .participacion import Participacion
from .procesos import Procesos
from .relaciones import Relaciones
from .verificar import Verificar

COMANDOS = {c.nombre: c for c in (Catalogo(), IndiceArea(), Briefing(), Ficha(), Documento(), Buscar(), Relaciones(),
                                   Participacion(), Gobierno(), Procesos(), Indicadores(), Normativa(), Verificar())}
