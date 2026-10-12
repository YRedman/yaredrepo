# Corpus organizacional

Scripts del skill `corpus-organizacional` (ver `SKILL.md`):

- `scripts/convertir.py`: convierte descriptivos de puesto y procedimientos (PDF/Word) a Markdown, construye el índice y publica el corpus.
- `scripts/corpus.py`: consulta el corpus publicado (solo biblioteca estándar).

La línea de comandos y el formato de los archivos generados son los mismos de la v2.0, así que un corpus publicado con la v2.0 se puede seguir consultando. Conviene reconstruirlo para aprovechar las correcciones de metadatos.

## Estructura

```
scripts/
  convertir.py, corpus.py        Puntos de entrada (solo llaman a main)
  corpus_org/
    comun/                       Compartido por ambos scripts (solo biblioteca estándar)
      esquema.py                 Contrato de datos: columnas del índice, códigos, estados no publicables
      texto.py, archivos.py, markdown.py, errores.py
    conversion/
      configuracion.py           Títulos de sección, etiquetas y campos clave (editable)
      extractores/               Un extractor por formato (pdf.py, word.py, texto.py) + maquetacion.py
      analisis.py                Secciones, campos, actividades y códigos citados
      metadatos.py               Versión, estado, vigencia, propietario... (solo con etiqueta explícita)
      render.py, verificacion.py, reportes.py
      inventario.py, entradas.py, asignacion.py, lote.py, publicacion.py
      cli.py                     Argumentos y orquestación de los modos
    consulta/
      repositorio.py             Carga del corpus publicado y exclusión de no vigentes
      parser.py                  Recorrido único del Markdown de un documento
      areas.py, puestos.py, roles.py, relaciones.py
      comandos/                  Un archivo por comando (catalogo, area, ficha, doc, ...)
      cli.py
tests/                           Pruebas unitarias y de integración
```

### Cómo se aplican los principios

| Principio | Antes | Ahora |
|---|---|---|
| Responsabilidad única | `extraer_pdf` (220 líneas), `procesar_grupo` y `Corpus.__init__` hacían extracción, análisis, escritura e impresión a la vez. | Cada módulo tiene un solo motivo de cambio. Por ejemplo, `metadatos.py` solo extrae metadatos, `reportes.py` solo escribe reportes y cada comando vive en su propio archivo. |
| Abierto/cerrado | Para agregar un comando o un formato había que editar `if/elif` y diccionarios dispersos. | Un comando nuevo es una subclase de `Comando` registrada en `comandos/__init__.py`. Un formato nuevo es una subclase de `Extractor`. Las secciones y etiquetas se configuran en `configuracion.py` y `metadatos.CAMPOS`. |
| Sustitución de Liskov / interfaces | No había contratos. | `Extractor.extraer()` y `Comando.ejecutar()` son contratos pequeños: cualquier implementación sirve al pipeline o a la CLI. |
| Inversión de dependencias | Los comandos hacían `print` y `sys.exit` dentro de la lógica, y `DATOS` se calculaba al importar. | La lógica lanza excepciones (`CorpusError`, `AreaAmbigua`...). Los comandos escriben en una `Salida` inyectada y reciben el corpus ya cargado, así que se pueden probar con `StringIO` y un corpus en memoria. |
| Fuente única de verdad | `corpus.py` tenía una lista de columnas propia, desactualizada respecto a `convertir.py` (22 frente a 29 columnas). | Ambos scripts usan `comun/esquema.py`. |
| Estado explícito | `analizar()` agregaba atributos sueltos al documento (`getattr(doc, "version", "")`). Además, `_CACHE_PUESTOS` era una variable global que había que llenar en cierto orden. | Se usan `DocumentoExtraido`, `Analisis` y `Metadatos` como dataclasses, y `DetectorPuestos` es una clase autocontenida. |

## Falsos positivos corregidos

Todos se reprodujeron con el corpus de `tests/fixtures_corpus.py` y quedaron cubiertos por pruebas.

