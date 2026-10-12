---
name: corpus-organizacional
description: >-
  Consulta exacta del corpus publicado de descriptivos de puesto, procedimientos y contexto organizacional. Úsalo cuando el usuario mencione un área, departamento, puesto, procedimiento, proceso, actividad, código, responsable, propietario, versión, vigencia, relación entre áreas o preparación de reuniones.
---

# Corpus organizacional

> Compatible con `convertir.py` v3.2 y `corpus.py` v3.2.

Este skill consulta exclusivamente el corpus publicado. Los documentos son la fuente de verdad; el índice sirve para localizar, contar y filtrar, pero los datos sustantivos se confirman en el Markdown original.

## 1. Estructura

- `salida_corpus/publicado/D_<ÁREA>.md`: descriptivos publicados.
- `salida_corpus/publicado/P_<ÁREA>.md`: procedimientos publicados.
- `salida_corpus/publicado/contexto.md`: organigrama, glosario y contexto, con códigos `C-CTX-NN`. El contexto puede venir en PDF, Word o transcrito a mano en `.md`, `.csv` o `.txt` (por ejemplo, capturas de un tablero).
- `salida_corpus/publicado/indice_corpus.csv`: índice maestro consolidado, una fila por documento.
- `salida_corpus/publicado/inventario_maestro.csv`: documentos que deberían existir.
- `salida_corpus/publicado/catalogo.csv`: resumen de áreas y cantidades, cuando esté disponible.
- `salida_corpus/control/`: reportes y diccionarios parciales de QA. No es fuente operativa de respuestas.
- `salida_corpus/RESUMEN_CONSTRUCCION.md`: resultado de la última construcción.
- `scripts/convertir.py`: construye, publica y valida el corpus.
- `scripts/corpus.py`: consulta el corpus publicado.
- `scripts/corpus_org/`: paquete con la lógica de ambos scripts. Debe copiarse siempre junto con ellos.

Compatibilidad: `corpus.py` busca primero la ruta indicada por `CORPUS_DATOS`, luego `salida_corpus/publicado/`, `publicado/` y finalmente la estructura histórica `datos/`. Si no existe `indice_corpus.csv`, puede leer `DIC_*.csv` como transición.

## 2. Interpretación de documentos

- Cada documento empieza con `## [CÓDIGO] Título`.
- `D-XXX-NN` es un descriptivo; `P-XXX-NN` es un procedimiento; `C-CTX-NN` es contexto.
- Las líneas que empiezan con `>` son metadatos de conversión, no texto original.
- `[NO ESPECIFICADO]` significa que el original no trae el campo.
- `[DIAGRAMA: la sección «…» no se transcribe…]`, `[DIAGRAMA O IMAGEN...]`, `[CELDA COMBINADA]`, `[TEXTO OCR...]` e `[IMAGEN OMITIDA]` son marcas de conversión. El contenido de un diagrama no está en el corpus: remite a la página del original.
- La sección “Datos de encabezado y pie” conserva código interno, versión y otros datos del encabezado original.
- `Versión`, `Estado documental`, `Fecha de vigencia`, `Propietario` y `Responsable` se usan solo cuando aparecen explícitamente en el original.
- Un estado vacío no significa “Vigente” ni “No vigente”. Se reporta `[NO ESPECIFICADO]`.
- Por defecto se excluyen estados explícitamente no publicables: `Borrador`, `Sustituido`, `Obsoleto`, `Inactivo`, `No vigente` y `Cancelado`. Un documento excluido no aparece en ninguna consulta; `doc <CÓDIGO>` indica que está excluido y `verificar` lo informa sin contarlo como problema.
- Los metadatos de gobierno solo se registran cuando aparecen con su etiqueta (`Estado: Vigente`, o una celda `Estado` junto a `Vigente`). Una frase como “estado de cuenta” nunca se toma como estado documental.

## 3. Construcción y actualización

Para construir o actualizar el corpus:

```bash
python scripts/convertir.py construir --entrada <carpeta_documentos> --contexto <carpeta_contexto>
python scripts/corpus.py verificar
```

El modo `construir` genera:

- `publicado/`: archivos que puede consultar el agente.
- `control/`: reportes, diccionarios parciales y evidencia de QA.
- `RESUMEN_CONSTRUCCION.md`: estado `LISTO PARA PUBLICAR` o `REQUIERE REVISIÓN`.

