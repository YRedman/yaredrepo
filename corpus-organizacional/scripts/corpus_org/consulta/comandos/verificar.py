from pathlib import Path

from ... import VERSION
from ...comun.estructura import informe_limites
from ...comun.texto import porcentaje
from ...comun.tipos import es_general
from ..integridad import verificar_huellas
from ..salida import resumir_lista
from .base import Comando


def _cobertura_incompleta(valor):
    try:
        return porcentaje(valor) < 100.0
    except ValueError:
        return True


def _problemas_del_indice(cp):
    problemas = []
    if cp.duplicados:
        problemas.append(f"Códigos repetidos: {resumir_lista(sorted(set(cp.duplicados)))}")
    md_sin_dic = sorted(c for c in cp.docs if c not in cp.meta and not es_general(c))
    if md_sin_dic:
        problemas.append(f"Documentos sin fila en el diccionario: {resumir_lista(md_sin_dic)}")
    dic_sin_md = sorted(c for c in cp.meta if c not in cp.docs)
    if dic_sin_md:
        problemas.append(f"Filas del diccionario sin texto en los .md: {resumir_lista(dic_sin_md)}")
    return problemas


def _problemas_de_inventario(cp):
    if not cp.inventario:
        return []
    problemas = []
    faltan = cp.faltantes_de_inventario()
    inventariados = cp.codigos_inventario()
    sobran = sorted(c for c in cp.docs if not es_general(c) and c not in inventariados)
    if faltan:
        problemas.append(f"Documentos del inventario que no están convertidos ({len(faltan)}): {resumir_lista(faltan)}")
    if sobran:
        problemas.append(f"Documentos que no están en el inventario: {resumir_lista(sobran)}")
    return problemas


def _problemas_de_texto(cp):
    problemas = []
    bajos = [(c, f["cobertura"]) for c, f in cp.meta.items() if f.get("cobertura") and _cobertura_incompleta(f["cobertura"])]
    if bajos:
        problemas.append("Documentos con texto presente menor a 100 % en la conversión: "
                         + ", ".join(f"{c} ({v})" for c, v in bajos))
    agregadas = sorted(c for c, f in cp.meta.items() if (f.get("palabras_agregadas") or "").strip())
    if agregadas:
        problemas.append(f"Documentos con palabras que no están en el original: {resumir_lista(agregadas)}")
    return problemas


def _problema_de_huellas(huellas):
    if huellas.existe and not huellas.correcto:
        return [f"Archivos modificados después de la conversión: {', '.join(huellas.modificados) or '—'}"
                f" · faltantes: {', '.join(huellas.faltantes) or '—'}"]
    return []


def _notas_de_huellas(s, huellas):
    if huellas.correcto:
        s.linea("- Huellas SHA-256: todos los archivos coinciden con la conversión.")
    elif not huellas.existe:
        s.linea("- Aviso: no hay huellas.sha256 (corpus construido con una versión anterior a la 3.3).")


def _notas_del_corpus(s, cp):
    estructura = sorted(c for c, f in cp.meta.items() if (f.get("avisos_estructura") or "0").strip() not in ("", "0"))
    if estructura:
        s.linea(f"- Aviso: documentos con avisos de estructura (deben estar revisados visualmente): "
                f"{resumir_lista(estructura)}")
    if cp.retirados:
        s.linea("- Información: códigos retirados del inventario (reservados): "
                + resumir_lista(f.get("codigo", "") for f in cp.retirados))
    if not cp.inventario:
        s.linea("- Aviso: no hay inventario_maestro.csv; no se puede comprobar que estén todos los documentos.")
    if cp.excluidos:
        s.linea("- Información: excluidos por estado documental (no es un problema): "
                + resumir_lista(f"{c} ({e})" for c, e in sorted(cp.excluidos.items())))


def _limites(s, cp):
    carpetas = [c for c in (cp.carpeta, cp.carpeta_documentos)
                if c and (c == cp.carpeta or cp.carpeta not in Path(c).parents)]       # los documentos ya van dentro del skill
    medidas, avisos_limites = informe_limites(carpetas)
    for m in medidas:
        s.linea(f"- Peso y archivos · {m}")
    for a in avisos_limites:
        s.linea(f"- Aviso: {a}")


class Verificar(Comando):
    nombre = "verificar"
    ayuda = "Revisa que el corpus publicado este completo y sea coherente."

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        s.linea(f"VERIFICACIÓN · corpus.py v{VERSION} · skill fuente-corpus: {cp.carpeta}")
        s.linea(f"documentos: {cp.carpeta_documentos}")
        s.linea(f"Índice utilizado: {cp.fuente_indice}")
        huellas = verificar_huellas(cp.carpeta, cp.carpeta_documentos)
        problemas = (_problemas_del_indice(cp) + _problemas_de_inventario(cp) + _problemas_de_texto(cp)
                     + _problema_de_huellas(huellas))
        s.lista(problemas)
        _notas_de_huellas(s, huellas)
        _notas_del_corpus(s, cp)
        _limites(s, cp)
        s.linea(f"Archivos .md: {len(cp.archivos_md)} · documentos: {len(cp.docs)} · filas de índice: {len(cp.meta)} · "
                f"corpus completo: {'sí' if cp.completo else 'no'}")
        s.linea("Resultado: " + ("sin problemas" if not problemas else f"{len(problemas)} tipos de problema"))
