"""Paquete del corpus publicado para el conocimiento de un agente de Copilot (limite de archivos).

Copilot no ejecuta corpus.py: solo lee archivos. El paquete tiene un indice de documentos en Markdown,
el contexto, los indicadores y los documentos agrupados por area en pocos archivos, sin superar
``max_archivos``. Las instrucciones del agente se escriben aparte (no cuentan como conocimiento).
"""

import re
import shutil
from pathlib import Path

from ..comun.archivos import leer_csv, leer_texto
from ..comun.errores import CorpusError
from ..comun.esquema import (ARCHIVO_INDICE, ARCHIVO_KPIS, ARCHIVO_RESUMEN, ARCHIVO_REVISION, AVISO_ESCANEADO,
                             estado_no_publicable)
from ..comun.estructura import rutas_publicadas
from ..comun.markdown import esc_celda
from ..comun.tipos import PATRON_CODIGO, RE_ARCHIVO_DOCUMENTOS, TIPOS_AREA

CARPETA_COPILOT = "copilot"
ARCHIVO_INSTRUCCIONES = "instrucciones_copilot.md"
MAX_ARCHIVOS = 20
RE_RESULTADO = re.compile(r"Resultado:\s*\**([^*\n]+)")


def _repartir(archivos, cupos):
    """Reparte los archivos (en orden) en ``cupos`` grupos contiguos de tamano parecido."""
    if len(archivos) <= cupos:
        return [[a] for a in archivos]
    total = sum(a.stat().st_size for a in archivos)
    grupos, actual, acumulado = [], [], 0
    for i, a in enumerate(archivos):
        restantes_archivos = len(archivos) - i
        restantes_cupos = cupos - len(grupos)
        if actual and (restantes_archivos < restantes_cupos
                       or acumulado + a.stat().st_size / 2 > total * (len(grupos) + 1) / cupos):
            grupos.append(actual)
            actual = []
        actual.append(a)
        acumulado += a.stat().st_size
    grupos.append(actual)
    return grupos


def _estado(raiz):
    resumen = raiz / ARCHIVO_RESUMEN
    m = RE_RESULTADO.search(leer_texto(resumen)) if resumen.is_file() else None
    return m.group(1).strip() if m else "desconocido"


def _pendientes(raiz):
    p = raiz / "control" / ARCHIVO_REVISION
    return {(f.get("codigo") or "").upper() for f in leer_csv(p) if not (f.get("revisado") or "").strip()} \
        if p.is_file() else set()


def _nota(fila, pendientes):
    if AVISO_ESCANEADO in (fila.get("detalle_avisos") or "") or (fila.get("palabras") or "").strip() == "0":
        return "SIN TEXTO (escaneado): no hay contenido"
    if (fila.get("paginas_ocr") or "").strip() and (fila.get("codigo") or "").upper() not in pendientes:
        return "leído con OCR (escaneado)"
    if estado_no_publicable(fila.get("estado_documental", "")):
        return f"excluido ({fila.get('estado_documental')})"
    if (fila.get("codigo") or "").upper() in pendientes:
        return "pendiente de revisión"
    return ""


