"""Analisis de un documento extraido: secciones, campos clave, actividades y codigos citados."""

import collections
import difflib
import re

from ..comun.esquema import MARCA_COMBINADA
from ..comun.texto import norm, numeros, tokens
from .configuracion import (BLOQUES_INICIALES_METADATOS, CAMPO_OTRO, CAMPOS_CLAVE, COLUMNAS_ACTIVIDAD,
                            COLUMNAS_RESPONSABLE, ETIQUETAS_D, SECCIONES_P, SECCIONES_POR_TIPO, TIPOS_RELACION)
from .metadatos import extraer_metadatos
from .modelo import Analisis
from .secciones import buscar_alias, clave_titulo, es_excluida, es_seccion_conocida, etiqueta_exacta

# Codigos de otros documentos: al menos dos guiones (PR-ALM-001, NOM-035-STPS-2018).
# Asi no se confunden con normas o nombres como ISO-9001 o COVID-19.
RE_CODIGO_DOC = re.compile(r"\b[A-Z]{1,6}-[A-Z0-9]{2,6}-(?:[A-Z0-9]{1,6}-)?\d{1,4}\b")


def texto_bloque(b):
    if b["k"] == "tabla":
        return " ".join(" ".join(c.replace(MARCA_COMBINADA, "") for c in f) for f in b["filas"])
    return b.get("texto", "")


def analizar(doc, tipo):
    """Devuelve ``(bloques_publicables, Analisis)`` sin modificar ``doc``."""
    a = Analisis()
    bloques = _sustituir_diagramas(doc.bloques, a) if tipo == "P" else list(doc.bloques)
    bloques, secciones = _separar_secciones(bloques, tipo, a)
    a.campos = _campos_de_secciones(secciones)
    if tipo == "D":
        _campos_por_etiqueta(bloques, a.campos)
        _campos_por_relacionamiento(bloques, a.campos)
        _nombre_por_titulo(bloques, a.campos)
    a.subprocedimientos = [b["texto"] for _t, campo, bs in secciones if campo == "desarrollo"
                           for b in bs if b["k"] == "h"]
    a.titulos = [s[0] for s in secciones]
    a.faltantes = [nombre for campo, nombre in CAMPOS_CLAVE.get(tipo, []) if not a.campos.get(campo, "").strip()]
    # En materiales de contexto (glosarios, organigramas) las tablas "Etiqueta | Valor" son contenido,
    # no metadatos del documento: ahi solo se lee el encabezado.
    iniciales = [] if tipo == "C" else bloques[:BLOQUES_INICIALES_METADATOS]
    a.metadatos = extraer_metadatos(doc.encabezado, iniciales)
    a.actividades = _actividades(secciones) if tipo == "P" else []
    a.codigos_citados = _codigos_citados(doc.encabezado, bloques, a.metadatos.codigo_interno)
    a.avisos += avisos_de_estructura(bloques, len(doc.diagramas), doc.hoja_de_calculo)
    return bloques, a


def _excluir(a, b):
    """Registra el texto de un bloque que se omite a proposito (no cuenta como faltante en la verificacion)."""
    texto = texto_bloque(b)
    a.excluidos.update(tokens(texto))
    a.excluidos_numeros.update(numeros(texto))


def _es_titulo_diagrama(b):
    return b["k"] == "h" and buscar_alias(clave_titulo(b["texto"]), SECCIONES_P) == "diagrama"


def _marca_diagrama(titulo, paginas):
    pags = sorted(p + 1 for p in paginas if isinstance(p, int))
    if pags:
        ref = ("página " if len(pags) == 1 else "páginas ") + ", ".join(map(str, pags))
    else:
        ref = "el documento original"
    return {"k": "marca", "texto": f"[DIAGRAMA: la sección «{titulo}» no se transcribe; ver {ref}]"}


