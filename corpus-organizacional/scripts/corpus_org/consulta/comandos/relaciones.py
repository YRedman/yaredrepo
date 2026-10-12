import collections

from ...comun.texto import recortar_palabras as recortar
from ..relaciones import AnalizadorRelaciones, NoResueltas
from ..salida import resumir_lista
from .base import Comando

MAX_PAR = 60
MAX_DETALLE = 40
MAX_NO_RESUELTAS = 40
CABECERA_DETALLE = ["Cómo se menciona", "Verbo detectado", "Cita"]


def _cita(linea, n):
    return recortar(linea.strip("| ").replace("|", "·"), n)


def relaciones_de_area(analizador, a):
    """(salida, entrada, resumen, no_resueltas) de un area con todas las demas.

    ``resumen`` es {otra_area: {sal, ent, docs_sal, docs_ent, verbos}} ordenado por cantidad de menciones.
    """
    cp = analizador.corpus
    no_resueltas = NoResueltas()
    salida = analizador.menciones(a, list(cp.areas), no_resueltas)
    entrada = [m for otra in cp.areas if otra != a for m in analizador.menciones(otra, [a])]
    resumen = collections.OrderedDict()

    def fila(cod):
        return resumen.setdefault(cod, {"sal": 0, "ent": 0, "docs_sal": set(), "docs_ent": set(),
                                        "verbos": collections.Counter()})
    for m in salida:
        r = fila(m.destino)
        r["sal"] += 1
        r["docs_sal"].add(m.codigo)
        r["verbos"][m.verbo] += 1
    for m in entrada:
        r = fila(m.area_origen)
        r["ent"] += 1
        r["docs_ent"].add(m.codigo)
        r["verbos"][m.verbo] += 1
    ordenado = collections.OrderedDict(sorted(resumen.items(), key=lambda kv: -(kv[1]["sal"] + kv[1]["ent"])))
    return salida, entrada, ordenado, no_resueltas


def tabla_resumen(s, cp, a, resumen):
    s.tabla(["Código", "Otra área", f"Menciones en docs de {a}", "Documentos", f"Menciones de {a} en sus docs",
             "Documentos", "Verbos más frecuentes"],
            [[otra, cp.areas[otra].nombre, r["sal"], ", ".join(sorted(r["docs_sal"])), r["ent"],
              ", ".join(sorted(r["docs_ent"])), ", ".join(f"{k} ({n})" for k, n in r["verbos"].most_common(3))]
             for otra, r in resumen.items()])


def imprimir_no_resueltas(s, no_resueltas, maximo=MAX_NO_RESUELTAS):
    if not no_resueltas:
        return
    s.linea()
    s.linea("Menciones no resueltas (no se cuentan como relación con un área del corpus; validar en la reunión)")
    filas = [[frase, tipo, len(cods), resumir_lista(sorted(cods), 8)] for (frase, tipo), cods in no_resueltas.ordenadas()]
    s.tabla(["Mención", "Tipo", "Documentos", "Códigos"], filas[:maximo])
    if len(filas) > maximo:
        s.linea(f"… y {len(filas) - maximo} menciones no resueltas más")


class Relaciones(Comando):
    nombre = "relaciones"
    ayuda = "Menciones explicitas entre areas, con codigo y cita, y menciones no resueltas."

    def configurar(self, parser):
        parser.add_argument("area_a")
        parser.add_argument("area_b", nargs="?", default=None)

    def ejecutar(self, ctx, args):
        a = ctx.area(args.area_a)
        b = ctx.area(args.area_b) if args.area_b else None
        analizador = AnalizadorRelaciones(ctx.corpus)
        if b:
            self._par(ctx, analizador, a, b)
        else:
            self._todas(ctx, analizador, a)

    def _par(self, ctx, analizador, a, b):
        cp, s = ctx.corpus, ctx.salida
        s.linea(f"RELACIONES · {cp.areas[a].nombre} ({a}) ↔ {cp.areas[b].nombre} ({b})")
        no_resueltas = NoResueltas()
        ab, ba = analizador.menciones(a, [b], no_resueltas), analizador.menciones(b, [a], no_resueltas)
        s.linea(f"Documentos de {a} que mencionan a {b}: {len({x.codigo for x in ab})} · "
                f"documentos de {b} que mencionan a {a}: {len({x.codigo for x in ba})}")
        for titulo, lista in ((f"Menciones de {b} en documentos de {a}", ab), (f"Menciones de {a} en documentos de {b}", ba)):
            s.linea()
            s.linea(titulo)
            if not lista:
                s.linea("(ninguna mención explícita)")
                continue
            s.tabla(["Código", "Documento", "Sección"] + CABECERA_DETALLE,
                    [[m.codigo, cp.nombre(m.codigo), recortar(m.seccion, 8), m.via, m.verbo, _cita(m.linea, 40)]
                     for m in lista[:MAX_PAR]])
            if len(lista) > MAX_PAR:
                s.linea(f"… y {len(lista) - MAX_PAR} menciones más")
        imprimir_no_resueltas(s, no_resueltas)

    def _todas(self, ctx, analizador, a):
        cp, s = ctx.corpus, ctx.salida
        s.linea(f"RELACIONES · {cp.areas[a].nombre} ({a}) con las demás áreas")
        salida, entrada, resumen, no_resueltas = relaciones_de_area(analizador, a)
        if not resumen:
            s.linea("No hay menciones explícitas de otras áreas del corpus ni de sus puestos.")
        else:
            s.linea()
            tabla_resumen(s, cp, a, resumen)
            s.linea()
            s.linea(f"Detalle (máximo {MAX_DETALLE} filas; para un par de áreas usa: relaciones A B)")
            detalle = [(m, f"{a} menciona a {m.destino}") for m in salida] + \
                      [(m, f"{m.area_origen} menciona a {a}") for m in entrada]
            s.tabla(["Código", "Sentido", "Sección"] + CABECERA_DETALLE,
                    [[m.codigo, sentido, recortar(m.seccion, 8), m.via, m.verbo, _cita(m.linea, 35)]
                     for m, sentido in detalle[:MAX_DETALLE]])
            if len(detalle) > MAX_DETALLE:
                s.linea(f"… y {len(detalle) - MAX_DETALLE} menciones más")
        imprimir_no_resueltas(s, no_resueltas)