def _indice(filas, ubicacion, estado, pendientes):
    sin_texto = [f for f in filas if _nota(f, pendientes).startswith("SIN TEXTO")]
    l = ["# Índice del corpus organizacional", "",
         f"Estado de la construcción: **{estado}**. Documentos: {len(filas)}; sin texto (escaneados): "
         f"{len(sin_texto)}. Cada documento está en el archivo indicado en la columna «Archivo», donde empieza "
         "con «## [CÓDIGO]».", "",
         "| Código | Tipo | Área | Área propietaria | Documento / puesto | Reporta a | Supervisa a | Versión | "
         "Vigencia | Archivo | Nota |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for f in filas:
        nombre = f.get("nombre_puesto") or f.get("nombre") or ""
        celdas = [f.get("codigo"), f.get("tipo"), f.get("departamento"), f.get("area_propietaria"), nombre,
                  f.get("reporta_a"), f.get("supervisa_a"),
                  f.get("version"), f.get("fecha_vigencia"), ubicacion.get((f.get("codigo") or "").upper(), ""),
                  _nota(f, pendientes)]
        l.append("| " + " | ".join(esc_celda(c or "—") for c in celdas) + " |")
    return "\n".join(l) + "\n"


def _kpis(path):
    filas = leer_csv(path)
    if not filas:
        return None
    columnas = list(filas[0].keys())
    l = ["# Indicadores (KPIs)", "", "| " + " | ".join(columnas) + " |", "|" + "---|" * len(columnas)]
    l += ["| " + " | ".join(esc_celda(f.get(c) or "") for c in columnas) + " |" for f in filas]
    return "\n".join(l) + "\n"


def _instrucciones(estado):
    return f"""Eres un asistente que responde preguntas sobre la estructura organizacional usando SOLO los archivos de conocimiento del corpus. Son la única fuente de verdad: no uses conocimiento general ni supongas datos.

CÓMO ESTÁ ORGANIZADO
- "00_indice_corpus.md": una fila por documento con código, tipo, área, área propietaria, puesto, a quién reporta, a quién supervisa, versión, vigencia, el archivo donde está el documento y una nota. Úsalo para localizar, contar y filtrar.
- "NN_DES_*.md", "NN_PRD_*.md", "NN_PRO_*.md", "NN_POL_*.md": los documentos completos, agrupados por tipo y área. Cada uno empieza con "## [TTT-AAA-NN] Título": TTT es el tipo (DES descriptivo de puesto, PRD procedimiento, PRO protocolo, POL política), AAA la sigla del área (GEN = aplica a varias áreas o a toda la empresa) y NN el número.
- "01_contexto.md" e "02_indicadores.md" (si están): documentos generales (ORG organigrama, KPI indicadores, GLO glosario, MPR mapa de procesos…, todos con área GEN) e indicadores.
- Las líneas que empiezan con ">" son metadatos de la conversión, no texto del original.
- "[NO ESPECIFICADO]" significa que el original no trae ese dato. "[ORGANIGRAMA: …]" seguido de "Jefe → Puesto" resume el organigrama del original.

REGLAS
1. Cita el código del documento entre corchetes, por ejemplo [DES-CAL-01], junto a cada dato.
2. Copia literalmente funciones, objetivos y requisitos cuando pidan qué dice el documento. Si resumes, dilo.
3. Si algo no está en el corpus, responde "No está en los documentos del corpus". No completes con suposiciones.
4. Marca como [Inferido] cualquier deducción propia y explica de dónde sale.
5. "Reporta a" sale de "Subordinación directa" o del organigrama; "Supervisa a", de "Reporte directo". Pares, Equipo Interdisciplinario, Subordinación Indirecta y Matricial son relaciones, no líneas de mando.
6. Si la nota del índice dice "SIN TEXTO (escaneado)", el corpus no tiene el contenido de ese documento: dilo así y no inventes sus funciones.
7. Si la nota dice "pendiente de revisión", añade "Pendiente de revisión contra el original" al usar ese documento.
8. Para contar o listar (cuántos puestos tiene un área, quién reporta a quién) usa el índice completo y confirma en el documento.
9. Responde en español, claro y breve; usa tablas para comparar.

Estado de la construcción del corpus: {estado}.
"""


def exportar_copilot(raiz, max_archivos=MAX_ARCHIVOS):
    """Escribe <raiz>/copilot/ (conocimiento, como maximo ``max_archivos``) y <raiz>/instrucciones_copilot.md.

    ``raiz`` es la carpeta de salida de ``construir`` (la que contiene publicado/). Devuelve la carpeta.
    """
    raiz = Path(raiz)
    _contexto, datos, documentos = rutas_publicadas(raiz / "publicado")
    indice_p = datos / ARCHIVO_INDICE
    if not indice_p.is_file():
        raise CorpusError(f"No existe {indice_p}: ejecute primero 'construir'.")
    if max_archivos < 4:
        raise CorpusError("Se necesitan al menos 4 archivos (índice, contexto, indicadores y documentos).")
    destino = raiz / CARPETA_COPILOT
    if destino.is_dir():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)

    filas = [f for f in leer_csv(indice_p) if (f.get("codigo") or "").strip()]
    estado, pendientes = _estado(raiz), _pendientes(raiz)
    extras = []
    generales = sorted(p for p in datos.glob("*.md") if RE_ARCHIVO_DOCUMENTOS.match(p.name))
    if generales:
        extras.append(("01_contexto.md", "\n\n".join(leer_texto(p).strip() for p in generales) + "\n"))
    if (datos / ARCHIVO_KPIS).is_file():
        texto = _kpis(datos / ARCHIVO_KPIS)
        if texto:
            extras.append(("02_indicadores.md", texto))
    cupos = max_archivos - 1 - len(extras)

    por_tipo = [(t, sorted((documentos / t).glob(f"{t}_*.md"))) for t in TIPOS_AREA]
    por_tipo = [(t, docs) for t, docs in por_tipo if docs]
    ubicacion = {}
    n = 3
    for k, (t, docs) in enumerate(por_tipo):
        # cada tipo restante necesita al menos un archivo
        cupos_tipo = max(1, cupos - (len(por_tipo) - k - 1)) if k == len(por_tipo) - 1 else \
            max(1, round(cupos * sum(p.stat().st_size for p in docs)
                         / max(1, sum(p.stat().st_size for _, ds in por_tipo[k:] for p in ds))))
        cupos_tipo = min(cupos_tipo, max(1, cupos - (len(por_tipo) - k - 1)))
        for grupo in _repartir(docs, cupos_tipo):
            siglas = [RE_ARCHIVO_DOCUMENTOS.match(p.name).group(2) for p in grupo]
            nombre = f"{n:02d}_{t}_{siglas[0]}" + (f"-{siglas[-1]}" if len(siglas) > 1 else "") + ".md"
            partes = [leer_texto(p).strip() for p in grupo]
            (destino / nombre).write_text("\n\n".join(partes) + "\n", encoding="utf-8")
            for texto in partes:
                for codigo in re.findall(rf"^## \[({PATRON_CODIGO})\]", texto, re.M):
                    ubicacion[codigo] = nombre
            n += 1
            cupos -= 1
    for nombre, texto in extras:
        (destino / nombre).write_text(texto, encoding="utf-8")
        for codigo in re.findall(rf"^## \[({PATRON_CODIGO})\]", texto, re.M):
            ubicacion[codigo] = nombre
    (destino / "00_indice_corpus.md").write_text(_indice(filas, ubicacion, estado, pendientes), encoding="utf-8")
    (raiz / ARCHIVO_INSTRUCCIONES).write_text(_instrucciones(estado), encoding="utf-8")
    return destino