def _sustituir_diagramas(bloques, a):
    """El contenido de una seccion 'Diagrama...' (de cualquier nivel) se cambia por una marca.

    Un diagrama de flujo extraido como texto produce cajas sueltas sin orden ("Inicio", "Evaluar",
    "Aprobar"...) que se leerian como contenido del procedimiento. Sus palabras cuentan como
    excluidas a proposito y la marca remite a las paginas del original.
    """
    salida, diag = [], None

    def cerrar():
        if diag is not None:
            salida.append(_marca_diagrama(diag["titulo"], diag["paginas"]))
            a.secciones_diagrama.append(diag["titulo"])

    for b in bloques:
        if diag is not None:
            if b["k"] == "h" and b["nivel"] <= diag["nivel"]:
                cerrar()
                diag = None
            else:
                if b["k"] != "marca":
                    _excluir(a, b)
                diag["paginas"].add(b.get("pagina"))
                continue
        salida.append(b)
        if _es_titulo_diagrama(b):
            diag = {"nivel": b["nivel"], "titulo": b["texto"], "paginas": {b.get("pagina")}}
    cerrar()
    return salida


def _separar_secciones(bloques, tipo, a):
    """Quita las secciones excluidas y agrupa los bloques por seccion de primer nivel."""
    tabla_secciones = SECCIONES_POR_TIPO.get(tipo, [])
    nivel_base = min((b["nivel"] for b in bloques if b["k"] == "h"), default=1)
    resultado, secciones = [], []   # secciones: [titulo, campo, [bloques]]
    actual = None
    excluyendo = False
    for b in bloques:
        campo_titulo = _campo_de_titulo(b, tabla_secciones)
        if campo_titulo and actual is not None and actual[1] is None and not excluyendo:
            # un subtitulo o una tabla cuyo encabezado es una seccion conocida ("Función General/Objetivo
            # del Puesto:" bajo el titulo del puesto, "FUNCIONES ESPECÍFICAS" como cabecera de tabla)
            # abre una seccion logica aunque no sea un titulo de primer nivel
            actual = [_texto_titulo(b), campo_titulo, [] if b["k"] == "h" else [b]]
            secciones.append(actual)
            resultado.append(b)
            continue
        if b["k"] == "tabla" and campo_titulo and actual is not None and actual[1] != campo_titulo and not excluyendo:
            actual = [_texto_titulo(b), campo_titulo, [b]]
            secciones.append(actual)
            resultado.append(b)
            continue
        if b["k"] == "h" and b["nivel"] <= nivel_base:
            clave = clave_titulo(b["texto"])
            if es_excluida(clave):
                excluyendo = True
                a.secciones_excluidas.append(b["texto"])
                _excluir(a, b)
                continue
            excluyendo = False
            actual = [b["texto"], buscar_alias(clave, tabla_secciones) if tabla_secciones else None, []]
            secciones.append(actual)
            resultado.append(b)
            continue
        if excluyendo:
            _excluir(a, b)
            continue
        resultado.append(b)
        if actual is not None:
            actual[2].append(b)
    return resultado, secciones


def _texto_titulo(b):
    if b["k"] == "h":
        return b["texto"]
    return next((c for c in b["filas"][0] if c.strip()), "")


def _campo_de_titulo(b, tabla_secciones):
    """Campo de un subtitulo o de una tabla cuya primera celda con texto es el titulo de una seccion."""
    if not tabla_secciones:
        return None
    if b["k"] == "h":
        texto = b["texto"]
    elif b["k"] == "tabla" and b["filas"]:
        texto = _texto_titulo(b)
    else:
        return None
    clave = clave_titulo(texto)
    if not clave or len(clave.split()) > 8 or es_excluida(clave):
        return None
    return buscar_alias(clave, tabla_secciones)


# Campos de texto corrido: si la seccion tiene parrafos se usan solo ellos (una tabla o un organigrama
# que quedo en la misma seccion no es el objetivo del puesto).
CAMPOS_PROSA = {"proposito", "objetivo", "alcance"}


