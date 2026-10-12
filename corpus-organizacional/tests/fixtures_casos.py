"""Corpus sintetico con los casos de lectura que corrige la v3.1.

- Inventario: bloqueo de Word (~$...), copia "(1)" y el mismo documento en .docx y .pdf.
- El mismo nombre de archivo y de puesto en dos areas ("Asistente Administrativo").
- Descriptivos con "Jefe directo", "Depende de" y tabla horizontal con "Salario".
- Seccion "Diagrama de flujo" en un procedimiento.
- Roles en minuscula o en plural en la columna Responsable y un puesto parecido a dos.
- Contexto transcrito en .md y .csv.
- PDF (solo si hay LibreOffice): ligaduras en celdas y diagrama hecho con formas.

Requiere python-docx. Uso directo: python tests/fixtures_casos.py <carpeta>
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import docx


def _tabla(d, filas):
    t = d.add_table(rows=len(filas), cols=len(filas[0]))
    for i, fila in enumerate(filas):
        for j, v in enumerate(fila):
            t.cell(i, j).text = v
    return t


def descriptivo(path, datos, funciones, horizontal=False):
    d = docx.Document()
    d.add_heading("Datos generales", 1)
    if horizontal:
        _tabla(d, [[k for k, _ in datos], [v for _, v in datos]])
    else:
        _tabla(d, [list(par) for par in datos])
    d.add_heading("Actividades principales", 1)
    for f in funciones:
        d.add_paragraph(f, style="List Bullet")
    d.save(path)


def procedimiento(path, objetivo, pasos, diagrama=False):
    d = docx.Document()
    d.add_heading("Objetivo", 1)
    d.add_paragraph(objetivo)
    d.add_heading("Desarrollo del proceso", 1)
    _tabla(d, [["No.", "Actividad", "Responsable"]] + [[str(i), a, r] for i, (a, r) in enumerate(pasos, 1)])
    if diagrama:
        d.add_heading("Diagrama de flujo", 1)
        for caja in ("Inicio", "Recibir solicitud", "¿Aprobada?", "Fin"):
            d.add_paragraph(caja)
    d.add_heading("Referencias", 1)
    d.add_paragraph("Manual de calidad.")
    d.save(path)


def generar(base):
    """Crea <base>/entrada (con lista.txt) y <base>/contexto. Devuelve (entrada, contexto)."""
    base = Path(base)
    ent, ctx = base / "entrada", base / "contexto"
    carpetas = {k: ent / k for k in ("Descriptivos/Compras", "Descriptivos/Almacen", "Descriptivos/Calidad",
                                     "Procedimientos/Compras", "Procedimientos/Almacen")}
    for p in list(carpetas.values()) + [ctx]:
        p.mkdir(parents=True, exist_ok=True)
    dc, da, dq = carpetas["Descriptivos/Compras"], carpetas["Descriptivos/Almacen"], carpetas["Descriptivos/Calidad"]
    pc, pa = carpetas["Procedimientos/Compras"], carpetas["Procedimientos/Almacen"]

    descriptivo(dc / "Gerente de Compras.docx", [("Nombre del puesto", "Gerente de Compras"),
                                                 ("Reporta a", "Director General")], ["Aprobar compras."])
    descriptivo(dc / "Comprador.docx", [("Nombre del puesto", "Comprador"), ("Jefe directo", "Gerente de Compras")],
                ["Cotizar con proveedores."])
    descriptivo(dc / "Asistente Administrativo.docx", [("Nombre del puesto", "Asistente Administrativo"),
                                                       ("Reporta a", "Gerente de Compras")], ["Archivar órdenes."])
    descriptivo(da / "Asistente Administrativo.docx", [("Nombre del puesto", "Asistente Administrativo"),
                                                       ("Depende de", "Jefe de Almacén")], ["Registrar entradas."])
    descriptivo(dq / "Gerente de Control de Calidad.docx",
                [("Nombre del puesto", "Gerente de Control de Calidad"), ("Departamento", "Calidad"),
                 ("Salario", "Confidencial"), ("Reporta a", "Director General")], ["Inspeccionar lotes."],
                horizontal=True)
    descriptivo(dq / "Gerente de Aseguramiento de Calidad.docx",
                [("Nombre del puesto", "Gerente de Aseguramiento de Calidad"), ("Reporta a", "Director General")],
                ["Auditar procesos."])

    procedimiento(pc / "Compra de insumos.docx", "Comprar insumos.",
                  [("Solicitar la cotización", "Comprador"), ("Registrar la orden", "Asistente Administrativo"),
                   ("Validar especificaciones con el Gerente de Calidad", "comité de compras"),
                   ("Entregar la mercancía a Almacén", "coordinadores de logística")], diagrama=True)
    shutil.copy(pc / "Compra de insumos.docx", pc / "Compra de insumos (1).docx")
    (pc / "~$mpra de insumos.docx").write_bytes(b"bloqueo de Word")
    procedimiento(pa / "Recepcion de mercancia.docx", "Recibir mercancía.",
                  [("Recibir la mercancía enviada por Compras", "Jefe de Almacén"),
                   ("Archivar el comprobante", "Asistente Administrativo")])

    lista = ["C:\\Empresa\\" + "\\".join(p.relative_to(ent).parts)
             for p in sorted(ent.rglob("*")) if p.suffix == ".docx"]
    (ent / "lista.txt").write_text("\n".join(lista) + "\n", encoding="utf-8")

    (ctx / "glosario.md").write_text("# Glosario\n\n| Sigla | Significado |\n|---|---|\n| RRHH | Recursos Humanos |\n\n"
                                     "- Un punto de la minuta.\n", encoding="utf-8")
    (ctx / "indicadores.csv").write_text("id;indicador;meta\nI-01;Tiempo de entrega;5 días\n", encoding="utf-8")
    return ent, ctx


def generar_pdf(base):
    """PDF con ligaduras en celdas y con un diagrama de formas. Devuelve la carpeta o None sin LibreOffice."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    fuente = Path(base) / "pdf_fuente"
    salida = Path(base) / "pdf" / "Procedimientos" / "Pruebas"
    fuente.mkdir(parents=True, exist_ok=True)
    salida.mkdir(parents=True, exist_ok=True)
    d = docx.Document()
    d.add_heading("1. Objetivo", 1)
    d.add_paragraph("Verificar la confiabilidad del flujo de firmas.")
    d.add_heading("3. Desarrollo del proceso", 1)
    t = _tabla(d, [["No.", "Actividad", "Responsable"],
                   ["1", "Verificar la eficiencia del flujo", "Oficial de Cumplimiento"],
                   ["2", "Clasificar los archivos confidenciales", "Oficial de Cumplimiento"]])
    t.style = "Table Grid"
    for p in d.paragraphs + [p for c in t._cells for p in c.paragraphs]:
        for r in p.runs:
            r.font.name = "Carlito"   # fuente con ligaduras fi, fl, ffi
    d.save(fuente / "Ligaduras.docx")
    html = ("<html><body><h1>4. Diagrama de flujo</h1>"
            + "".join(f'<p style="border:1px solid black;padding:8px;width:200px">{x}</p>'
                      for x in ["Inicio", "Recibir solicitud", "Evaluar", "Aprobar", "Fin"])
            + "<h1>5. Referencias</h1><p>Manual</p></body></html>")
    (fuente / "Diagrama vectorial.html").write_text(html, encoding="utf-8")
    for n in os.listdir(fuente):
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(salida), str(fuente / n)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=180)
    return salida if any(salida.glob("*.pdf")) else None


if __name__ == "__main__":
    generar(sys.argv[1])
    print("PDF:", generar_pdf(sys.argv[1]))
