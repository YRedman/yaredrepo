# Corpus organizacional

Scripts del corpus organizacional para un agente de Copilot (ver `SKILL.md`, que es el del skill `fuente-contexto`):

- `scripts/convertir.py`: convierte descriptivos de puesto, procedimientos, protocolos y políticas (PDF/Word) a Markdown, construye el índice y publica el corpus en dos carpetas para comprimir: `fuente-documentos` y `fuente-contexto`.
- `scripts/corpus.py`: consulta el corpus publicado (solo biblioteca estándar: en Copilot no hay red ni instalación de paquetes).

Desde la v4.0 los códigos son `TTT-AAA-NN` (ver «v4.0» más abajo). Un corpus construido con la codificación anterior (`D-`, `P-`, `C-CTX-`) se migra solo al volver a construir.

## Instalación

Requisitos: Python 3.10 o superior (se recomienda 3.12 o 3.13) y, para los PDF escaneados, Tesseract con el idioma español.

**Windows (un solo paso):** desde la carpeta del proyecto,

```powershell
powershell -ExecutionPolicy Bypass -File .\instalar.ps1
```

El script busca Python, crea el entorno virtual `.venv`, instala `requirements.txt`, instala Tesseract con `winget` si falta, descarga el idioma español (`spa.traineddata`) y termina con `convertir.py diagnostico`. Opciones: `-SinOCR` (no instala Tesseract) y `-Pruebas` (instala también `requirements-dev.txt`). Después, en cada terminal nueva: `.\.venv\Scripts\Activate.ps1`.

**A mano (cualquier sistema):**

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/convertir.py diagnostico
```

Tesseract no se instala con pip: en Windows, instalador de UB Mannheim (marcar *Additional language data → Spanish*); en Linux, `apt install tesseract-ocr tesseract-ocr-spa`; en macOS, `brew install tesseract tesseract-lang`.

## Estructura

```
scripts/
  convertir.py, corpus.py        Puntos de entrada (solo llaman a main)
  corpus_org/
    comun/                       Compartido por ambos scripts (solo biblioteca estándar)
      tipos.py                   Tabla de tipos de documento (DES, PRD, PRO, POL, ORG, KPI...) y patrones de código
      estructura.py              Las dos skills publicadas y sus carpetas
      esquema.py                 Contrato de datos: columnas del índice, códigos, estados no publicables
      texto.py, archivos.py, markdown.py, errores.py
    conversion/
      configuracion.py           Títulos de sección, etiquetas y campos clave (editable)
      extractores/               Un extractor por formato (pdf.py, word.py, texto.py) + maquetacion.py
      analisis.py                Secciones, campos, actividades y códigos citados
      metadatos.py               Versión, estado, vigencia, propietario... (solo con etiqueta explícita)
      render.py, verificacion.py, reportes.py
      inventario.py, entradas.py, asignacion.py, lote.py, publicacion.py, skills.py (aplana corpus_org al publicar)
      cli.py                     Argumentos y orquestación de los modos
    consulta/
      repositorio.py             Carga del corpus publicado y exclusión de no vigentes
      parser.py                  Recorrido único del Markdown de un documento
      ubicacion.py               Localiza fuente-contexto y fuente-documentos (en Copilot, por el nombre del skill)
      areas.py, entidades.py, puestos.py, roles.py, relaciones.py, participacion.py, indicadores.py, integridad.py
      comandos/                  Un archivo por comando (catalogo, area, briefing, ficha, doc, kpis, ...)
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

## v3.3: fase 2 (control de calidad y comandos para el agente)

**Construcción**

