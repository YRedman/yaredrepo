"""Registro de comandos de ``corpus.py`` (en el orden en que se muestran en la ayuda)."""

from .area import IndiceArea
from .briefing import Briefing
from .buscar import Buscar
from .cadena import Cadena
from .catalogo import Catalogo
from .checklist import Checklist
from .citar import Citar
from .doc import Documento
from .donde import Donde
from .ficha import Ficha
from .gobierno import Gobierno
from .kpis import Indicadores
from .llenar_k4 import LlenarK4
from .normativa import Normativa
from .participacion import Participacion
from .procesos import Procesos
from .relaciones import Relaciones
from .vaciar import Vaciar
from .verificar import Verificar

COMANDOS = {c.nombre: c for c in (Donde(), Catalogo(), IndiceArea(), Briefing(), Ficha(), Documento(), Buscar(), Relaciones(),
                                   Participacion(), Gobierno(), Procesos(), Indicadores(), Normativa(), Cadena(), Citar(), Verificar(), Vaciar(), LlenarK4(), Checklist())}
