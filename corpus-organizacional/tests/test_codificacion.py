"""Codificacion TTT-AAA-NN, migracion de codigos anteriores y estructura en dos skills de Copilot."""

import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tests import ayuda
from corpus_org.comun.archivos import escribir_csv
from corpus_org.comun.errores import CorpusError
from corpus_org.comun.esquema import COLUMNAS_INVENTARIO, RE_CODIGO
from corpus_org.comun.tipos import (codigo_nuevo_desde_anterior, cumple_tipo, familia, filtro_tipo, nombre_archivo,
                                    tipo_de_carpeta, tipo_general_de)
from corpus_org.consulta import ubicacion
from corpus_org.conversion.inventario import (InventarioBase, construir_inventario, escribir_equivalencias,
                                              inventario_contexto, leer_base, leer_equivalencias, parsear_lista)
from corpus_org.conversion.metadatos import extraer_metadatos

try:
    import docx  # noqa: F401
    import lxml  # noqa: F401
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        import fitz  # noqa: F401
    from tests.fixtures_corpus import desc, proc
    DEPENDENCIAS = True
except ImportError:
    DEPENDENCIAS = False


def _lista(tmp, *rutas):
    p = Path(tmp) / "lista.txt"
    p.write_text("\n".join(rutas) + "\n", encoding="utf-8")
    return p


class TiposTest(unittest.TestCase):
    def test_codigos_y_archivos(self):
        for c in ("DES-SEG-01", "PRD-SEG-01", "POL-GEN-01", "ORG-GEN-01", "PRO-SEG-100"):
            self.assertTrue(RE_CODIGO.match(c), c)
        for c in ("D-SEG-01", "ABC-FOR-040", "XYZ-SEG-01"):
            self.assertFalse(RE_CODIGO.match(c), c)
        self.assertEqual(nombre_archivo("POL", "GEN"), "POL_GEN.md")
        self.assertEqual((familia("DES"), familia("PRO"), familia("POL"), familia("GLO")), ("D", "P", "P", "C"))

    def test_migracion_de_codigos(self):
        self.assertEqual(codigo_nuevo_desde_anterior("D-SEG-01"), "DES-SEG-01")
        self.assertEqual(codigo_nuevo_desde_anterior("P-SEG-102"), "PRD-SEG-102")
        self.assertIsNone(codigo_nuevo_desde_anterior("C-CTX-01"))   # se clasifica por archivo

    def test_material_de_contexto(self):
        from corpus_org.comun.tipos import tipo_de_material
        self.assertEqual([tipo_de_material(x) for x in (
            "ABC-CAL-FDP-01 Ficha de proceso Compras", "Procedimiento de diseño organizacional", "Normativa interna",
            "Protocolo de emergencias", "Mapa de procesos", "Organigrama", "Fichas de proceso", "notas")],
            ["PRD", "PRD", "POL", "PRO", "MPR", "ORG", "PRD", None])

    def test_carpeta_con_varios_tipos_decide_el_nombre_del_archivo(self):
        from corpus_org.conversion.inventario import clasificar_material
        raiz = Path("/c")
        casos = {
            "12 Políticas y procedimientos relevantes/Política de compras.pdf": ("POL", ""),
            "12 Políticas y procedimientos relevantes/Compras/Procedimiento de pedidos.pdf": ("PRD", "Compras"),
            "Estructura Organizacional y Descriptivos de Puestos/Organigrama 2026.pdf": ("ORG", ""),
            "Estructura Organizacional y Descriptivos de Puestos/Perfil de analista.pdf": ("DES", ""),
            "Estructura Organizacional y Descriptivos de Puestos/1. ANALISTA.pdf": ("ORG", ""),   # sin pista: general
            "9 Mapa de procesos o macroprocesos/Mapa.pdf": ("MPR", ""),
            "PMO/Plan.pdf": ("CTX", ""),
        }
        for ruta, esperado in casos.items():
            self.assertEqual(clasificar_material(raiz / ruta, raiz), esperado, ruta)

    def test_carpetas_y_contexto(self):
        self.assertEqual([tipo_de_carpeta(x) for x in ("Descriptivos", "Procedimientos", "Políticas", "Protocolos")],
                         ["DES", "PRD", "POL", "PRO"])
        self.assertEqual(tipo_general_de("Organigrama general.pdf"), "ORG")
        self.assertIsNone(tipo_general_de("kpis_dashboard"))   # los indicadores van en kpis.csv, no en un .md
        self.assertEqual(tipo_general_de("Mapa de procesos"), "MPR")
        self.assertIsNone(tipo_general_de("notas varias"))

    def test_filtro_tipo(self):
        self.assertEqual([filtro_tipo(x) for x in ("des", "PRD", "Política", "GEN", "general")],
                         ["DES", "PRD", "POL", "GEN", "GEN"])
        with self.assertRaises(ValueError):
            filtro_tipo("XYZ")
        self.assertTrue(cumple_tipo("POL-GEN-01", "GEN") and cumple_tipo("ORG-GEN-01", "GEN"))
        self.assertFalse(cumple_tipo("POL-SEG-01", "GEN"))
        self.assertTrue(cumple_tipo("POL-SEG-01", "POL"))

    def test_area_propietaria(self):
        meta = extraer_metadatos(["Código: POL-001 Área propietaria: Calidad"], [])
        self.assertEqual(meta.area_propietaria, "Calidad")


