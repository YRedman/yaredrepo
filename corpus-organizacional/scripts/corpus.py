#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
corpus.py - Consultas exactas sobre el corpus de descriptivos y procedimientos.

Uso: python scripts/corpus.py <comando> [argumentos]

  catalogo                         Areas, codigos y numero de documentos.
  area "<area>"                    Indice completo de un area: todos sus codigos con sus datos clave.
  ficha "<area o codigo>" [--tipo P|D]
                                   Campos clave literales de cada documento (para briefings).
  doc <CODIGO> [--seccion "<texto>"]
                                   Texto completo y literal de un documento (o de una seccion).
  buscar "<termino1|termino2>" [--area "<area>"] [--tipo P|D]
                                   Busqueda literal (sin distinguir mayusculas ni acentos).
  relaciones "<area A>" ["<area B>"]
                                   Menciones explicitas entre areas, con codigo y cita.
  participacion "<area o codigo>"  Puestos que aparecen en los procedimientos y con que rol.
  gobierno [--area "<area>"]       Versiones, vigencia, propietario y responsable.
  procesos [--area "<area>"]       Macroproceso, proceso, procedimiento y actividades.
  verificar                        Revisa que el corpus publicado este completo y sea coherente.

Solo usa la biblioteca estandar de Python. No modifica ningun archivo.
La logica vive en el paquete ``corpus_org`` (junto a este archivo).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_org.consulta.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(uso=__doc__))