| Función | Qué hace | Dónde |
|---|---|---|
| Avisos de estructura | Cada documento registra señales de que la estructura pudo leerse mal aunque el texto esté completo: tabla tratada como texto, líneas fuera de celdas, tabla partida con líneas sueltas, filas sin primera celda, párrafos repetidos, contenido sobre todo en imágenes, posible diagrama vectorial, nombre del puesto distinto del archivo, números que no aparecen completos (`45.000,00` → `45.000`) y OCR. Columnas nuevas del índice: `palabras_agregadas`, `avisos_estructura`, `detalle_avisos` (al final; las anteriores no se mueven) | `extractores/pdf.py`, `analisis.avisos_de_estructura`, `modelo.DocumentoConvertido.avisos` |
| Validación más estricta | Cobertura < 100 %, palabras que no están en el original y errores del contexto pasan a ser **problemas** (antes eran avisos) | `publicacion.validar_publicacion` |
| Revisión visual | Los documentos con avisos y una muestra reproducible del 10 % quedan pendientes hasta anotar su código en `revision_visual_ok.txt`. Tres estados con código de salida: LISTO (0), REQUIERE REVISIÓN (2), PENDIENTE DE REVISIÓN VISUAL (3). `--muestra-revision` ajusta la muestra | `publicacion.py`, `cli.modo_construir` |
| Huellas SHA-256 | `huellas.sha256` (desde la v4.0 en `fuente-contexto/indice/`); `corpus.py verificar` detecta archivos editados o borrados después de la conversión | `publicacion.escribir_huellas`, `consulta/integridad.py` |
| Códigos estables | Al reconstruir con `lista.txt`, el inventario anterior es la base: cada documento conserva su código, los nuevos van al final de su grupo y los que ya no están quedan `RETIRADO` reservando su código (`inventario --base`) | `inventario.construir_inventario` |
| Datos del contexto | Los `kpi*.csv` de la carpeta de contexto se unen en `kpis.csv` y `areas_extra.csv` se publica tal cual (no se convierte a `contexto.md`) | `cli._datos_de_contexto` |

**Consulta**

| Función | Qué hace | Dónde |
|---|---|---|
| `areas_extra.csv` | Áreas internas sin documentos, entidades externas y frases a excluir (“Seguridad Social” no es el área Seguridad; hay exclusiones base) | `consulta/entidades.py` |
| Menciones no resueltas | `relaciones` lista aparte las entidades sin documentos, las unidades no identificadas (“Dirección de Logística”) y los puestos ambiguos; nunca cuentan como relación con un área | `relaciones.NoResueltas` |
| `kpis` | Indicadores con meta, medición (“sin medición” si está vacía, nunca cero) y documentos que mencionan sus términos `[Inferido]` | `consulta/indicadores.py`, `comandos/kpis.py` |
| `participacion` | Resumen por puesto sobre todas las filas y detalle acotado (`--detalle N\|todo`). Las ausencias (roles sin descriptivo, descriptivos sin participación) solo se afirman con el corpus completo | `consulta/participacion.py` |
| `briefing` | Tablas del briefing ya calculadas por partes de 15 documentos, con la línea de cobertura; el modelo solo redacta resumen, insights y “para profundizar” | `comandos/briefing.py` |
| `verificar` y `catalogo` | Huellas, corpus completo, palabras agregadas, documentos con avisos, códigos retirados, KPIs y entidades sin documentos | `comandos/verificar.py`, `comandos/catalogo.py` |

**Actividades:** si el desarrollo tiene tabla, las actividades son sus filas con su responsable (“Solicitar cotización (Responsable: Comprador)”); si no, sus viñetas.

**Falsos positivos encontrados al probar la fase 2 y corregidos:**
- Una tabla de indicadores en el contexto (`| K-01 | Compras |`) convertía “K-01” en alias del área Compras. Ahora una sigla no lleva dígitos.
- En una fila `| Entregar la mercancía a Almacén | coordinadores de logística |`, el sustantivo “coordinadores” se tomaba como el verbo. Ahora el verbo se busca primero en la celda de la mención.

**Comparación con la batería de la v2.1:** con esta versión pasan 34 de sus 35 pruebas punta a punta. La que falla solo cambia el formato del mensaje de ambigüedad, no el comportamiento. La v2.1 fallaba la de la tabla partida de 60 filas, que aquí pasa.

Otras mejoras:

- Los archivos PDF y ZIP ahora se cierran siempre.
- `construir` llama a las funciones directamente, sin lanzar subprocesos de sí mismo.
- `gobierno` muestra `[NO ESPECIFICADO]` en lugar de celdas vacías.
- El campo `proceso`, que antes siempre quedaba vacío, se llena cuando el original trae `Proceso:`.