class InventarioTest(unittest.TestCase):
    def test_area_general_y_numeracion_por_tipo_y_area(self):
        with tempfile.TemporaryDirectory() as tmp:
            filas, ignoradas = parsear_lista(_lista(
                tmp, r"C:\e\Políticas\General\Calidad.docx", r"C:\e\Políticas\Toda la empresa\Ética.docx",
                r"C:\e\Políticas\Seguridad\Accesos.docx", r"C:\e\Protocolos\Seguridad\Emergencias.docx",
                r"C:\e\Procedimientos\Seguridad\Rondas.docx", r"C:\e\Descriptivos\Seguridad\Jefe.docx"))
        self.assertEqual(ignoradas, [])
        inv = construir_inventario(filas, ignoradas)
        codigos = {f["archivo"]: f["codigo"] for f in inv.documentos}
        self.assertEqual(codigos, {"Calidad.docx": "POL-GEN-01", "Ética.docx": "POL-GEN-02",
                                   "Accesos.docx": "POL-SEG-01", "Emergencias.docx": "PRO-SEG-01",
                                   "Rondas.docx": "PRD-SEG-01", "Jefe.docx": "DES-SEG-01"})
        self.assertEqual([f["codigo"].split("-")[0] for f in inv.documentos],
                         ["DES", "PRD", "PRO", "POL", "POL", "POL"])
        cat = {r["codigo"]: r for r in inv.catalogo}
        self.assertEqual(cat["GEN"]["departamento"], "General")
        self.assertEqual((cat["SEG"]["DES"], cat["SEG"]["PRD"], cat["SEG"]["PRO"], cat["SEG"]["POL"]), (1, 1, 1, 1))

    def test_migracion_de_base_anterior(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base.csv"
            escribir_csv(base, COLUMNAS_INVENTARIO, [
                {"codigo": "D-SEG-02", "tipo": "Descriptivo", "codigo_departamento": "SEG", "departamento": "Seguridad",
                 "archivo": "Jefe.docx", "estado_inventario": "ACTIVO"},
                {"codigo": "D-SEG-01", "tipo": "Descriptivo", "codigo_departamento": "SEG", "departamento": "Seguridad",
                 "archivo": "Retirado.docx", "estado_inventario": "ACTIVO"},
                {"codigo": "P-SEG-01", "tipo": "Procedimiento", "codigo_departamento": "SEG",
                 "departamento": "Seguridad", "archivo": "Rondas.docx", "estado_inventario": "ACTIVO"}])
            b = leer_base(base)
            filas, ign = parsear_lista(_lista(tmp, r"C:\e\Descriptivos\Seguridad\Jefe.docx",
                                              r"C:\e\Descriptivos\Seguridad\Nuevo.docx",
                                              r"C:\e\Procedimientos\Seguridad\Rondas.docx"))
            inv = construir_inventario(filas, ign, base=b)
            eq = Path(tmp) / "equivalencias.csv"
            escribir_equivalencias(eq, b.equivalencias)
            escribir_equivalencias(eq, b.equivalencias)       # acumulativo, sin repetir
            equivalencias = leer_equivalencias(eq)
        codigos = {f["archivo"]: (f["codigo"], f["estado_inventario"]) for f in inv.documentos}
        self.assertEqual(codigos["Jefe.docx"], ("DES-SEG-02", "ACTIVO"))       # conserva su numero
        self.assertEqual(codigos["Rondas.docx"], ("PRD-SEG-01", "ACTIVO"))
        self.assertEqual(codigos["Retirado.docx"], ("DES-SEG-01", "RETIRADO"))  # reserva su codigo
        self.assertEqual(codigos["Nuevo.docx"], ("DES-SEG-03", "ACTIVO"))       # nuevo al final
        self.assertEqual(equivalencias, {"D-SEG-02": "DES-SEG-02", "D-SEG-01": "DES-SEG-01",
                                         "P-SEG-01": "PRD-SEG-01"})
        self.assertEqual(InventarioBase().equivalencias, [])

    def test_documento_que_cambia_de_area_registra_equivalencia(self):
        """Un procedimiento que estaba en General y ahora tiene area: el codigo viejo queda reservado y mapeado."""
        with tempfile.TemporaryDirectory() as tmp:
            filas, ign = parsear_lista(_lista(tmp, r"C:\e\Procedimientos\General\Compras.docx"))
            primero = construir_inventario(filas, ign)
            base = Path(tmp) / "base.csv"
            escribir_csv(base, COLUMNAS_INVENTARIO, primero.documentos)
            filas2, ign2 = parsear_lista(_lista(tmp, r"C:\e\Procedimientos\Calidad\Compras.docx"))
            segundo = construir_inventario(filas2, ign2, base=leer_base(base))
        codigos = {f["codigo"]: f["estado_inventario"] for f in segundo.documentos}
        self.assertEqual(codigos, {"PRD-GEN-01": "RETIRADO", "PRD-CAL-01": "ACTIVO"})
        self.assertEqual(segundo.equivalencias, [("PRD-GEN-01", "PRD-CAL-01")])

    def test_contexto_area_por_defecto_y_nombre_general(self):
        from corpus_org.conversion.inventario import clasificar_material, documentos_de_area_en_contexto
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "Procedimientos" / "Calidad").mkdir(parents=True)
            archivos = [raiz / "Procedimientos" / "Calidad" / "Auditoria.pdf",
                        raiz / "Procedimientos" / "Compras.pdf",
                        raiz / "Procedimientos" / "Gestión humana.pdf",
                        raiz / "Procedimientos" / "Mapa de Procesos 2025.pdf",
                        raiz / "Procedimientos" / "Procedimiento de diseño y estructura organizacional.pdf"]
            self.assertEqual(clasificar_material(archivos[3], raiz), ("MPR", ""))           # general aunque este en la carpeta
            self.assertEqual(clasificar_material(archivos[4], raiz)[0], "PRD")              # dice «procedimiento»
            filas = documentos_de_area_en_contexto(archivos, raiz, {"gestion humana": "Gestión Humana"})
        por_nombre = {f["archivo"]: (f["departamento"], f["area_por_defecto"]) for f in filas}
        self.assertEqual(por_nombre, {"Auditoria.pdf": ("Calidad", False), "Compras.pdf": ("General", True),
                                      "Gestión humana.pdf": ("Gestión Humana", False),
                                      "Procedimiento de diseño y estructura organizacional.pdf": ("General", True)})

    def test_area_del_documento_es_la_carpeta_que_contiene_la_del_tipo(self):
        from corpus_org.conversion.inventario import clasificar_material, documentos_de_area_en_contexto
        raiz = Path("/c")
        base = "03. Políticas y procedimientos/Gestión de Cadena de Suministro"
        casos = {
            f"{base}/Almacén/Procedimiento/Recepción de mercancía.docx": ("PRD", "Almacén"),
            f"{base}/Almacén/Política/Política de devolución.docx": ("POL", "Almacén"),
            "03. Políticas y procedimientos/Procedimiento/Compras generales.docx": ("PRD", ""),   # el padre es un contenedor de tipos
            "Procedimientos/Calidad/Auditoria.pdf": ("PRD", "Calidad"),                          # la carpeta siguiente al tipo manda
        }
        for ruta, esperado in casos.items():
            self.assertEqual(clasificar_material(raiz / ruta, raiz), esperado, ruta)
        # lo que el usuario escribe en areas.csv manda sobre la carpeta
        ruta = raiz / base / "Almacén" / "Procedimiento" / "Recepción de mercancía.docx"
        filas = documentos_de_area_en_contexto([ruta], raiz, {"recepcion de mercancia": "Logística"})
        self.assertEqual((filas[0]["departamento"], filas[0]["area_por_defecto"]), ("Logística", False))

    def test_contexto_por_tipo_estable_y_migrado(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "Organigramas").mkdir()
            archivos = [raiz / "Organigramas" / "Operaciones.pdf", raiz / "Glosario.docx", raiz / "Mapa de procesos.pdf",
                        raiz / "notas.md", raiz / "Organigrama general.pdf"]
            anteriores = {"glosario": "C-CTX-01", "notas": "C-CTX-02"}
            filas, eq = inventario_contexto(archivos, raiz, anteriores=anteriores)
            codigos = {f["archivo"]: f["codigo"] for f in filas}
            self.assertEqual(codigos, {"Operaciones.pdf": "ORG-GEN-01", "Organigrama general.pdf": "ORG-GEN-02",
                                       "Mapa de procesos.pdf": "MPR-GEN-01", "Glosario.docx": "GLO-GEN-01",
                                       "notas.md": "CTX-GEN-01"})
            self.assertEqual(sorted(eq), [("C-CTX-01", "GLO-GEN-01"), ("C-CTX-02", "CTX-GEN-01")])
            # reconstruir sin un organigrama y con uno nuevo: los codigos no cambian
            otros = [archivos[1], archivos[2], archivos[3], archivos[4], raiz / "Organigrama 2025.pdf"]
            filas2, _ = inventario_contexto(otros, raiz, base=filas)
        codigos2 = {f["archivo"]: (f["codigo"], f["estado_inventario"]) for f in filas2}
        self.assertEqual(codigos2["Operaciones.pdf"], ("ORG-GEN-01", "RETIRADO"))
        self.assertEqual(codigos2["Organigrama general.pdf"], ("ORG-GEN-02", "ACTIVO"))
        self.assertEqual(codigos2["Organigrama 2025.pdf"], ("ORG-GEN-03", "ACTIVO"))


