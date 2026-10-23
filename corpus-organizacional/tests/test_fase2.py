"""Pruebas de la fase 2 (v3.3): avisos de estructura, revision visual, huellas, codigos estables,
areas_extra.csv, KPIs, menciones no resueltas, resumen por puesto y briefing."""

import csv
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tests import ayuda  # noqa: F401
from corpus_org.comun.texto import numeros
from corpus_org.consulta import cli as consulta_cli
from corpus_org.consulta.areas import RE_SIGLA
from corpus_org.consulta.entidades import leer_areas_extra, quitar_exclusiones
from corpus_org.consulta.integridad import verificar_huellas
from corpus_org.consulta.roles import verbo
from corpus_org.conversion import cli as conversion_cli
from corpus_org.conversion.analisis import analizar
from corpus_org.conversion.analisis.estructura import avisos_de_estructura
from corpus_org.conversion.extractores.pdf.continuas import unir_tablas_continuas
from corpus_org.conversion.inventario import InventarioBase, construir_inventario, leer_base
from corpus_org.conversion.modelo import DocumentoExtraido, bloque_h
from corpus_org.conversion.publicacion import escribir_huellas
from corpus_org.conversion.validacion import muestra_reproducible
from corpus_org.conversion.render import render_documento
from corpus_org.conversion.verificacion import verificar

try:
    import docx  # noqa: F401
    import lxml  # noqa: F401
    from tests.fixtures_casos import generar
    DEPENDENCIAS = True
except ImportError:
    DEPENDENCIAS = False


class NumerosTest(unittest.TestCase):
    def test_numeros_completos(self):
        self.assertEqual(numeros("RD$ 45.000,00 y 352,600,000 y 1.5 y 7"),
                         {"45.000,00": 1, "352,600,000": 1, "1.5": 1})

    def test_numero_truncado_genera_aviso(self):
        d = DocumentoExtraido(bloques=[bloque_h(1, "Objetivo"), {"k": "p", "texto": "Pagar 45.000 pesos."}])
        d.crudo.update(["objetivo", "pagar", "45", "000", "00", "pesos"])
        d.numeros.update({"45.000,00": 1})
        bloques, a = analizar(d, "P")
        _, cuerpo = render_documento(d, bloques, a, "PRD-PRU-01", "PRD", "Pruebas", "x.docx", "x")
        v = verificar(d, bloques, a, cuerpo)
        self.assertEqual(dict(v.numeros_faltan), {"45.000,00": 1})


class AvisosEstructuraTest(unittest.TestCase):
    def test_filas_sin_primera_celda(self):
        filas = [["No.", "Actividad", "Responsable"]] + [[str(i), f"Paso {i}", "Jefe"] for i in range(1, 6)]
        filas.insert(3, ["", "continuación del paso 2", ""])
        avisos = avisos_de_estructura([{"k": "tabla", "filas": filas, "pagina": 1}], 0)
        self.assertEqual(avisos, ["p.2: 1 filas de tabla sin primera celda (posible fila partida)"])

    def test_parrafos_repetidos_e_imagenes(self):
        p = {"k": "p", "texto": "Este párrafo largo aparece dos veces por un error de conversión del original."}
        avisos = avisos_de_estructura([p, dict(p)], 3)
        self.assertTrue(any("párrafos repetidos" in a for a in avisos))
        self.assertTrue(any("sobre todo en imágenes" in a for a in avisos))

    def test_tabla_partida_con_lineas_sueltas(self):
        def tabla(filas):
            return {"tipo": "tabla", "filas": filas, "xs": [80, 200], "pagina": 0}
        suelta = {"tipo": "fila", "texto": "continuación de la fila", "bold": False, "pagina": 1}
        items = [(0, 100, 80, tabla([["No.", "Actividad"], ["1", "Uno"]])), (1, 60, 80, suelta),
                 (1, 80, 80, tabla([["2", "Dos"], ["3", "Tres"]]))]
        d = DocumentoExtraido()
        unir_tablas_continuas(items, d)
        self.assertEqual([it[3]["tipo"] for it in items], ["tabla", "fila"])
        self.assertEqual([f[0] for f in items[0][3]["filas"]], ["No.", "1", "2", "3"])
        self.assertIn("líneas sueltas en medio", d.avisos[0])


