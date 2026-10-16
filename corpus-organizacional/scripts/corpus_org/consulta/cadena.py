"""Cadena documental: que documento cita a cual, resuelto contra los codigos internos del propio corpus.

Cada documento trae en su encabezado su codigo interno (SUMI-ALMA-RD-PRO-011) y, en el texto, los codigos de los
documentos que cita (a veces completos, a veces sin el prefijo de gerencia: ALMA-RD-PRO-011). Aqui se unen: un codigo
citado es de un documento del corpus si es igual a su codigo interno o si es su final (con al menos tres segmentos y
sin ambiguedad). Lo que no se encuentra queda como documento citado que falta en el corpus. No se interpreta: solo se
une un codigo con otro.
"""

import collections
from dataclasses import dataclass

TIPOS_CODIGO_CLIENTE = {"FOR": "Formato", "PRO": "Procedimiento", "POL": "Política", "PRT": "Protocolo",
                        "INS": "Instructivo", "MAT": "Matriz", "MAN": "Manual", "REG": "Registro", "GUI": "Guía"}
MIN_SEGMENTOS_SUFIJO = 3


@dataclass(frozen=True)
class Enlace:
    origen: str          # codigo del corpus que cita
    citado: str          # codigo interno tal como esta escrito
    destino: str         # codigo del corpus al que corresponde ('' si no esta en el corpus)
    via: str             # 'exacto', 'final del código' o ''

    @property
    def resuelto(self):
        return bool(self.destino)


def tipo_de_codigo_cliente(codigo):
    """'Formato' de 'COM-FOR-001'; '' si ningun segmento del codigo es un tipo conocido."""
    for seg in reversed(codigo.upper().split("-")[:-1]):
        if seg in TIPOS_CODIGO_CLIENTE:
            return TIPOS_CODIGO_CLIENTE[seg]
    return ""


def _citados(fila):
    return [c.strip().upper() for c in (fila.get("codigos_citados") or "").split(",") if c.strip()]


def calcular_enlaces(meta):
    """[Enlace] de todos los documentos de ``meta`` ({codigo: fila del indice})."""
    internos = collections.OrderedDict()
    for cod, f in meta.items():
        interno = (f.get("codigo_interno") or "").strip().upper()
        if interno:
            internos.setdefault(interno, cod)
    enlaces = []
    for cod in sorted(meta):
        propio = (meta[cod].get("codigo_interno") or "").strip().upper()
        for citado in _citados(meta[cod]):
            destino, via = internos.get(citado, ""), "exacto"
            if not destino and citado.count("-") + 1 >= MIN_SEGMENTOS_SUFIJO:
                finales = {c for k, c in internos.items() if k.endswith("-" + citado)}
                if len(finales) == 1:
                    destino, via = finales.pop(), "final del código"
            if destino == cod or (propio and (citado == propio or propio.endswith("-" + citado))):
                continue          # el documento se cita a si mismo (su codigo aparece en cada pie de pagina)
            enlaces.append(Enlace(cod, citado, destino, via if destino else ""))
    return enlaces


def vecinos(enlaces, codigo, sentido, profundidad=1):
    """{codigo: distancia} de los documentos que ``codigo`` cita (sentido 'sale') o que lo citan ('entra'), hasta
    ``profundidad`` saltos."""
    sig = collections.defaultdict(set)
    for e in enlaces:
        if e.resuelto:
            a, b = (e.origen, e.destino) if sentido == "sale" else (e.destino, e.origen)
            sig[a].add(b)
    vistos, frontera = {}, {codigo}
    for d in range(1, profundidad + 1):
        nueva = set()
        for c in frontera:
            for v in sig.get(c, ()):
                if v != codigo and v not in vistos:
                    vistos[v] = d
                    nueva.add(v)
        frontera = nueva
    return vistos


def faltantes(enlaces):
    """{codigo citado: {documentos que lo citan}} de los codigos que no estan en el corpus, del mas citado al menos."""
    res = collections.defaultdict(set)
    for e in enlaces:
        if not e.resuelto:
            res[e.citado].add(e.origen)
    return collections.OrderedDict(sorted(res.items(), key=lambda kv: (-len(kv[1]), kv[0])))
