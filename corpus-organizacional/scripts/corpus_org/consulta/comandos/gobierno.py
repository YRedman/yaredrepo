from ...comun.esquema import NO_ESPECIFICADO
from .base import Comando

CAMPOS = ("version", "estado_documental", "fecha_vigencia", "propietario", "responsable")


class Gobierno(Comando):
    nombre = "gobierno"
    ayuda = "Versiones, vigencia, propietario y responsable."

    def configurar(self, parser):
        parser.add_argument("--area", default=None)

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        cods = ctx.filtrar_area(sorted(cp.meta), args.area)
        filas = []
        for c in cods:
            f = cp.meta[c]
            # un campo vacio no significa 'Vigente': se muestra como no especificado
            filas.append([c, cp.nombre(c), f.get("departamento", "")]
                         + [f.get(k) or NO_ESPECIFICADO for k in CAMPOS])
        s.linea(f"GOBIERNO DOCUMENTAL · {len(filas)} documentos · índice: {cp.fuente_indice}")
        s.tabla(["Código", "Documento", "Área", "Versión", "Estado", "Vigencia", "Propietario", "Responsable"], filas)
        if cp.excluidos:
            s.linea(f"No se muestran {len(cp.excluidos)} documentos con estado no vigente "
                    "(para incluirlos: CORPUS_INCLUIR_NO_VIGENTES=1).")