class ActividadesTest(unittest.TestCase):
    def test_vinetas_si_el_desarrollo_no_tiene_tabla(self):
        d = DocumentoExtraido(bloques=[bloque_h(1, "Políticas"), {"k": "li", "marcador": "-", "texto": "No comprar sin orden"},
                                       bloque_h(1, "Desarrollo del proceso"),
                                       {"k": "li", "marcador": "-", "texto": "Solicitar cotización"}])
        self.assertEqual(analizar(d, "P")[1].actividades, ["Solicitar cotización"])


class MuestraTest(unittest.TestCase):
    def test_reproducible(self):
        cods = [f"DES-COM-{i:02d}" for i in range(1, 21)]
        self.assertEqual(len(muestra_reproducible(cods, 0.10)), 2)
        self.assertEqual(muestra_reproducible(cods, 0.10), muestra_reproducible(list(reversed(cods)), 0.10))
        self.assertEqual(muestra_reproducible(cods, 0), [])


class CodigosEstablesTest(unittest.TestCase):
    def filas(self, *archivos):
        return [{"tipo": "DES", "departamento": "Compras", "archivo": a, "ruta": f"C:\\D\\Compras\\{a}"} for a in archivos]

    def test_base_conserva_codigos(self):
        primero = construir_inventario(self.filas("Analista.docx", "Comprador.docx", "Gerente.docx"), [])
        codigos = {f["archivo"]: f["codigo"] for f in primero.documentos}
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "base.csv"
            with open(p, "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(primero.documentos[0]), delimiter=";")
                w.writeheader()
                w.writerows(primero.documentos)
            base = leer_base(p)
        # se retira 'Comprador' y se agrega 'Auxiliar' (alfabeticamente primero)
        segundo = construir_inventario(self.filas("Analista.docx", "Auxiliar.docx", "Gerente.docx"), [], base=base)
        por_archivo = {f["archivo"]: f for f in segundo.documentos}
        self.assertEqual(por_archivo["Analista.docx"]["codigo"], codigos["Analista.docx"])
        self.assertEqual(por_archivo["Gerente.docx"]["codigo"], codigos["Gerente.docx"])
        self.assertEqual(por_archivo["Auxiliar.docx"]["codigo"], "DES-COM-04")
        self.assertEqual(por_archivo["Comprador.docx"]["estado_inventario"], "RETIRADO")
        self.assertEqual(por_archivo["Comprador.docx"]["codigo"], codigos["Comprador.docx"])

    def test_sin_base_numera_en_orden(self):
        inv = construir_inventario(self.filas("B.docx", "A.docx"), [], base=InventarioBase())
        self.assertEqual([(f["archivo"], f["codigo"]) for f in inv.documentos],
                         [("A.docx", "DES-COM-01"), ("B.docx", "DES-COM-02")])


class EntidadesTest(unittest.TestCase):
    def test_areas_extra_y_exclusiones(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "areas_extra.csv"
            p.write_text("nombre;alias;tipo\nFinanzas;Gerencia Financiera;interna\nARS X;;externa\nSeguridad Social;;excluir\n",
                         encoding="utf-8")
            extra, exclusiones = leer_areas_extra(p)
        self.assertEqual([(e.nombre, e.tipo) for e in extra], [("Finanzas", "interna"), ("ARS X", "externa")])
        self.assertIn("seguridad social", exclusiones)
        self.assertNotIn("Seguridad", quitar_exclusiones("Pagar la Seguridad Social", exclusiones))
        self.assertIn("Seguridad", quitar_exclusiones("Avisar a Seguridad", exclusiones))

    def test_sigla_sin_digitos(self):
        for sigla in ("RRHH", "TI", "R.H.", "I+D"):
            self.assertTrue(RE_SIGLA.match(sigla), sigla)
        for no in ("K-01", "PR-001", "Responsable", "A"):
            self.assertFalse(RE_SIGLA.match(no), no)


class VerboEnTablaTest(unittest.TestCase):
    def test_verbo_de_la_celda_de_la_mencion(self):
        fila = "| 4 | Entregar la mercancía a Almacén | coordinadores de logística |"
        self.assertEqual(verbo(fila, "Almacén"), "Entrega")
        self.assertEqual(verbo("| 2 | Almacén | Revisar el pedido |", "Almacén"), "Aprueba o revisa")


class HuellasTest(unittest.TestCase):
    def test_detecta_modificaciones(self):
        with tempfile.TemporaryDirectory() as tmp:
            publicado = Path(tmp)
            contexto = publicado / "fuente-corpus"
            datos, docs = publicado / ayuda.INDICE, publicado / ayuda.DOCUMENTOS / "DES"
            datos.mkdir(parents=True)
            docs.mkdir(parents=True)
            (docs / "DES_COM.md").write_text("original", encoding="utf-8")
            (datos / "indice_corpus.csv").write_text("codigo\n", encoding="utf-8")
            escribir_huellas(publicado)
            self.assertTrue(verificar_huellas(contexto).correcto)
            (docs / "DES_COM.md").write_text("editado a mano", encoding="utf-8")
            (datos / "indice_corpus.csv").unlink()
            r = verificar_huellas(contexto)
        self.assertEqual((r.modificados, r.faltantes),
                         (["fuente-corpus/documentos/DES/DES_COM.md"], ["fuente-corpus/indice/indice_corpus.csv"]))


def _construir(base, *extra):
    with redirect_stdout(io.StringIO()) as out:
        try:
            conversion_cli.main(["construir", "--entrada", str(base / "entrada"), "--contexto", str(base / "contexto"),
                                 "--sin-verificacion-cruzada", *extra])
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
class Fase2IntegracionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.tmp.name)
        generar(cls.base)
        cls.raiz = cls.base / "entrada" / "salida_corpus"
        cls.publicado = cls.raiz / "copilot"
        cls.codigo, cls.salida = _construir(cls.base)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_1_revision_visual_y_huellas(self):
        """Primero PENDIENTE DE REVISIÓN VISUAL (3); con los códigos revisados, LISTO (0)."""
        self.assertEqual(self.codigo, 3, self.salida)
        with open(self.raiz / "control" / "revision_visual.csv", encoding="utf-8-sig") as f:
            pendientes = [r["codigo"] for r in csv.DictReader(f, delimiter=";")]
        self.assertTrue(pendientes)
        (self.base / "entrada" / "revision_visual_ok.txt").write_text(
            "# revisados\n" + "\n".join(pendientes) + "\n", encoding="utf-8")
        codigo, salida = _construir(self.base)
        self.assertEqual(codigo, 0, salida)
        self.assertIn("LISTO PARA PUBLICAR", salida)
        _, out = _consultar(self.publicado, "verificar")
        self.assertIn("Huellas SHA-256: todos los archivos coinciden", out)
        self.assertIn("corpus completo: sí", out)

    def test_2_datos_de_contexto_publicados(self):
        self.assertTrue((self.publicado / ayuda.CONTEXTO / "kpis.csv").is_file())
        self.assertTrue((self.publicado / ayuda.INDICE / "areas_extra.csv").is_file())
        contexto = "\n".join(p.read_text(encoding="utf-8") for p in (self.publicado / ayuda.CONTEXTO).glob("*_GEN.md"))
        self.assertTrue(contexto)
        self.assertFalse((self.publicado / ayuda.CONTEXTO / "KPI_GEN.md").exists())
        self.assertNotIn("areas_extra", contexto)

    def test_3_kpis(self):
        _, out = _consultar(self.publicado, "kpis", "--relacionar")
        self.assertIn("INDICADORES · 2 de 2", out)
        self.assertIn("| K-02 | Almacén | Mercancía rechazada | 2 | sin medición |", out)
        self.assertIn("Sin documentos relacionados: K-02", out)
        _, out = _consultar(self.publicado, "kpis", "--sin-medicion")
        self.assertIn("INDICADORES · 1 de 2", out)

    def test_4_relaciones_no_resueltas_y_exclusiones(self):
        _, out = _consultar(self.publicado, "relaciones", "Compras")
        self.assertIn("| Finanzas | sin documentos (interna) |", out)
        self.assertIn("| Dirección de Logística | unidad no identificada |", out)
        self.assertIn("| Gerente de Calidad | puesto ambiguo:", out)
        _, par = _consultar(self.publicado, "relaciones", "Compras", "Calidad")
        self.assertNotIn("Calidad de Vida", par)
        _, out = _consultar(self.publicado, "area", "Tesoreria")
        self.assertIn("Áreas o entidades mencionadas sin documentos propios: Finanzas", out)

    def test_5_participacion_resumen_y_detalle(self):
        _, out = _consultar(self.publicado, "participacion", "Compras", "--detalle", "1")
        self.assertIn("Resumen por puesto (completo", out)
        self.assertIn("Detalle: filas 1–1 de", out)
        self.assertIn("(corpus completo)", out)

    def test_6_briefing(self):
        _, out = _consultar(self.publicado, "briefing", "Compras")
        self.assertIn("# Briefing: Compras (COM) · parte 1 de 1", out)
        self.assertTrue(out.startswith("Partes: 1\nCobertura: DES 3/3 · PRD 1/1 · PRO 0/0 · POL 0/0 · GEN pertinentes: 0\n"))
        for seccion in ("## Puestos (DES)", "## Procedimientos (PRD)", "## Relaciones", "## No documentado",
                        "## Indicadores relacionados"):
            self.assertIn(seccion, out)
        codigo, _ = _consultar(self.publicado, "briefing", "Compras", "--parte", "2")
        self.assertEqual(codigo, 2)

    def test_7_huellas_detectan_cambios_y_codigos_estables(self):
        (self.publicado / ayuda.DOCUMENTOS / "DES" / "DES_COM.md").write_text("editado", encoding="utf-8")
        _, out = _consultar(self.publicado, "verificar")
        self.assertIn("Archivos modificados después de la conversión: fuente-corpus/documentos/DES/DES_COM.md", out)
        # retirar un documento y volver a construir: los demás conservan su código
        antes = self._inventario()
        lista = self.base / "entrada" / "lista.txt"
        lineas = [l for l in lista.read_text(encoding="utf-8").splitlines() if "Comprador" not in l]
        lista.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        (self.base / "entrada" / "Descriptivos" / "Compras" / "Comprador.docx").unlink()
        _construir(self.base, "--muestra-revision", "0")
        despues = self._inventario()
        retirado = antes[("COM", "Comprador.docx")]
        self.assertEqual(despues[("COM", "Comprador.docx")], (retirado[0], "RETIRADO"))
        for clave, (codigo, _estado) in antes.items():
            self.assertEqual(despues[clave][0], codigo, clave)
        _, out = _consultar(self.publicado, "verificar")
        self.assertIn(f"códigos retirados del inventario (reservados): {retirado[0]}", out)

    def _inventario(self):
        with open(self.publicado / ayuda.INDICE / "inventario_maestro.csv", encoding="utf-8-sig") as f:
            return {(r["codigo_departamento"], r["archivo"]): (r["codigo"], r["estado_inventario"])
                    for r in csv.DictReader(f, delimiter=";")}


if __name__ == "__main__":
    unittest.main()