| # | Problema en v2.0 | Ejemplo real | Corrección |
|---|---|---|---|
| 1 | Los metadatos se buscaban sin exigir `:` en el texto unido de encabezado y cuerpo. | `Estado documental: "de cuenta revisado mensualmente"`, `Versión: "de"` (de “Revisión de la solicitud”), `Propietario: "Gerente de Compras Objetivo Establecer el proceso…"` | `metadatos.py` exige la etiqueta (`Estado:` o una celda `Estado`), corta el valor en la siguiente etiqueta o separador y valida la forma del valor. |
| 2 | Un documento obsoleto no se filtraba, porque su estado capturado era `"Obsoleto Objetivo Atender…"`. | P-COM-02 aparecía en búsquedas y fichas. | Consecuencia de la corrección 1, más `estado_no_publicable()`, que compara por palabra completa. |
| 3 | El filtro de no vigentes quitaba el documento del índice pero no del texto. | `verificar` reportaba “Documentos sin fila en el diccionario”, `buscar` seguía encontrándolo y `area` lo contaba como “NO CONVERTIDO”. | `repositorio.cargar_corpus` excluye el documento del índice y del texto a la vez. Los excluidos se informan aparte. |
| 4 | Cualquier tabla de 2 columnas del contexto creaba alias de área. | Una fila `\| Responsable \| Compras \|` hacía que “Responsable” contara como mención del área Compras en `relaciones`. | Solo se aceptan alias con forma de sigla (`RRHH`, `TI`, `R.H.`). |
| 5 | El rol y el verbo se calculaban con toda la línea. | En “El Gerente aprueba las órdenes. El Jefe de Almacén recibe el material.”, el Jefe de Almacén aparecía con rol “Aprueba”. | Se usa la oración que contiene la mención (`oracion_con`). |
| 6 | Las raíces se buscaban sin límite de palabra. | “con**firm**a” se clasificaba como Aprueba e “in**valid**ar” como Revisa. | Las raíces se buscan al inicio de una palabra (`\b`). |
| 7 | Una frase parecida a varios puestos se asignaba al primero. | “Gerente de Compras” se asignaba a “Gerente de Compras Nacionales” cuando también existía “…Internacionales”. | Los empates quedan como “ambigua” y se listan sin asignar. |
| 8 | Las actividades eran todas las viñetas del documento. | “Compras nacionales” (del Alcance) contaba como actividad del proceso. Los descriptivos también tenían actividades. | Solo cuentan las viñetas y la columna “Actividad” de la sección de desarrollo de los procedimientos. |
| 9 | Los códigos citados aceptaban cualquier `XX-123`. | `ISO-9001` y `COVID-19` aparecían como documentos citados. | Se exigen al menos dos guiones (`PR-ALM-001`, `NOM-035-STPS-2018`). |
| 10 | Al reconstruir, quedaban en `control/` los DIC y .md de corridas anteriores. | Después de una conversión parcial, `construir` daba **REQUIERE REVISIÓN** por “Códigos duplicados: P-COM-01”. | `construir` limpia los archivos generados antes de convertir. |
| 11 | pdfplumber devuelve `(cid:NN)` para glifos que no puede leer. | El reporte decía “palabras solo detectadas por el segundo motor: cid”. | Se filtra `(cid:NN)` antes de comparar. |
| 12 | La `ficha` comparaba subcadenas. | La sección “Comisiones” se mostraba como “misión”. Además, la cabecera de una segunda tabla se contaba como un paso más. | Se compara al inicio de palabra y cada tabla reinicia su cabecera. |
| 13 | Un área sin nombre coincidía con cualquier búsqueda parcial (`"" in texto`). | Daba un `AMBIGUO` espurio. | Las áreas sin nombre se ignoran en la búsqueda por parecido. Cuando se elige un área por parecido, se avisa con `AVISO: se interpretó como…`. |

## v3.1: correcciones tomadas de la v2.1

La v2.1 se desarrolló en paralelo a partir de la misma v2.0 y corrigió otros problemas de lectura. Se compararon ambas versiones con los corpus de prueba de cada una y se portaron sus correcciones a esta estructura. Ninguna versión resolvía todo por sí sola.

