---
name: fuente-corpus
description: >-
  Consulta exacta del corpus organizacional publicado (descriptivos de puesto, procedimientos, protocolos, políticas, documentos generales e indicadores) con scripts/corpus.py. Incluye el texto de los documentos (carpeta documentos/), el contexto, el índice y la matriz. Úsalo cuando el usuario mencione un área, departamento, puesto, procedimiento, proceso, actividad, código, responsable, propietario, versión, vigencia, relación entre áreas, indicador, KPI, meta o preparación de reuniones.
---

# Corpus organizacional

> Compatible con `convertir.py` v4.6 y `corpus.py` v4.6.

Este skill consulta exclusivamente el corpus publicado. Los documentos son la fuente de verdad; el índice sirve para localizar, contar y filtrar, pero los datos sustantivos se confirman en el Markdown original.

## 0. Dónde está el corpus (primero, antes de ejecutar nada)

El skill cargado **no** está en `/home/oai/skills/fuente-corpus`. Queda en una carpeta intermedia que cambia en cada carga: `/home/oai/skills/appCatalog/<carpeta>/fuente-corpus`. **No adivines la ruta**; localízala primero:

```bash
find /home/oai/skills -type f -path '*fuente-corpus/scripts/corpus.py' 2>/dev/null | head -1
```

Ejecuta `corpus.py` con esa ruta completa (funciona desde cualquier carpeta): `python <ruta>/corpus.py <comando>`. Los ejemplos de este documento escriben `python scripts/corpus.py …` por brevedad; sustituye `scripts/corpus.py` por la ruta completa que hallaste. `corpus.py donde` muestra dónde está el skill y el comando listo para copiar; `corpus.py verificar` también lo informa.

Si `find` no devuelve nada, o `corpus.py` dice «no encuentro el skill…», es un problema de **localización, no de datos**: carga primero el skill `fuente-corpus` (lee su SKILL.md) y repite. Nunca concluyas que un documento o un área «no está en el corpus» sin haber localizado antes el skill.

## 1. Estructura

El corpus se publica en **un solo skill**, `fuente-corpus` (`salida_corpus/copilot/fuente-corpus/`), con este `SKILL.md` en su raíz:

- `documentos/`: un Markdown por tipo y área, en una carpeta por tipo: `DES/DES_<ÁREA>.md` descriptivos de puesto, `PRD/PRD_<ÁREA>.md` procedimientos, `PRO/PRO_<ÁREA>.md` protocolos y `POL/POL_<ÁREA>.md` políticas. Las políticas y protocolos que aplican a más de un área o a toda la empresa están en `POL_GEN.md` / `PRO_GEN.md`. Un área grande puede venir en partes (`PRD_SEG_01-20.md`).
- `scripts/corpus.py` consulta; `scripts/corpus_org/` es el paquete con la lógica (solo biblioteca estándar).
- `contexto/<TTT>_GEN.md`: documentos generales: `ORG_GEN.md` organigramas, `GLO_GEN.md` glosarios, `MPR_GEN.md` mapas de procesos y `CTX_GEN.md` otro contexto. `contexto/kpis.csv`: indicadores transcritos (ID propio, meta, medición, unidad, estado según el color); no hay un Markdown de indicadores.
- `indice/indice_corpus.csv`: índice maestro, una fila por documento (con `area_propietaria` para políticas y protocolos).
- `indice/inventario_maestro.csv`: documentos que deberían existir. Las filas `RETIRADO` solo reservan su código.
- `indice/equivalencias_codigos.csv`: `codigo_anterior;codigo_nuevo` de la codificación anterior (`D-`, `P-`, `C-CTX-`).
- `indice/areas_extra.csv`: áreas y entidades sin documentos propios (internas, externas) y frases que no son menciones de un área.
- `indice/RESUMEN_CONSTRUCCION.md`: resultado de la última construcción.
- `indice/huellas.sha256`: SHA-256 de cada archivo publicado en el skill (integridad).
- `matriz/matriz_organizacional.xlsx` y `matriz/*.csv`: la matriz maestra, una hoja por CSV (UTF-8, separador `;`). Incluye **Cadena documental** (qué documento cita a cuál) y **Revisión** (calidad de lectura de cada documento).

El reporte de control (`salida_corpus/control/`) no se publica ni es fuente de respuestas. `convertir.py` construye el corpus; el agente no lo ejecuta.

`corpus.py` encuentra los documentos en `documentos/`, dentro de su propio skill; si lo copiaron a otro lugar, usa `CORPUS_DATOS` (la carpeta del skill o la que lo contiene) y luego busca por nombre (en `/home/oai/skills/appCatalog/*/`, en `/home/oai/skills/`, en `/mnt/data` y recorriendo esas carpetas). Si no lo encuentra imprime `ERROR: no encuentro el skill fuente-corpus. Carga primero el skill fuente-corpus (lee su SKILL.md) y vuelve a ejecutar.`: carga el skill y repite el comando (ver sección 0).

