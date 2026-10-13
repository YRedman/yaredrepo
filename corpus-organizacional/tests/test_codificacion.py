"""Codificacion TTT-AAA-NN, migracion de codigos anteriores y estructura en dos skills de Copilot."""

import csv
import io
import os
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
        self.assertEqual((familia("DES"), familia("PRO"), familia("POL"), familia("KPI")), ("D", "P", "P", "C"))

    def test_migracion_de_codigos(self):
        self.assertEqual(codigo_nuevo_desde_anterior("D-SEG-01"), "DES-SEG-01")
        self.assertEqual(codigo_nuevo_desde_anterior("P-SEG-102"), "PRD-SEG-102")
        self.assertIsNone(codigo_nuevo_desde_anterior("C-CTX-01"))   # se clasifica por archivo

    def test_carpetas_y_contexto(self):
        self.assertEqual([tipo_de_carpeta(x) for x in ("Descriptivos", "Procedimientos", "Políticas", "Protocolos")],
                         ["DES", "PRD", "POL", "PRO"])
        self.assertEqual(tipo_general_de("Organigrama general.pdf"), "ORG")
        self.assertEqual(tipo_general_de("kpis_dashboard"), "KPI")
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

    def test_contexto_por_tipo_estable_y_migrado(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "Organigramas").mkdir()
            archivos = [raiz / "Organigramas" / "Operaciones.pdf", raiz / "Glosario.docx", raiz / "kpis.csv",
                        raiz / "notas.md", raiz / "Organigrama general.pdf"]
            anteriores = {"glosario": "C-CTX-01", "notas": "C-CTX-02"}
            filas, eq = inventario_contexto(archivos, raiz, anteriores=anteriores)
            codigos = {f["archivo"]: f["codigo"] for f in filas}
            self.assertEqual(codigos, {"Operaciones.pdf": "ORG-GEN-01", "Organigrama general.pdf": "ORG-GEN-02",
                                       "kpis.csv": "KPI-GEN-01", "Glosario.docx": "GLO-GEN-01",
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
    def _skills(self, raiz):
        ctx = raiz / "appCatalog" / "a1" / "corpus-contexto"
        (ctx / "datos").mkdir(parents=True)
        (ctx / "datos" / "indice_corpus.csv").write_text("codigo\n", encoding="utf-8")
        docs = raiz / "appCatalog" / "b2" / "corpus-documentos"
        (docs / "DES").mkdir(parents=True)
        (docs / "DES" / "DES_SEG.md").write_text("## [DES-SEG-01] Jefe\n", encoding="utf-8")
        return ctx, docs

    def test_busca_corpus_documentos_por_nombre(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            ctx, docs = self._skills(raiz)
            with mock.patch.object(ubicacion, "RAIZ_SKILLS_COPILOT", raiz / "appCatalog"):
                u = ubicacion.resolver_ubicacion(ctx, entorno={})
            self.assertEqual((u.datos, u.documentos), ((ctx / "datos").resolve(), docs.resolve()))

    def test_variables_de_entorno(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            ctx, docs = self._skills(raiz)
            u = ubicacion.resolver_ubicacion(raiz / "otro", entorno={"CORPUS_DATOS": str(ctx / "datos"),
                                                                     "CORPUS_DOCUMENTOS": str(docs)})
            self.assertEqual((u.datos, u.documentos), ((ctx / "datos").resolve(), docs.resolve()))

    def test_error_claro_si_no_esta(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            ctx, docs = self._skills(raiz)
            (docs / "DES" / "DES_SEG.md").unlink()
            (docs / "DES").rmdir()
            with mock.patch.object(ubicacion, "RAIZ_SKILLS_COPILOT", raiz / "no-existe"):
                with self.assertRaises(CorpusError) as e:
                    ubicacion.resolver_ubicacion(ctx, entorno={})
        self.assertIn("No encontré la carpeta del skill «corpus-documentos»", e.exception.mensaje)
        self.assertIn("CORPUS_DOCUMENTOS", e.exception.mensaje)


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
                    "pro": ent / "Protocolos" / "Seguridad", "org": ctx / "Organigramas"}
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
        g = docx.Document()
        g.add_paragraph("Gerente General -> Jefe de Seguridad")
        g.save(carpetas["org"] / "Seguridad.docx")
        (ctx / "kpis_seguridad.csv").write_text("id;gestion;indicador;meta;medicion\nK-01;Seguridad;Rondas;30;28\n",
                                                encoding="utf-8")
        cls.codigo, cls.salida = _construir(cls.base)
        cls.publicado = ent / "salida_corpus" / "publicado"
        with open(cls.publicado / ayuda.DATOS / "indice_corpus.csv", encoding="utf-8-sig") as f:
            cls.indice = {r["codigo"]: r for r in csv.DictReader(f, delimiter=";")}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_construccion(self):
        self.assertEqual(self.codigo, 0, self.salida)
        self.assertEqual(sorted(self.indice), ["DES-SEG-01", "KPI-GEN-01", "ORG-GEN-01", "POL-GEN-01", "POL-SEG-01",
                                               "PRD-SEG-01", "PRO-SEG-01"])
        self.assertEqual(self.indice["POL-GEN-01"]["area_propietaria"], "Calidad")
        self.assertEqual(self.indice["POL-GEN-01"]["departamento"], "General")

    def test_estructura_de_skills(self):
        docs = self.publicado / ayuda.DOCUMENTOS
        self.assertEqual(sorted(p.relative_to(docs).as_posix() for p in docs.rglob("*.md")),
                         ["DES/DES_SEG.md", "POL/POL_GEN.md", "POL/POL_SEG.md", "PRD/PRD_SEG.md", "PRO/PRO_SEG.md",
                          "SKILL.md"])
        datos = self.publicado / ayuda.DATOS
        self.assertTrue({"ORG_GEN.md", "KPI_GEN.md", "huellas.sha256", "matriz_organizacional.xlsx",
                         "inventario_contexto.csv"} <= {p.name for p in datos.iterdir()})
        politica = (docs / "POL" / "POL_GEN.md").read_text(encoding="utf-8")
        self.assertIn("\n## [POL-GEN-01] Política de calidad\n", politica)
        self.assertIn("> - Área propietaria: Calidad", politica)
        skill = self.publicado / "corpus-contexto"
        self.assertTrue((skill / "SKILL.md").is_file() and (skill / "scripts" / "corpus.py").is_file())
        self.assertTrue((skill / "scripts" / "corpus_org" / "consulta" / "cli.py").is_file())

    def test_matriz_en_csv(self):
        matriz = self.publicado / ayuda.DATOS / "matriz"
        nombres = sorted(p.name for p in matriz.glob("*.csv"))
        self.assertIn("09_politicas_y_protocolos.csv", nombres)
        with open(matriz / "09_politicas_y_protocolos.csv", encoding="utf-8-sig") as f:
            filas = list(csv.reader(f, delimiter=";"))
        self.assertEqual(filas[0][:4], ["Código", "Tipo", "Área de aplicación", "Área propietaria"])
        self.assertIn(["POL-GEN-01", "Política", "General", "Calidad"], [r[:4] for r in filas[1:]])
        with open(matriz / "02_resumen.csv", encoding="utf-8-sig") as f:
            resumen = list(csv.reader(f, delimiter=";"))
        self.assertEqual(resumen[-1][:2], ["Total", "1"])

    def test_consulta_desde_el_skill_solo_biblioteca_estandar(self):
        """corpus.py publicado corre sin paquetes instalados (-S) y encuentra el skill de documentos."""
        script = self.publicado / "corpus-contexto" / "scripts" / "corpus.py"
        entorno = {k: v for k, v in os.environ.items() if not k.startswith("CORPUS_")}
        r = subprocess.run([sys.executable, "-I", "-S", str(script), "buscar", "calidad", "--tipo", "GEN"],
                           capture_output=True, text=True, encoding="utf-8", env=entorno)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("POL-GEN-01", r.stdout)
        r = subprocess.run([sys.executable, "-I", "-S", str(script), "verificar"],
                           capture_output=True, text=True, encoding="utf-8", env=entorno)
        self.assertIn("Huellas SHA-256: todos los archivos coinciden", r.stdout)
        self.assertIn("Resultado: sin problemas", r.stdout)


if __name__ == "__main__":
    unittest.main()
