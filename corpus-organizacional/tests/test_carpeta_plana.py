"""Descriptivos sin carpeta de area (entrada/Descriptivos/archivo.pdf) y lista.txt opcional (v3.4)."""

import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tests import ayuda  # noqa: F401
from corpus_org.comun.archivos import escribir_csv
from corpus_org.comun.esquema import AREA_SIN_ASIGNAR, AVISO_ESCANEADO, COLUMNAS_INDICE
from corpus_org.conversion import cli as conversion_cli
from corpus_org.conversion.asignacion import asignar_archivos
from corpus_org.conversion.validacion import validar_publicacion
from corpus_org.conversion.inventario import actualizar_plantilla_areas, leer_base, parsear_lista

try:
    from tests.fixtures_casos import descriptivo
    DEPENDENCIAS = True
except ImportError:
    DEPENDENCIAS = False


def _lista(tmp, *rutas):
    p = Path(tmp) / "lista.txt"
    p.write_text("\n".join(rutas) + "\n", encoding="utf-8")
    return p


class ListaPlanaTest(unittest.TestCase):
    def test_area_desde_areas_csv_o_sin_asignar(self):
        with tempfile.TemporaryDirectory() as tmp:
            lista = _lista(tmp, r"C:\Corpus\entrada\Descriptivos\1. Analista de Compras.pdf",
                           r"C:\Corpus\entrada\Descriptivos\Jefe de Almacén.pdf")
            filas, ignoradas = parsear_lista(lista, {"1. analista de compras": "Compras"})
        self.assertEqual(ignoradas, [])
        self.assertEqual([(f["departamento"], f["sin_area"]) for f in filas],
                         [("Compras", False), (AREA_SIN_ASIGNAR, True)])

    def test_area_que_empieza_como_un_tipo(self):
        """Una carpeta de area llamada "Procesos ..." dentro de Descriptivos sigue siendo el area."""
        with tempfile.TemporaryDirectory() as tmp:
            filas, _ = parsear_lista(_lista(tmp, r"Descriptivos\Procesos Industriales\Operador.pdf"))
        self.assertEqual((filas[0]["tipo"], filas[0]["departamento"]), ("DES", "Procesos Industriales"))

    def test_copias_ocupan_una_fila_de_areas_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "areas.csv"
            # plantilla de una version anterior: con la copia y el original en filas separadas
            p.write_text("archivo;area\nJefe (1).pdf;Compras\nJefe.pdf;\nAnalista (2).pdf;\n", encoding="utf-8")
            filas = [{"archivo": n, "sin_area": True} for n in
                     ("Jefe.pdf", "Jefe (1).pdf", "Analista.pdf", "Analista (2).pdf", "Nuevo (1).pdf", "Nuevo.pdf")]
            agregados = actualizar_plantilla_areas(p, filas)
            texto = p.read_text(encoding="utf-8-sig")
        self.assertEqual(agregados, 1)
        self.assertEqual(texto.splitlines(), ["archivo;area", "Analista (2).pdf;", "Jefe (1).pdf;Compras", "Nuevo.pdf;"])

    def test_codigos_provisionales_no_se_conservan(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "inventario.csv"
            p.write_text("codigo;tipo;codigo_departamento;departamento;archivo\n"
                         f"DES-SAR-01;Descriptivo;SAR;{AREA_SIN_ASIGNAR};a.pdf\n"
                         "DES-COM-01;Descriptivo;COM;Compras;b.pdf\n", encoding="utf-8")
            base = leer_base(p)
        self.assertEqual(list(base.departamentos.values()), ["COM"])
        self.assertEqual(len(base.documentos), 1)


def _construir(entrada, salida):
    with redirect_stdout(io.StringIO()):
        try:
            conversion_cli.main(["construir", "--entrada", str(entrada), "--salida", str(salida),
                                 "--sin-verificacion-cruzada", "--muestra-revision", "0"])
            return 0
        except SystemExit as e:
            return e.code


def _inventario(salida):
    with open(salida / "control" / "inventario_maestro.csv", encoding="utf-8-sig", newline="") as f:
        return {r["archivo"]: (r["codigo"], r["estado_inventario"]) for r in csv.DictReader(f, delimiter=";")}


@unittest.skipUnless(DEPENDENCIAS, "faltan python-docx o lxml")
class ConstruirSinListaTest(unittest.TestCase):
    def test_flujo_completo(self):
        with tempfile.TemporaryDirectory() as tmp:
            entrada, salida = Path(tmp) / "entrada", Path(tmp) / "salida_corpus"
            carpeta = entrada / "Descriptivos"
            carpeta.mkdir(parents=True)
            for nombre, jefe in (("Comprador", "Gerente de Compras"), ("Almacenista", "Jefe de Almacén")):
                descriptivo(carpeta / f"{nombre}.docx", [("Nombre del puesto", nombre), ("Reporta a", jefe)],
                            ["Registrar movimientos."])

            # 1) sin lista.txt ni areas.csv: se arma la lista, se crea la plantilla y no se publica como listo
            self.assertEqual(_construir(entrada, salida), 2)
            plantilla = (entrada / "areas.csv").read_text(encoding="utf-8-sig")
            self.assertIn("Comprador.docx;", plantilla)
            self.assertEqual({c for c, _ in _inventario(salida).values()}, {"DES-SAR-01", "DES-SAR-02"})

            # 2) con las areas escritas: codigos definitivos y sin restos de los provisionales
            (entrada / "areas.csv").write_text("archivo;area\nComprador.docx;Compras\nAlmacenista.docx;Almacén\n",
                                               encoding="utf-8")
            self.assertEqual(_construir(entrada, salida), 0)
            self.assertEqual(_inventario(salida), {"Comprador.docx": ("DES-COM-01", "ACTIVO"),
                                                   "Almacenista.docx": ("DES-ALM-01", "ACTIVO")})

            # 3) un archivo nuevo se agrega a la lista sola y a la plantilla, sin cambiar los codigos
            descriptivo(carpeta / "Cotizador.docx", [("Nombre del puesto", "Cotizador")], ["Cotizar."])
            self.assertEqual(_construir(entrada, salida), 2)
            inv = _inventario(salida)
            self.assertEqual(inv["Comprador.docx"], ("DES-COM-01", "ACTIVO"))
            self.assertEqual(inv["Cotizador.docx"], ("DES-SAR-01", "ACTIVO"))
            self.assertIn("Cotizador.docx;", (entrada / "areas.csv").read_text(encoding="utf-8-sig"))


class CopiasYEscaneadosTest(unittest.TestCase):
    def test_se_convierte_el_original_y_no_la_copia(self):
        fila = {"codigo": "DES-SAR-01", "tipo": "Descriptivo", "codigo_departamento": "SAR", "archivo": "Jefe.pdf",
                "ruta_original": r"C:\e\Descriptivos\Jefe.pdf"}
        for orden in ((Path("e/Descriptivos/Jefe (1).pdf"), Path("e/Descriptivos/Jefe.pdf")),
                      (Path("e/Descriptivos/Jefe.pdf"), Path("e/Descriptivos/Jefe (1).pdf"))):
            a = asignar_archivos([fila], list(orden))
            self.assertEqual(a.asignados[("DES", "SAR")]["DES-SAR-01"].name, "Jefe.pdf")

    def test_original_con_espacios_dobles(self):
        """El inventario (CSV) guarda «5. Soporte .pdf» aunque el archivo se llame «5.  Soporte .pdf»."""
        fila = {"codigo": "DES-TIN-07", "tipo": "Descriptivo", "codigo_departamento": "TIN",
                "archivo": "5. Soporte Técnico .pdf", "ruta_original": r"C:\e\Descriptivos\5. Soporte Técnico .pdf"}
        copia, original = Path("e/Descriptivos/5.  Soporte Técnico  (2).pdf"), Path("e/Descriptivos/5.  Soporte Técnico .pdf")
        for orden in ((copia, original), (original, copia)):
            a = asignar_archivos([fila], list(orden))
            self.assertEqual(a.asignados[("DES", "TIN")]["DES-TIN-07"], original)

    def test_escaneado_sin_texto_es_problema(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = Path(tmp)
            (pub / ayuda.INDICE).mkdir(parents=True)
            (pub / ayuda.DOCUMENTOS / "DES").mkdir(parents=True)
            filas = [{"codigo": "DES-COM-01", "cobertura": "100.0 %", "avisos_estructura": "1",
                      "detalle_avisos": AVISO_ESCANEADO + ": 1, 2"},
                     {"codigo": "DES-COM-02", "cobertura": "100.0 %", "avisos_estructura": "0"}]
            escribir_csv(pub / ayuda.INDICE / "indice_corpus.csv", COLUMNAS_INDICE, filas)
            (pub / ayuda.DOCUMENTOS / "DES" / "DES_COM.md").write_text("## [DES-COM-01] A\n\n## [DES-COM-02] B\n", encoding="utf-8")
            v = validar_publicacion(pub, muestra=0)
        self.assertEqual(v.estado, "REQUIERE REVISIÓN")
        self.assertTrue(any("escaneadas" in x and "DES-COM-01" in x and "DES-COM-02" not in x for x in v.problemas))


if __name__ == "__main__":
    unittest.main()
