"""Secciones de diagrama: su contenido se cambia por una marca que remite al original."""

from ..configuracion import SECCIONES_P
from ..secciones import buscar_alias, clave_titulo
from .bloques import excluir_bloque


def _es_titulo_diagrama(b):
    return b["k"] == "h" and buscar_alias(clave_titulo(b["texto"]), SECCIONES_P) == "diagrama"


def _marca_diagrama(titulo, paginas):
    pags = sorted(p + 1 for p in paginas if isinstance(p, int))
    if pags:
        ref = ("página " if len(pags) == 1 else "páginas ") + ", ".join(map(str, pags))
    else:
        ref = "el documento original"
    return {"k": "marca", "texto": f"[DIAGRAMA: la sección «{titulo}» no se transcribe; ver {ref}]"}


def sustituir_diagramas(bloques, a):
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
                    excluir_bloque(a, b)
                diag["paginas"].add(b.get("pagina"))
                continue
        salida.append(b)
        if _es_titulo_diagrama(b):
            diag = {"nivel": b["nivel"], "titulo": b["texto"], "paginas": {b.get("pagina")}}
    cerrar()
    return salida
