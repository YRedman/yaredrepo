"""Codigos que cambian: migracion de la codificacion anterior, inventario base y tabla de equivalencias."""

from ...comun.archivos import escribir_csv, leer_csv, leer_csv_opcional
from ...comun.esquema import AREA_SIN_ASIGNAR, COLUMNAS_EQUIVALENCIAS, tipo_de_fila
from ...comun.texto import norm
from ...comun.tipos import RE_CODIGO_ANTERIOR, codigo_nuevo_desde_anterior, tipo as tipo_documento
from .claves import clave_documento
from .modelo import InventarioBase


def migrar_fila(f, equivalencias=None):
    """Fila del inventario con el codigo anterior (D-/P-) pasada a la codificacion TTT-AAA-NN."""
    anterior = (f.get("codigo") or "").strip().upper()
    nuevo = codigo_nuevo_desde_anterior(anterior) if RE_CODIGO_ANTERIOR.match(anterior) else None
    t = tipo_de_fila(f)
    f = dict(f, tipo=tipo_documento(t).nombre if tipo_documento(t) else f.get("tipo", ""))
    if nuevo:
        f["codigo"] = nuevo
        if equivalencias is not None:
            equivalencias.append((anterior, nuevo))
    return f


def leer_base(path):
    base = InventarioBase()
    for f in leer_csv(path):
        f = migrar_fila(f, base.equivalencias)
        t = tipo_de_fila(f)
        dep = (f.get("departamento") or "").strip()
        cod_dep = (f.get("codigo_departamento") or "").strip().upper()
        if norm(dep) == norm(AREA_SIN_ASIGNAR):
            continue   # codigos provisionales: cambian cuando se asigna el area
        if dep and cod_dep:
            base.departamentos.setdefault(norm(dep), cod_dep)
        try:
            n = int(f["codigo"].rsplit("-", 1)[1])
        except (KeyError, ValueError, IndexError):
            continue
        base.maximos[(t, cod_dep)] = max(base.maximos[(t, cod_dep)], n)
        base.documentos[(t, norm(dep), clave_documento(f.get("archivo", "")))] = f
    return base


def escribir_equivalencias(path, nuevas):
    """Agrega a equivalencias_codigos.csv (codigo_anterior;codigo_nuevo) las equivalencias nuevas, sin repetir."""
    existentes = leer_csv_opcional(path)
    vistos = {(r.get("codigo_anterior", ""), r.get("codigo_nuevo", "")) for r in existentes}
    filas = [{"codigo_anterior": r.get("codigo_anterior", ""), "codigo_nuevo": r.get("codigo_nuevo", "")}
             for r in existentes]
    for ant, nuevo in nuevas:
        if (ant, nuevo) not in vistos and ant != nuevo:
            vistos.add((ant, nuevo))
            filas.append({"codigo_anterior": ant, "codigo_nuevo": nuevo})
    if filas:
        escribir_csv(path, COLUMNAS_EQUIVALENCIAS, filas)
    return filas


def leer_equivalencias(path):
    """{codigo_anterior: codigo_nuevo} de equivalencias_codigos.csv."""
    return {(r.get("codigo_anterior") or "").strip().upper(): (r.get("codigo_nuevo") or "").strip().upper()
            for r in leer_csv_opcional(path) if r.get("codigo_anterior")}
