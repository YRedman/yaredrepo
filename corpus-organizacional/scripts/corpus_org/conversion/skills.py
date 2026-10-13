"""Contenido de las dos skills publicadas: scripts de consulta y SKILL.md."""

import shutil
from pathlib import Path

from .. import VERSION
from ..comun.archivos import leer_texto
from ..comun.estructura import (CARPETA_DATOS, NOMBRE_SKILL_MD, SKILL_CONTEXTO, SKILL_DOCUMENTOS,
                                markdown_de_documentos)
from ..comun.tipos import POR_CODIGO, TIPOS_AREA, TIPOS_GENERALES

CARPETA_SCRIPTS = Path(__file__).resolve().parents[2]          # scripts/ (corpus.py y corpus_org/)
SKILL_MD_CONTEXTO = CARPETA_SCRIPTS.parent / NOMBRE_SKILL_MD     # SKILL.md del repositorio


def copiar_scripts(carpeta_skill):
    """Copia corpus.py y el paquete corpus_org a <skill>/scripts/. Devuelve los archivos copiados."""
    destino = carpeta_skill / "scripts"
    destino.mkdir(parents=True, exist_ok=True)
    copiados = [shutil.copy2(CARPETA_SCRIPTS / "corpus.py", destino / "corpus.py")]
    shutil.copytree(CARPETA_SCRIPTS / "corpus_org", destino / "corpus_org", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    copiados += [p for p in (destino / "corpus_org").rglob("*") if p.is_file()]
    return copiados


def _lista_tipos(codigos):
    return ", ".join(f"{c} ({POR_CODIGO[c].nombre.lower()})" for c in codigos)


def _skill_documentos(documentos):
    archivos = [p.relative_to(documentos).as_posix() for p in markdown_de_documentos(documentos)]
    lineas = [
        "---",
        f"name: {SKILL_DOCUMENTOS}",
        "description: >-",
        "  Texto completo de los documentos de área del corpus organizacional: descriptivos de puesto, "
        "procedimientos, protocolos y políticas, un archivo por tipo y área. Úsalo junto con el skill "
        f"{SKILL_CONTEXTO}, que tiene corpus.py, el índice y la matriz para localizar cada documento.",
        "---", "",
        "# Corpus organizacional · documentos", "",
        f"> Generado por `convertir.py` v{VERSION}. No edite estos archivos: se regeneran en cada construcción "
        f"y `corpus.py verificar` detecta los cambios.", "",
        "Este skill solo contiene datos. Para consultar, usa los comandos de `scripts/corpus.py` del skill "
        f"`{SKILL_CONTEXTO}`: localiza esta carpeta por su nombre.", "",
        "## Estructura", "",
        f"- Una carpeta por tipo: {_lista_tipos(TIPOS_AREA)}.",
        "- Un archivo por tipo y área: `DES/DES_SEG.md`, `PRD/PRD_SEG.md`, `POL/POL_GEN.md`…",
        "- Cada documento empieza con `## [TTT-AAA-NN] Título`: TTT es el tipo, AAA el área (GEN = aplica a "
        "varias áreas o a toda la empresa) y NN el número.",
        "- Las líneas que empiezan con `>` son metadatos de la conversión, no texto del original.", "",
        f"## Archivos ({len(archivos)})", "",
    ] + [f"- `{a}`" for a in archivos]
    return "\n".join(lineas) + "\n"


def _skill_contexto_minimo():
    return "\n".join([
        "---", f"name: {SKILL_CONTEXTO}", "description: >-",
        "  Consulta del corpus organizacional con scripts/corpus.py: índice, inventario, matriz y documentos "
        "generales.", "---", "",
        "# Corpus organizacional · contexto", "",
        f"- `scripts/corpus.py`: consulta (solo biblioteca estándar). Busca los documentos en el skill "
        f"`{SKILL_DOCUMENTOS}`.",
        f"- `{CARPETA_DATOS}/`: índice, inventarios, matriz y documentos generales ({_lista_tipos(TIPOS_GENERALES)}).",
        ""])


def escribir_skill_md(carpeta, nombre, datos, documentos):
    """Escribe <carpeta>/SKILL.md del skill ``nombre``. Devuelve la ruta."""
    destino = carpeta / NOMBRE_SKILL_MD
    if nombre == SKILL_DOCUMENTOS:
        texto = _skill_documentos(documentos)
    else:
        texto = leer_texto(SKILL_MD_CONTEXTO) if SKILL_MD_CONTEXTO.is_file() else _skill_contexto_minimo()
    destino.write_text(texto, encoding="utf-8")
    return destino
