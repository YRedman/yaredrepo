"""Pruebas de las correcciones de lectura de la v3.1 (inventario, descriptivos, diagramas, puestos, PDF)."""

import csv
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tests import ayuda  # noqa: F401
from corpus_org.consulta import cli as consulta_cli
from corpus_org.consulta.participacion import rol_sin_descriptivo
from corpus_org.consulta.puestos import DetectorPuestos, Puesto
from corpus_org.consulta.roles import rol, verbo
from corpus_org.conversion import cli as conversion_cli
from corpus_org.conversion.analisis import analizar
from corpus_org.conversion.asignacion import asignar_archivos
from corpus_org.conversion.entradas import es_archivo_ignorado
from corpus_org.conversion.extractores.pdf import _repetidas
from corpus_org.conversion.extractores.texto import ExtractorTexto
from corpus_org.conversion.inventario import parsear_lista, quitar_duplicados
from corpus_org.conversion.modelo import DocumentoExtraido, bloque_h

try:
    import docx  # noqa: F401
    import lxml  # noqa: F401
    from tests.fixtures_casos import generar, generar_pdf
    DEPENDENCIAS = True
except ImportError:
    DEPENDENCIAS = False


def tabla(*filas):
    return {"k": "tabla", "filas": [list(f) for f in filas]}