## 2. Interpretación de documentos

- Cada documento empieza con `## [TTT-AAA-NN] Título`. TTT es el tipo: `DES` descriptivo de puesto, `PRD` procedimiento, `PRO` protocolo, `POL` política; y los generales `ORG` organigrama, `GLO` glosario, `MPR` mapa de procesos, `CTX` otro contexto. AAA es el área (3 letras); `GEN` = aplica a varias áreas o a toda la empresa, o documento general. NN es el número (tres dígitos si el grupo pasa de 99).
- En políticas y protocolos, «Área propietaria» es el área que los emite (si el documento la trae); el área del código es a quién aplican.
- Las líneas que empiezan con `>` son metadatos de conversión, no texto original.
- `[NO ESPECIFICADO]`: el original no trae el campo.
- `[DIAGRAMA: la sección «…» no se transcribe…]`, `[DIAGRAMA O IMAGEN…]`, `[CELDA COMBINADA]`, `[TEXTO OCR…]` e `[IMAGEN OMITIDA]` son marcas de conversión. El contenido de un diagrama no está en el corpus: remite a la página del original.
- La sección “Datos de encabezado y pie” conserva código interno, versión y otros datos del encabezado original.
- `[TEXTO OCR…]`: la página era un escaneo y se leyó con OCR (la matriz indica la confianza en «Calidad de lectura»). Un documento leído con OCR puede traer errores de letras en cifras, códigos y nombres propios: cita su código, confirma el dato con `doc` y, si es una cifra o una fecha decisiva, dilo como «a confirmar contra el original».
- Las firmas manuscritas se ignoran (no son texto): no afirmes que un documento está o no firmado.
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
python scripts/corpus.py verificar        # informa también peso y número de archivos por carpeta
```

`construir` convierte varios documentos a la vez (`--trabajadores N`; por defecto núcleos − 1, hasta 4; `1` = uno a uno) y escribe `salida_corpus\NOTA_UBICACION_SKILL.md` (el párrafo de la sección 0; avisa si este `SKILL.md` no lo trae) y copia este `SKILL.md` a `fuente-corpus/`. Se comprime y se sube **una sola carpeta**: `salida_corpus/copilot/fuente-corpus`.

- Los documentos van en `Descriptivos\<Área>\archivo`, `Procedimientos\<Área>\…`, `Protocolos\<Área>\…` o `Políticas\<Área>\…`. Una política o protocolo de varias áreas o de toda la empresa va en la carpeta de área `General` (código `GEN`). Si están directamente en `Descriptivos\` (sin carpeta de área), el área se escribe en `entrada\areas.csv` (`archivo;area`); el script crea ese archivo con la columna `area` vacía. `lista.txt` es opcional: sin ella, la lista se arma con la carpeta de entrada.
- En la carpeta de contexto, los procedimientos y fichas de proceso (`PRD`), las políticas, normativas y reglamentos (`POL`), los protocolos (`PRO`) y los descriptivos (`DES`) se tratan como documentos de área: área de `areas.csv` (manda si el archivo está ahí), de la subcarpeta que sigue a la del tipo (`Fichas de proceso\Calidad\`) o, si el archivo está directamente en la carpeta del tipo, de la carpeta que la contiene (`Gestión Comercial\Ventas\Procedimiento\x.docx` → Ventas); si no, `GEN`. Un árbol `Gestión X\<Área>\Procedimiento|Política\archivo` se clasifica solo. Lo demás es un documento general por su subcarpeta o nombre (organigrama, glosario, mapa de procesos) o `CTX`; los `kpi*.csv` van a `kpis.csv`.
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
| `donde` | Dónde está el skill `fuente-corpus`, ruta completa de `corpus.py` y comando listo (no carga el corpus: úsalo si algo no se encuentra) |
| `catalogo` | Áreas, cobertura por tipo (DES, PRD, PRO, POL), documentos generales, KPIs y entidades sin documentos |
| `area "<área>"` | Índice completo del área |
| `briefing "<área>" [--parte N]` | Tablas del briefing ya calculadas, 15 documentos por parte |
| `normativa [--area "<área>"]` | Citas literales de leyes, reglamentos, normas, políticas, protocolos, procedimientos, manuales y códigos de documento, por tipo de referencia |
| `ficha "<área o código>" [--tipo DES\|PRD\|PRO\|POL\|GEN]` | Secciones y campos clave literales |
| `doc <CÓDIGO> [--seccion "<texto>"]` | Documento completo o una sección |
| `buscar "<t1\|t2\|t3*>" [--area "<área>"] [--tipo DES\|PRD\|PRO\|POL\|GEN]` | Búsqueda literal normalizada |
| `relaciones "<área A>" ["<área B>"]` | Menciones explícitas entre áreas y menciones no resueltas |
| `participacion "<área o código>" [--detalle N\|todo]` | Resumen por puesto (completo) y detalle acotado |
| `gobierno [--area "<área>"]` | Versión, estado, vigencia, propietario y responsable |
| `procesos [--area "<área>"]` | Macroproceso, proceso, procedimiento y actividades del desarrollo |
| `cadena [<CÓDIGO>] [--profundidad N] [--area "<área>"]` | Cadena documental: qué documento cita a cuál (códigos internos resueltos contra el corpus), citas entre áreas, documentos más citados y **documentos citados que faltan en el corpus**; con un código, lo que cita y quién lo cita (2 saltos por defecto) |
| `citar <CÓDIGO>… [--texto "<afirmación>"]` | Confirma que el documento existe, si es específico de un área o general, dónde está su original y, con `--texto` (repetible), si respalda la afirmación: `RESPALDADO (literal)`, `RESPALDO PARCIAL` o `SIN RESPALDO` |
| `kpis [--gestion "<texto>"] [--sin-medicion] [--relacionar] [--area "<área>"]` | Indicadores y documentos que mencionan sus términos |
| `verificar` | Integridad (huellas), inventario, cobertura, corpus completo, peso y número de archivos por carpeta |

### Reglas de uso

- **Solo documentos suministrados.** Responde únicamente con lo que traen los documentos del corpus (`doc`, `ficha`, tablas del script). No completes con conocimiento general ni con lo que “sería conveniente”; si algo no está, dilo (`No documentado`).
- **Cada documento es un registro único.** No mezcles datos de dos documentos (puestos, versiones, funciones) en una sola afirmación; cita el código de cada uno.
- **Respalda lo que afirmas.** Antes de citar un documento, confirma con `citar <CÓDIGO> --texto "<lo que afirmas>"` que existe y que lo dice. Con `SIN RESPALDO` no lo atribuyas a ese documento; con `RESPALDO PARCIAL` usa el pasaje literal. Un documento `GENERAL (GEN)` no es específico del área consultada: preséntalo como contexto o norma de toda la empresa y reevalúa si hay un documento más específico.

- El área puede escribirse por nombre, código o alias (glosario o `areas_extra.csv`).
- `--tipo GEN` filtra los documentos con área `GEN`: los generales (organigramas, glosario, mapas de procesos…) y las políticas y protocolos de toda la empresa.
- `participacion`, la matriz y el briefing cuentan los protocolos (`PRO`) junto con los procedimientos (`PRD`): tienen responsables y actividades. `procesos` muestra solo procedimientos.
- `AMBIGUO`: muestra las opciones y formula una sola pregunta.
- `AVISO: '<texto>' se interpretó como el área …`: menciona esa interpretación en la respuesta.
- `NO ENCONTRADO`: indica qué revisaste y muestra las alternativas, incluidas las áreas o entidades sin documentos propios.
- “probable”, los verbos detectados y las actividades extraídas son ayudas automáticas: confírmalas con `doc` o marca `[Inferido]`.
- Las “menciones parecidas a varios puestos” no se asignaron a ningún puesto. No elijas uno: confírmalo con `doc` o déjalo como punto a validar. Un puesto con el mismo nombre en varias áreas se asigna al área del documento que lo menciona.
- Toda celda de la columna “Responsable” es un rol: si no coincide con un descriptivo aparece en “Puestos o roles … sin descriptivo”.
- El rol y el verbo se calculan con la oración (o la celda de la tabla) donde aparece el puesto o el área; si hay varios verbos se toma el más cercano. Como rol, “Aprueba” y “Revisa o verifica” son distintos; el verbo de una relación es “Aprueba o revisa”. Una firma o una liberación no son una aprobación.
- `relaciones` muestra menciones explícitas. Las “menciones no resueltas” (áreas sin documentos, entidades externas, unidades no identificadas, puestos ambiguos) se reportan como tales, nunca como relación con un área del corpus. La ausencia de una mención no demuestra que la relación no exista.
- Para contar quién concentra más procedimientos usa el **Resumen por puesto** de `participacion` o de `briefing`, nunca el detalle.
- Si el script no se encuentra o dice «no encuentro el skill…», sigue la sección 0 antes de cualquier otra cosa; no lo trates como ausencia de datos.
- Si el script falla por otra causa, lee `indice/indice_corpus.csv` y luego el Markdown correspondiente.

## 5. Flujo: briefing de un área

1. Ejecuta `briefing "<área>"`. La primera línea es `Partes: N`; ejecuta `--parte 2`, `--parte 3`… hasta la última. Las tablas que resumen toda el área vienen en la parte 1; los documentos se reparten de 15 en 15.
2. Copia las tablas tal como vienen, con sus títulos y en su orden. No las recalcules.
3. Si una celda es dudosa o necesitas funciones completas, consulta `doc <CÓDIGO>` o `ficha "<código>"`; para el detalle de las citas, `normativa --area "<área>"`.
4. Redacta tú solo: Resumen del área, Insights y Para profundizar.
5. Comprueba que la cobertura de tu respuesta coincide con la línea `Cobertura:` del script.

Orden de las tablas (títulos exactos): `Partes: N` · `Cobertura: DES x/x · PRD y/y · PRO z/z · POL w/w · GEN pertinentes: n` · Puestos (DES) · Procedimientos (PRD) · Protocolos (PRO) · Políticas (POL) · Jerarquía de procesos · Relaciones · Participación — Resumen por puesto · Procedimientos con un solo puesto participante · Mismo puesto con roles Ejecuta y Aprueba en un procedimiento · Estructura · Indicadores relacionados · Gobierno documental (resumen) · Normativa citada (resumen) · Perfil y funciones (resumen por puesto) · No documentado.

- En Protocolos y Políticas, la columna `Motivo` dice por qué entra cada uno: `Del área`, o, si es GEN, `Menciona al área`, `Menciona al puesto <nombre>` o `Alcance: toda la empresa`. No agregues un GEN por afinidad de tema.
- Los verbos de Relaciones son Entrega, Recibe, Solicita, Aprueba o revisa, Notifica, Coordina y Reporta; las entidades externas (proveedores, autoridades, clientes) están en su propia tabla de menciones no resueltas.
- En «No documentado» incluye solo los campos `[NO ESPECIFICADO]` y, únicamente si el script los informa (solo lo hace con el corpus completo), los roles sin descriptivo y los descriptivos que no aparecen en procedimientos. No agregues ausencias deducidas.

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
- **Dependencias entre documentos:** `cadena` (sección 11).

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

## 11. Flujo: cadena documental (cadena de valor)

Úsalo para «qué documento depende de cuál», «qué otros procedimientos intervienen» o «qué falta para completar el proceso».

1. Ejecuta `cadena` para el panorama: citas entre áreas, documentos más citados y documentos citados que faltan.
2. Para un documento, `cadena <CÓDIGO>`: lo que cita (hacia delante) y quién lo cita (hacia atrás), con los saltos pedidos.
3. Confirma cada eslabón con `doc <CÓDIGO>` (sección «Documentos relacionados» o la actividad que lo cita) antes de afirmarlo.
4. Un código citado se une con un documento del corpus solo si coincide con su código interno (completo o su final, sin ambigüedad). Los códigos de otra numeración (`ALM-PRO-005`) y los formatos (`COM-FOR-007`) quedan como «no está en el corpus»: preséntalos como documentos por solicitar, no como errores.
5. La cadena es lo que los documentos citan, no el flujo del negocio. No deduzcas dependencias ni el orden entre procesos: cualquier vínculo adicional va marcado `[Inferido]`.

## 12. Reglas para redactar respuestas

- Todo dato lleva su código (`DES-SEG-01`, `PRD-SEG-01`, `POL-GEN-01`, `ORG-GEN-01`, ID del KPI).
- Citas literales: frase breve entre comillas.
- Toda conclusión propia lleva `[Inferido]` y sus códigos base.
- Si algo no está: “No encontrado en los documentos”, indicando qué se revisó.
- Usa el índice para ubicar y el Markdown para confirmar. No uses `control/` como evidencia.
- Para un área, cubre todos sus códigos e incluye la línea de cobertura.
- No evalúes si un proceso está bien o mal. Presenta “puntos a validar en la reunión”.
- Usa solo el corpus; no completes con conocimiento general.

## 13. Preguntas analíticas internas

- ¿Qué procedimientos ejecuta, aprueba, revisa o recibe el área?
- ¿Qué puestos concentran más procedimientos (resumen por puesto)?
- ¿Cómo es la línea de reporte?
- ¿Con qué áreas tiene más menciones, y qué menciones quedaron sin resolver?
- ¿Qué indicadores mencionan términos de sus procedimientos y cuáles no tienen medición?
- ¿Qué campos están `[NO ESPECIFICADO]`?
- Solo con el corpus completo: ¿qué roles no tienen descriptivo y qué descriptivos no aparecen en procedimientos?
- ¿Qué jerarquía macroproceso → proceso → procedimiento → actividad está documentada?
- ¿Qué documentos cita cada procedimiento y cuáles de esos documentos faltan en el corpus (`cadena`)?

Elige los insights más útiles. Cada insight es descriptivo, trazable y, si es conclusión propia, `[Inferido]`.
