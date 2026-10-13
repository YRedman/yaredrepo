---
name: corpus-contexto
description: >-
  Consulta exacta del corpus organizacional publicado (descriptivos de puesto, procedimientos, protocolos, políticas, documentos generales e indicadores) con scripts/corpus.py. Trabaja junto con el skill corpus-documentos, que tiene el texto de los documentos. Úsalo cuando el usuario mencione un área, departamento, puesto, procedimiento, proceso, actividad, código, responsable, propietario, versión, vigencia, relación entre áreas, indicador, KPI, meta o preparación de reuniones.
---

# Corpus organizacional

> Compatible con `convertir.py` v4.0 y `corpus.py` v4.0.

Este skill consulta exclusivamente el corpus publicado. Los documentos son la fuente de verdad; el índice sirve para localizar, contar y filtrar, pero los datos sustantivos se confirman en el Markdown original.

## 1. Estructura

El corpus se publica en dos skills (en `salida_corpus/publicado/`):

**`corpus-documentos`** (solo datos): un Markdown por tipo y área, en una carpeta por tipo.

- `DES/DES_<ÁREA>.md` descriptivos de puesto, `PRD/PRD_<ÁREA>.md` procedimientos, `PRO/PRO_<ÁREA>.md` protocolos y `POL/POL_<ÁREA>.md` políticas. Las políticas y protocolos que aplican a más de un área o a toda la empresa están en `POL_GEN.md` / `PRO_GEN.md`.

**`corpus-contexto`** (este skill):

- `scripts/corpus.py` consulta; `scripts/corpus_org/` es el paquete con la lógica (solo biblioteca estándar).
- `datos/<TTT>_GEN.md`: documentos generales: `ORG_GEN.md` organigramas, `KPI_GEN.md` indicadores, `GLO_GEN.md` glosarios, `MPR_GEN.md` mapas de procesos y `CTX_GEN.md` otro contexto. Pueden venir en PDF, Word o transcritos a mano en `.md`, `.csv` o `.txt`.
- `datos/indice_corpus.csv`: índice maestro, una fila por documento (con `area_propietaria` para políticas y protocolos).
- `datos/inventario_maestro.csv` e `inventario_contexto.csv`: documentos que deberían existir. Las filas `RETIRADO` solo reservan su código.
- `datos/equivalencias_codigos.csv`: `codigo_anterior;codigo_nuevo` de la codificación anterior (`D-`, `P-`, `C-CTX-`).
- `datos/matriz_organizacional.xlsx` y `datos/matriz/*.csv`: la matriz maestra, una hoja por CSV (UTF-8, separador `;`).
- `datos/kpis.csv`: indicadores transcritos (meta, medición, unidad, estado según el color), si el contexto trae un CSV cuyo nombre empieza con `kpi`.
- `datos/areas_extra.csv`: áreas y entidades sin documentos propios (internas, externas) y frases que no son menciones de un área.
- `datos/huellas.sha256`: SHA-256 de cada archivo publicado en las dos skills (integridad).

Fuera de los skills: `salida_corpus/RESUMEN_CONSTRUCCION.md` (resultado de la última construcción) y `salida_corpus/control/` (reportes de QA; no es fuente de respuestas). `scripts/convertir.py` construye.

`corpus.py` busca los datos en `CORPUS_DATOS`, luego en `datos/` de su propio skill y en `salida_corpus/publicado/corpus-contexto/datos/`. La carpeta `corpus-documentos` se busca en `CORPUS_DOCUMENTOS`, junto al skill y por su nombre en `/home/oai/skills/appCatalog/<id>/corpus-documentos` (en Copilot el `<id>` cambia). Si no la encuentra, lo dice con la lista de lugares revisados.

## 2. Interpretación de documentos