def _campos_de_secciones(secciones):
    campos = {}
    for _titulo, campo, bloques in secciones:
        if not campo or campo in campos:
            continue
        prosa = [b for b in bloques if b["k"] in ("p", "li")]
        usados = prosa if campo in CAMPOS_PROSA and prosa else [b for b in bloques if b["k"] not in ("h", "marca")]
        texto = " ".join(texto_bloque(b) for b in usados).strip()
        if texto:
            campos[campo] = texto
        elif any(b["k"] == "h" for b in bloques):
            campos[campo] = " ".join(texto_bloque(b) for b in bloques)
    return campos


def _etiqueta_d(texto):
    """Campo de la etiqueta de descriptivo con la que empieza ``texto`` ('Reporta a:' -> reporta_a)."""
    clave = clave_titulo(texto or "")
    if not clave or len(clave.split()) > 4:
        return None
    return buscar_alias(clave, ETIQUETAS_D)


def _es_etiqueta_d(texto):
    """True si el texto es exactamente una etiqueta: entonces nunca puede ser el valor de otro campo."""
    return etiqueta_exacta(texto, ETIQUETAS_D) is not None


def _guardar(campos, campo, valor):
    valor = valor.replace(MARCA_COMBINADA, "").strip()
    if campo and campo != CAMPO_OTRO and valor and campo not in campos and not _es_etiqueta_d(valor):
        campos[campo] = valor


def _es_fila_de_etiquetas(fila, siguiente):
    """Tabla horizontal: todas las celdas llenas son etiquetas y la fila siguiente no tiene ninguna."""
    llenas = [c for c in fila if c.strip()]
    return (len(llenas) >= 2 and all(_es_etiqueta_d(c) for c in llenas) and siguiente is not None
            and not any(_es_etiqueta_d(c) for c in siguiente if c.strip()))


def _campos_por_etiqueta(bloques, campos):
    """Datos del puesto (descriptivos) en tres formas:

    - tabla vertical "Etiqueta | Valor";
    - tabla horizontal (fila de etiquetas y debajo la fila de valores);
    - lineas "Etiqueta: valor".

    Un valor que es a su vez una etiqueta conocida no se acepta: en una tabla horizontal leida como
    vertical, "Nombre del puesto | Departamento" daba nombre_puesto = "Departamento".
    """
    for b in bloques:
        if b["k"] == "tabla":
            filas = b["filas"]
            i = 0
            while i < len(filas):
                f = filas[i]
                siguiente = filas[i + 1] if i + 1 < len(filas) else None
                if _es_fila_de_etiquetas(f, siguiente):
                    for j, celda in enumerate(f):
                        if j < len(siguiente):
                            _guardar(campos, etiqueta_exacta(celda, ETIQUETAS_D), siguiente[j])
                    i += 2
                    continue
                for j in range(len(f) - 1):
                    _guardar(campos, _etiqueta_d(f[j]), f[j + 1])
                i += 1
        elif b["k"] in ("p", "li"):
            m = re.match(r"^([^:]{2,40}):\s*(\S.*)$", b["texto"])
            if m:
                _guardar(campos, buscar_alias(clave_titulo(m.group(1)), ETIQUETAS_D), m.group(2))


def _columna(cabecera, prefijos):
    """Indice de la primera columna cuya cabecera empieza con alguno de ``prefijos`` (en orden de preferencia)."""
    for prefijo in prefijos:
        j = next((j for j, c in enumerate(cabecera) if c.startswith(prefijo)), None)
        if j is not None:
            return j
    return None


RE_TITULO_NUMERADO = re.compile(r"^\s*\d{1,2}[.)]\s+(.{3,90}?)\.?\s*$")


