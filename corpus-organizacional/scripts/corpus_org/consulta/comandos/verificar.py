from ... import VERSION
from ..salida import resumir_lista
from .base import Comando


def _cobertura_incompleta(valor):
    try:
        return float(valor.replace("%", "").replace(",", ".").strip()) < 100.0
    except ValueError:
        return True


class Verificar(Comando):
    nombre = "verificar"
    ayuda = "Revisa que el corpus publicado este completo y sea coherente."

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        s.linea(f"VERIFICACIÓN · corpus.py v{VERSION} · carpeta publicada: {cp.carpeta}")
        s.linea(f"Índice utilizado: {cp.fuente_indice}")
        problemas = []
        if cp.duplicados:
            problemas.append(f"Códigos repetidos: {resumir_lista(sorted(set(cp.duplicados)))}")
        md_sin_dic = sorted(c for c in cp.docs if c not in cp.meta and not c.startswith("C-"))
        if md_sin_dic:
            problemas.append(f"Documentos sin fila en el diccionario: {resumir_lista(md_sin_dic)}")
        dic_sin_md = sorted(c for c in cp.meta if c not in cp.docs)
        if dic_sin_md:
            problemas.append(f"Filas del diccionario sin texto en los .md: {resumir_lista(dic_sin_md)}")
        if cp.inventario:
            faltan = cp.faltantes_de_inventario()
            inventariados = cp.codigos_inventario()
            sobran = sorted(c for c in cp.docs if not c.startswith("C-") and c not in inventariados)
            if faltan:
                problemas.append(f"Documentos del inventario que no están convertidos ({len(faltan)}): "
                                 f"{resumir_lista(faltan)}")
            if sobran:
                problemas.append(f"Documentos que no están en el inventario: {resumir_lista(sobran)}")
        bajos = [(c, f["cobertura"]) for c, f in cp.meta.items()
                 if f.get("cobertura") and _cobertura_incompleta(f["cobertura"])]
        if bajos:
            problemas.append("Documentos con texto presente menor a 100 % en la conversión: "
                             + ", ".join(f"{c} ({v})" for c, v in bajos))
        s.lista(problemas)
        if not cp.inventario:
            s.linea("- Aviso: no hay inventario_maestro.csv; no se puede comprobar que estén todos los documentos.")
        if cp.excluidos:
            s.linea("- Información: excluidos por estado documental (no es un problema): "
                    + resumir_lista(f"{c} ({e})" for c, e in sorted(cp.excluidos.items())))
        s.linea(f"Archivos .md: {len(cp.archivos_md)} · documentos: {len(cp.docs)} · filas de índice: {len(cp.meta)}")
        s.linea("Resultado: " + ("sin problemas" if not problemas else f"{len(problemas)} tipos de problema"))
