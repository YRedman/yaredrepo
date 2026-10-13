from ...comun.errores import CorpusError
from ...comun.esquema import area_de
from ...comun.tipos import es_general
from ...comun.texto import norm, recortar_palabras as recortar
from ..indicadores import kpis_relacionados, sin_medicion
from ..salida import resumir_lista
from .base import Comando


class Indicadores(Comando):
    nombre = "kpis"
    ayuda = "Indicadores transcritos (meta, medicion, estado) y documentos que mencionan sus terminos."

    def configurar(self, parser):
        parser.add_argument("--gestion", default=None)
        parser.add_argument("--sin-medicion", action="store_true")
        parser.add_argument("--relacionar", action="store_true")
        parser.add_argument("--area", default=None)

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        if not cp.kpis:
            raise CorpusError("No hay kpis.csv en el corpus publicado. Agrega a la carpeta de contexto un CSV cuyo "
                              "nombre empiece con 'kpi' y vuelve a ejecutar convertir.py construir.", 2)
        ks = cp.kpis
        if args.gestion:
            ks = [k for k in ks if norm(args.gestion) in norm(k.get("gestion", ""))]
        if args.sin_medicion:
            ks = [k for k in ks if sin_medicion(k)]
        s.linea(f"INDICADORES · {len(ks)} de {len(cp.kpis)} · fuente: kpis.csv (transcripción del contexto)")
        s.linea("El estado según la leyenda es [Inferido] del color de la celda. Una medición vacía es "
                "'sin medición', no cero.")
        s.linea()
        s.tabla(["ID", "Gestión", "Indicador", "Meta", "Medición", "Unidad", "Estado", "Periodo", "Observaciones"],
                [[k.get("id", ""), k.get("gestion", ""), k.get("indicador", ""), k.get("meta", ""),
                  "sin medición" if sin_medicion(k) else k.get("medicion", ""), k.get("unidad", ""),
                  k.get("estado_segun_leyenda", ""), k.get("periodo", ""), recortar(k.get("observaciones", ""), 14)]
                 for k in ks])
        if args.relacionar:
            self._relacionar(ctx, args, ks)

    def _relacionar(self, ctx, args, ks):
        cp, s = ctx.corpus, ctx.salida
        cods = [c for c in sorted(cp.docs) if not es_general(c)]
        if args.area:
            cod = ctx.area(args.area)
            cods = [c for c in cods if area_de(c) == cod]
        rel = kpis_relacionados(cp, cods, ks)
        s.linea()
        s.linea("Documentos que mencionan los términos de cada indicador [Inferido: coincidencia de términos, "
                f"no una relación documentada] · revisados: {len(cods)}")
        if not rel:
            s.linea("Ningún documento menciona los términos de búsqueda de estos indicadores.")
        else:
            s.tabla(["ID", "Indicador", "Términos", "Documentos (n)", "Códigos"],
                    [[k.get("id", ""), recortar(k.get("indicador", ""), 10), k.get("terminos_busqueda", ""), len(cs),
                      resumir_lista(sorted(cs), 10)] for k, cs in rel])
        con_relacion = {k.get("id") for k, _ in rel}
        sin = [k.get("id", "") for k in ks if k.get("id") not in con_relacion]
        if sin:
            s.linea(f"Sin documentos relacionados: {', '.join(sin)}")