Si el resumen indica `REQUIERE REVISIÓN`, no presentes el corpus como completo sin explicar los problemas detectados.

Inventario: se ignoran los archivos temporales o del sistema (`~$…`, `Thumbs.db`, `desktop.ini`). Si el mismo documento está en `.docx` y `.pdf`, o hay una copia `(1)`, se inventaría una sola vez (preferencia `.docx`) y se avisa; `--incluir-duplicados` conserva todos. Los archivos se emparejan por su ruta `Tipo/Departamento/Archivo`, así dos áreas pueden tener un archivo con el mismo nombre.

## 4. Herramienta de consulta

Ejecuta siempre `scripts/corpus.py` antes de leer archivos manualmente:

```bash
python scripts/corpus.py <comando> <argumentos>
```

| Comando | Uso |
|---|---|
| `catalogo` | Áreas, códigos y número de descriptivos y procedimientos |
| `area "<área>"` | Índice completo del área |
| `ficha "<área o código>" [--tipo D|P]` | Secciones y campos clave literales |
| `doc <CÓDIGO> [--seccion "<texto>"]` | Documento completo o una sección |
| `buscar "<t1|t2|t3*>" [--area "<área>"] [--tipo D|P]` | Búsqueda literal normalizada |
| `relaciones "<área A>" ["<área B>"]` | Menciones explícitas entre áreas y puestos |
| `participacion "<área o código>"` | Puestos en procedimientos y rol detectado |
| `gobierno [--area "<área>"]` | Versión, estado, vigencia, propietario y responsable |
| `procesos [--area "<área>"]` | Macroproceso, proceso, procedimiento y actividades extraídas |
| `verificar` | Integridad del índice, Markdown, inventario, duplicados y cobertura |

### Reglas de uso

- El área puede escribirse por nombre, código o alias del glosario.
- Si el script responde `AMBIGUO`, muestra las opciones y formula una sola pregunta.
- Si el script responde `AVISO: '<texto>' se interpretó como el área ...`, menciona esa interpretación en la respuesta.
- Si responde `NO ENCONTRADO`, indica qué revisaste y muestra las alternativas disponibles.
- Las coincidencias “probable”, los verbos detectados y las actividades extraídas son ayudas automáticas. Confírmalas con `doc`; si se usan sin confirmación, marca `[Inferido]`.
- Las “menciones parecidas a varios puestos” de `participacion` no se asignaron a ningún puesto. No elijas uno: confírmalo con `doc` o déjalo como punto a validar. Un puesto con el mismo nombre en varias áreas se asigna al área del documento que lo menciona; si el documento es de otra área, queda en esa lista.
- Toda celda de la columna “Responsable” es un rol: si no coincide con un descriptivo aparece en “Puestos o roles … sin descriptivo”.
- El rol y el verbo se calculan con la oración donde aparece el puesto o el área, no con toda la línea; si hay varios verbos se toma el más cercano a la mención. “Aprueba” y “Revisa o verifica” son roles distintos; una firma o una liberación no cuentan como aprobación.
- `relaciones` identifica menciones explícitas. La ausencia de una mención no demuestra que la relación no exista.
- Si el script falla, lee primero `indice_corpus.csv` y luego el Markdown correspondiente. Usa `DIC_*.csv` solo si no existe el índice consolidado.

## 5. Flujo: briefing de un área

1. Ejecuta `area "<área>"` y anota todos los códigos.
2. Ejecuta `ficha "<código del área>"`; si falta un código, consulta `doc <CÓDIGO>`.
3. Ejecuta `relaciones "<código del área>"`.
4. Ejecuta `participacion "<código del área>"`.
5. Si hay procedimientos, ejecuta `procesos --area "<código del área>"`.
6. Si se requieren versión, vigencia o responsables, ejecuta `gobierno --area "<código del área>"`.
7. Redacta una fila por documento y comprueba la cobertura.

### Plantilla de briefing

```text
# Briefing: <Área> (<COD>)
Cobertura: X/X descriptivos · Y/Y procedimientos

## 1. Resumen del área
## 2. Puestos
| Código | Puesto | Reporta a | Propósito | Funciones principales | Otros datos |
## 3. Procedimientos
| Código | Procedimiento | Macroproceso / proceso | Objetivo | Responsable / propietario | Versión / estado | Áreas relacionadas |
## 4. Jerarquía de procesos
## 5. Relaciones con otras áreas
## 6. Insights
## 7. Información no documentada
## 8. Para profundizar
```