## v3.4: plantillas reales de descriptivo de puesto (PDF)

Ajustes hechos al probar el lector con descriptivos reales (procesados fuera del repositorio; las pruebas usan un PDF ficticio con la misma maquetación, `tests/fixtures_plantilla.py`).

| # | Problema | Corrección | Dónde |
|---|---|---|---|
| 27 | La tabla de funciones salía con una fila por renglón de texto | Las filas se agrupan entre los bordes horizontales reales de la tabla (los que cubren ≥ 90 % de su ancho) | `pdf.bordes_horizontales_completos`, `pdf._filas_por_bordes` |
| 28 | El organigrama y el párrafo vecino entraban a la tabla | La tabla se recorta a sus bordes reales; las cajas dibujadas con texto se leen como `[ORGANIGRAMA: …]` seguido de “Jefe → Puesto”, una sola vez aunque también se detecten como tabla de una columna | `pdf._cajas_con_texto`, `pdf._es_organigrama`, `_ExtraccionPDF._organigrama` |
| 29 | Valores del encabezado (fecha, “1 de 3”) en el cuerpo y vigencia perdida | Los valores que están debajo de su etiqueta en la celda del encabezado son parte del encabezado; los lados de un recuadro con contorno cuentan como bordes; nueva etiqueta “Vigente a partir de” | `_ExtraccionPDF._fondo_encabezado`, `pdf._bordes_horizontales`, `metadatos.py` |
| 30 | El objetivo del puesto (letra más grande) salía partido como título | Un renglón que termina en artículo o preposición, o que empieza en minúscula, no es título; un “título” largo se convierte en párrafo; renglones con cajas de texto superpuestas continúan el párrafo | `maquetacion.nivel_titulo`, `maquetacion._continua` |
| 31 | Columnas corridas en tablas con celdas combinadas | Se unen columnas adyacentes cuando una no tiene cabecera y ninguna fila tiene texto en ambas | `pdf._unir_columnas_corridas` |
| 32 | Nombre del puesto, “Reporta a” y funciones sin detectar | Título numerado “1. Puesto.”; tabla “Áreas de Relacionamiento” (Subordinación directa → `reporta_a`, Reporte directo → `supervisa_a`); un título o tabla con nombre de campo abre su sección; el propósito usa solo párrafos | `analisis._nombre_por_titulo`, `analisis._campos_por_relacionamiento`, `analisis._separar_secciones`, `configuracion.py` |

**Entrada sin carpetas de área y sin `lista.txt`**

- Si `entrada` no tiene `lista.txt`, `construir` la arma con los documentos que están en una carpeta `Descriptivos` o `Procedimientos` (directamente o en una subcarpeta de área) y la guarda en `control/lista.txt`. Se regenera en cada construcción, así que los archivos nuevos entran solos.
- Se aceptan dos estructuras: `Descriptivos\<Área>\archivo.pdf` (el área es la carpeta) y `Descriptivos\archivo.pdf`. En la segunda, el área se toma de `entrada\areas.csv` (columnas `archivo;area`). El script crea ese archivo con todos los documentos y la columna `area` vacía, y agrega los nuevos en cada construcción sin tocar lo ya escrito.
- Un documento sin área queda en «Sin Área» con un código provisional (`DES-SAR-NN`) y la construcción termina en REQUIERE REVISIÓN. Los códigos provisionales no se conservan: al escribir el área, el documento recibe su código definitivo sin dejar filas `RETIRADO`.

- Un documento y sus copias (`archivo (1).pdf`) ocupan una sola fila en `areas.csv`, y se convierte el archivo que se llama igual que la fila del inventario (el original), no la copia.
- Un PDF con páginas escaneadas que no se pudieron leer (no hay Tesseract instalado) es un **problema**, no solo un aviso: su texto no está en el corpus aunque la cobertura diga 100 %.

Código: `cli._lista_desde_carpeta`, `inventario.parsear_lista`, `inventario.leer_areas`, `inventario.actualizar_plantilla_areas`, `inventario.leer_base` y `publicacion.validar_publicacion`.

