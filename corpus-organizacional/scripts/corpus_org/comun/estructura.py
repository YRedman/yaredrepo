"""Estructura publicada: dos carpetas listas para comprimir y subir como skills de Copilot.

    salida_corpus/copilot/
      fuente-documentos/   DES/ PRD/ PRO/ POL/   (un .md por tipo y area)
      fuente-contexto/     contexto/ indice/ matriz/ scripts/

``SKILL.md`` de cada carpeta lo provee el equipo: el script nunca lo escribe ni lo borra.
En Copilot los skills cargados quedan en /home/oai/skills/appCatalog/<carpeta>/<skill>/ y la
<carpeta> cambia, por eso ``corpus.py`` busca ``fuente-documentos`` por su nombre.
"""

from dataclasses import dataclass
from pathlib import Path

SKILL_DOCUMENTOS = "fuente-documentos"
SKILL_CONTEXTO = "fuente-contexto"
CARPETA_PUBLICADA = "copilot"      # dentro de salida_corpus/
CARPETA_CONTEXTO = "contexto"      # documentos generales (ORG_GEN.md...) y kpis.csv
CARPETA_INDICE = "indice"          # indice, inventario, areas_extra, huellas, resumen, equivalencias
CARPETA_MATRIZ = "matriz"          # matriz_organizacional.xlsx y un CSV por hoja
CARPETA_SCRIPTS = "scripts"        # corpus.py y corpus_org/ (sin subcarpetas)
RAIZ_SKILLS_COPILOT = Path("/home/oai/skills/appCatalog")
NOMBRE_SKILL_MD = "SKILL.md"
ARCHIVO_NOTA_UBICACION = "NOTA_UBICACION_SKILL.md"
LLAVE_NOTA_UBICACION = "appCatalog"      # si el SKILL.md no la nombra, no explica donde quedan cargados los skills
NOTA_UBICACION_SKILL = """## Dónde está el corpus (léelo antes de ejecutar nada)

Los skills cargados **no** están en `/home/oai/skills/fuente-contexto`. Quedan en una carpeta intermedia que cambia en cada
carga: `/home/oai/skills/appCatalog/<carpeta>/fuente-contexto` (y `.../<otra carpeta>/fuente-documentos`). No adivines la
ruta; localízala primero:

```bash
find /home/oai/skills -type f -path '*fuente-contexto/scripts/corpus.py' 2>/dev/null | head -1
```

Ejecuta `corpus.py` con esa ruta completa (funciona desde cualquier carpeta). `python <ruta>/corpus.py donde` muestra dónde
están las dos carpetas y el comando listo para copiar; `python <ruta>/corpus.py verificar` también lo informa.

Si `find` no devuelve nada, o `corpus.py` dice «no encuentro el skill…», es un problema de localización, no de datos:
carga primero los skills `fuente-contexto` y `fuente-documentos` (lee su SKILL.md) y repite. Nunca concluyas que un
documento o un área «no está en el corpus» sin haber localizado antes las carpetas.
"""

# Limites de Copilot para los skills de un agente
MAX_NIVELES = 3                    # niveles de carpetas contando la del skill: fuente-contexto/scripts/corpus_org
MAX_BYTES_ARCHIVO = 25 * 1024 * 1024
MAX_BYTES_SKILL = 50 * 1024 * 1024
MAX_ARCHIVOS_AGENTE = 350
BYTES_DIVIDIR_MD = 20 * 1024 * 1024    # un Markdown mas grande se divide en partes


@dataclass(frozen=True)
class Rutas:
    raiz: Path                 # salida_corpus/copilot
    documentos: Path           # fuente-documentos
    skill_contexto: Path       # fuente-contexto
    contexto: Path
    indice: Path
    matriz: Path
    scripts: Path


def rutas_publicadas(publicado):
    """Carpetas de la publicacion (``publicado`` = salida_corpus/copilot)."""
    raiz = Path(publicado)
    skill = raiz / SKILL_CONTEXTO
    return Rutas(raiz, raiz / SKILL_DOCUMENTOS, skill, skill / CARPETA_CONTEXTO, skill / CARPETA_INDICE,
                 skill / CARPETA_MATRIZ, skill / CARPETA_SCRIPTS)


