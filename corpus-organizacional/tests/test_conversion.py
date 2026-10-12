"""Pruebas unitarias de la conversion (sin archivos reales)."""

import unittest

from tests import ayuda  # noqa: F401
from corpus_org.comun.esquema import estado_no_publicable
from corpus_org.conversion.analisis import RE_CODIGO_DOC, analizar
from corpus_org.conversion.metadatos import extraer_metadatos
from corpus_org.conversion.modelo import DocumentoExtraido, bloque_h


def p(texto):
    return {"k": "p", "texto": texto}


def li(texto):
    return {"k": "li", "marcador": "-", "texto": texto, "nivel": 0}


class MetadatosTest(unittest.TestCase):
    def test_valores_con_etiqueta_en_una_linea(self):
        m = extraer_metadatos(["Código: PR-COM-001 Versión: 3 Estado: Vigente Propietario: Gerente de Compras"], [])
        self.assertEqual((m.codigo_interno, m.version, m.estado_documental, m.propietario),
                         ("PR-COM-001", "3", "Vigente", "Gerente de Compras"))

    def test_no_toma_valores_del_texto_corrido(self):
        bloques = [p("Controlar el inventario. Estado de cuenta revisado mensualmente."),
                   p("Revisión de la solicitud por el área."),
                   p("Responsable de mantener el registro de proveedores.")]
        m = extraer_metadatos([], bloques)
        self.assertEqual((m.estado_documental, m.version, m.responsable), ("", "", ""))

    def test_no_se_extiende_al_titulo_siguiente(self):
        m = extraer_metadatos(["Código: PR-COM-002 Estado: Obsoleto"], [bloque_h(1, "Objetivo"), p("Atender")])
        self.assertEqual(m.estado_documental, "Obsoleto")

    def test_separadores_de_pdf_y_tablas(self):
        m = extraer_metadatos(["Código: PR-ALM-001   Versión: 1   Página 1 de 2"],
                              [{"k": "tabla", "filas": [["Estado", "No vigente"], ["Proceso:", "Abastecimiento"]]}])
        self.assertEqual((m.version, m.estado_documental, m.proceso), ("1", "No vigente", "Abastecimiento"))

    def test_version_sin_dos_puntos_requiere_numero(self):
        self.assertEqual(extraer_metadatos(["Versión 02"], []).version, "02")
        self.assertEqual(extraer_metadatos(["Revisión anual del proceso"], []).version, "")


class EstadoTest(unittest.TestCase):
    def test_estados(self):
        for e in ("Obsoleto", "obsoleto.", "No vigente desde 2023", "BORRADOR"):
            self.assertTrue(estado_no_publicable(e), e)
        for e in ("", "Vigente", "Vigente Obsoleto"):
            self.assertFalse(estado_no_publicable(e), e)


class AnalisisTest(unittest.TestCase):
    def _procedimiento(self):
        d = DocumentoExtraido()
        d.encabezado = ["Código: PR-COM-001"]
        d.bloques = [
            bloque_h(1, "Alcance"), li("Compras nacionales"),
            bloque_h(1, "Desarrollo del proceso"), li("Registrar la solicitud"),
            {"k": "tabla", "filas": [["No.", "Actividad", "Responsable"], ["1", "Aprobar la orden", "Gerente"]]},
            bloque_h(1, "Referencias"), p("PR-ALM-001, ISO-9001, COVID-19 y NOM-035-STPS-2018"),
            bloque_h(1, "Control de cambios"), p("Versión 1 inicial"),
        ]
        return d

    def test_actividades_solo_del_desarrollo(self):
        _, a = analizar(self._procedimiento(), "P")
        self.assertEqual(a.actividades, ["Registrar la solicitud", "Aprobar la orden"])

    def test_codigos_citados_sin_normas_ni_nombres(self):
        _, a = analizar(self._procedimiento(), "P")
        self.assertEqual(a.codigos_citados, ["NOM-035-STPS-2018", "PR-ALM-001"])
        self.assertIsNone(RE_CODIGO_DOC.search("COVID-19"))

    def test_secciones_excluidas(self):
        bloques, a = analizar(self._procedimiento(), "P")
        self.assertEqual(a.secciones_excluidas, ["Control de cambios"])
        self.assertNotIn("Versión 1 inicial", [b.get("texto") for b in bloques])

    def test_no_modifica_el_documento(self):
        d = self._procedimiento()
        n = len(d.bloques)
        analizar(d, "P")
        self.assertEqual(len(d.bloques), n)

    def test_contexto_no_lee_metadatos_del_cuerpo(self):
        d = DocumentoExtraido(bloques=[{"k": "tabla", "filas": [["Responsable", "Compras"]]}])
        _, a = analizar(d, "C")
        self.assertEqual(a.metadatos.responsable, "")


if __name__ == "__main__":
    unittest.main()