def _nombre_por_titulo(bloques, campos):
    """Nombre del puesto tomado del titulo numerado del documento ("1. Analista de Compras.").

    Solo si no se encontro con etiqueta y si el titulo no es el de una seccion conocida.
    """
    if campos.get("nombre_puesto"):
        return
    for b in bloques[:BLOQUES_INICIALES_METADATOS]:
        if b["k"] == "h":
            texto = b["texto"]
        elif b["k"] == "li" and re.match(r"^\d{1,2}[.)]$", b.get("marcador") or ""):
            texto = f"{b['marcador']} {b['texto']}"   # en OCR el titulo numerado se lee como item
        elif b["k"] == "p":
            texto = b["texto"]
        else:
            continue
        m = RE_TITULO_NUMERADO.match(texto)
        if m and not es_seccion_conocida(clave_titulo(m.group(1))):
            campos["nombre_puesto"] = m.group(1).strip()
            return
        if b["k"] == "h":
            return   # solo hasta el primer titulo del documento


def _campos_por_relacionamiento(bloques, campos):
    """'Reporta a' y 'Supervisa a' desde la tabla "Áreas de Relacionamiento" (Área de Interacción | Tipo de Relación).

    Cada fila tiene el area o puesto y el tipo de relacion: "Subordinación Directa" es a quien reporta el
    puesto y "Reporte Directo" quien le reporta. Las demas relaciones (pares, equipos, matricial) no se indexan.
    """
    encontrados = collections.defaultdict(list)
    for b in bloques:
        if b["k"] != "tabla" or not b["filas"]:
            continue
        cabecera = [norm(c) for c in b["filas"][0]]
        if not any(c.startswith("tipo de relacion") for c in cabecera):
            continue
        for f in b["filas"][1:]:
            llenas = [c.replace(MARCA_COMBINADA, "").strip() for c in f if c.strip()]
            if len(llenas) < 2:
                continue
            tipo = norm(llenas[-1])
            campo = next((c for t, c in TIPOS_RELACION if tipo.startswith(t)), None)
            if campo and llenas[0] not in encontrados[campo]:
                encontrados[campo].append(llenas[0])
    for campo, valores in encontrados.items():
        if not campos.get(campo):
            campos[campo] = "; ".join(valores)


def _actividades_de_tabla(filas):
    cabecera = [norm(c) for c in filas[0]]
    ia = _columna(cabecera, COLUMNAS_ACTIVIDAD)
    if ia is None:
        return []
    ir = _columna(cabecera, COLUMNAS_RESPONSABLE)
    actividades = []
    for f in filas[1:]:
        if ia >= len(f) or f[ia].endswith(MARCA_COMBINADA):
            continue   # una celda combinada repite la actividad de arriba
        actividad = f[ia].strip()
        if not actividad:
            continue
        responsable = f[ir].replace(MARCA_COMBINADA, "").strip() if ir is not None and ir < len(f) else ""
        actividades.append(actividad + (f" (Responsable: {responsable})" if responsable else ""))
    return actividades


def _actividades(secciones):
    """Actividades documentadas en la seccion de desarrollo de un procedimiento.

    Si el desarrollo tiene tablas, son sus filas (columna Actividad/Descripcion...) con su responsable;
    si no, sus vinetas. Las vinetas de otras secciones (alcance, politicas, referencias) nunca son actividades.
    """
    actividades = []
    for _titulo, campo, bloques in secciones:
        if campo != "desarrollo":
            continue
        desde_tablas = [a for b in bloques if b["k"] == "tabla" and len(b["filas"]) >= 2
                        for a in _actividades_de_tabla(b["filas"])]
        actividades += desde_tablas or [b["texto"].strip() for b in bloques if b["k"] == "li" and b.get("texto", "").strip()]
    return actividades


def _codigos_citados(encabezado, bloques, codigo_interno):
    todo = " ".join(encabezado) + " " + " ".join(texto_bloque(b) for b in bloques)
    return sorted(set(RE_CODIGO_DOC.findall(todo)) - ({codigo_interno} if codigo_interno else set()))


