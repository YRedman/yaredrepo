"""La hoja Resumen: conteos por area, como valores (CSV) y como formulas (Excel)."""

from .esquema import COLUMNAS_RESUMEN

COLUMNAS_TOTAL = range(1, len(COLUMNAS_RESUMEN))


def areas_del_resumen(hojas):
    return sorted({f[1] for f in hojas["Puestos"]} | {f[2] for f in hojas["Procedimientos"]}
                  | {f[2] for f in hojas["Políticas y protocolos"]})


def valores_resumen(hojas):
    """Las mismas cuentas de la hoja Resumen (que en Excel son formulas), ya calculadas, con fila Total."""
    filas = []
    for area in areas_del_resumen(hojas):
        puestos = [f for f in hojas["Puestos"] if f[1] == area]
        filas.append([area, len(puestos), sum(1 for f in puestos if str(f[12]).startswith("OCR")),
                      sum(1 for f in puestos if str(f[12]).startswith("Sin texto")),
                      sum(1 for f in hojas["Funciones"] if f[1] == area),
                      sum(1 for f in hojas["Relaciones"] if f[1] == area),
                      sum(1 for f in hojas["Revisión"] if f[1] == area and f[5] == "Pendiente")])
    filas.append(["Total"] + [sum(f[k] for f in filas) for k in COLUMNAS_TOTAL])
    return filas


def formulas_resumen(r):
    """Las formulas de la fila ``r`` (el area esta en $A) de la hoja Resumen."""
    return [f"=COUNTIF('Puestos'!$B:$B,$A{r})",
            f"=COUNTIFS('Puestos'!$B:$B,$A{r},'Puestos'!$M:$M,\"OCR*\")",
            f"=COUNTIFS('Puestos'!$B:$B,$A{r},'Puestos'!$M:$M,\"Sin texto*\")",
            f"=COUNTIF('Funciones'!$B:$B,$A{r})",
            f"=COUNTIF('Relaciones'!$B:$B,$A{r})",
            f"=COUNTIFS('Revisión'!$B:$B,$A{r},'Revisión'!$F:$F,\"Pendiente\")"]
