"""Configuracion editable de la conversion.

Para reconocer un titulo de seccion o una etiqueta nueva basta con agregarla
aqui; no hace falta tocar el codigo de extraccion (principio abierto/cerrado).
"""

EXT_SOPORTADAS = {".pdf", ".docx"}
EXT_RECONOCIDAS = {".pdf", ".docx", ".doc"}
# Transcripciones manuales (Markdown, CSV, texto): solo se aceptan como material de contexto.
EXT_TEXTO = {".md", ".csv", ".txt"}
# Archivos del sistema o temporales que nunca son documentos (bloqueos de Word, miniaturas...).
ARCHIVOS_IGNORADOS = r"^(~\$|\.~lock|\._)|^(thumbs\.db|desktop\.ini|\.ds_store)$"
# Si el mismo documento existe en varios formatos se usa el de menor valor.
PREFERENCIA_EXT = {".docx": 0, ".pdf": 1, ".doc": 2}

# Secciones que no se incluyen en el corpus (titulo normalizado, sin numeracion).
SECCIONES_EXCLUIDAS = [
    "control de cambios", "historial de cambios", "control de versiones",
    "seccion aprobada", "seccion de aprobacion", "seccion de aprobaciones",
    "aprobaciones", "aprobacion del documento", "firmas de aprobacion", "firma de aprobacion",
    "firma del colaborador",
]

# Secciones conocidas: titulo normalizado -> campo. El orden importa (mas largo primero).
SECCIONES_P = [
    ("macroproceso", "macroproceso"), ("macro proceso", "macroproceso"),
    ("objetivos", "objetivo"), ("objetivo", "objetivo"), ("proposito", "objetivo"), ("objeto", "objetivo"),
    ("alcance", "alcance"),
    ("glosario de terminos", "glosario"), ("glosario", "glosario"), ("terminos y definiciones", "glosario"),
    ("definiciones", "glosario"),
    ("roles y responsabilidades", "responsabilidades"), ("responsabilidades", "responsabilidades"),
    ("responsables", "responsabilidades"),
    ("politicas del procedimiento", "politicas"), ("politicas", "politicas"), ("lineamientos", "politicas"),
    ("desarrollo de proceso", "desarrollo"), ("desarrollo del proceso", "desarrollo"),
    ("desarrollo del procedimiento", "desarrollo"), ("desarrollo", "desarrollo"),
    ("descripcion del proceso", "desarrollo"), ("descripcion del procedimiento", "desarrollo"),
    ("diagrama de proceso", "diagrama"), ("diagrama del proceso", "diagrama"), ("diagrama de flujo", "diagrama"),
    ("flujograma", "diagrama"), ("diagrama", "diagrama"),
    ("documentos de referencia", "referencias"), ("referencias", "referencias"),
    ("documentos relacionados", "referencias"),
    ("lista de distribucion", "distribucion"), ("distribucion", "distribucion"), ("entrenamiento", "distribucion"),
    ("anexos y formatos", "anexos"), ("anexos", "anexos"), ("formatos", "anexos"), ("registros", "anexos"),
]
SECCIONES_D = [
    ("datos generales", "datos_generales"), ("identificacion del puesto", "datos_generales"),
    ("datos del puesto", "datos_generales"), ("informacion general", "datos_generales"),
    ("proposito del puesto", "proposito"), ("objetivo del puesto", "proposito"), ("mision del puesto", "proposito"),
    ("objetivo general", "proposito"), ("funcion general", "proposito"), ("proposito", "proposito"),
    ("objetivo", "proposito"), ("mision", "proposito"),
    ("funciones y responsabilidades", "funciones"), ("funciones principales", "funciones"),
    ("principales funciones", "funciones"), ("funciones especificas", "funciones"),
    ("areas de relacionamiento", "relacionamiento"), ("relaciones de trabajo", "relacionamiento"),
    ("requisitos del puesto", "requisitos"),
    ("descripcion de funciones", "funciones"), ("responsabilidades del puesto", "funciones"),
    ("actividades principales", "funciones"), ("principales actividades", "funciones"),
    ("funciones", "funciones"), ("responsabilidades", "funciones"), ("actividades", "funciones"),
]
SECCIONES_POR_TIPO = {"P": SECCIONES_P, "D": SECCIONES_D}

