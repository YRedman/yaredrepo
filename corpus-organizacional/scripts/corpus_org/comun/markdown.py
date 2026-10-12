"""Escritura de Markdown GFM."""

import re


def esc_celda(s):
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def esc_linea(s):
    """Escapa una linea de texto para que no se interprete como titulo, cita o tabla."""
    s = s.replace("\u00a0", " ")
    if re.match(r"^\s*(#|>|\||=+\s*$)", s):
        s = "\\" + s.lstrip()
    return s


def tabla(cabecera, filas):
    """Tabla GFM como texto. ``filas`` puede contener cualquier valor convertible a str."""
    out = ["| " + " | ".join(cabecera) + " |", "|" + "|".join(["---"] * len(cabecera)) + "|"]
    for f in filas:
        out.append("| " + " | ".join(esc_celda(str(x)) for x in f) + " |")
    return "\n".join(out)


def lineas_tabla(filas):
    """Tabla GFM como lista de lineas; la primera fila es la cabecera."""
    ncol = max(len(f) for f in filas)
    filas = [f + [""] * (ncol - len(f)) for f in filas]
    lineas = ["| " + " | ".join(esc_celda(c) or " " for c in filas[0]) + " |",
              "|" + "|".join(["---"] * ncol) + "|"]
    for f in filas[1:]:
        lineas.append("| " + " | ".join(esc_celda(c) for c in f) + " |")
    return lineas


def celdas(linea):
    """Celdas de una linea de tabla GFM."""
    return [x.strip() for x in linea.strip().strip("|").split("|")]
