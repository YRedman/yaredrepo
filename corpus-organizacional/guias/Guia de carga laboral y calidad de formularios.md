# Guía de carga laboral y calidad de los formularios

Esta guía aplica cuando completes el formulario K4 o la plantilla metodológica de PwC (formulario de levantamiento de carga laboral). Analizas el puesto, no a la persona: la carga mide el trabajo, no el desempeño.

## 1. Formato: los archivos nunca se arman a mano
- No crees, reescribas, "arregles", conviertas ni vuelvas a guardar un .xlsx con tu propio código. Los archivos salen solo de `corpus.py llenar-k4` (K4) y `corpus.py vaciar` (plantilla de PwC), a partir del archivo en blanco original del usuario.
- Entrega el archivo solo si el script imprimió «Verificación: correcta»; cita esa línea y los pendientes. Si el script falla o no hay verificación, no entregues archivo: di el error exacto y ofrece la tabla Markdown.
- Si el usuario dice que el formato se dañó: no lo corrijas a mano ni reenvíes el mismo archivo. Pregunta qué hoja y celda se ven mal, pide el archivo en blanco original y repite el comando con los mismos datos.
- Texto de cada celda: frases completas y sin Markdown (`**`, `|`, `#`, viñetas), una sola actividad por fila, menos de 1 000 caracteres, números como números y tiempos en minutos. Valores de listas desplegables: solo las opciones permitidas (el script las muestra con `--estructura`).
- Pendientes: en el K4, `VALIDAR: …` en morado (lo escribe el script); en la plantilla de PwC, la celda queda vacía y el dato va a `Puntos_a_validar`.

## 2. Qué detallar de cada actividad (enfoque de carga laboral)
Cada actividad es una fila y sale solo del K4, la entrevista, la minuta o el descriptivo (con su código). Nunca inventes tiempos, volúmenes ni frecuencias: sin dato, formula la pregunta concreta («¿Cuántos minutos le toma una vez?», «¿Cuántas veces por semana?», «¿Qué parte se repite por errores?»).
- **Nombre:** verbo en infinitivo + objeto («Emitir órdenes de compra»), no «Gestión de compras».
- **Jerarquía:** Proceso → Subproceso → Actividad. Una actividad es lo que una persona ejecuta de principio a fin; si es demasiado general, divídela; si es una microtarea, agrúpala.
- **Descripción (1 a 3 frases):** qué hace el empleado, con qué entradas y herramientas, dónde empieza y termina y qué entrega. Lo que realmente hace, no lo que «debería».
- **Categorías (solo valores de la lista):** Tipo de proceso (Core, Soporte, Gobierno/Control); Valor (VA = transforma o es lo que paga el cliente; NVA-N = no agrega valor pero es necesaria, por norma o control; NVA = desperdicio: esperas, retrabajo, reprocesos, aprobaciones repetidas); Automatización (Manual, Semiautomatizada, Automatizada); Frecuencia; Cliente (Interno, Externo, Mixto).
- **Medidas:** tiempo unitario (min), eventos por frecuencia, meses al año, participantes, % de dedicación, espera y retrabajo (fracción 0–1). Marca la fuente (K4, entrevista, minuta) y si es dato real o estimación.
- **Coherencia:** horas al mes = tiempo × eventos × veces al mes × (1 + retrabajo) × dedicación ÷ 60. Compara el total del puesto con la capacidad (≈190 h/mes): si pasa de 100 % o queda bajo 50 %, es un punto a validar, no una conclusión sobre sobrar o faltar gente (el FTE es preliminar).
- **Cobertura:** toda responsabilidad del puesto debe tener al menos una actividad y toda actividad un proceso; lista los vacíos.

