#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convertir.py - Conversion de descriptivos de puesto, procedimientos, protocolos y politicas a Markdown GFM.

Codigos TTT-AAA-NN: tipo (DES, PRD, PRO, POL; generales ORG, KPI, GLO, MPR...), area (GEN = varias areas,
toda la empresa o documento general) y numero. Los tipos se definen en corpus_org/comun/tipos.py.

Modos (se ejecuta con: python convertir.py <modo> [opciones]):

  inventario  Lee lista.txt (rutas Tipo/Departamento/Archivo copiadas desde el
              Explorador de Windows) y genera inventario_maestro.csv con los
              codigos de todos los documentos y catalogo.csv con los codigos de
              3 letras de cada departamento. Los codigos anteriores (D-, P-) se
              migran y quedan en equivalencias_codigos.csv.

  convertir   Convierte los PDF y Word adjuntos usando inventario_maestro.csv.
              Genera un archivo .md por tipo y area (DES_SEG.md, POL_GEN.md...),
              sus filas de diccionario (.csv) y un reporte de verificacion.

  contexto    Convierte los materiales de contexto adjuntos como documentos
              generales: un archivo por tipo (ORG_GEN.md, GLO_GEN.md, MPR_GEN.md...). Los
              indicadores (kpi*.csv) se unen en kpis.csv.

  construir   Ejecuta el flujo completo: inventario, conversion, contexto opcional,
              indice consolidado, publicacion en dos carpetas listas para
              comprimir (salida_corpus/copilot/fuente-corpus: un solo skill),
              matriz maestra (xlsx y un CSV por hoja) y validacion automatica.
              Los SKILL.md los provee el equipo: el script no los escribe.

El script no modifica los archivos originales. Todo lo que genera queda en la
carpeta de salida (por defecto: <carpeta de entrada>/salida).

La logica vive en el paquete ``corpus_org`` (junto a este archivo); este
script solo es el punto de entrada.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_org.conversion.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