# Etiquetas de datos generales del descriptivo: tablas "Etiqueta | Valor", tablas horizontales (fila de
# etiquetas + fila de valores) o lineas "Etiqueta: valor". CAMPO_OTRO = etiqueta conocida que no se indexa;
# sirve para que su valor (o la etiqueta misma) nunca se tome como dato de otro campo.
CAMPO_OTRO = "_otro"
ETIQUETAS_D = [
    ("nombre del puesto", "nombre_puesto"), ("titulo del puesto", "nombre_puesto"),
    ("denominacion del puesto", "nombre_puesto"), ("nombre del cargo", "nombre_puesto"),
    ("titulo del cargo", "nombre_puesto"), ("denominacion del cargo", "nombre_puesto"),
    ("puesto", "nombre_puesto"), ("cargo", "nombre_puesto"),
    ("reporta directamente a", "reporta_a"), ("reporta a", "reporta_a"), ("reporta", "reporta_a"),
    ("jefe inmediato superior", "reporta_a"), ("jefe inmediato", "reporta_a"), ("jefe directo", "reporta_a"),
    ("superior inmediato", "reporta_a"), ("supervisor inmediato", "reporta_a"), ("depende de", "reporta_a"),
    ("dependencia jerarquica", "reporta_a"), ("puesto superior", "reporta_a"),
    ("supervisa a", "supervisa_a"), ("supervisa", "supervisa_a"), ("puestos que supervisa", "supervisa_a"),
    ("puestos a su cargo", "supervisa_a"), ("personal a cargo", "supervisa_a"), ("subordinados", "supervisa_a"),
    ("area de interaccion", CAMPO_OTRO), ("tipo de relacion", CAMPO_OTRO),
    ("area", "area"), ("departamento", "area"), ("gerencia", "area"), ("direccion", "area"),
    ("unidad organizativa", "area"), ("unidad", "area"),
    ("salario", CAMPO_OTRO), ("sueldo", CAMPO_OTRO), ("banda salarial", CAMPO_OTRO), ("nivel", CAMPO_OTRO),
    ("ubicacion", CAMPO_OTRO), ("sede", CAMPO_OTRO), ("codigo", CAMPO_OTRO), ("fecha", CAMPO_OTRO),
]

CAMPOS_CLAVE = {
    "P": [("objetivo", "Objetivo"), ("alcance", "Alcance"), ("responsabilidades", "Responsabilidades"),
          ("desarrollo", "Desarrollo del proceso")],
    "D": [("nombre_puesto", "Nombre del puesto"), ("reporta_a", "Reporta a"), ("proposito", "Propósito"),
          ("funciones", "Funciones")],
    "C": [],
}

# Tabla "Áreas de Relacionamiento" (Área de Interacción | Tipo de Relación): tipo -> campo del descriptivo.
TIPOS_RELACION = (("subordinacion directa", "reporta_a"), ("reporte directo", "supervisa_a"))

# Columnas de una tabla del desarrollo cuyo contenido es una actividad (en orden de preferencia) y
# columnas que indican quien la ejecuta.
COLUMNAS_ACTIVIDAD = ("actividad", "descripcion", "accion", "tarea", "que se hace")
COLUMNAS_RESPONSABLE = ("responsab", "quien", "ejecuta", "rol")

# Palabras que se ignoran al proponer el codigo de 3 letras de un departamento.
PALABRAS_VACIAS_DEP = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "Y", "E", "EN", "PARA", "POR", "A", "AL"}

# Cuantos bloques del inicio del documento se revisan (ademas del encabezado) para buscar metadatos.
BLOQUES_INICIALES_METADATOS = 6
