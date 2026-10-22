"""Scripts de consulta que se publican en fuente-corpus/scripts/.

Copilot admite como maximo 3 niveles de carpetas por skill, asi que ``corpus_org`` se publica sin
subcarpetas: cada modulo de ``comun/`` y ``consulta/`` pasa a un archivo con su ruta como nombre
(``consulta/comandos/base.py`` -> ``consulta_comandos_base.py``) y sus imports relativos se reescriben.
El codigo de conversion (``convertir.py`` y ``corpus_org/conversion``) no se publica: el agente no
construye el corpus.
"""

import re
from pathlib import Path

CARPETA_SCRIPTS = Path(__file__).resolve().parents[2]      # scripts/ del repositorio
PAQUETES_PUBLICADOS = ("comun", "consulta")
RE_IMPORT_RELATIVO = re.compile(r"^(?P<sangria>[ \t]*)from (?P<puntos>\.+)(?P<modulo>[\w.]*) import (?P<resto>.*)$",
                                re.M)


def nombre_plano(partes):
    """Nombre del archivo plano de un modulo: ('consulta', 'comandos', 'base') -> consulta_comandos_base."""
    return "_".join(partes)


def _modulos(origen):
    """{tupla de partes del modulo: (archivo, paquete en el que esta)} de los modulos a publicar.

    Un ``__init__.py`` es el modulo de su carpeta (``consulta/comandos/__init__.py`` -> ('consulta', 'comandos'));
    el ``__init__.py`` raiz (VERSION) es ().
    """
    mods = {}
    for archivo in sorted(Path(origen).rglob("*.py")):
        rel = archivo.relative_to(origen)
        carpetas = list(rel.parts[:-1])
        if carpetas and carpetas[0] not in PAQUETES_PUBLICADOS:
            continue
        if "__pycache__" in rel.parts:
            continue
        partes = carpetas if rel.name == "__init__.py" else carpetas + [rel.stem]
        mods[tuple(partes)] = (archivo, carpetas)
    return mods


def _reescribir(texto, paquete, modulos):
    """Reescribe los imports relativos de un modulo para el paquete plano."""
    def cambiar(m):
        puntos, modulo, resto = len(m["puntos"]), m["modulo"], m["resto"]
        sangria = m["sangria"]
        if puntos - 1 > len(paquete):
            raise ValueError(f"import relativo fuera del paquete: {m.group(0)}")
        base = paquete[:len(paquete) - (puntos - 1)]
        if modulo:
            destino = tuple(base) + tuple(modulo.split("."))
            if destino not in modulos:
                raise ValueError(f"el modulo {'.'.join(destino)} no se publica: {m.group(0)}")
            return f"{sangria}from .{nombre_plano(destino)} import {resto}"
        if resto.lstrip().startswith("("):
            raise ValueError(f"import multilinea de submodulos no soportado: {m.group(0)}")
        lineas = []
        for item in (x.strip() for x in resto.split(",") if x.strip()):
            nombre = item.split(" as ")[0].strip()
            alias = item.split(" as ")[1].strip() if " as " in item else nombre
            if tuple(base) + (nombre,) in modulos:      # from . import parser -> el modulo plano
                lineas.append(f"{sangria}from . import {nombre_plano(tuple(base) + (nombre,))} as {alias}")
            elif base:                                  # un nombre definido en el __init__ de un paquete
                lineas.append(f"{sangria}from .{nombre_plano(base)} import {item}")
            else:                                       # un nombre del __init__ raiz (VERSION)
                lineas.append(f"{sangria}from . import {item}")
        return "\n".join(lineas)
    return RE_IMPORT_RELATIVO.sub(cambiar, texto)


def aplanar_paquete(origen, destino):
    """Escribe en ``destino`` el paquete ``corpus_org`` de ``origen`` sin subcarpetas. Devuelve los archivos."""
    origen, destino = Path(origen), Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    modulos = _modulos(origen)
    escritos = []
    for partes, (archivo, carpetas) in modulos.items():
        paquete = list(partes) if archivo.name == "__init__.py" else carpetas
        nombre = "__init__.py" if not partes else nombre_plano(partes) + ".py"
        texto = _reescribir(archivo.read_text(encoding="utf-8"), paquete, modulos)
        (destino / nombre).write_text(texto, encoding="utf-8")
        escritos.append(destino / nombre)
    return escritos


def copiar_scripts(carpeta_scripts, origen=None):
    """Publica corpus.py y el paquete corpus_org plano en ``carpeta_scripts`` (fuente-corpus/scripts)."""
    origen = Path(origen) if origen else CARPETA_SCRIPTS
    carpeta_scripts = Path(carpeta_scripts)
    if carpeta_scripts.is_dir():
        for p in sorted(carpeta_scripts.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
    carpeta_scripts.mkdir(parents=True, exist_ok=True)
    entrada = (origen / "corpus.py").read_text(encoding="utf-8")
    if "from corpus_org.consulta.cli import main" not in entrada:
        raise ValueError("corpus.py no importa corpus_org.consulta.cli: no se puede publicar")
    entrada = entrada.replace("from corpus_org.consulta.cli import main", "from corpus_org.consulta_cli import main")
    (carpeta_scripts / "corpus.py").write_text(entrada, encoding="utf-8")
    return [carpeta_scripts / "corpus.py"] + aplanar_paquete(origen / "corpus_org", carpeta_scripts / "corpus_org")