## 3. Hallazgos y oportunidades (solo con evidencia)
Por actividad que lo amerite: hallazgo (qué pasa), evidencia (dato o cita con código), causa raíz, impacto en carga (minutos o horas al mes afectados), probabilidad e impacto (Bajo, Medio, Alto), acción (Eliminar, Simplificar, Estandarizar, Automatizar, Centralizar, Redistribuir, Mantener), beneficio esperado, esfuerzo (Muy bajo a Muy alto) y prioridad (Baja, Media, Alta, Crítica).
Señales a buscar: retrabajo alto, esperas, aprobaciones duplicadas, tareas manuales de alto volumen, dependencia de una sola persona, actividades sin dueño o de otro puesto (apoyo indirecto), picos estacionales, herramientas duplicadas, consultas reiteradas por falta de información.
Toda propuesta lleva `[Inferido]`. No cuantifiques ahorros sin dato: «ahorro: por medir».

## 4. Qué escribe cada herramienta y qué va al chat
- `llenar-k4` escribe el K4: tiempos, volúmenes, frecuencias y demás campos de cada hoja, con los pendientes en morado.
- `vaciar` pasa el K4 a la plantilla de PwC: tiempos, frecuencia, tipo de proceso, automatización, retrabajo, los riesgos del K4 y los puntos a validar. Lo que **tú propones** (el K4 no lo trae) lo entregas en `--complementos` y el script lo escribe en **letra morada**, con una nota «Inferido por el agente», para que el consultor lo valide a mano y vuelva la letra a negro:
  - `clasificacion` (una por actividad): `valor` (VA, NVA-N o NVA), `subproceso`, `cliente` (Interno, Externo o Mixto), `responsabilidad` (la responsabilidad vinculada) y `participantes`.
  - `hallazgos`: `actividad`, `hallazgo`, `evidencia`, `causa_raiz`, `impacto` y `probabilidad` (Bajo, Medio, Alto), `tipo_oportunidad`, `accion` (Eliminar, Simplificar, Estandarizar, Automatizar, Centralizar, Redistribuir, Mantener), `beneficio`, `esfuerzo` (Muy bajo a Muy alto) y `prioridad` (Baja, Media, Alta, Crítica). Con `complementa_k4: true` se completa la fila del riesgo que ya trae el K4 sin pisar lo que escribió el ocupante; no repitas los riesgos del K4 como hallazgos nuevos.
  - Un valor que no esté en la lista de la plantilla no se escribe: va a `Puntos_a_validar`.
  - Cada propuesta puede llevar `motivo` (por qué la propones); va en la nota de la celda.
- **Ninguna celda queda vacía.** Lo que ni el K4 ni tú entregan, `vaciar` lo completa solo, en letra morada y con una nota dentro de la misma celda de Excel (clic derecho → mostrar nota): **«Inferido: …»** cuando hay una regla (Valor VA / NVA-N / NVA y tipo de proceso por las palabras de la actividad, cliente interno o externo, responsabilidad o proceso por coincidencia de palabras, impacto por el peso de las horas, probabilidad por el retrabajo, acción, esfuerzo, prioridad, frecuencia o nivel aproximados) y **«A validar: …»** cuando no hay base (en las celdas de texto se escribe «A validar: …»; en las listas desplegables, que solo admiten sus opciones, se pone un valor provisional y la nota lo advierte). Solo las fechas quedan vacías. Tu trabajo es mejorar esas propuestas con lo que sepas de la entrevista (`clasificacion` y `hallazgos`), no dejar huecos.
- Después de generar el archivo, responde con tablas Markdown: (1) actividades por proceso con tiempo, frecuencia, horas al mes, Tipo y Valor; (2) horas al mes y % de la carga por categoría (Core/Soporte/Control; VA/NVA-N/NVA; Manual/Semi/Automatizada); (3) las cinco actividades de mayor carga; (4) hallazgos priorizados; (5) pendientes y preguntas para la próxima entrevista. Cada dato con su fuente: K4, entrevista, minuta, documento `[CÓDIGO]` o `[Inferido]`.
