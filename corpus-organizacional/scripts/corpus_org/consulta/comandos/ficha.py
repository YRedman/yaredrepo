import collections
import re

from ...comun.esquema import tipo_desde_texto
from ...comun.markdown import celdas
from ...comun.texto import empieza_palabra, limitar_lineas, norm, recortar_palabras
from ..parser import es_seccion_encabezado_pie
from .base import Comando

# Secciones que se muestran en la ficha (raices; se comparan al inicio de palabra).
SECCIONES_FICHA = {
    "P": ["macroproceso", "objetivo", "proposito", "alcance", "responsab", "politica", "desarrollo", "descripcion del",
          "referencia", "distribucion", "entrenamiento", "anexo", "formato"],
    "D": ["datos generales", "identificacion", "proposito", "objetivo", "mision", "funcion", "responsab",
          "relacion", "requisito", "competencia", "perfil", "condicion"],
}
SECCIONES_DESARROLLO = ("desarrollo", "descripcion del")
PALABRAS_FICHA = 220
RE_NUMERACION = re.compile(r"^[\dIVXivx\.\)\s]+")


def resumen_desarrollo(lineas):
    """Subsecciones, numero de pasos y responsables del desarrollo del proceso."""
    out = []
    sub = None
    pasos = collections.Counter()
    responsables = collections.OrderedDict()
    col_resp = None          # columna 'Responsable' de la tabla actual; None = la proxima fila es cabecera
    texto_libre = []
    for l in lineas:
        m = re.match(r"^#{4,6}\s+(.*)$", l)
        if m:
            sub = m.group(1).strip()
            out.append(f"- Subproceso: {sub}")
            col_resp = None
            continue
        if not l.startswith("|"):
            col_resp = None  # termina la tabla: la siguiente tabla trae su propia cabecera
            texto_libre.append(l)
            continue
        cel = celdas(l)
        if col_resp is None:
            idx = [i for i, x in enumerate(cel) if norm(x).startswith("responsab") or norm(x) == "quien"]
            col_resp = idx[0] if idx else -1
            continue
        pasos[sub] += 1
        if 0 <= col_resp < len(cel) and cel[col_resp]:
            r = cel[col_resp].replace("[CELDA COMBINADA]", "").strip()
            responsables.setdefault(r, set()).add(sub or "")
    if pasos:
        out.append("- Pasos en tablas: " + "; ".join(f"{k or 'general'}: {v}" for k, v in pasos.items()))
    if responsables:
        out.append("- Responsables que aparecen en el desarrollo: " + "; ".join(responsables))
    if texto_libre:
        out.append("- Texto del desarrollo (inicio): " + recortar_palabras(" ".join(texto_libre), 80))
    return "\n".join(out) if out else "(sin contenido)"


class Ficha(Comando):
    nombre = "ficha"
    ayuda = "Campos clave literales de cada documento (para briefings)."

    def configurar(self, parser):
        parser.add_argument("objetivo", metavar="area_o_codigo")
        parser.add_argument("--tipo", type=tipo_desde_texto, default=None)

    def ejecutar(self, ctx, args):
        cp, s = ctx.corpus, ctx.salida
        cods = ctx.codigos_objetivo(args.objetivo, args.tipo)
        s.linea(f"FICHA · {len(cods)} documentos · campos clave en texto literal (lo largo se recorta con '…'; "
                "el texto completo se lee con: doc <CÓDIGO>)")
        for c in cods:
            f = cp.meta.get(c, {})
            s.linea()
            s.linea(f"## {c} · {cp.nombre(c)}")
            if f.get("campos_no_especificados"):
                s.linea(f"No especificado en el original: {f['campos_no_especificados']}")
            claves = SECCIONES_FICHA.get(c[0], [])
            otras = []
            for titulo, lineas in cp.secciones(c):
                if es_seccion_encabezado_pie(titulo):
                    continue
                t = norm(RE_NUMERACION.sub("", titulo))
                contenido = [l for l in lineas if l.strip() and not l.startswith("|---")]
                if any(empieza_palabra(k, t) for k in claves):
                    s.linea(f"### {titulo}")
                    if any(empieza_palabra(k, t) for k in SECCIONES_DESARROLLO):
                        s.linea(resumen_desarrollo(contenido))
                    else:
                        s.linea(limitar_lineas("\n".join(contenido), PALABRAS_FICHA))
                else:
                    otras.append(f"{titulo} ({len(' '.join(contenido).split())} palabras)")
            if otras:
                s.linea("Otras secciones (leer con doc si hacen falta): " + "; ".join(otras))