class InventarioTest(unittest.TestCase):
    def test_archivos_del_sistema(self):
        for n in ("~$mpra.docx", "Thumbs.db", "desktop.ini", ".~lock.x.docx#"):
            self.assertTrue(es_archivo_ignorado(n), n)
        self.assertFalse(es_archivo_ignorado("Compra.docx"))

    def test_lista_ignora_bloqueos_de_word(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "lista.txt"
            p.write_text("C:\\E\\Procedimientos\\Compras\\Compra.docx\nC:\\E\\Procedimientos\\Compras\\~$mpra.docx\n",
                         encoding="utf-8")
            filas, ignoradas = parsear_lista(p)
        self.assertEqual([f["archivo"] for f in filas], ["Compra.docx"])
        self.assertEqual(ignoradas[0][1], "archivo temporal o del sistema")

    def test_duplicados(self):
        filas = [{"tipo": "PRD", "departamento": "Compras", "archivo": n}
                 for n in ("Compra.pdf", "Compra (1).docx", "Compra.docx", "Otra.docx")]
        salida, avisos = quitar_duplicados(filas)
        self.assertEqual([f["archivo"] for f in salida], ["Compra.docx", "Otra.docx"])
        self.assertEqual(len(avisos), 1)
        self.assertEqual(len(quitar_duplicados(filas, incluir=True)[0]), 4)

    def test_asignacion_por_ruta(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            archivos = []
            for dep in ("Compras", "Almacen"):
                p = raiz / "Descriptivos" / dep / "Asistente.docx"
                p.parent.mkdir(parents=True)
                p.write_bytes(b"")
                archivos.append(p)
            inventario = [{"codigo": f"DES-{c}-01", "tipo": "Descriptivo", "codigo_departamento": c, "archivo": "Asistente.docx",
                           "ruta_original": f"C:\\E\\Descriptivos\\{dep}\\Asistente.docx"}
                          for c, dep in (("COM", "Compras"), ("ALM", "Almacen"))]
            a = asignar_archivos(inventario, archivos, raiz=raiz)
        self.assertEqual(a.ambiguos, [])
        self.assertEqual(a.asignados[("DES", "COM")]["DES-COM-01"].parent.name, "Compras")
        self.assertEqual(a.asignados[("DES", "ALM")]["DES-ALM-01"].parent.name, "Almacen")


class DescriptivoTest(unittest.TestCase):
    def campos(self, *bloques):
        return analizar(DocumentoExtraido(bloques=list(bloques)), "D")[1].campos

    def test_etiquetas_nuevas(self):
        c = self.campos(tabla(("Jefe directo", "Gerente de Compras"), ("Puestos a su cargo", "Compradores")))
        self.assertEqual((c["reporta_a"], c["supervisa_a"]), ("Gerente de Compras", "Compradores"))
        self.assertEqual(self.campos({"k": "p", "texto": "Depende de: Director General"})["reporta_a"],
                         "Director General")

    def test_tabla_horizontal(self):
        c = self.campos(tabla(("Nombre del puesto", "Departamento", "Salario", "Reporta a"),
                              ("Gerente de Calidad", "Calidad", "Confidencial", "Director General")))
        self.assertEqual((c["nombre_puesto"], c["area"], c["reporta_a"]),
                         ("Gerente de Calidad", "Calidad", "Director General"))

    def test_una_etiqueta_nunca_es_valor(self):
        c = self.campos(tabla(("Nombre del puesto", "Departamento"), ("Reporta a", "Salario")))
        self.assertNotIn("nombre_puesto", c)
        self.assertNotIn("reporta_a", c)


class DiagramaTest(unittest.TestCase):
    def test_seccion_diagrama_se_sustituye(self):
        d = DocumentoExtraido(bloques=[bloque_h(1, "Desarrollo"), {"k": "p", "texto": "Paso uno."},
                                       bloque_h(1, "4. Diagrama de flujo"), {"k": "p", "texto": "¿Aprobada?", "pagina": 2},
                                       bloque_h(1, "Referencias"), {"k": "p", "texto": "Manual"}])
        bloques, a = analizar(d, "P")
        textos = [b.get("texto") for b in bloques]
        self.assertNotIn("¿Aprobada?", textos)
        self.assertIn("[DIAGRAMA: la sección «4. Diagrama de flujo» no se transcribe; ver página 3]", textos)
        self.assertIn("Manual", textos)
        self.assertEqual(a.secciones_diagrama, ["4. Diagrama de flujo"])
        self.assertGreater(a.excluidos["aprobada"], 0)


class EncabezadosRepetidosTest(unittest.TestCase):
    """Un encabezado real aparece una vez por pagina y a la misma altura; una fila de tabla no."""

    def test_encabezado_real(self):
        zonas = [{"codigo: pr-#": [40.0]}, {"codigo: pr-#": [41.5]}]
        self.assertEqual(_repetidas(zonas, 0, 2), {"codigo: pr-#"})

    def test_filas_de_tabla_que_continuan(self):
        varias_por_pagina = [{"analista de procesos": [130.0, 150.0, 170.0]}, {"analista de procesos": [80.0, 100.0]}]
        self.assertEqual(_repetidas(varias_por_pagina, 0, 2), set())
        otra_altura = [{"actividad numero #": [130.0]}, {"actividad numero #": [80.0]}]
        self.assertEqual(_repetidas(otra_altura, 0, 2), set())


@unittest.skipUnless(DEPENDENCIAS, "faltan python-docx o lxml")
class TextoEnZonaDeEncabezadoTest(unittest.TestCase):
    """Un texto junto al encabezado que solo aparece en una pagina no se descarta como encabezado."""

    def test_se_conserva_y_se_avisa(self):
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
            try:
                import pymupdf  # noqa: F401
            except ImportError:
                import fitz  # noqa: F401
        except ImportError:
            self.skipTest("faltan reportlab o PyMuPDF")
        with tempfile.TemporaryDirectory() as tmp:
            entrada, salida = Path(tmp) / "entrada", Path(tmp) / "salida"
            entrada.mkdir()
            c = canvas.Canvas(str(entrada / "Encabezado.pdf"), pagesize=letter)
            for pg in (1, 2):
                c.setFont("Helvetica", 9)
                c.drawString(72, 750, "Código: PR-ENC-001")
                if pg == 2:
                    c.drawString(330, 750, "Aviso exclusivo de la segunda hoja")
                c.setFont("Helvetica", 10)
                c.drawString(72, 650, f"Contenido de la página {pg} del procedimiento de prueba.")
                c.setFont("Helvetica", 8)
                c.drawString(72, 40, "Documento controlado - uso interno")
                c.showPage()
            c.save()
            with redirect_stdout(io.StringIO()):
                conversion_cli.main(["convertir", "--entrada", str(entrada), "--salida", str(salida),
                                     "--departamento", "Pruebas", "--tipo", "PRD", "--dep", "PRU",
                                     "--sin-verificacion-cruzada"])
            md = (salida / "PRD_PRU.md").read_text(encoding="utf-8")
            reporte = (salida / "REPORTE_PRD_PRU.md").read_text(encoding="utf-8")
        cuerpo = md[:md.index("Datos de encabezado y pie")]
        self.assertIn("Aviso exclusivo de la segunda hoja", cuerpo)
        self.assertIn("se conservaron como contenido", reporte)
        self.assertEqual(md.count("Código: PR-ENC-001"), 1)


class ContextoTextoTest(unittest.TestCase):
    def test_markdown_y_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            md, cs = Path(tmp) / "g.md", Path(tmp) / "k.csv"
            md.write_text("# Título\n\nUna línea\nque sigue.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n- item\n", encoding="utf-8")
            cs.write_text("id;nombre\nK-1;Tiempo\n", encoding="utf-8")
            d = ExtractorTexto().extraer(md)
            self.assertEqual([b["k"] for b in d.bloques], ["h", "p", "tabla", "li"])
            self.assertEqual(d.bloques[1]["texto"], "Una línea que sigue.")
            self.assertEqual(ExtractorTexto().extraer(cs).bloques[0]["filas"], [["id", "nombre"], ["K-1", "Tiempo"]])


class PuestosRolesTest(unittest.TestCase):
    def setUp(self):
        self.det = DetectorPuestos([Puesto("DES-COM-01", "Asistente Administrativo"),
                                    Puesto("DES-ALM-01", "Asistente Administrativo")])

    def test_homonimo_por_area_del_documento(self):
        self.assertEqual(self.det.detectar("El Asistente Administrativo archiva", "ALM")[0].puesto.codigo, "DES-ALM-01")
        m = self.det.detectar("El Asistente Administrativo archiva", "CAL")[0]
        self.assertEqual(m.tipo, "ambigua")
        self.assertEqual(len(m.candidatos), 2)

    def test_aprobacion_y_firma(self):
        self.assertEqual(rol("", "la aprobación del gerente", ""), "Aprueba")
        self.assertEqual(rol("", "registrar la firma y preparar la liberación", ""), "Mencionado")
        self.assertEqual(verbo("Revisa el documento"), "Aprueba o revisa")

    def test_verbo_mas_cercano(self):
        self.assertEqual(verbo("Compras solicita el material y lo entrega a Almacén", "Almacén"), "Entrega")

    def test_rol_libre_de_la_columna_responsable(self):
        self.assertEqual(rol_sin_descriptivo("comité de compras"), "comité de compras")
        self.assertEqual(rol_sin_descriptivo("—"), "")


def _construir(base):
    with redirect_stdout(io.StringIO()) as out:
        try:
            conversion_cli.main(["construir", "--entrada", str(base / "entrada"), "--contexto", str(base / "contexto"),
                                 "--sin-verificacion-cruzada", "--muestra-revision", "0"])
            codigo = 0
        except SystemExit as e:
            codigo = e.code
    return codigo, out.getvalue()


def _consultar(publicado, *argv):
    flujo = io.StringIO()
    with mock.patch.dict(os.environ, {"CORPUS_DATOS": str(publicado)}):
        codigo = consulta_cli.main(list(argv), uso="uso", flujo=flujo)
    return codigo, flujo.getvalue()


@unittest.skipUnless(DEPENDENCIAS, "faltan python-docx o lxml")
class CasosIntegracionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.tmp.name)
        generar(cls.base)
        cls.codigo, cls.salida = _construir(cls.base)
        cls.publicado = cls.base / "entrada" / "salida_corpus" / "copilot"
        with open(cls.publicado / ayuda.INDICE / "indice_corpus.csv", encoding="utf-8-sig") as f:
            filas = list(csv.DictReader(f, delimiter=";"))
        cls.por_archivo = {(r["codigo_departamento"], r["archivo_origen"]): r for r in filas}
        cls.inventario = (cls.publicado / ayuda.INDICE / "inventario_maestro.csv").read_text(encoding="utf-8-sig")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_construccion(self):
        self.assertEqual(self.codigo, 0, self.salida)
        self.assertIn("LISTO PARA PUBLICAR", self.salida)

    def test_inventario_sin_fantasmas(self):
        self.assertNotIn("~$", self.inventario)
        self.assertNotIn("(1)", self.inventario)

    def test_mismo_archivo_en_dos_areas(self):
        self.assertIn(("COM", "Asistente Administrativo.docx"), self.por_archivo)
        self.assertIn(("ALM", "Asistente Administrativo.docx"), self.por_archivo)

    def test_descriptivos(self):
        self.assertEqual(self.por_archivo[("COM", "Comprador.docx")]["reporta_a"], "Gerente de Compras")
        self.assertEqual(self.por_archivo[("ALM", "Asistente Administrativo.docx")]["reporta_a"], "Jefe de Almacén")
        r = self.por_archivo[("CAL", "Gerente de Control de Calidad.docx")]
        self.assertEqual((r["nombre_puesto"], r["reporta_a"]), ("Gerente de Control de Calidad", "Director General"))

    def test_diagrama_marcado(self):
        md = (self.publicado / ayuda.DOCUMENTOS / "PRD" / "PRD_COM.md").read_text(encoding="utf-8")
        self.assertIn("[DIAGRAMA: la sección «Diagrama de flujo» no se transcribe", md)
        self.assertNotIn("¿Aprobada?", md)

    def test_contexto_md_y_csv(self):
        md = "\n".join(p.read_text(encoding="utf-8") for p in (self.publicado / ayuda.CONTEXTO).glob("*_GEN.md"))
        self.assertIn("| RRHH | Recursos Humanos |", md)
        self.assertIn("| I-01 | Tiempo de entrega | 5 días |", md)

    def test_participacion(self):
        _, out = _consultar(self.publicado, "participacion", "Compras")
        self.assertIn("- Gerente de Calidad: PRD-COM-01 · posibles:", out)
        self.assertIn("- comité de compras: PRD-COM-01", out)
        self.assertIn("- coordinadores de logística: PRD-COM-01", out)
        self.assertIn("Asistente Administrativo (DES-COM-", out)
        self.assertNotIn("Asistente Administrativo (DES-ALM-", out)

    def test_homonimo_no_crea_relacion(self):
        _, out = _consultar(self.publicado, "relaciones", "Almacen", "Compras")
        self.assertNotIn("puesto Asistente Administrativo", out)

    def test_titulos_con_numeracion_automatica_de_word(self):
        md = (self.publicado / ayuda.DOCUMENTOS / "PRD" / "PRD_ALM.md").read_text(encoding="utf-8")
        self.assertIn("] 1. Objetivo", md)
        self.assertIn("] 2. Alcance", md)
        r = self.por_archivo[("ALM", "Control de inventario.docx")]
        self.assertEqual(r["campos_no_especificados"], "Responsabilidades")

    def test_ficha_muestra_actividades_principales(self):
        codigo = self.por_archivo[("COM", "Comprador.docx")]["codigo"]
        _, out = _consultar(self.publicado, "ficha", codigo)
        self.assertIn("### Actividades principales", out)
        self.assertIn("Cotizar con proveedores.", out)


@unittest.skipUnless(DEPENDENCIAS, "faltan python-docx o lxml")
class PDFTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            try:
                import pymupdf  # noqa: F401
            except ImportError:
                import fitz  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("PyMuPDF no instalado")
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        carpeta = generar_pdf(base)
        if carpeta is None:
            raise unittest.SkipTest("LibreOffice no disponible para generar los PDF")
        salida = base / "salida"
        with redirect_stdout(io.StringIO()):
            conversion_cli.main(["convertir", "--entrada", str(carpeta), "--salida", str(salida),
                                 "--departamento", "Pruebas", "--tipo", "PRD", "--dep", "PRU"])
        cls.md = "\n".join(p.read_text(encoding="utf-8") for p in salida.glob("PRD_PRU*.md"))
        cls.reporte = "\n".join(p.read_text(encoding="utf-8") for p in salida.glob("REPORTE_*.md"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_ligaduras_en_celdas(self):
        self.assertIn("eficiencia", self.md)
        self.assertIn("confidenciales", self.md)
        self.assertNotIn("Palabras que no están en el original", self.reporte)

    def test_diagrama_vectorial(self):
        self.assertTrue("[DIAGRAMA" in self.md or "posible diagrama vectorial" in self.reporte)

    def test_tabla_partida_entre_paginas(self):
        """Las 60 filas, en orden y en una sola tabla; nada termina en el bloque de encabezado y pie."""
        doc = self.md[self.md.index("] Tabla partida"):]
        doc = doc[:doc.index("\n---\n")]
        numeros = [int(l.split("|")[1]) for l in doc.splitlines()
                   if l.startswith("| ") and "Analista de Procesos" in l]
        self.assertEqual(numeros, list(range(1, 61)))
        self.assertEqual(doc.count("|---|---|---|"), 1)
        self.assertNotIn("Datos de encabezado y pie", doc)
        self.assertIn("### [PRD-PRU-", doc)
        self.assertNotIn("Desarrollo del proceso: [NO ESPECIFICADO]", doc)


if __name__ == "__main__":
    unittest.main()