def avisar_nombre_puesto(analisis, titulo_archivo):
    """Nota si el puesto leido no se parece al nombre del archivo (tabla de datos generales mal leida)."""
    puesto = analisis.campos.get("nombre_puesto", "")
    if not puesto:
        return

    def palabras(texto):
        texto = re.sub(r"\b(descriptivo|descripcion|perfil|de|del|puesto|cargo|dp|v\d+)\b", " ", norm(texto))
        return {w for w in re.sub(r"[^a-z0-9 ]", " ", texto).split() if len(w) >= 4}

    ta, tb = palabras(titulo_archivo), palabras(puesto)
    parecido = difflib.SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    if not tb or tb <= ta or ta <= tb or parecido >= 0.6:
        return
    analisis.avisos.append(f"nombre del puesto leído «{puesto}» no se parece al archivo «{titulo_archivo}»: "
                           "revisar la tabla de datos generales")


def _pagina(b):
    p = b.get("pagina")
    return f"p.{p + 1}" if isinstance(p, int) else "documento"


CERCA_REPETIDO = 3      # bloques: un parrafo repetido tan cerca de su copia es casi seguro un duplicado


def _repetidos_por_conversion(bloques):
    """Parrafos largos que aparecen dos veces como si la conversion los hubiera duplicado: en la misma pagina o a
    pocos bloques de distancia. Una frase que vuelve en otra pagina (el pie de cada diapositiva, una clausula que
    el documento repite en dos secciones) es contenido del original, no un duplicado de la conversion."""
    posiciones = collections.defaultdict(list)
    for i, b in enumerate(bloques):
        if b["k"] in ("p", "li") and len(b.get("texto", "")) >= 40:
            pag = b.get("pagina")
            posiciones[norm(b["texto"])].append((i, pag if isinstance(pag, int) else None))
    repetidos = []
    for t, apariciones in posiciones.items():
        if any(a[1] is None or b[1] is None or a[1] == b[1] or b[0] - a[0] <= CERCA_REPETIDO
               for k, a in enumerate(apariciones) for b in apariciones[k + 1:]):
            repetidos.append(t)
    return repetidos


def avisos_de_estructura(bloques, imagenes_grandes, hoja_de_calculo=False):
    """Senales de que la estructura pudo leerse mal aunque el texto este completo.

    - tabla con filas sin primera celda (fila partida que quedo como fila nueva);
    - parrafos largos repetidos (contenido duplicado por la conversion);
    - documento cuyo contenido esta sobre todo en imagenes (hay que transcribirlo a mano).
    """
    avisos = []
    for b in bloques:
        if b["k"] == "tabla" and len(b["filas"]) >= 4 and not hoja_de_calculo:
            datos = b["filas"][1:]
            if sum(1 for f in datos if f and f[0].strip()) >= 0.8 * len(datos):
                huerfanas = [f for f in datos if f and not f[0].strip()
                             and any(c.strip() and not c.endswith(MARCA_COMBINADA) for c in f[1:])]
                if huerfanas:
                    avisos.append(f"{_pagina(b)}: {len(huerfanas)} filas de tabla sin primera celda "
                                  "(posible fila partida)")
    repetidos = _repetidos_por_conversion(bloques)
    if repetidos:
        avisos.append(f"{len(repetidos)} párrafos repetidos (posible duplicado de conversión): «{repetidos[0][:60]}…»")
    palabras = sum(len(tokens(texto_bloque(b))) for b in bloques if b["k"] != "marca")
    if imagenes_grandes >= 3 and palabras < 40 * imagenes_grandes:
        avisos.append(f"el contenido está sobre todo en imágenes ({imagenes_grandes} imágenes, {palabras} palabras): "
                      "transcribirlo a mano (.md o .csv) si es relevante")
    return avisos