En “Información no documentada” incluye solo campos `[NO ESPECIFICADO]` y roles de procedimientos sin descriptivo. No agregues ausencias deducidas.

## 6. Flujo: relaciones entre áreas

1. Ejecuta `relaciones "<A>" "<B>"`.
2. Confirma citas ambiguas con `doc <CÓDIGO> --seccion "<sección>"`.
3. Ejecuta `participacion "<A>"` y `participacion "<B>"` para identificar puntos de contacto.
4. Separa menciones de A hacia B, de B hacia A y relaciones mencionadas por un solo lado.
5. No deduzcas relaciones por lógica del negocio.

## 7. Flujo: consultas puntuales

- **Dato o documento:** ubica el código con `buscar` o `area`, luego ejecuta `doc`.
- **Comparación:** ejecuta `doc` para cada código y usa los mismos campos; donde falte información escribe `[NO ESPECIFICADO]`.
- **Tema:** ejecuta `buscar` con variantes, sinónimos y siglas documentadas.
- **Cobertura:** ejecuta `catalogo`; si preguntan si falta algo, ejecuta `verificar`.

## 8. Flujo: gobierno documental

Úsalo para versión, vigencia, estado, propietario, responsable o documentos actuales.

1. Ejecuta `gobierno` o `gobierno --area "<área>"`.
2. Confirma el dato con `doc <CÓDIGO>` cuando la respuesta dependa de él.
3. No conviertas un campo vacío en “Vigente”. El comando ya muestra `[NO ESPECIFICADO]` en los campos vacíos.
4. Para consultas históricas, habilita documentos no vigentes solo cuando el usuario lo solicite explícitamente:

```bash
CORPUS_INCLUIR_NO_VIGENTES=1 python scripts/corpus.py gobierno
```

Plantilla:

| Código | Documento | Versión | Estado | Vigencia | Propietario | Responsable |
|---|---|---|---|---|---|---|

## 9. Flujo: procesos y actividades

Úsalo para macroprocesos, procesos, procedimientos, subprocedimientos o actividades.

1. Ejecuta `procesos` o `procesos --area "<área>"`.
2. Confirma con `doc <CÓDIGO>` la sección de desarrollo.
3. Presenta la jerarquía solo cuando esté documentada.
4. No conviertas automáticamente el nombre del área en proceso. El campo `Proceso` solo se llena si el original trae la etiqueta `Proceso:`.
5. Las actividades indexadas salen solo de la sección de desarrollo (viñetas y columna “Actividad” de sus tablas).
6. No presentes toda viñeta como actividad confirmada. Si el contexto no lo confirma, marca `[Inferido]`.

Plantilla:

| Macroproceso | Proceso | Código | Procedimiento | Actividades documentadas | Responsable |
|---|---|---|---|---|---|

## 10. Reglas para redactar respuestas

- Todo dato lleva su código documental.
- Las citas literales usan una frase breve entre comillas.
- Toda conclusión propia lleva `[Inferido]` y sus códigos base.
- Si algo no está: “No encontrado en los documentos”, indicando qué se revisó.
- No mezcles el índice con el texto original: usa el índice para ubicar y el Markdown para confirmar.
- No uses `control/` como evidencia empresarial.
- Para un área, cubre todos sus códigos e incluye la línea de cobertura.
- No evalúes si el proceso está bien o mal. Presenta “puntos a validar en la reunión”.

## 11. Preguntas analíticas internas

- ¿Qué procedimientos ejecuta, aprueba, revisa o recibe el área?
- ¿Qué puestos concentran más responsabilidades?
- ¿Cómo es la línea de reporte?
- ¿Con qué áreas tiene más menciones y en qué procedimientos?
- ¿Qué dependencias están explícitamente documentadas?
- ¿Qué roles no tienen descriptivo y qué descriptivos no aparecen en procedimientos?
- ¿Qué campos están `[NO ESPECIFICADO]`?
- ¿Qué documentos tienen versión, estado, vigencia, propietario o responsable explícitos?
- ¿Qué jerarquía macroproceso → proceso → procedimiento → actividad está realmente documentada?

Elige los insights más útiles. Cada insight debe ser descriptivo, trazable y, cuando sea una conclusión propia, marcado `[Inferido]`.
