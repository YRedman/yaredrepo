#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
corpus.py - Consultas exactas sobre el corpus organizacional (descriptivos, procedimientos, protocolos,
politicas y documentos generales).

Uso: python scripts/corpus.py <comando> [argumentos]

  catalogo                         Areas, codigos y numero de documentos.
  area "<area>"                    Indice completo de un area: todos sus codigos con sus datos clave.
  briefing "<area>" [--parte N]    Tablas del briefing ya calculadas, 15 documentos por parte.
  ficha "<area o codigo>" [--tipo DES|PRD|PRO|POL|GEN]
                                   Campos clave literales de cada documento (para briefings).
  doc <CODIGO> [--seccion "<texto>"]
                                   Texto completo y literal de un documento (o de una seccion).
  buscar "<termino1|termino2>" [--area "<area>"] [--tipo DES|PRD|PRO|POL|GEN]
                                   Busqueda literal (sin distinguir mayusculas ni acentos).
  relaciones "<area A>" ["<area B>"]
                                   Menciones explicitas entre areas, con codigo y cita, y menciones no resueltas.
  participacion "<area o codigo>" [--detalle N|todo]
                                   Resumen por puesto (completo) y detalle de su rol en los procedimientos.
  gobierno [--area "<area>"]       Versiones, vigencia, propietario y responsable.
  procesos [--area "<area>"]       Macroproceso, proceso, procedimiento y actividades.
  normativa [--area "<area>"]      Citas de leyes, reglamentos, normas, politicas, protocolos... (literales), por tipo.
  kpis [--gestion "<texto>"] [--sin-medicion] [--relacionar] [--area "<area>"]
                                   Indicadores y documentos que mencionan sus terminos.
  verificar                        Integridad (huellas), inventario, cobertura y corpus completo.

Codigos TTT-AAA-NN: tipo (DES, PRD, PRO, POL; ORG, KPI, GLO, MPR... generales), area (GEN = general) y numero.

Datos: este skill (fuente-contexto: indice/, contexto/, matriz/). Documentos: el skill hermano fuente-documentos;
si no esta, CORPUS_DATOS (la carpeta que contiene ambos skills) y luego una busqueda por nombre en
/home/oai/skills/appCatalog/<carpeta>/ (en Copilot la <carpeta> cambia).
Solo usa la biblioteca estandar de Python (sin red ni paquetes). No modifica ningun archivo.
La logica vive en el paquete ``corpus_org`` (junto a este archivo).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_org.consulta.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(uso=__doc__))
