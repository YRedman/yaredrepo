"""Campos clave del documento (nombre del puesto, a quien reporta, objetivo...) segun su tipo."""

import collections
import re

from ...comun.esquema import MARCA_COMBINADA
from ...comun.texto import norm
from ..configuracion import BLOQUES_INICIALES_METADATOS, CAMPO_OTRO, ETIQUETAS_D, TIPOS_RELACION
from ..secciones import buscar_alias, clave_titulo, es_seccion_conocida, etiqueta_exacta
from .bloques import texto_bloque


# Campos de texto corrido: si la seccion tiene parrafos se usan solo ellos (una tabla o un organigrama
# que quedo en la misma seccion no es el objetivo del puesto).
CAMPOS_PROSA = {"proposito", "objetivo", "alcance"}


def campos_de_secciones(secciones):
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


def campos_por_etiqueta(bloques, campos):
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


RE_TITULO_NUMERADO = re.compile(r"^\s*\d{1,2}[.)]\s+(.{3,90}?)\.?\s*$")


def nombre_por_titulo(bloques, campos):
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


def campos_por_relacionamiento(bloques, campos):
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