| # | Problema | Ejemplo | Corrección | Dónde |
|---|---|---|---|---|
| 14 | Archivos fantasma en el inventario | `~$mpra de insumos.docx` (bloqueo de Word) y `Compra de insumos (1).docx` recibían código | Se ignoran los temporales y del sistema. El mismo documento en .docx/.pdf o con copia `(1)` se inventaría una vez (preferencia .docx) y se avisa (`--incluir-duplicados` para conservarlos) | `inventario.py`, `entradas.py` |
| 15 | Mismo nombre de archivo en dos áreas | “Asistente Administrativo” de Compras y de Almacén quedaban sin convertir | Emparejamiento por ruta `Tipo/Departamento/Archivo` (la de `lista.txt`); por nombre solo si los adjuntos llegan sin carpetas | `asignacion.py` |
| 16 | Etiquetas de descriptivos no reconocidas | “Jefe directo”, “Depende de”, “Puestos a su cargo”, “Actividades principales” | Etiquetas y secciones nuevas en `configuracion.py` | `configuracion.py` |
| 17 | Tabla horizontal leída como vertical | `nombre_puesto = "Departamento"`, `reporta_a = "Salario"` | Se reconoce la fila de etiquetas con la fila de valores debajo, y un valor que es una etiqueta conocida nunca se acepta | `analisis._campos_por_etiqueta` |
| 18 | Ligaduras rotas en celdas de PDF | “eficiencia” salía como “efci encia” y el reporte avisaba palabras inexistentes | El texto de cada celda se rehace con las palabras de la página (`get_text("words")`) | `extractores/pdf.py` |
| 19 | Diagramas transcritos como texto | Cajas sueltas (“Inicio”, “¿Aprobada?”) se leían como contenido | Las secciones “Diagrama…” se sustituyen por `[DIAGRAMA: la sección «…» no se transcribe; ver página N]`. Un diagrama dibujado con formas en PDF genera una nota en el reporte | `analisis._sustituir_diagramas`, `pdf._formas_con_texto` |
| 20 | Puestos homónimos | El “Asistente Administrativo” de Almacén se asignaba al de Compras y creaba una relación falsa | Se resuelve con el área del documento que menciona; si no alcanza, queda como ambiguo | `puestos.elegir` |
| 21 | Verbos y roles | “aprobación” no contaba como Aprueba; “registrar la firma” sí | Se reconoce `aprob*`; `firm` y `liber` dejan de ser aprobación; Aprueba y Revisa son roles distintos; se toma el verbo más cercano a la mención | `roles.py` |
| 22 | Roles fuera del patrón “Jefe/Gerente…” | “comité de compras” o “coordinadores de logística” en la columna Responsable no aparecían | Toda celda de esa columna es un rol | `participacion.rol_sin_descriptivo` |
| 23 | Contexto transcrito a mano | Un contexto en `.md` o `.csv` detenía `construir` | Extractor de texto (Markdown simple y CSV), solo para el modo contexto | `extractores/texto.py` |

## v3.2: exactitud de tablas PDF y títulos de Word

| # | Problema | Ejemplo | Corrección | Dónde |
|---|---|---|---|---|
| 24 | Filas de tabla tomadas como encabezado de página | En una tabla de 60 filas partida entre dos páginas, “Analista de Procesos” y “Actividad número #” aparecían arriba en ambas páginas y se trataron como encabezado repetido. El título “3. Desarrollo del proceso”, la cabecera y las filas 1–3 terminaban en “Datos de encabezado y pie”, y el índice marcaba el desarrollo como `[NO ESPECIFICADO]` | Un encabezado o pie repetido debe aparecer **una sola vez por página y a la misma altura** (±4 pt). Las filas de una tabla se repiten varias veces o a otra altura | `pdf._repetidas` |
| 25 | Pérdida silenciosa de texto en la zona de encabezado | Las filas 26–32 de la página 2 se borraban y la verificación seguía diciendo 100 %, porque descontaba del original todo lo marcado como encabezado (446 de 446 palabras; el documento tiene 523) | Solo se descarta como encabezado lo que coincide con el encabezado guardado de la primera página. El resto queda como contenido y el reporte lo avisa | `pdf._sin_texto_unico` |
| 26 | Numeración automática de Word en títulos | “2. Alcance” salía como “Alcance” | El número de Word se calcula también para los títulos | `word._bloque_texto` |

Resultado en el caso de prueba de la v2.1: 60 de 60 filas, en orden, en una sola tabla (antes 48).

Pendiente de la comparación (no incluido en esta versión): comandos `briefing` y `kpis`, `areas_extra.csv`, códigos congelados con `--base`, avisos de estructura y revisión visual, y huellas SHA-256.

Otras mejoras:

- Los archivos PDF y ZIP ahora se cierran siempre.
- `construir` llama a las funciones directamente, sin lanzar subprocesos de sí mismo.
- `gobierno` muestra `[NO ESPECIFICADO]` en lugar de celdas vacías.
- El campo `proceso`, que antes siempre quedaba vacío, se llena cuando el original trae `Proceso:`.

## Pruebas

```bash
python -m unittest discover -s tests -t .      # o: python -m pytest tests
```

Las pruebas de integración generan corpus sintéticos (`tests/fixtures_corpus.py`, `tests/fixtures_casos.py`). Necesitan `pymupdf`, `lxml`, `python-docx` y `reportlab`, y las de PDF además LibreOffice (`soffice`); si falta alguno, esas pruebas se omiten.

Los datos del cliente (documentos, materiales de contexto y corpus generado) no se versionan: `.gitignore` excluye `contexto/`, `entrada/`, `salida_corpus/` y `publicado/`.
