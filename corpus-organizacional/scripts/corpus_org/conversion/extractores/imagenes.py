"""Texto dentro de imagenes incrustadas en un documento de Office (captura pegada en una hoja, foto de una diapositiva)."""

import difflib
import io
import re
import unicodedata

from .maquetacion import agrupar_filas, bloques_desde_items
from .ocr_pagina import CONFIANZA_OBJETIVO

MIN_PALABRAS_IMAGEN = 6      # palabras de 4+ letras para considerar que una imagen trae texto
MIN_CONFIANZA_INCLUIR = 60   # por debajo, el OCR es ruido: se deja la marca y un aviso, no el texto
LADO_MIN_PX = 300            # una imagen mas chica (icono, vineta) no se lee


def hash_imagen(datos):
    import hashlib
    return hashlib.md5(datos).hexdigest()


def es_imagen_de_contenido(datos):
    """False para iconos y logos chicos (menos de LADO_MIN_PX en alguno de sus lados) o ilegibles."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(datos)) as im:
            return min(im.size) >= LADO_MIN_PX
    except Exception:
        return False


def _clave(t):
    """Texto sin acentos, en minusculas y con un solo espacio: para comparar etiquetas de OCR con textos del libro."""
    t = unicodedata.normalize("NFD", t.casefold())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


def depurar_etiquetas(etiquetas, referencia=()):
    """Limpia las etiquetas leidas con OCR de un diagrama. Devuelve (etiquetas, corregidas, descartadas).

    - Una etiqueta casi igual (>= 85 %) a un texto de ``referencia`` (las celdas del propio libro, donde las mismas
      actividades estan escritas) se sustituye por ese texto: es la lectura que respalda el documento.
    - Se quitan las letras sueltas del inicio (restos de una palabra cortada) y se descartan los fragmentos de menos
      de 4 letras (salvo si/no), que son restos de bordes y flechas.
    - Se eliminan las repetidas."""
    ref = {}
    for r in referencia:
        ref.setdefault(_clave(r), r)
    claves = list(ref)
    res, vistas, corregidas, descartadas = [], set(), 0, 0
    for t in etiquetas:
        t = t.strip()
        k = _clave(t)
        if k in ref:
            t = ref[k]
        else:
            cerca = difflib.get_close_matches(k, claves, n=1, cutoff=0.85) if len(k) >= 6 else []
            if cerca:
                t, k = ref[cerca[0]], cerca[0]
                corregidas += 1
        palabras = t.split()
        while len(palabras) > 1 and len(palabras[0]) <= 2 and palabras[0].islower():
            palabras.pop(0)
        t = " ".join(palabras)
        k = _clave(t)
        if k in vistas:
            continue
        if len(re.findall(r"[^\W\d_]", t)) < 4 and k not in ("si", "no") and k not in ref:
            descartadas += 1
            continue
        vistas.add(k)
        res.append(t)
    return res, corregidas, descartadas


def texto_de_imagen(d, bloques, donde, n_unidad, datos, referencia=()):
    """Lee con OCR el texto de una imagen y lo agrega a ``bloques`` bajo una marca.

    ``donde``: «la hoja «X»» o «la diapositiva 3» (para la marca); ``n_unidad``: numero de hoja o diapositiva, que
    se anota como pagina leida con OCR. Sin OCR o sin texto legible deja solo la marca."""
    from .ocr import configurar_pytesseract, idioma_ocr
    marca = f"[IMAGEN EN {donde}"
    idioma = idioma_ocr()
    if not idioma:
        d.imagenes_omitidas += 1
        bloques.append({"k": "marca", "texto": marca + ": no se pudo leer (falta OCR); ver el original]"})
        return
    try:
        from PIL import Image
        from .ocr_pagina import leer_imagen
        from .pdf import palabras_ocr
        res = leer_imagen(Image.open(io.BytesIO(datos)), idioma, configurar_pytesseract())
    except Exception as e:
        d.notas.append(f"OCR de una imagen falló en {donde}: {e}")
        bloques.append({"k": "marca", "texto": marca + "; ver el original]"})
        return
    utiles = sum(1 for L in res.lineas for _ in re.findall(r"[^\W\d_]{4,}", L["texto"]))
    if utiles < MIN_PALABRAS_IMAGEN:
        d.diagramas.append(n_unidad)
        bloques.append({"k": "marca", "texto": marca + "; sin texto legible, ver el original]"})
        return
    if res.confianza < MIN_CONFIANZA_INCLUIR:
        d.diagramas.append(n_unidad)
        bloques.append({"k": "marca", "texto": marca + f"; el OCR solo lo lee con {res.confianza:.0f} % de confianza "
                                                       "(ilegible), ver el original]"})
        d.avisos.append(f"la imagen de {donde} no se pudo leer (OCR {res.confianza:.0f} %): su contenido no está en el "
                        "corpus; use una versión más nítida o transcríbala")
        return
    d.paginas_ocr.append(n_unidad)
    d.idioma_ocr = idioma
    d.confianzas_ocr += res.confianzas
    d.crudo_ocr |= palabras_ocr([L["texto"] for L in res.lineas] + [e[0] for e in res.etiquetas])
    descartadas = f"; {res.descartadas} palabras de baja confianza descartadas" if res.descartadas else ""
    if res.disperso:
        # un diagrama de flujo: etiquetas sueltas (tareas, decisiones, carriles), no parrafos
        etiquetas, corregidas, quitadas = depurar_etiquetas([e[0] for e in res.etiquetas], referencia)
        if corregidas:
            descartadas += f"; {corregidas} etiquetas corregidas con los textos del libro"
        if quitadas:
            descartadas += f"; {quitadas} fragmentos descartados"
        bloques.append({"k": "marca", "texto": marca + ": etiquetas del diagrama leídas con OCR, de izquierda a derecha y "
                                                       f"de arriba abajo (confianza {res.confianza:.0f} %{descartadas}), "
                                                       "revisar contra el original]"})
        bloques += [{"k": "li", "marcador": "-", "texto": t, "nivel": 0, "ocr": True} for t in etiquetas]
    else:
        bloques.append({"k": "marca", "texto": marca + f": texto leído con OCR (confianza {res.confianza:.0f} %"
                                                       f"{descartadas}), revisar contra el original]"})
        filas = agrupar_filas(res.lineas)
        for f in filas:
            f["pagina"] = 0
            f["ocr"] = True
        bloques += bloques_desde_items(filas)
    if res.confianza < CONFIANZA_OBJETIVO:
        d.avisos.append(f"la imagen de {donde} se leyó con {res.confianza:.0f} % de confianza "
                        f"(menos de {CONFIANZA_OBJETIVO:.0f} %): revise el original")