Resultado en el piloto (10 descriptivos reales, dos variantes de plantilla): cobertura 100 % en todos; nombre, reporta a, propósito, versión y vigencia en los 9 digitales. El escaneado (OCR) no trae “Reporta a” ni funciones legibles: conviene usar la versión digital.

## OCR de PDF escaneados (Tesseract)

Las páginas escaneadas se leen con Tesseract. `python scripts/convertir.py diagnostico` comprueba PyMuPDF, pytesseract, Pillow, Tesseract y el idioma español. El ejecutable se busca en `TESSERACT_CMD`, en el PATH y en las carpetas de instalación de Windows (`Program Files`, `Program Files (x86)` y `%LOCALAPPDATA%\Programs`), así que no hace falta editar el PATH. Código: `conversion/extractores/ocr.py`.

## Matriz organizacional (Excel)

`construir` escribe `salida_corpus/copilot/fuente-contexto/matriz/matriz_organizacional.xlsx` (requiere `openpyxl`) y un CSV por hoja, una base de datos para revisar el corpus sin ejecutar código. `python scripts/convertir.py matriz --salida salida_corpus` la regenera sin volver a convertir. Hojas:

| Hoja | Contenido |
|---|---|
| Léeme | Qué contiene cada hoja, estado de la construcción y cómo leer las columnas |
| Resumen | Conteos por área con fórmulas (puestos, OCR, sin texto, funciones, relaciones, pendientes) |
| Puestos | Un puesto por fila: área, reporta a y supervisa a (literal), código del jefe si está en el corpus, propósito, versión, vigencia, calidad de lectura y revisión |
| Funciones | Una función por fila con su evidencia o entregable |
| Relaciones | Área o puesto de interacción y tipo de relación, con el código del puesto relacionado si está en el corpus |
| Perfil y requisitos | Educación, experiencia, competencias, accesos, herramientas y características especiales |
| Normativa citada | Cada texto literal que menciona una política, protocolo, procedimiento, norma, reglamento, manual, ley o código de documento |
| Procedimientos, Participación, Puestos x Procedimientos | Procedimientos, el rol de cada puesto en cada uno y la matriz puesto × procedimiento (se llenan cuando hay procedimientos) |
| Indicadores | KPIs del contexto |
| Revisión | Documentos para comparar con el original, con una columna para las observaciones del auditor |

Todo es literal del corpus; los cruces por nombre de puesto indican si la coincidencia es exacta o probable. Código: `consulta/matriz.py`.

## v3.5: lectura de PDF escaneados (OCR con estructura)

Tesseract reconoce bien las palabras, pero en un descriptivo escaneado las tablas salían como texto corrido, el texto sobre fondo de color se perdía y el encabezado del formato aparecía en el cuerpo de cada página. Por eso faltaban «Reporta a», las funciones, la versión y la vigencia. `conversion/extractores/ocr_pagina.py` lee cada página escaneada así:

