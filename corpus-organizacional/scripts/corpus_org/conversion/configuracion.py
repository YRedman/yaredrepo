"""Configuracion editable de la conversion.

Para reconocer un titulo de seccion o una etiqueta nueva basta con agregarla
aqui; no hace falta tocar el codigo de extraccion (principio abierto/cerrado).
"""

EXT_SOPORTADAS = {".pdf", ".docx"}
EXT_RECONOCIDAS = {".pdf", ".docx", ".doc"}

# Secciones que no se incluyen en el corpus (titulo normalizado, sin numeracion).
SECCIONES_EXCLUIDAS = [
    "control de cambios", "historial de cambios", "control de versiones",
    "seccion aprobada", "seccion de aprobacion", "seccion de aprobaciones",
    "aprobaciones", "aprobacion del documento", "firmas de aprobacion",
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
    ("objetivo general", "proposito"), ("proposito", "proposito"), ("objetivo", "proposito"), ("mision", "proposito"),
    ("funciones y responsabilidades", "funciones"), ("funciones principales", "funciones"),
    ("funciones", "funciones"), ("responsabilidades", "funciones"), ("actividades", "funciones"),
]
SECCIONES_POR_TIPO = {"P": SECCIONES_P, "D": SECCIONES_D}

# Etiquetas de datos generales del descriptivo (en tablas "Etiqueta | Valor" o lineas "Etiqueta: valor").
ETIQUETAS_D = [
    ("nombre del puesto", "nombre_puesto"), ("titulo del puesto", "nombre_puesto"),
    ("denominacion del puesto", "nombre_puesto"), ("puesto", "nombre_puesto"), ("cargo", "nombre_puesto"),
    ("reporta a", "reporta_a"), ("reporta", "reporta_a"), ("jefe inmediato", "reporta_a"),
    ("supervisor inmediato", "reporta_a"),
    ("supervisa a", "supervisa_a"), ("supervisa", "supervisa_a"), ("puestos que supervisa", "supervisa_a"),
    ("area", "area"), ("departamento", "area"), ("gerencia", "area"), ("direccion", "area"),
]

CAMPOS_CLAVE = {
    "P": [("objetivo", "Objetivo"), ("alcance", "Alcance"), ("responsabilidades", "Responsabilidades"),
          ("desarrollo", "Desarrollo del proceso")],
    "D": [("nombre_puesto", "Nombre del puesto"), ("reporta_a", "Reporta a"), ("proposito", "Propósito"),
          ("funciones", "Funciones")],
    "C": [],
}

# Columnas de una tabla del desarrollo cuyo contenido es una actividad.
COLUMNAS_ACTIVIDAD = ("actividad", "descripcion", "accion", "tarea")

# Palabras que se ignoran al proponer el codigo de 3 letras de un departamento.
PALABRAS_VACIAS_DEP = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "Y", "E", "EN", "PARA", "POR", "A", "AL"}

# Cuantos bloques del inicio del documento se revisan (ademas del encabezado) para buscar metadatos.
BLOQUES_INICIALES_METADATOS = 6