def rutas_de_skill_contexto(skill_contexto):
    """Las mismas carpetas a partir de la carpeta fuente-contexto (la de documentos es su hermana)."""
    return rutas_publicadas(Path(skill_contexto).parent)


def markdown_de_documentos(carpeta_documentos):
    """Markdown de documentos de un skill fuente-documentos (todas las carpetas de tipo, sin SKILL.md)."""
    carpeta = Path(carpeta_documentos)
    if not carpeta.is_dir():
        return []
    return sorted(p for p in carpeta.rglob("*.md") if p.name != NOMBRE_SKILL_MD)


def _es_temporal(p):
    """Archivos que no son del corpus: bloqueos de Office (~$x.xlsx), temporales (~x.tmp), .tmp y Thumbs.db."""
    n = p.name.lower()
    return n.startswith(("~$", ".~lock", ".~")) or n.endswith((".tmp", ".part")) or n in ("thumbs.db", ".ds_store")


def _es_cache(p):
    return p.suffix == ".pyc" or "__pycache__" in p.parts or _es_temporal(p)


def archivos_de_skill(carpeta):
    """Archivos de un skill (sin la cache de Python ni los temporales de Office, como ~$matriz.xlsx)."""
    carpeta = Path(carpeta)
    return sorted(p for p in carpeta.rglob("*") if p.is_file() and not _es_cache(p)) if carpeta.is_dir() else []


def archivos_de_huellas(publicado):
    """Archivos de las dos carpetas cuya huella se guarda (sin SKILL.md, que edita el equipo, ni la cache)."""
    publicado = Path(publicado)
    archivos = []
    for skill in (SKILL_CONTEXTO, SKILL_DOCUMENTOS):
        archivos += [p for p in archivos_de_skill(publicado / skill)
                     if p.name not in (NOMBRE_SKILL_MD, "huellas.sha256")]
    return sorted(archivos, key=lambda p: p.relative_to(publicado).as_posix())


def medir_skill(carpeta):
    """(numero de archivos, bytes, niveles de carpetas, archivo mas grande (ruta, bytes)) de un skill."""
    carpeta = Path(carpeta)
    archivos = archivos_de_skill(carpeta)
    tamanos = [(p, p.stat().st_size) for p in archivos]
    niveles = max((len(p.relative_to(carpeta).parts) for p in archivos), default=0)
    mayor = max(tamanos, key=lambda t: t[1], default=(None, 0))
    return len(archivos), sum(t for _, t in tamanos), niveles, mayor


def _mb(b):
    return f"{b / 1024 / 1024:.1f} MB"


def informe_limites(carpetas):
    """([lineas 'carpeta: N archivos · X MB'], [avisos]) de las carpetas de skill indicadas."""
    lineas, avisos, total = [], [], 0
    for carpeta in map(Path, carpetas):
        n, b, niveles, (mayor, mb) = medir_skill(carpeta)
        total += n
        lineas.append(f"{carpeta.name}: {n} archivos · {_mb(b)} · {niveles} niveles de carpetas")
        if b > MAX_BYTES_SKILL:
            avisos.append(f"{carpeta.name} pesa {_mb(b)} y Copilot admite {_mb(MAX_BYTES_SKILL)} por skill.")
        if mb > MAX_BYTES_ARCHIVO:
            avisos.append(f"{carpeta.name}: {mayor.name} pesa {_mb(mb)} y Copilot admite "
                          f"{_mb(MAX_BYTES_ARCHIVO)} por archivo.")
        if niveles > MAX_NIVELES:
            avisos.append(f"{carpeta.name} tiene {niveles} niveles de carpetas y Copilot admite {MAX_NIVELES}.")
    if total > MAX_ARCHIVOS_AGENTE:
        avisos.append(f"Las dos carpetas suman {total} archivos y Copilot admite {MAX_ARCHIVOS_AGENTE} entre todos "
                      "los skills del agente.")
    lineas.append(f"Total: {total} archivos (límite de Copilot para todos los skills del agente: "
                  f"{MAX_ARCHIVOS_AGENTE})")
    return lineas, avisos