1. **Endereza** la página si está torcida (≥ 0,1°).
2. **Detecta las líneas de las tablas en la imagen por contraste** con su entorno (no con un umbral fijo), así distingue las líneas grises del fondo gris de las filas. Una franja gruesa es un relleno de color y aporta sus bordes. Una línea algo inclinada sigue siendo línea, porque su grosor se mide por columna.
3. **Arma la cuadrícula**: líneas horizontales unidas por verticales o por un relleno. En una fila con relleno no se toman como columnas los bordes de las letras claras, y un título de ancho completo no se parte.
4. **Ubica cada palabra del OCR en su celda** por su posición. Lo demás queda como texto.
5. **Relee sola cada celda** con fondo de color, con lectura poco confiable o que el OCR dejó vacía teniendo tinta. Invierte el texto claro sobre fondo oscuro y acepta la relectura solo si es más confiable y no pierde texto.
6. **Limpia**: bordes leídos como caracteres («|», «[»), letras sueltas dudosas, palabras leídas dos veces (negrita) y viñetas leídas como «e» o «+».
7. **Separa** la tabla de arriba con «Código / Versión / Vigencia / Página» como encabezado (metadatos) y las cajas angostas como organigrama.

Cada documento guarda las páginas leídas con OCR y la **confianza media** de Tesseract (columnas nuevas `paginas_ocr` y `confianza_ocr`, al final del índice). Solo pasa a revisión visual si la confianza es menor que 85 % (`CONFIANZA_OCR_REVISION`); la matriz Excel lo muestra como «OCR» en todos los casos.

Resultado en el descriptivo escaneado real del piloto (4 páginas): 22 de 24 elementos esperados (encabezado, caja del jefe y filas de las tablas), antes 0 tablas. Confianza media del 93 %, y «Reporta a», funciones, versión y vigencia completos. Requiere `numpy`; sin numpy se usa solo el OCR de texto corrido.

## v4.0: codificación TTT-AAA-NN y dos carpetas para Copilot

**Codificación.** `TTT` = tipo (3 letras), `AAA` = área (3 letras), `NN` = número (dos dígitos; tres si el grupo pasa de 99). Los tipos están en una sola tabla, `corpus_org/comun/tipos.py` (`TIPOS_DOCUMENTO`): para agregar uno basta una fila; los patrones, los nombres de archivo, los filtros `--tipo` y las carpetas se derivan de ella.

| Tipo | Documento | Área | Carpeta de entrada |
|---|---|---|---|
| `DES` | Descriptivo de puesto | la del puesto | `Descriptivos\<Área>\` |
| `PRD` | Procedimiento | la del procedimiento | `Procedimientos\<Área>\` |
| `PRO` | Protocolo | una área, o `GEN` si aplica a varias o a toda la empresa | `Protocolos\<Área o General>\` |
| `POL` | Política | ídem | `Políticas\<Área o General>\` |
| `ORG`, `GLO`, `MPR` | Organigrama, glosario, mapa de procesos | siempre `GEN` | carpeta de contexto (subcarpeta o nombre del archivo) |
| `CTX` | Otro material de contexto | `GEN` | carpeta de contexto |

- Los **indicadores** no son un tipo de documento: los `kpi*.csv` de la carpeta de contexto se unen en `kpis.csv` (con su ID propio); no se crea `KPI_GEN.md`.
- Una carpeta de área llamada `General`, `Toda la empresa`, `Corporativo`… (o ese valor en `areas.csv`) es el área `GEN`. El área que emite una política o protocolo se guarda aparte, en `area_propietaria` (índice, matriz y metadatos del Markdown), si el documento trae «Área propietaria», «Área emisora» o «Área responsable».
- **Carpeta de contexto:** los procedimientos (incluidas las fichas de proceso), las políticas/normativas/reglamentos, los protocolos y los descriptivos que estén en la carpeta de contexto se inventarían, convierten, validan y entran a la matriz igual que los de la entrada. El tipo sale de la subcarpeta (`Procedimientos\`, `Fichas de proceso\`, `Normativas\`, `Políticas\`…) o del nombre del archivo; el área, de la subcarpeta siguiente (`Fichas de proceso\Calidad\`), de `entrada\areas.csv` o, si no hay, `GEN`. Los que quedan en `GEN` por no tener área se agregan a `areas.csv` con la columna `area` vacía para que escriba la suya; al hacerlo, el documento recibe un código nuevo, el anterior queda `RETIRADO` (reservado) y la equivalencia se guarda en `equivalencias_codigos.csv`. En la carpeta de contexto se leen PDF, Word, Excel (`.xlsx`, `.xlsm`), `.md`, `.csv` y `.txt`: los demás formatos (`.pptx`, `.png`, `.zip`, `.xls`…) no se leen, se listan en `control/archivos_no_leidos.csv` y se avisa; un `.zip` hay que descomprimirlo dentro de la carpeta. El formato se reconoce por el contenido, no por la extensión: un Excel guardado como `.csv` se lee como Excel y un `.csv` que en realidad es un PowerPoint o un Office antiguo da un error claro en lugar de letras sin sentido. Una carpeta cuyo nombre indica varios tipos («Políticas y procedimientos», «Estructura organizacional y descriptivos») no clasifica todo su contenido: decide el nombre de cada archivo y, si no dice nada, es un documento general. Un archivo de contexto con el mismo nombre que uno de la entrada no se repite. Un nombre de archivo que dice «Organigrama», «Glosario» o «Mapa de procesos» (sin «procedimiento», «protocolo» ni «política») es un documento general aunque esté en la carpeta Procedimientos.
- Numeración por tipo + área desde 01. Al reconstruir, los códigos no cambian: los nuevos van al final y los retirados reservan su código. El contexto tiene su propio inventario estable, `control/inventario_contexto.csv`.
- **Migración:** `D-AAA-NN` → `DES-AAA-NN` y `P-AAA-NN` → `PRD-AAA-NN` con el mismo número; los `C-CTX-NN` se clasifican por tipo y se numeran dentro de `GEN` en su orden anterior. Todo queda en `equivalencias_codigos.csv` (`codigo_anterior;codigo_nuevo`, acumulativo), y `revision_visual_ok.txt` acepta los códigos anteriores.
- Cada documento empieza con `## [TTT-AAA-NN] Título`. Un archivo por tipo y área (`DES_SEG.md`, `PRD_SEG.md`, `POL_GEN.md`…) y uno por tipo general (`ORG_GEN.md`, `GLO_GEN.md`…). Un Markdown de más de 20 MB se divide en partes (`PRD_SEG_01-20.md`, `PRD_SEG_21-40.md`) y el índice apunta a la parte correcta.

**Dos carpetas listas para comprimir** (`salida_corpus/copilot/`). `construir` ya no genera el paquete de 20 archivos ni las instrucciones de la versión anterior:

```
fuente-documentos/
  SKILL.md                 lo provee el equipo; el script no lo escribe ni lo borra
  DES/  PRD/  PRO/  POL/   un .md por tipo y área (PRO_GEN.md, POL_GEN.md…)
fuente-contexto/
  SKILL.md                 lo provee el equipo
  contexto/   ORG_GEN.md, GLO_GEN.md, MPR_GEN.md, CTX_GEN.md, kpis.csv
  indice/     indice_corpus.csv, inventario_maestro.csv, areas_extra.csv, huellas.sha256,
              RESUMEN_CONSTRUCCION.md, equivalencias_codigos.csv
  matriz/     matriz_organizacional.xlsx y un CSV por hoja (puestos.csv, funciones.csv, relaciones.csv,
              perfil_requisitos.csv, normativa_citada.csv, procedimientos.csv, politicas_protocolos.csv,
              participacion.csv, indicadores.csv, revision.csv…)
  scripts/    corpus.py y corpus_org/ (sin subcarpetas)
```

- `convertir.py` y el código de conversión **no** van en `fuente-contexto/scripts/`: el agente no construye el corpus. `control/` tampoco se publica.
- **Límites de Copilot:** máximo 3 niveles de carpetas, 25 MB por archivo, 50 MB por skill y 350 archivos entre todos los skills del agente. Para cumplir el primero, `corpus_org` se publica aplanado (`consulta/comandos/base.py` → `consulta_comandos_base.py`, con los imports reescritos; `conversion/skills.py`). El resumen de la construcción y `corpus.py verificar` informan el peso y el número de archivos de cada carpeta y avisan si se supera algún límite.
- `RESUMEN_CONSTRUCCION.md` se copia a `indice/` y `huellas.sha256` se escribe al final, con rutas `<skill>/<ruta>`: se verifican aunque cada skill esté en otra carpeta.

**Localización en Copilot.** Un skill solo está en disco después de que el agente lo carga, y los skills cargados quedan en `/home/oai/skills/appCatalog/<carpeta>/<skill>/` (la `<carpeta>` cambia). `corpus.py` busca `fuente-documentos` como carpeta hermana de su skill; si no está, usa `CORPUS_DATOS` (la carpeta que contiene ambos skills) y luego busca por nombre en `/home/oai/skills/appCatalog/*/` y en las carpetas superiores. Si no la encuentra, imprime exactamente: `ERROR: no encuentro el skill fuente-documentos. Carga primero fuente-contexto y fuente-documentos (lee su SKILL.md) y vuelve a ejecutar.` La consulta usa solo la biblioteca estándar (una prueba la ejecuta con `python -I -S`).

**Comandos.** Los 12 de siempre, `citar <CÓDIGO>… [--texto "…"]` (aval de la fuente: confirma que el documento existe, dónde está su original y si respalda una afirmación) y `normativa [--area]` (citas literales agrupadas por tipo de referencia: ley, reglamento, norma, política, protocolo, procedimiento, manual, instructivo, código de documento). `--tipo DES|PRD|PRO|POL|GEN` en `buscar` y `ficha` (`GEN` = documentos con área `GEN`). Los verbos de `relaciones` son Entrega, Recibe, Solicita, Aprueba o revisa, Notifica, Coordina y Reporta.

**`briefing "<área>"`** (los documentos se reparten de 15 en 15 por parte; las tablas de toda el área van en la parte 1): `Partes: N`, `Cobertura: DES x/x · PRD y/y · PRO z/z · POL w/w · GEN pertinentes: n` y, en este orden, Puestos (DES), Procedimientos (PRD, con `N.º de puestos que participan`), Protocolos (PRO), Políticas (POL), Jerarquía de procesos, Relaciones (con `Verbo` y las entidades externas aparte), Participación — Resumen por puesto, Procedimientos con un solo puesto participante, Mismo puesto con roles Ejecuta y Aprueba, Estructura (subordinados directos y nivel jerárquico), Indicadores relacionados (más indicadores sin medición y procedimientos sin indicador), Gobierno documental (resumen), Normativa citada (resumen), Perfil y funciones (resumen por puesto) y No documentado. A los PRO y POL del área se suman los **GEN pertinentes**, con la columna `Motivo`: `Menciona al área` (nombre, código o alias), `Menciona al puesto <nombre>` o `Alcance: toda la empresa` (según su sección de alcance). Nunca se incluye un GEN por afinidad de tema (`consulta/pertinencia.py`).

**Matriz.** Hojas nuevas «Políticas y protocolos» (código, tipo, área, área propietaria, alcance literal, versión, vigencia, estado documental…) y «Documentos generales». La hoja «Procedimientos» y la de participación incluyen también los protocolos, con su tipo.

**PDF: cajas de una columna y tablas partidas (v4.0).** Una banda de color con su título y filas con borde fino debajo («Accesos a Sistemas», «Herramientas de Trabajo»…) se lee como tabla; antes quedaba como líneas sueltas y se marcaba «posible diagrama vectorial». Una fila solo cuenta si tiene su línea de separación, así un párrafo bajo una banda no se parte en filas. Y una línea en negrita entre el final de una página y la tabla de la siguiente es un título: no se unen como una tabla partida. Código: `extractores/pdf.py` (`_bandas_apiladas`, `_es_suelta_entre_tablas`); pruebas en `tests/test_bandas.py`.

Código: `comun/tipos.py`, `comun/estructura.py`, `conversion/inventario.py`, `conversion/publicacion.py`, `conversion/skills.py`, `consulta/ubicacion.py`, `consulta/extraccion.py`, `consulta/pertinencia.py`, `consulta/jerarquia.py`, `consulta/matriz.py`, `consulta/comandos/briefing.py` y `normativa.py`. La conversión y la verificación de fidelidad no cambian.

## v4.1: lectura más fiel, ubicación de los originales y aval de las fuentes

- **PDF en pliegos.** Un folleto cuyas páginas son dos páginas de libro lado a lado se lee mitad izquierda y mitad derecha (con la numeración impresa); antes se mezclaban línea por línea. Solo se activa si la mayoría de las páginas apaisadas tienen el centro libre de texto. Una foto de página completa que el OCR lee como ruido queda como imagen. Código: `extractores/pdf.py` (`_separar_pliegos`).
- **Cajas de una columna que continúan en la página siguiente.** La fila con borde fino que abre la página 4 sigue a la caja con que termina la 3 (antes salía como título y la caja «Firma de Aprobación» se fundía con la anterior). Una celda sin borde propio (el texto de la última fila de una tabla) se recupera de las palabras de la página sin duplicar las de otras celdas. Un párrafo con letra un poco mayor que el cuerpo (el objetivo del puesto junto a un organigrama) ya no se convierte en título, y el organigrama pequeño del puesto ya no se marca como «diagrama vectorial». Las filas de un índice con título conocido («3. Alcance 7») conservan su número.
- **Plantilla GECA-ATTA-FOR-034 y filas partidas por celda interior.** Las bandas de título delgadas (13 pt) cuentan como caja solo si traen un título en negrita centrado (una fila con relleno de color de la misma altura no es una banda) y el rectángulo interior de la banda no se cuenta como otra. El valor bajo «Vigencia:» o «Página:» (fecha, «2 de 6») es parte del encabezado aunque quede más abajo de lo esperado; antes se colaba como línea suelta entre dos tablas partidas y disparaba la alerta. Una celda que PyMuPDF reconoce dos veces (la grande y su rectángulo interior) deja de repetir su texto en dos columnas.
- **OCR con umbral de confianza del 80 %.** Si una página escaneada no llega a 80 % se vuelve a leer con la página girada (OSD), más contraste y nitidez, ajuste de brillo, blanco y negro (Otsu) y 400 dpi, y se conserva la mejor lectura; el tratamiento queda en las notas del reporte. Lo que no llega a 80 % se avisa como «página poco legible». El texto de una imagen o gráfico grande sin texto digital (organigrama en imagen, diagrama de proceso) también se lee con OCR y queda bajo su marca `[DIAGRAMA O IMAGEN…]` con su confianza; si no se lee con 80 % queda solo la marca y un aviso. Código: `extractores/ocr_pagina.py` (`leer_pagina`, `leer_region`, `RECETAS`).
- **Dónde está cada original.** El índice tiene la columna `ruta_original` (`entrada/<ruta>` o `contexto/<ruta>`). La consola («Revisar en…», «Revisión visual pendiente», «PROBLEMA en…»), `control/REPORTE_*.md`, `RESUMEN_CONSTRUCCION.md` y `control/revision_visual.csv` (`archivo`, `ruta_original`) indican la ruta de cada documento a revisar.
- **Archivos de Office abiertos.** `~$matriz.xlsx` y otros temporales no entran en las huellas ni en el conteo; un archivo bloqueado solo avisa. Un material repetido en el contexto (`X (1).csv` junto a `X.csv`) se numera una vez, con aviso si su contenido difiere.
- **Excel en el contexto.** Cada hoja visible se convierte en una tabla (primera fila no vacía = cabecera; una hoja de una columna son párrafos; fechas en ISO, enteros sin `.0`, porcentajes con `%`); se leen los valores guardados, y las fórmulas sin valor guardado, las hojas ocultas y los gráficos se avisan. Una captura o imagen pegada en una hoja (un calendario, un organigrama) se amplía y se lee con OCR bajo `[IMAGEN EN LA HOJA «…»]` con su confianza. Código: `extractores/excel.py`, `extractores/__init__.py` (`formato_real`), `ocr_pagina.leer_imagen`; pruebas en `tests/test_excel.py`.
- **`citar <CÓDIGO>… [--texto "…"]`.** Confirma que el documento existe, si es específico de un área o general (`GEN`), dónde está su original y, con `--texto`, si lo respalda (`RESPALDADO (literal)`, `RESPALDO PARCIAL` o `SIN RESPALDO`; código de salida 3). Es el aval de que las fuentes que cita el agente existen y dicen lo que se les atribuye. Código: `consulta/comandos/citar.py`; pruebas en `tests/test_briefing.py`, `tests/test_pliegos.py`, `tests/test_ocr_imagenes.py`.

## Pruebas

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -t .      # o: python -m pytest tests
```

Las pruebas de integración generan corpus sintéticos (`tests/fixtures_corpus.py`, `tests/fixtures_casos.py`, `tests/fixtures_plantilla.py`). Necesitan `pymupdf`, `lxml`, `python-docx` y `reportlab`, y las de PDF además LibreOffice (`soffice`); si falta alguno, esas pruebas se omiten.

Los datos del cliente (documentos, materiales de contexto y corpus generado) no se versionan: `.gitignore` excluye `contexto/`, `entrada/`, `salida_corpus/` y `publicado/`.