class UbicacionTest(unittest.TestCase):
    def _skills(self, raiz, carpeta_docs="b2"):
        ctx = raiz / "appCatalog" / "a1" / "fuente-contexto"
        (ctx / "indice").mkdir(parents=True)
        (ctx / "indice" / "indice_corpus.csv").write_text("codigo\n", encoding="utf-8")
        docs = raiz / "appCatalog" / carpeta_docs / "fuente-documentos"
        (docs / "DES").mkdir(parents=True)
        (docs / "DES" / "DES_SEG.md").write_text("## [DES-SEG-01] Jefe\n", encoding="utf-8")
        return ctx, docs

    def test_hermana_primero(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx, docs = self._skills(Path(tmp), "a1")           # misma carpeta <carpeta> que fuente-contexto
            u = ubicacion.resolver_ubicacion(ctx, entorno={})
            self.assertEqual((u.contexto, u.documentos), (ctx.resolve(), docs.resolve()))

    def test_busqueda_por_nombre(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            ctx, docs = self._skills(raiz)                       # en otra <carpeta>
            with mock.patch.object(ubicacion, "RAIZ_SKILLS_COPILOT", raiz / "appCatalog"):
                u = ubicacion.resolver_ubicacion(ctx, entorno={})
            self.assertEqual((u.contexto, u.documentos), (ctx.resolve(), docs.resolve()))

    def test_variable_corpus_datos(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            ctx, docs = self._skills(raiz, "a1")
            for valor in (raiz / "appCatalog" / "a1", ctx, docs):   # la carpeta que contiene ambas, o una de ellas
                u = ubicacion.resolver_ubicacion(raiz / "otro", entorno={"CORPUS_DATOS": str(valor)})
                self.assertEqual((u.contexto, u.documentos), (ctx.resolve(), docs.resolve()), valor)

    def test_mensaje_exacto_si_no_esta(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            ctx, docs = self._skills(raiz)
            for p in sorted(docs.rglob("*"), reverse=True):
                p.unlink() if p.is_file() else p.rmdir()
            docs.rmdir()
            with mock.patch.object(ubicacion, "RAIZ_SKILLS_COPILOT", raiz / "no-existe"):
                with self.assertRaises(CorpusError) as e:
                    ubicacion.resolver_ubicacion(ctx, entorno={})
        self.assertEqual("ERROR: " + e.exception.mensaje,
                         "ERROR: no encuentro el skill fuente-documentos. Carga primero fuente-contexto y "
                         "fuente-documentos (lee su SKILL.md) y vuelve a ejecutar.")


class DividirMarkdownTest(unittest.TestCase):
    def test_divide_entre_documentos_y_conserva_ubicacion(self):
        from corpus_org.conversion.publicacion import dividir_markdown
        docs = [f"## [PRD-SEG-{n:02d}] Doc {n}\n" + "texto de relleno largo " * 20 + "\n\n---\n" for n in range(1, 7)]
        texto = "# Procedimientos · Seguridad (SEG)\n\nDocumentos de este archivo: 6. Cada...\n\n" + "\n".join(docs)
        partes = dividir_markdown(texto, "PRD_SEG.md", max_bytes=1500)
        self.assertGreater(len(partes), 1)
        nombres = [n for n, _, _ in partes]
        self.assertTrue(nombres[0].startswith("PRD_SEG_01-") and nombres[-1].endswith("-06.md"), nombres)
        codigos = [c for _, _, u in partes for c in u]
        self.assertEqual(codigos, [f"PRD-SEG-{n:02d}" for n in range(1, 7)])        # ninguno repetido ni perdido
        for nombre, t, ubic in partes:
            self.assertLessEqual(len(t.encode()), 1700)
            lineas = t.split("\n")
            for c, (ini, fin) in ubic.items():
                self.assertTrue(lineas[ini - 1].startswith(f"## [{c}]"), (nombre, c))
        self.assertEqual(dividir_markdown(texto, "PRD_SEG.md", max_bytes=10 ** 6)[0][0], "PRD_SEG.md")


def _construir(base):
    from corpus_org.conversion import cli as conversion_cli
    with redirect_stdout(io.StringIO()) as out:
        try:
            conversion_cli.main(["construir", "--entrada", str(base / "entrada"), "--contexto",
                                 str(base / "contexto"), "--sin-verificacion-cruzada", "--muestra-revision", "0"])
            codigo = 0
        except SystemExit as e:
            codigo = e.code
    return codigo, out.getvalue()


@unittest.skipUnless(DEPENDENCIAS, "faltan dependencias de conversion o de las pruebas")
class DosSkillsIntegracionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.tmp.name)
        ent, ctx = cls.base / "entrada", cls.base / "contexto"
        carpetas = {"des": ent / "Descriptivos" / "Seguridad", "prd": ent / "Procedimientos" / "Seguridad",
                    "polg": ent / "Políticas" / "General", "pols": ent / "Políticas" / "Seguridad",
                    "pro": ent / "Protocolos" / "Seguridad", "org": ctx / "Organigramas",
                    "fichas": ctx / "Fichas de proceso" / "Calidad"}
        for c in carpetas.values():
            c.mkdir(parents=True)
        desc(carpetas["des"] / "Jefe de Seguridad.docx", "Jefe de Seguridad", "Gerente General",
             "Proteger las instalaciones.", ["Coordinar las rondas.", "Aplicar la política de accesos."], "Código: DP-SEG-01")
        pasos = [("Realizar la ronda", "Jefe de Seguridad"), ("Registrar novedades", "Jefe de Seguridad")]
        proc(carpetas["prd"] / "Rondas.docx", "Código: PR-SEG-001", "Recorrer las instalaciones.", pasos, [])
        proc(carpetas["polg"] / "Política de calidad.docx", "Código: POL-CAL-001 Área propietaria: Calidad",
             "Asegurar la calidad en toda la empresa.", pasos, [])
        proc(carpetas["pols"] / "Política de accesos.docx", "Código: POL-SEG-001", "Controlar los accesos.", pasos, [])
        proc(carpetas["pro"] / "Protocolo de emergencias.docx", "Código: PRT-SEG-001", "Actuar ante emergencias.",
             pasos, [])
        # procedimiento y normativa en la carpeta de contexto: son documentos de area, no contexto general
        proc(carpetas["fichas"] / "Ficha de proceso de auditoría.docx", "Código: FP-CAL-001",
             "Auditar los procesos.", pasos, [])
        proc(ctx / "Reglamento interno.docx", "Código: RG-001", "Normar la convivencia.", pasos, [])
        # formatos que no se leen, un .zip y un descriptivo que ya esta en la entrada (mismo nombre)
        (ctx / "Plan.ppt").write_bytes(b"x")
        (ctx / "Datos.dat").write_bytes(b"x")
        (ctx / "todo.zip").write_bytes(b"x")
        desc(ctx / "Jefe de Seguridad.docx", "Jefe de Seguridad", "Gerente General", "Proteger.", ["Rondas."], "Código: DP-SEG-01")
        g = docx.Document()
        g.add_paragraph("Gerente General -> Jefe de Seguridad")
        g.save(carpetas["org"] / "Seguridad.docx")
        (ctx / "kpis_seguridad.csv").write_text("id;gestion;indicador;meta;medicion\nK-01;Seguridad;Rondas;30;28\n",
                                                encoding="utf-8")
        cls.codigo, cls.salida = _construir(cls.base)
        cls.publicado = ent / "salida_corpus" / "copilot"
        with open(cls.publicado / ayuda.INDICE / "indice_corpus.csv", encoding="utf-8-sig") as f:
            cls.indice = {r["codigo"]: r for r in csv.DictReader(f, delimiter=";")}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_documentos_de_area_del_contexto_sin_area_van_a_areas_csv(self):
        areas = (self.base / "entrada" / "areas.csv").read_text(encoding="utf-8-sig")
        self.assertIn("Reglamento interno.docx;", areas)          # quedo en General: se agrega con el area vacia
        self.assertNotIn("Ficha de proceso de auditoría", areas)    # ya tiene area (su subcarpeta)
        self.assertIn("quedan en «General» (GEN)", self.salida)

    def test_formatos_no_soportados_y_repetidos_de_la_entrada(self):
        self.assertIn("3 archivos de la carpeta de contexto no se leen", self.salida)
        self.assertIn(".zip ×1", self.salida)
        self.assertIn("descomprímalo", self.salida)
        lista = (self.base / "entrada" / "salida_corpus" / "control" / "archivos_no_leidos.csv").read_text("utf-8-sig")
        self.assertIn("Plan.ppt", lista)
        self.assertIn("ya están en la entrada (mismo nombre)", self.salida)
        self.assertEqual(sum(1 for r in self.indice.values() if r["archivo_origen"] == "Jefe de Seguridad.docx"), 1)

    def test_construccion(self):
        self.assertEqual(self.codigo, 0, self.salida)
        self.assertEqual(sorted(self.indice), ["DES-SEG-01", "ORG-GEN-01", "POL-GEN-01", "POL-GEN-02",
                                               "POL-SEG-01", "PRD-CAL-01", "PRD-SEG-01", "PRO-SEG-01"])
        self.assertEqual(self.indice["PRD-CAL-01"]["archivo_origen"], "Ficha de proceso de auditoría.docx")
        self.assertEqual(self.indice["POL-GEN-02"]["archivo_origen"], "Reglamento interno.docx")
        self.assertTrue(self.indice["PRD-CAL-01"]["actividades"])
        self.assertEqual(self.indice["POL-GEN-01"]["area_propietaria"], "Calidad")
        self.assertEqual(self.indice["POL-GEN-01"]["departamento"], "General")

    def test_estructura_de_carpetas(self):
        docs = self.publicado / ayuda.DOCUMENTOS
        self.assertEqual(sorted(p.relative_to(docs).as_posix() for p in docs.rglob("*") if p.is_file()),
                         ["DES/DES_SEG.md", "POL/POL_GEN.md", "POL/POL_SEG.md", "PRD/PRD_CAL.md", "PRD/PRD_SEG.md",
                          "PRO/PRO_SEG.md"])
        skill = self.publicado / "fuente-contexto"
        self.assertEqual(sorted(p.name for p in skill.iterdir()), ["contexto", "indice", "matriz", "scripts"])
        self.assertEqual(sorted(p.name for p in (skill / "contexto").iterdir()), ["ORG_GEN.md", "kpis.csv"])
        indice = {p.name for p in (skill / "indice").iterdir()}
        self.assertTrue({"indice_corpus.csv", "inventario_maestro.csv", "huellas.sha256", "RESUMEN_CONSTRUCCION.md"}
                        <= indice, indice)
        self.assertFalse(any(self.publicado.rglob("KPI_GEN.md")))
        politica = (docs / "POL" / "POL_GEN.md").read_text(encoding="utf-8")
        self.assertIn("\n## [POL-GEN-01] Política de calidad\n", politica)
        self.assertIn("> - Área propietaria: Calidad", politica)

    def test_scripts_planos_sin_convertir(self):
        scripts = self.publicado / "fuente-contexto" / "scripts"
        self.assertEqual(sorted(p.name for p in scripts.iterdir() if p.name != "__pycache__"),
                         ["corpus.py", "corpus_org"])
        carpeta = scripts / "corpus_org"
        self.assertEqual([p for p in carpeta.iterdir() if p.is_dir() and p.name != "__pycache__"], [])
        self.assertTrue((carpeta / "consulta_comandos_base.py").is_file())
        self.assertFalse(any("conversion" in p.name for p in carpeta.iterdir()))
        self.assertFalse(any(self.publicado.rglob("convertir.py")))
        self.assertFalse(any(p.parts[-2:] == ("control", p.name) for p in self.publicado.rglob("*")))
        from corpus_org.comun.estructura import informe_limites
        _, avisos = informe_limites([self.publicado / "fuente-contexto", self.publicado / "fuente-documentos"])
        self.assertEqual(avisos, [])
        resumen = (self.publicado / ayuda.INDICE / "RESUMEN_CONSTRUCCION.md").read_text(encoding="utf-8")
        self.assertIn("## Peso y número de archivos por carpeta", resumen)
        self.assertIn("fuente-documentos: ", resumen)

    def test_skill_md_del_equipo_no_se_sobrescribe(self):
        for nombre in ("fuente-contexto", "fuente-documentos"):
            (self.publicado / nombre / "SKILL.md").write_text("del equipo " + nombre, encoding="utf-8")
        codigo, salida = _construir(self.base)
        self.assertEqual(codigo, 0, salida)
        for nombre in ("fuente-contexto", "fuente-documentos"):
            self.assertEqual((self.publicado / nombre / "SKILL.md").read_text(encoding="utf-8"), "del equipo " + nombre)
        self.assertNotIn("Falta fuente-", salida)

    def test_matriz_en_csv(self):
        matriz = self.publicado / ayuda.MATRIZ
        nombres = sorted(p.name for p in matriz.glob("*.csv"))
        for esperado in ("puestos.csv", "funciones.csv", "relaciones.csv", "perfil_requisitos.csv",
                         "normativa_citada.csv", "procedimientos.csv", "participacion.csv", "indicadores.csv",
                         "revision.csv", "politicas_protocolos.csv"):
            self.assertIn(esperado, nombres)
        self.assertTrue((matriz / "matriz_organizacional.xlsx").is_file())
        with open(matriz / "politicas_protocolos.csv", encoding="utf-8-sig") as f:
            filas = list(csv.reader(f, delimiter=";"))
        self.assertEqual(filas[0][:4], ["Código", "Tipo", "Área", "Área propietaria"])
        self.assertIn(["POL-GEN-01", "Política", "General", "Calidad"], [r[:4] for r in filas[1:]])
        self.assertIn("POL-GEN-02", [r[0] for r in filas[1:]])
        with open(matriz / "procedimientos.csv", encoding="utf-8-sig") as f:
            filas = list(csv.reader(f, delimiter=";"))
        self.assertIn("PRD-CAL-01", [r[0] for r in filas])
        self.assertIn("PRO-SEG-01", [r[0] for r in filas])            # los protocolos tambien, con su tipo
        with open(matriz / "resumen.csv", encoding="utf-8-sig") as f:
            resumen = list(csv.reader(f, delimiter=";"))
        self.assertEqual(resumen[-1][:2], ["Total", "1"])

    def test_sin_codigos_del_formato_anterior(self):
        import re
        viejo = re.compile(r"(?<![A-Za-z0-9])[DPC]-[A-Z0-9]{3}-\d{2,3}\b")
        for p in self.publicado.rglob("*"):
            if p.is_file() and p.suffix in (".md", ".csv", ".sha256") and p.name != "equivalencias_codigos.csv":
                self.assertIsNone(viejo.search(p.read_text(encoding="utf-8-sig")), p)

    def test_consulta_desde_el_skill_solo_biblioteca_estandar(self):
        """corpus.py publicado corre sin paquetes instalados (-S) y encuentra el skill de documentos."""
        script = self.publicado / "fuente-contexto" / "scripts" / "corpus.py"
        entorno = {k: v for k, v in os.environ.items() if not k.startswith("CORPUS_")}
        r = subprocess.run([sys.executable, "-I", "-S", str(script), "buscar", "calidad", "--tipo", "GEN"],
                           capture_output=True, text=True, encoding="utf-8", env=entorno)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("POL-GEN-01", r.stdout)
        r = subprocess.run([sys.executable, "-I", "-S", str(script), "verificar"],
                           capture_output=True, text=True, encoding="utf-8", env=entorno)
        self.assertIn("Huellas SHA-256: todos los archivos coinciden", r.stdout)
        self.assertIn("Resultado: sin problemas", r.stdout)


    def test_todos_los_comandos_desde_los_scripts_publicados(self):
        script = self.publicado / "fuente-contexto" / "scripts" / "corpus.py"
        entorno = {k: v for k, v in os.environ.items() if not k.startswith("CORPUS_")}
        for comando in (["catalogo"], ["area", "Seguridad"], ["briefing", "Seguridad"], ["ficha", "Seguridad"],
                        ["doc", "DES-SEG-01"], ["buscar", "ronda"], ["relaciones", "Seguridad"],
                        ["participacion", "Seguridad"], ["gobierno"], ["procesos"], ["kpis"], ["verificar"]):
            r = subprocess.run([sys.executable, "-I", "-S", str(script), *comando], capture_output=True,
                               text=True, encoding="utf-8", env=entorno)
            self.assertEqual(r.returncode, 0, (comando, r.stdout[-400:], r.stderr[-400:]))
            self.assertNotIn("Traceback", r.stderr, comando)

    def test_sin_fuente_documentos_mensaje_exacto(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "solo" / "fuente-contexto"
            shutil.copytree(self.publicado / "fuente-contexto", destino)
            entorno = {k: v for k, v in os.environ.items() if not k.startswith("CORPUS_")}
            r = subprocess.run([sys.executable, "-I", "-S", str(destino / "scripts" / "corpus.py"), "catalogo"],
                               capture_output=True, text=True, encoding="utf-8", env=entorno)
        self.assertEqual(r.stdout.strip(),
                         "ERROR: no encuentro el skill fuente-documentos. Carga primero fuente-contexto y "
                         "fuente-documentos (lee su SKILL.md) y vuelve a ejecutar.")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()