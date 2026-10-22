"""Estructura publicada: UN solo skill listo para comprimir y subir a Copilot (el agente admite un skill por carga).

    salida_corpus/copilot/
      fuente-corpus/       SKILL.md  documentos/ (DES/ PRD/ PRO/ POL/: un .md por tipo y area)
                           contexto/ indice/ matriz/ scripts/

El ``SKILL.md`` es el del repositorio (junto a ``scripts/``): ``construir`` lo copia a la carpeta del skill. Copilot carga
el skill en /home/oai/skills/appCatalog/<carpeta>/fuente-corpus/ y la <carpeta> cambia, por eso ``corpus.py`` se localiza
por su propia ubicacion y, si hace falta, buscando ``fuente-corpus`` por su nombre.

Las versiones anteriores publicaban dos skills (``fuente-contexto`` y ``fuente-documentos``); esas carpetas se siguen
reconociendo al leer, pero ``construir`` ya no las genera.
"""

from dataclasses import dataclass
from pathlib import Path

SKILL_CORPUS = "fuente-corpus"     # el unico skill publicado
SKILL_DOCUMENTOS = "fuente-documentos"     # estructura anterior (dos skills): solo para reconocerla
SKILL_CONTEXTO = "fuente-contexto"         # estructura anterior
CARPETA_DOCUMENTOS = "documentos"  # dentro del skill: DES/ PRD/ PRO/ POL/
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

El skill cargado **no** está en `/home/oai/skills/fuente-corpus`. Queda en una carpeta intermedia que cambia en cada carga:
`/home/oai/skills/appCatalog/<carpeta>/fuente-corpus`. No adivines la ruta; localízala primero:

```bash
find /home/oai/skills -type f -path '*fuente-corpus/scripts/corpus.py' 2>/dev/null | head -1
```

Ejecuta `corpus.py` con esa ruta completa (funciona desde cualquier carpeta). `python <ruta>/corpus.py donde` muestra dónde
está el skill y el comando listo para copiar; `python <ruta>/corpus.py verificar` también lo informa.

Si `find` no devuelve nada, o `corpus.py` dice «no encuentro el skill…», es un problema de localización, no de datos:
carga primero el skill `fuente-corpus` (lee su SKILL.md) y repite. Nunca concluyas que un documento o un área «no está
en el corpus» sin haber localizado antes el skill.
"""

# Limites de Copilot para los skills de un agente
MAX_NIVELES = 3                    # niveles de carpetas contando la del skill: fuente-corpus/scripts/corpus_org
MAX_BYTES_ARCHIVO = 25 * 1024 * 1024
MAX_BYTES_SKILL = 50 * 1024 * 1024
MAX_ARCHIVOS_AGENTE = 350
BYTES_DIVIDIR_MD = 20 * 1024 * 1024    # un Markdown mas grande se divide en partes


@dataclass(frozen=True)
class Rutas:
    raiz: Path                 # salida_corpus/copilot
    skill: Path                # fuente-corpus: el unico skill
    documentos: Path           # fuente-corpus/documentos
    contexto: Path
    indice: Path
    matriz: Path
    scripts: Path

    @property
    def skill_contexto(self):
        """Nombre anterior de ``skill`` (cuando habia dos skills): hoy es el mismo skill."""
        return self.skill


def rutas_de_skill(skill, documentos=None):
    """Carpetas de un skill: ``documentos`` es ``skill/documentos`` salvo que se indique otra (estructura anterior, con
    el skill fuente-documentos como hermano)."""
    skill = Path(skill)
    return Rutas(skill.parent, skill, Path(documentos) if documentos else skill / CARPETA_DOCUMENTOS,
                 skill / CARPETA_CONTEXTO, skill / CARPETA_INDICE, skill / CARPETA_MATRIZ, skill / CARPETA_SCRIPTS)


def rutas_publicadas(publicado):
    """Carpetas de la publicacion (``publicado`` = salida_corpus/copilot)."""
    return rutas_de_skill(Path(publicado) / SKILL_CORPUS)


def rutas_de_skill_contexto(skill_contexto):
    """Compatibilidad: las carpetas a partir de la carpeta del skill. Con la estructura anterior (``fuente-contexto``
    con ``fuente-documentos`` al lado y sin ``documentos/`` dentro) los documentos son la carpeta hermana."""
    skill = Path(skill_contexto)
    if not (skill / CARPETA_DOCUMENTOS).is_dir() and (skill.parent / SKILL_DOCUMENTOS).is_dir():
        return rutas_de_skill(skill, skill.parent / SKILL_DOCUMENTOS)
    return rutas_de_skill(skill)


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
    """Archivos del skill cuya huella se guarda (sin SKILL.md, que edita el equipo, ni la cache)."""
    publicado = Path(publicado)
    archivos = [p for p in archivos_de_skill(publicado / SKILL_CORPUS)
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
        avisos.append(f"El skill suma {total} archivos y Copilot admite {MAX_ARCHIVOS_AGENTE} entre todos "
                      "los skills del agente.")
    lineas.append(f"Total: {total} archivos (límite de Copilot para todos los skills del agente: "
                  f"{MAX_ARCHIVOS_AGENTE})")
    return lineas, avisos
