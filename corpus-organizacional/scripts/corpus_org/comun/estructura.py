"""Estructura publicada en dos skills de Copilot.

- ``corpus-documentos``: un Markdown por tipo y area, en una carpeta por tipo (DES/, PRD/, PRO/, POL/).
- ``corpus-contexto``: ``scripts/corpus.py`` con el paquete ``corpus_org`` y, en ``datos/``, el indice,
  el inventario, la matriz maestra (xlsx y un CSV por hoja), los documentos generales (ORG_GEN.md...)
  y las huellas.

En Copilot cada skill queda en /home/oai/skills/appCatalog/<id>/<nombre-skill>/ y el <id> cambia, por
eso corpus.py busca la carpeta de cada skill por su nombre.
"""

from pathlib import Path

SKILL_DOCUMENTOS = "corpus-documentos"
SKILL_CONTEXTO = "corpus-contexto"
CARPETA_DATOS = "datos"           # dentro de corpus-contexto
CARPETA_MATRIZ = "matriz"         # dentro de datos/: un CSV por hoja de la matriz maestra
RAIZ_SKILLS_COPILOT = Path("/home/oai/skills/appCatalog")
NOMBRE_SKILL_MD = "SKILL.md"


def rutas_publicadas(publicado):
    """(skill corpus-contexto, su carpeta datos/, skill corpus-documentos) dentro de salida_corpus/publicado."""
    publicado = Path(publicado)
    contexto = publicado / SKILL_CONTEXTO
    return contexto, contexto / CARPETA_DATOS, publicado / SKILL_DOCUMENTOS


def markdown_de_documentos(carpeta_documentos):
    """Markdown de documentos de un skill corpus-documentos (todas las carpetas de tipo, sin SKILL.md)."""
    carpeta = Path(carpeta_documentos)
    if not carpeta.is_dir():
        return []
    return sorted(p for p in carpeta.rglob("*.md") if p.name != NOMBRE_SKILL_MD)


def _excluido_de_huellas(p):
    return (p.name in (NOMBRE_SKILL_MD, "huellas.sha256") or p.suffix == ".pyc"
            or "__pycache__" in p.parts)


def archivos_de_huellas(publicado):
    """Archivos de las dos skills cuya huella se guarda (sin SKILL.md, editable, ni cache de Python)."""
    publicado = Path(publicado)
    archivos = []
    for skill in (SKILL_CONTEXTO, SKILL_DOCUMENTOS):
        carpeta = publicado / skill
        if carpeta.is_dir():
            archivos += [p for p in carpeta.rglob("*") if p.is_file() and not _excluido_de_huellas(p)]
    return sorted(archivos, key=lambda p: p.relative_to(publicado).as_posix())