- Cada documento empieza con `## [TTT-AAA-NN] Título`. TTT es el tipo: `DES` descriptivo de puesto, `PRD` procedimiento, `PRO` protocolo, `POL` política; y los generales `ORG` organigrama, `KPI` indicadores, `GLO` glosario, `MPR` mapa de procesos, `CTX` otro contexto. AAA es el área (3 letras); `GEN` = aplica a varias áreas o a toda la empresa, o documento general. NN es el número (tres dígitos si el grupo pasa de 99).
- En políticas y protocolos, «Área propietaria» es el área que los emite (si el documento la trae); el área del código es a quién aplican.
- Las líneas que empiezan con `>` son metadatos de conversión, no texto original.
- `[NO ESPECIFICADO]`: el original no trae el campo.
- `[DIAGRAMA: la sección «…» no se transcribe…]`, `[DIAGRAMA O IMAGEN…]`, `[CELDA COMBINADA]`, `[TEXTO OCR…]` e `[IMAGEN OMITIDA]` son marcas de conversión. El contenido de un diagrama no está en el corpus: remite a la página del original.
- La sección “Datos de encabezado y pie” conserva código interno, versión y otros datos del encabezado original.
- Versión, estado, vigencia, propietario, responsable y proceso solo existen si el original los trae con su etiqueta (`Estado: Vigente`, o una celda `Estado` junto a `Vigente`). Una frase como “estado de cuenta” nunca es un estado documental. Vacío = `[NO ESPECIFICADO]`, nunca “Vigente”.
- Los documentos en estado `Borrador`, `Sustituido`, `Obsoleto`, `Inactivo`, `No vigente`, `Cancelado`, `Anulado` o `Derogado` se excluyen de todas las consultas. Si `doc` responde “excluido por su estado documental”, dilo así.

## 3. Estado de la construcción

Antes del primer briefing de una sesión, ejecuta `verificar`.

- `RESUMEN_CONSTRUCCION.md` dice `LISTO PARA PUBLICAR`, `PENDIENTE DE REVISIÓN VISUAL` o `REQUIERE REVISIÓN`. Si no dice LISTO, avísalo una vez al inicio de la respuesta.
- Si `verificar` dice “corpus completo: no”, no afirmes ausencias (“no tiene descriptivo”, “no participa”).
- Si `verificar` informa archivos modificados después de la conversión, avísalo: el corpus pudo alterarse.

Para construir o actualizar:

```bash
python scripts/convertir.py construir --entrada <carpeta_documentos> --contexto <carpeta_contexto>
python scripts/corpus.py verificar
```

