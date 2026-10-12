"""Analisis de un documento extraido: secciones, campos clave, actividades y codigos citados."""

import difflib
import re

from ..comun.esquema import MARCA_COMBINADA
from ..comun.texto import norm, tokens
from .configuracion import (BLOQUES_INICIALES_METADATOS, CAMPO_OTRO, CAMPOS_CLAVE, COLUMNAS_ACTIVIDAD, ETIQUETAS_D,
                            SECCIONES_P, SECCIONES_POR_TIPO)
from .metadatos import extraer_metadatos
from .modelo import Analisis
from .secciones import buscar_alias, clave_titulo, es_excluida, etiqueta_exacta

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
    return bloques, a


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
                    a.excluidos.update(tokens(texto_bloque(b)))
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
        if b["k"] == "h" and b["nivel"] <= nivel_base:
            clave = clave_titulo(b["texto"])
            if es_excluida(clave):
                excluyendo = True
                a.secciones_excluidas.append(b["texto"])
                a.excluidos.update(tokens(b["texto"]))
                continue
            excluyendo = False
            actual = [b["texto"], buscar_alias(clave, tabla_secciones) if tabla_secciones else None, []]
            secciones.append(actual)
            resultado.append(b)
            continue
        if excluyendo:
            a.excluidos.update(tokens(texto_bloque(b)))
            continue
        resultado.append(b)
        if actual is not None:
            actual[2].append(b)
    return resultado, secciones


def _campos_de_secciones(secciones):
    campos = {}
    for _titulo, campo, bloques in secciones:
        if not campo or campo in campos:
            continue
        texto = " ".join(texto_bloque(b) for b in bloques if b["k"] not in ("h", "marca")).strip()
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


def _actividades(secciones):
    """Actividades documentadas: items de lista y celdas de la columna 'Actividad' en el desarrollo.

    Las vinetas de otras secciones (alcance, politicas, referencias...) no son actividades.
    """
    actividades = []
    for _titulo, campo, bloques in secciones:
        if campo != "desarrollo":
            continue
        for b in bloques:
            if b["k"] == "li" and b.get("texto", "").strip():
                actividades.append(b["texto"].strip())
            elif b["k"] == "tabla" and b["filas"]:
                cols = [j for j, c in enumerate(b["filas"][0]) if norm(c).startswith(COLUMNAS_ACTIVIDAD)]
                for f in b["filas"][1:]:
                    for j in cols:
                        valor = f[j].replace(MARCA_COMBINADA, "").strip() if j < len(f) else ""
                        if valor and not f[j].endswith(MARCA_COMBINADA):
                            actividades.append(valor)
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
    analisis.notas.append(f"El nombre del puesto leído «{puesto}» no se parece al archivo «{titulo_archivo}»: "
                          "revisar la tabla de datos generales.")
