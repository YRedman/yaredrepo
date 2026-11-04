"""Archivos de Excel sintéticos (solo biblioteca estandar) para probar el vaciado del K4: un K4 pequeño y una plantilla
metodologica reducida con la misma estructura que la real (rotulos, tablas de B7, celdas de entrada en gris, formulas y
listas desplegables x14). No contienen datos de ninguna persona ni de ningun cliente."""

import zipfile
from xml.sax.saxutils import escape


NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ' \
     'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'

# estilos (indice en cellXfs)
NORMAL, ENTRADA, ROJO, AMARILLO, ENCABEZADO = 0, 1, 2, 3, 4


class F:
    """Celda con formula y su valor guardado."""

    def __init__(self, formula, guardado=0):
        self.formula, self.guardado = formula, guardado


STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet {NS}>
<fonts count="3"><font><sz val="11"/><name val="Calibri"/></font>
<font><sz val="11"/><color rgb="FFFF0000"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor theme="0" tint="-4.9989318521683403E-2"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFFF00"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="5">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
<xf numFmtId="0" fontId="0" fillId="2" borderId="0" applyFill="1"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" applyFont="1"/>
<xf numFmtId="0" fontId="0" fillId="3" borderId="0" applyFill="1"/>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" applyFont="1"/>
</cellXfs></styleSheet>"""

X14 = ('<extLst><ext uri="{CCE6A557-97BC-48c9-9E6D-5FF8CF2C9D7E}" '
       'xmlns:x14="http://schemas.microsoft.com/office/spreadsheetml/2009/9/main">'
       '<x14:dataValidations count="1" xmlns:xm="http://schemas.microsoft.com/office/excel/2006/main">'
       '<x14:dataValidation type="list" allowBlank="1"><x14:formula1><xm:f>Listas!$A$1:$A$8</xm:f></x14:formula1>'
       '<xm:sqref>G8:G30</xm:sqref></x14:dataValidation></x14:dataValidations></ext></extLst>')


def _columna(n):
    letras = ""
    while n:
        n, r = divmod(n - 1, 26)
        letras = chr(65 + r) + letras
    return letras


def _celda(ref, valor, estilo):
    s = f' s="{estilo}"' if estilo else ""
    if isinstance(valor, F):
        guardado = "" if valor.guardado is None else f"<v>{valor.guardado}</v>"
        return f'<c r="{ref}"{s}><f>{escape(valor.formula)}</f>{guardado}</c>'
    if valor is None:
        return f'<c r="{ref}"{s}/>'
    if isinstance(valor, bool):
        return f'<c r="{ref}"{s} t="b"><v>{int(valor)}</v></c>'
    if isinstance(valor, (int, float)):
        return f'<c r="{ref}"{s}><v>{valor}</v></c>'
    return f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{escape(str(valor))}</t></is></c>'


def _fila_de(ref):
    return int("".join(c for c in ref if c.isdigit()))


def _col_de(ref):
    n = 0
    for c in "".join(c for c in ref if c.isalpha()):
        n = n * 26 + ord(c) - 64
    return n


def _hoja_xml(celdas, tabla=None, x14=False, combinadas=(), validaciones=(), alturas=None, legacy=False):
    """celdas: {ref: valor | (valor, estilo)}."""
    filas = {}
    for ref, v in celdas.items():
        valor, estilo = v if isinstance(v, tuple) else (v, NORMAL)
        filas.setdefault(_fila_de(ref), {})[_col_de(ref)] = _celda(ref, valor, estilo)
    alturas = alturas or {}
    cuerpo = "".join(f'<row r="{n}" spans="1:30"' + (f' ht="{alturas[n]}" customHeight="1"' if n in alturas else "") + ">"
                     + "".join(c[k] for k in sorted(c)) + "</row>" for n, c in sorted(filas.items()))
    listas = "".join(f'<dataValidation type="list" allowBlank="1" sqref="{sqref}"><formula1>"{escape(opciones)}"</formula1></dataValidation>'
                     for sqref, opciones in validaciones)
    listas = f'<dataValidations count="{len(validaciones)}">{listas}</dataValidations>' if validaciones else ""
    refs = list(celdas)
    dimension = f'<dimension ref="A1:{_columna(max(_col_de(r) for r in refs))}{max(_fila_de(r) for r in refs)}"/>' if refs else ""
    merges = f'<mergeCells count="{len(combinadas)}">' + "".join(f'<mergeCell ref="{m}"/>' for m in combinadas) + "</mergeCells>" if combinadas else ""
    partes = ('<legacyDrawing r:id="rId3"/>' if legacy else "") + ('<tableParts count="1"><tablePart r:id="rId1"/></tableParts>' if tabla else "")
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet {NS}>{dimension}<sheetViews><sheetView workbookViewId="0"/>'
            f'</sheetViews><sheetFormatPr defaultRowHeight="15"/><sheetData>{cuerpo}</sheetData>{merges}{listas}'
            f'<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>{partes}{X14 if x14 else ""}</worksheet>')


def _tabla_xml(numero, nombre, ref, encabezados):
    columnas = "".join(f'<tableColumn id="{i}" name="{escape(e)}"/>' for i, e in enumerate(encabezados, 1))
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<table {NS} id="{numero}" name="{nombre}" displayName="{nombre}" '
            f'ref="{ref}"><autoFilter ref="{ref}"/><tableColumns count="{len(encabezados)}">{columnas}</tableColumns></table>')


def crear_xlsx(ruta, hojas):
    """hojas: lista de dicts {nombre, celdas, estado?, tabla?: (nombre, ref, encabezados), x14?, combinadas?, notas?: {ref: texto}}."""
    tipos = ['<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
             '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    rels_libro = ['<Relationship Id="rIdE" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>']
    libro_hojas, partes = [], {}
    n_tabla = 0
    for i, h in enumerate(hojas, 1):
        estado = f' state="{h["estado"]}"' if h.get("estado") else ""
        libro_hojas.append(f'<sheet name="{escape(h["nombre"])}" sheetId="{i}"{estado} r:id="rId{i}"/>')
        rels_libro.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')
        tipos.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        partes[f"xl/worksheets/sheet{i}.xml"] = _hoja_xml(h["celdas"], h.get("tabla"), h.get("x14", False), h.get("combinadas", ()),
                                                          h.get("validaciones", ()), h.get("alturas"), bool(h.get("notas")))
        rels = []
        if h.get("tabla"):
            n_tabla += 1
            nombre, ref, encabezados = h["tabla"]
            partes[f"xl/tables/table{n_tabla}.xml"] = _tabla_xml(n_tabla, nombre, ref, encabezados)
            tipos.append(f'<Override PartName="/xl/tables/table{n_tabla}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"/>')
            rels.append(f'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/table" Target="../tables/table{n_tabla}.xml"/>')
        if h.get("notas"):
            comentarios = "".join(f'<comment ref="{r}" authorId="0"><text><r><t>{escape(t)}</t></r></text></comment>' for r, t in h["notas"].items())
            partes[f"xl/comments{i}.xml"] = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<comments {NS}><authors><author>a</author></authors>'
                                            f'<commentList>{comentarios}</commentList></comments>')
            tipos.append(f'<Override PartName="/xl/comments{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.comments+xml"/>')
            rels.append(f'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="../comments{i}.xml"/>')
            formas = "".join(
                f'<v:shape id="_x0000_s{i * 1024 + 1 + k}" type="#_x0000_t202" style="position:absolute;width:100pt;height:50pt" fillcolor="infoBackground [80]">'
                f'<x:ClientData ObjectType="Note"><x:Row>{_fila_de(r) - 1}</x:Row><x:Column>{_col_de(r) - 1}</x:Column></x:ClientData></v:shape>'
                for k, r in enumerate(h["notas"]))
            partes[f"xl/drawings/vmlDrawing{i}.vml"] = (
                '<xml xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel">'
                f'<o:shapelayout v:ext="edit"><o:idmap v:ext="edit" data="{i}"/></o:shapelayout>'
                '<v:shapetype id="_x0000_t202" coordsize="21600,21600" o:spt="202" path="m,l,21600r21600,l21600,xe"/>' + formas + "</xml>")
            rels.append(f'<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/vmlDrawing" Target="../drawings/vmlDrawing{i}.vml"/>')
        if rels:
            partes[f"xl/worksheets/_rels/sheet{i}.xml.rels"] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                                                + "".join(rels) + "</Relationships>")
    contenido = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="xml" ContentType="application/xml"/>' + "".join(tipos) + "</Types>")
    if any(h.get("notas") for h in hojas):
        contenido = contenido.replace("<Default Extension=\"xml\"", '<Default Extension="vml" ContentType="application/vnd.openxmlformats-officedocument.vmlDrawing"/><Default Extension="xml"', 1)
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", contenido)
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                  '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook {NS}><sheets>{"".join(libro_hojas)}</sheets><calcPr calcId="191029"/></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(rels_libro) + "</Relationships>")
        z.writestr("xl/styles.xml", STYLES)
        for nombre, texto in partes.items():
            z.writestr(nombre, texto)
    return ruta


# -- K4 ----------------------------------------------------------------------------------------------------------------

def _tabla(encabezados, filas, fila_encabezado=5, col_inicial=2):
    """Celdas de una tabla del K4: encabezados y filas (cada celda: valor o (valor, estilo))."""
    celdas = {}
    for j, e in enumerate(encabezados):
        celdas[f"{_columna(col_inicial + j)}{fila_encabezado}"] = (e, ENCABEZADO)
    for i, fila in enumerate(filas, fila_encabezado + 1):
        for j, v in enumerate(fila):
            if v is not None:
                celdas[f"{_columna(col_inicial + j)}{i}"] = v
    return celdas


def hojas_k4():
    rojo = lambda v: (v, ROJO)          # noqa: E731
    instrucciones = {"B3": "Nombre:", "C3": "Ana", "B4": "Apellido:", "C4": "Prueba", "B5": "Correo electrónico:", "C5": "ana@ejemplo.test",
                     "B6": "Número de teléfono:", "C6": "555-0000"}
    inventario = _tabla(["Proceso", "Actividad / Subproceso", "Tipo (Core/Soporte)"], [
        ["Compras", "Emitir orden de compra", "Core"], [None, "Conciliar facturas", None], ["Gestión", "Reportar al jefe", "Soporte"]])
    actividades = _tabla(
        ["Actividad / Subproceso", "Descripción de la actividad", "Recurrencia", "Tiempo que le toma (min)", "Volumen", "Período del volumen",
         "Tiempo de participación indirecta (min)", "Nivel de automatización", "Tiempo de retrabajo", "Causa del retrabajo", "Riesgos"],
        [["Emitir orden de compra", "Genera la orden", "Frecuente", 30, 5, "Diaria", None, "Manual", 0.1, "Datos incompletos", "Error de proveedor"],
         ["Conciliar facturas", "Revisa facturas", "Frecuente", ("1:30", NORMAL), 2, "Bimestral", None, "Semiautomatizada", 15, None, None],
         ["Reportar al jefe", "Informe", "Estacional", F("(1*60)", None), 1, "Mensual", 30, "Rara vez", None, None, None],
         [rojo("Ejemplo: archivar"), rojo("ejemplo"), rojo("x"), rojo(10), rojo(1), rojo("Diaria")],
         [None, None, None, 480]])           # fila auxiliar sin actividad
    return [
        {"nombre": "Instrucciones", "celdas": instrucciones},
        {"nombre": "1. Inventario de Procesos", "celdas": inventario},
        {"nombre": "2. Actividades Base", "celdas": actividades, "notas": {"F7": "Complementado en la entrevista"}},
        {"nombre": "6. Responsabilidades", "celdas": _tabla(
            ["Función / Tarea", "Frecuencia", "Nivel de responsabilidad", "Observaciones"],
            [["Aprobar compras menores", "A demanda", "Alto", "Hasta un tope"], ["Revisar el presupuesto", "Mensual", "Medio", None]])},
        {"nombre": "7. Propósito", "celdas": _tabla(
            ["Propósito principal del puesto", "Función clave", "Objetivos principales", "Resultados esperados"],
            [["Abastecer a la empresa", "Compras oportunas", "Reducir costos", "Entrega a tiempo"]])},
        {"nombre": "8. Información General", "celdas": _tabla(
            ["Nombre del puesto", "Código interno", "Área", "Departamento", "Reporta directamente a", "Reporta matricialmente a",
             "Número de personas a cargo", "Puestos bajo su cargo", "Ubicación"],
            [["Analista de Compras", "CMP-001", "Compras", "Abastecimiento", "Jefe de Compras", "Gerencia regional", 2, "Auxiliar", "Sede central"]])},
        {"nombre": "9. Competencias", "estado": "hidden", "celdas": _tabla(
            ["Tipo de competencia", "Competencia", "Nivel requerido", "Observaciones"],
            [["Técnica", "Negociación", "Avanzado", None], ["Conductual", "Orden", "Intermedio", None], ["Otra", "Idiomas", "Alto", None]])},
        {"nombre": "9. Educación", "celdas": _tabla(["Nivel académico", "Área de formación", "Certificaciones"], [["Licenciatura", "Administración", "Ninguna"]])},
        {"nombre": "10. Condiciones", "celdas": {**_tabla(["Horario de trabajo", "Modalidad", "Equipos utilizados", "Observaciones"],
                                                          [["8 a 5", "Híbrido", "Computadora", None]]),
                                                 "B9": "Exposición del puesto a riesgos laborales y disponibilidad",
                                                 "B10": "Disponibilidad: viajes ocasionales", "B11": "Ruido moderado"}},
        {"nombre": "5. Herramientas", "celdas": _tabla(["Nombre de la herramienta", "Tipo de herramienta", "¿Para qué se utiliza?", "Nivel de dominio",
                                                         "Frecuencia de uso", "Requerido o deseable"], [["SAP", "ERP", "Órdenes", "Alto", "Diaria", "Requerido"]])},
        {"nombre": "11. Optimización", "celdas": _tabla(["Actividad / Subproceso", "Sugerencia de mejora", "Tiempo estimado de ahorro"],
                                                         [["Conciliar facturas", "Automatizar la conciliación", "2 h por mes"]])},
    ]


# -- plantilla metodologica ---------------------------------------------------------------------------------------------

ROTULOS_CONTROL = ["Área / unidad*", "Subárea", "Código puesto*", "Nombre del puesto*", "Colaborador / Entrevistado", "Jefe inmediato",
                   "Ubicación", "Modalidad"]
ROTULOS_PERFIL = ["Código puesto*", "Nombre puesto*", "Área / unidad*", "Subárea", "Reporta a*", "Puestos que supervisa", "Ubicación",
                  "Estado de diseño", "Propósito general del puesto*", "Contribución a objetivos de calidad", "Alcance del rol",
                  "Indicadores principales", "Productos / servicios entregables", "Escolaridad mínima*", "Disciplina / especialidad",
                  "Certificaciones / licencias", "Conocimientos técnicos*", "Herramientas / sistemas", "Disponibilidad / viajes / turnos",
                  "Recursos requeridos", "Riesgos SST / ergonómicos", "Condiciones de trabajo"]
TABLAS = {
    "Responsabilidades": ("tblResponsabilidades", 30, ["Código puesto*", "Responsabilidad principal", "Resultado / entregable*", "Frecuencia", "Autoridad asociada"]),
    "Competencias": ("tblCompetencias", 30, ["Código puesto*", "Tipo", "Competencia / conocimiento", "Nivel requerido", "Conducta / evidencia observable"]),
    "Actividades_Carga": ("tblActividadesCarga", 30, [
        "Código puesto*", "Proceso", "Actividad", "Descripción / inicio-fin", "Tipo proceso", "Frecuencia", "Eventos por frecuencia", "Meses/año activos",
        "Tiempo unitario min", "Espera min", "% dedicación personal", "Retrabajo %", "Fuente del dato", "Calidad dato", "Automatización", "Horas/mes",
        "Subproceso", "Cliente", "Valor", "Responsabilidad vinculada", "Participantes por evento"]),
    "Interacciones": ("tblInteracciones", 30, ["Código puesto*", "Proceso / entregable", "Actor / área relacionada", "Tipo de relación", "Rol RACI*",
                                               "Entrada recibida", "Salida entregada", "Frecuencia"]),
    "Sistemas_Datos": ("tblSistemasDatos", 30, ["Código puesto*", "Sistema / herramienta", "Uso principal"]),
    "Riesgos_Mejoras": ("tblRiesgosMejoras", 30, ["Código puesto*", "Actividad / proceso", "Hallazgo / dolor", "Causa raíz", "Beneficio esperado", "Tipo oportunidad",
                                                  "Evidencia", "Impacto", "Probabilidad", "Acción sugerida", "Esfuerzo", "Prioridad"]),
    "Evidencias": ("tblEvidencias", 9, ["Código puesto*", "Tipo", "Nombre / descripción"]),          # cabe poco: prueba el desborde
    "Puntos_a_validar": ("tblDiccionario13", 18, ["ID", "Hoja", "Actividad / Campo", "Tipo", "Valor Formato", "Valor Reunión", "Fuente Reunión",
                                                  "Qué Validar", "Estado"]),
}


CATALOGOS = {"Valor": ["VA", "NVA-N", "NVA"], "Cliente": ["Interno", "Externo", "Mixto"], "Impacto": ["Bajo", "Medio", "Alto"],
             "Acción": ["Eliminar", "Simplificar", "Estandarizar", "Automatizar", "Centralizar", "Redistribuir", "Mantener"],
             "Escala": ["Muy bajo", "Bajo", "Medio", "Alto", "Muy alto"], "Prioridad": ["Baja", "Media", "Alta", "Crítica"]}


def hojas_plantilla():
    hojas = [{"nombre": "Portada", "celdas": {"B2": "Levantamiento", "B4": F("Control!C8", "0")}}]
    control = {f"B{9 + i}": r for i, r in enumerate(ROTULOS_CONTROL)}
    control.update({f"C{9 + i}": (None, ENTRADA) for i in range(len(ROTULOS_CONTROL))})
    hojas.append({"nombre": "Control", "celdas": control})
    perfil = {}
    for i, r in enumerate(ROTULOS_PERFIL):
        perfil[f"B{9 + 3 * i}"] = (r, ENCABEZADO)
        perfil[f"B{10 + 3 * i}"] = (None, ENTRADA)
    hojas.append({"nombre": "Perfil_Puesto", "celdas": perfil})
    for nombre, (tabla, ultima, encabezados) in TABLAS.items():
        celdas = {f"{_columna(2 + j)}7": (e, ENCABEZADO) for j, e in enumerate(encabezados)}
        for fila in range(8, ultima + 1):
            for j, e in enumerate(encabezados):
                if nombre == "Actividades_Carga" and e == "Horas/mes":
                    celdas[f"{_columna(2 + j)}{fila}"] = F(f'IFERROR(K{fila}*0,0)', 0)
                else:
                    celdas[f"{_columna(2 + j)}{fila}"] = (None, ENTRADA)
        hojas.append({"nombre": nombre, "celdas": celdas, "x14": nombre == "Actividades_Carga",
                      "tabla": (tabla, f"B7:{_columna(1 + len(encabezados))}{ultima}", encabezados),
                      "notas": {"H7": "Nota de la plantilla: eventos por frecuencia"} if nombre == "Actividades_Carga" else None})
    hojas.append({"nombre": "Capacidad", "celdas": {"B11": "Días laborables por mes", "C11": 23.83, "B19": "Horas por FTE", "C19": 190.64}})
    catalogos = {}
    for j, (encabezado, opciones) in enumerate(CATALOGOS.items()):
        catalogos[f"{_columna(1 + j)}6"] = (encabezado, ENCABEZADO)
        catalogos.update({f"{_columna(1 + j)}{7 + i}": o for i, o in enumerate(opciones)})
    hojas.append({"nombre": "Catálogos", "estado": "hidden", "celdas": catalogos})
    return hojas


def crear_k4(ruta):
    return crear_xlsx(ruta, hojas_k4())


# -- K4 en blanco (el que se llena con «llenar-k4») ----------------------------------------------------------------------

NOTA_ROJA = "Nota: La información en rojo es un ejemplo de cómo debe llenarse este formulario; puede eliminarla cuando ya no la necesite."
LISTA_RECURRENCIA = "Por evento,A demanda,Continua,Estacional,Única"
LISTA_PERIODO = "Diaria,Semanal,Quincenal,Mensual,Bimestral,Trimestral,Semestral,Anual"
LISTA_AUTOMATIZACION = "Manual,Semiautomatizada,Automatizada"


def _marco(primera, ultima, columnas, estilo=ROJO):
    """Celdas de respuesta vacias con el formato del formulario (letra roja, como en el K4 real)."""
    return {f"{_columna(c)}{n}": (None, estilo) for n in range(primera, ultima + 1) for c in range(2, 2 + columnas)}


def hojas_k4_en_blanco(sin_encabezados_de=None):
    """K4 vacio: encabezados grises, ejemplos y notas en rojo, combinadas, listas desplegables y un bloque de exposicion."""
    def hoja(nombre, encabezados, fila_enc, filas_marco, **extra):
        celdas = {"B6": (NOTA_ROJA, ROJO)}
        if nombre != sin_encabezados_de:
            celdas.update({f"{_columna(2 + j)}{fila_enc}": (e, ENCABEZADO) for j, e in enumerate(encabezados)})
        celdas.update(_marco(fila_enc + 1, fila_enc + filas_marco, len(encabezados)))
        celdas.update(extra.pop("celdas", {}))
        return {"nombre": nombre, "celdas": celdas, **extra}

    actividades = ["Actividad / Subproceso", "Descripción de la actividad", "Recurrencia", "Tiempo que le toma (min)", "Volumen", "Período del volumen",
                   "Tiempo de participación indirecta (min)", "Nivel de automatización", "Tiempo de retrabajo", "Causa del retrabajo", "Riesgos"]
    hojas = [
        {"nombre": "Instrucciones", "celdas": {"D7": "Nombre: ", "E7": (None, ENTRADA), "D8": "Apellido: ", "E8": (None, ENTRADA),
                                               "D9": "Correo: ", "E9": (None, ENTRADA), "D10": "Número de teléfono / Ext.: ", "E10": (None, ENTRADA)}},
        hoja("1. Inventario de Procesos", ["Proceso", "Actividad / Subproceso", "Tipo (Core / Soporte)"], 8, 5, combinadas=["B9:B13", "D9:D13"]),
        hoja("2. Actividades Base", actividades, 8, 3, validaciones=[("D9:D11", LISTA_RECURRENCIA), ("G9:G11", LISTA_PERIODO),
                                                                      ("I9:I11", LISTA_AUTOMATIZACION)], alturas={9: 20, 10: 20}),
        hoja("5. Herramientas Tecnológicas", ["Nombre de la herramienta o sistema", "Tipo de herramienta / sistema", "Para qué se utiliza en el puesto",
                                              "Nivel de dominio requerido", "Frecuencia de uso", "¿Es requerido o deseable?"], 9, 3),
        hoja("6. Responsabilidades del Puesto", ["Función / tarea detallada", "Frecuencia", "Nivel de responsabilidad", "Observaciones / comentarios"], 8, 4),
        hoja("8. Información General", ["Nombre del puesto", "Código interno", "Área", "Departamento", "Reporta directamente a (nombre, apellido y puesto)",
                                        "Reporta matricialmente / regionalmente a", "Número de personas a cargo", "Puestos bajo su cargo", "Ubicación / Sucursal"], 7, 2),
        hoja("9. Competencias", ["Tipo de competencia (técnica/conductual)", "Competencia", "Nivel requerido", "Observaciones"], 8, 2,
             estado="hidden", celdas={"B9": ("Técnica", ROJO), "C9": ("Legislación laboral", ROJO), "D9": ("Avanzado", ROJO), "E9": ("N/A", ROJO),
                                      "B10": ("Conductual", ROJO), "C10": ("Liderazgo", ROJO), "D10": ("Avanzado", ROJO), "E10": ("N/A", ROJO),
                                      "B13": ("La información en color rojo es un ejemplo de cómo debe llenarse esta hoja.", ROJO)}),
        hoja("10. Condiciones de Trabajo", ["Horario de trabajo", "Modalidad", "Equipos utilizados", "Observaciones"], 8, 2,
             combinadas=["B12:E12", "B13:E13", "B14:E14"],
             celdas={"B12": ("Exposición del puesto a riesgos laborales y disponibilidad", ENCABEZADO), "B13": (None, ROJO), "B14": (None, ROJO)}),
    ]
    return hojas


def crear_k4_en_blanco(ruta, sin_encabezados_de=None):
    return crear_xlsx(ruta, hojas_k4_en_blanco(sin_encabezados_de))


def crear_plantilla(ruta):
    return crear_xlsx(ruta, hojas_plantilla())