- Los documentos van en `Descriptivos\<Área>\archivo`, `Procedimientos\<Área>\…`, `Protocolos\<Área>\…` o `Políticas\<Área>\…`. Una política o protocolo de varias áreas o de toda la empresa va en la carpeta de área `General` (código `GEN`). Si están directamente en `Descriptivos\` (sin carpeta de área), el área se escribe en `entrada\areas.csv` (`archivo;area`); el script crea ese archivo con la columna `area` vacía. `lista.txt` es opcional: sin ella, la lista se arma con la carpeta de entrada.
- En la carpeta de contexto, los procedimientos y fichas de proceso (`PRD`), las políticas, normativas y reglamentos (`POL`), los protocolos (`PRO`) y los descriptivos (`DES`) se tratan como documentos de área: área de la subcarpeta (`Fichas de proceso\Calidad\`), de `areas.csv` o `GEN`. Lo demás es un documento general por su subcarpeta o nombre (organigrama, kpi, glosario, mapa de procesos) o `CTX`.
- Los documentos sin área quedan como «Sin Área» con códigos provisionales `DES-SAR-NN` y la construcción termina en REQUIERE REVISIÓN. No cites esos códigos como definitivos.

- **REQUIERE REVISIÓN** (código 2): faltan documentos, hay texto del original que no aparece (cobertura < 100 %), palabras que no están en el original, códigos duplicados o errores del contexto.
- **PENDIENTE DE REVISIÓN VISUAL** (código 3): documentos con avisos de estructura (tabla leída como texto, filas partidas, posible diagrama, números incompletos, OCR…) y una muestra del 10 % de los demás. Una persona compara cada uno con su original y anota su código en `revision_visual_ok.txt` (uno por línea); luego se vuelve a construir. `--muestra-revision 0` desactiva la muestra.
- **LISTO PARA PUBLICAR** (código 0).
- Inventario: se ignoran temporales (`~$…`, `Thumbs.db`); el mismo documento en `.docx` y `.pdf` o una copia `(1)` se inventaría una vez (`--incluir-duplicados` conserva todos); los archivos se emparejan por su ruta `Tipo/Departamento/Archivo`. Al reconstruir, los códigos no cambian: los documentos nuevos van al final y los retirados reservan su código. Un corpus construido con la codificación anterior se migra solo (`D-` → `DES-`, `P-` → `PRD-` con el mismo número; `C-CTX-` por tipo dentro de `GEN`) y `revision_visual_ok.txt` puede seguir con los códigos anteriores.

## 4. Herramienta de consulta

Ejecuta siempre `scripts/corpus.py` antes de leer archivos manualmente:

```bash
python scripts/corpus.py <comando> <argumentos>
```

| Comando | Uso |
|---|---|
| `catalogo` | Áreas, cobertura, contexto, KPIs y entidades sin documentos |
| `area "<área>"` | Índice completo del área |
| `briefing "<área>" [--parte N]` | Tablas del briefing ya calculadas, 15 documentos por parte |
| `ficha "<área o código>" [--tipo DES\|PRD\|PRO\|POL\|GEN]` | Secciones y campos clave literales |
| `doc <CÓDIGO> [--seccion "<texto>"]` | Documento completo o una sección |
| `buscar "<t1\|t2\|t3*>" [--area "<área>"] [--tipo DES\|PRD\|PRO\|POL\|GEN]` | Búsqueda literal normalizada |
| `relaciones "<área A>" ["<área B>"]` | Menciones explícitas entre áreas y menciones no resueltas |
| `participacion "<área o código>" [--detalle N\|todo]` | Resumen por puesto (completo) y detalle acotado |
| `gobierno [--area "<área>"]` | Versión, estado, vigencia, propietario y responsable |
| `procesos [--area "<área>"]` | Macroproceso, proceso, procedimiento y actividades del desarrollo |
| `kpis [--gestion "<texto>"] [--sin-medicion] [--relacionar] [--area "<área>"]` | Indicadores y documentos que mencionan sus términos |
| `verificar` | Integridad (huellas), inventario, cobertura y corpus completo |

### Reglas de uso

- El área puede escribirse por nombre, código o alias (glosario o `areas_extra.csv`).
- `--tipo GEN` filtra los documentos con área `GEN`: los generales (organigramas, indicadores, glosario…) y las políticas y protocolos de toda la empresa.
- En `participacion` y en la matriz, los protocolos y las políticas cuentan como procedimientos (tienen responsables y actividades); `procesos` muestra solo procedimientos (`PRD`).
- `AMBIGUO`: muestra las opciones y formula una sola pregunta.
- `AVISO: '<texto>' se interpretó como el área …`: menciona esa interpretación en la respuesta.
- `NO ENCONTRADO`: indica qué revisaste y muestra las alternativas, incluidas las áreas o entidades sin documentos propios.
- “probable”, los verbos detectados y las actividades extraídas son ayudas automáticas: confírmalas con `doc` o marca `[Inferido]`.
- Las “menciones parecidas a varios puestos” no se asignaron a ningún puesto. No elijas uno: confírmalo con `doc` o déjalo como punto a validar. Un puesto con el mismo nombre en varias áreas se asigna al área del documento que lo menciona.
- Toda celda de la columna “Responsable” es un rol: si no coincide con un descriptivo aparece en “Puestos o roles … sin descriptivo”.
- El rol y el verbo se calculan con la oración (o la celda de la tabla) donde aparece el puesto o el área; si hay varios verbos se toma el más cercano. “Aprueba” y “Revisa o verifica” son roles distintos; una firma o una liberación no son una aprobación.
- `relaciones` muestra menciones explícitas. Las “menciones no resueltas” (áreas sin documentos, entidades externas, unidades no identificadas, puestos ambiguos) se reportan como tales, nunca como relación con un área del corpus. La ausencia de una mención no demuestra que la relación no exista.
- Para contar quién concentra más procedimientos usa el **Resumen por puesto** de `participacion` o de `briefing`, nunca el detalle.
- Si el script falla, lee `indice_corpus.csv` y luego el Markdown correspondiente.

## 5. Flujo: briefing de un área

1. Ejecuta `briefing "<área>"`. La primera línea dice cuántas partes hay; ejecuta `--parte 2`, `--parte 3`… hasta la última.
2. Copia las tablas tal como vienen (puestos, procedimientos, jerarquía, relaciones, participación, no documentado, indicadores). No las recalcules.
3. Si una celda es dudosa o necesitas funciones completas, consulta `doc <CÓDIGO>` o `ficha "<código>"`.
4. Redacta tú solo: 1. Resumen del área, 6. Insights y 8. Para profundizar.
5. Comprueba que la cobertura de tu respuesta coincide con la línea `Cobertura:` del script.

```text
# Briefing: <Área> (<COD>)
Cobertura: (copiar la línea del script)
## 1. Resumen del área
## 2. Puestos
## 3. Procedimientos
## 4. Jerarquía de procesos
## 5. Relaciones con otras áreas (incluye menciones no resueltas)
## 6. Insights
## 7. Información no documentada
## 8. Para profundizar
```

En “Información no documentada” incluye solo los campos `[NO ESPECIFICADO]` y, únicamente si el script los informa (solo lo hace con el corpus completo), los roles de procedimientos sin descriptivo. No agregues ausencias deducidas.

## 6. Flujo: relaciones entre áreas

1. Ejecuta `relaciones "<A>" "<B>"`.
2. Confirma citas dudosas con `doc <CÓDIGO> --seccion "<sección>"`.
3. Ejecuta `participacion "<A>"` y `participacion "<B>"` para los puntos de contacto.
4. Separa: menciones de A hacia B, de B hacia A, mencionadas por un solo lado y no resueltas.
5. No deduzcas relaciones por lógica del negocio.

## 7. Flujo: indicadores (KPIs)

Úsalo para metas, mediciones, desempeño o “cómo afectan al negocio”.

1. Ejecuta `kpis` (filtra con `--gestion` o `--sin-medicion`).
2. Para vincular con procesos ejecuta `kpis --relacionar [--area "<área>"]`. Es coincidencia de términos: todo vínculo KPI → documento se marca `[Inferido]` y se confirma con `doc`.
3. Una medición vacía es “sin medición”, nunca cero. El estado (Óptimo, Bueno, Regular, Malo) viene del color de la celda y es `[Inferido]`.
4. Cita siempre el ID del indicador, la meta, la medición y el periodo.
5. No calcules tendencias ni causas que no estén en el contexto. Preséntalas como “puntos a validar en la reunión”.

## 8. Flujo: consultas puntuales

- **Dato o documento:** ubica el código con `buscar` o `area`, luego `doc`.
- **Comparación:** `doc` para cada código y los mismos campos; lo que falte, `[NO ESPECIFICADO]`.
- **Tema:** `buscar` con variantes, sinónimos y siglas documentadas.
- **Cobertura:** `catalogo`; si preguntan si falta algo, `verificar`.

## 9. Flujo: gobierno documental

1. Ejecuta `gobierno` o `gobierno --area "<área>"`.
2. Confirma con `doc <CÓDIGO>` cuando la respuesta dependa del dato.
3. El comando muestra `[NO ESPECIFICADO]` en los campos vacíos; nunca los conviertas en “Vigente”.
4. Consultas históricas solo si el usuario lo pide explícitamente:

```bash
CORPUS_INCLUIR_NO_VIGENTES=1 python scripts/corpus.py gobierno
```

| Código | Documento | Versión | Estado | Vigencia | Propietario | Responsable |
|---|---|---|---|---|---|---|

## 10. Flujo: procesos y actividades

1. Ejecuta `procesos` o `procesos --area "<área>"`.
2. Confirma con `doc <CÓDIGO>` la sección de desarrollo.
3. Presenta la jerarquía solo cuando esté documentada; `[NO ESPECIFICADO]` en lo demás. El campo `Proceso` solo se llena si el original trae `Proceso:`.
4. No conviertas el nombre del área en proceso.
5. Las actividades salen solo del desarrollo: las filas de su tabla (con su responsable) o, si no tiene tabla, sus viñetas. Si el contexto no confirma una actividad, márcala `[Inferido]`.

| Macroproceso | Proceso | Código | Procedimiento | Actividades documentadas | Responsable |
|---|---|---|---|---|---|

## 11. Reglas para redactar respuestas

- Todo dato lleva su código (`DES-SEG-01`, `PRD-SEG-01`, `POL-GEN-01`, `ORG-GEN-01`, ID del KPI).
- Citas literales: frase breve entre comillas.
- Toda conclusión propia lleva `[Inferido]` y sus códigos base.
- Si algo no está: “No encontrado en los documentos”, indicando qué se revisó.
- Usa el índice para ubicar y el Markdown para confirmar. No uses `control/` como evidencia.
- Para un área, cubre todos sus códigos e incluye la línea de cobertura.
- No evalúes si un proceso está bien o mal. Presenta “puntos a validar en la reunión”.
- Usa solo el corpus; no completes con conocimiento general.

## 12. Preguntas analíticas internas

- ¿Qué procedimientos ejecuta, aprueba, revisa o recibe el área?
- ¿Qué puestos concentran más procedimientos (resumen por puesto)?
- ¿Cómo es la línea de reporte?
- ¿Con qué áreas tiene más menciones, y qué menciones quedaron sin resolver?
- ¿Qué indicadores mencionan términos de sus procedimientos y cuáles no tienen medición?
- ¿Qué campos están `[NO ESPECIFICADO]`?
- Solo con el corpus completo: ¿qué roles no tienen descriptivo y qué descriptivos no aparecen en procedimientos?
- ¿Qué jerarquía macroproceso → proceso → procedimiento → actividad está documentada?

Elige los insights más útiles. Cada insight es descriptivo, trazable y, si es conclusión propia, `[Inferido]`.
