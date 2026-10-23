"""Nombre del puesto: avisa si el titulo del archivo trae siglas sin explicar."""

import difflib
import re

from ...comun.texto import norm


PALABRAS_DE_FORMATO = {"descripcion", "puesto", "perfil", "competencias", "regional"}


def _siglas_explicadas(titulo_archivo, puesto):
    """True si una sigla del archivo (TSMO, GDC) son las iniciales de palabras seguidas del puesto leido («Terapia de
    Soporte Multiorgánica», «Gestión del Conocimiento») y las demás palabras del archivo estan en el puesto."""
    palabras_puesto = re.sub(r"[^a-z0-9 ]", " ", norm(puesto)).split()
    vacias = {"de", "del", "la", "las", "el", "los", "y", "e", "en", "para"}
    variantes = ([w[0] for w in palabras_puesto], [w[0] for w in palabras_puesto if w not in vacias])
    for sigla in re.findall(r"\b[A-ZÁÉÍÓÚÑ]{3,6}\b", titulo_archivo):
        s = norm(sigla)
        resto = re.sub(rf"\b{sigla}\b", " ", titulo_archivo)
        resto = {w for w in re.sub(r"[^a-z0-9 ]", " ", norm(resto)).split() if len(w) >= 5}
        resto_en_puesto = all(any(w[:5] == p[:5] for p in palabras_puesto) or w in PALABRAS_DE_FORMATO for w in resto)
        for iniciales in variantes:
            # una palabra compuesta («Multiorgánica» = multi + orgánica) aporta una inicial de menos: se admite una letra de menos
            for largo in (len(s), len(s) - 1) if len(s) >= 4 else (len(s),):
                if resto_en_puesto and any("".join(iniciales[i:i + largo]) == s[:largo]
                                           for i in range(len(iniciales) - largo + 1)):
                    return True
    return False


def avisar_nombre_puesto(analisis, titulo_archivo):
    """Nota si el puesto leido no se parece al nombre del archivo (tabla de datos generales mal leida)."""
    puesto = analisis.campos.get("nombre_puesto", "")
    if not puesto:
        return

    def palabras(texto):
        texto = re.sub(r"\b(descriptivo|descripcion|perfil|de|del|puesto|cargo|dp|v\d+)\b", " ", norm(texto))
        return {w for w in re.sub(r"[^a-z0-9 ]", " ", texto).split() if len(w) >= 4}

    ta, tb = palabras(titulo_archivo), palabras(puesto)
    if _siglas_explicadas(titulo_archivo, puesto):
        return
    parecido = difflib.SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    if not tb or tb <= ta or ta <= tb or parecido >= 0.6:
        return
    analisis.avisos.append(f"nombre del puesto leído «{puesto}» no se parece al archivo «{titulo_archivo}»: "
                           "revisar la tabla de datos generales")
