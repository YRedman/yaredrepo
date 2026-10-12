#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convertir.py - Conversion de descriptivos de puesto y procedimientos a Markdown GFM.

Modos (se ejecuta con: python convertir.py <modo> [opciones]):

  inventario  Lee lista.txt (rutas Tipo/Departamento/Archivo copiadas desde el
              Explorador de Windows) y genera inventario_maestro.csv con los
              codigos de todos los documentos y catalogo.csv con los codigos de
              3 letras de cada departamento.

  convertir   Convierte los PDF y Word adjuntos usando inventario_maestro.csv.
              Genera un archivo .md por tipo y departamento, sus filas de
              diccionario (.csv) y un reporte de verificacion.

  contexto    Convierte los materiales de contexto adjuntos (organigrama, mapa
              de procesos, glosario...) a contexto.md.

  construir   Ejecuta el flujo completo: inventario, conversion, contexto opcional,
              indice consolidado, publicacion limpia y validacion automatica.

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
