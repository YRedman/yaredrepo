"""Pruebas unitarias de la conversion (sin archivos reales)."""

import tempfile
import unittest
from pathlib import Path

from tests import ayuda  # noqa: F401
from corpus_org.comun.esquema import estado_no_publicable
from corpus_org.conversion.analisis import analizar
from corpus_org.conversion.analisis.citas import RE_CODIGO_DOC
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
        self.assertEqual(a.actividades, ["Aprobar la orden (Responsable: Gerente)"])

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


class TemporalesYCsvTest(unittest.TestCase):
    def test_csv_con_saltos_r_sueltos_se_lee(self):
        from corpus_org.conversion.extractores.texto import ExtractorTexto
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "kpis.csv"
            ruta.write_bytes("area;indicador;meta\rVentas;Margen;10\rTI;Disponibilidad;99".encode("utf-8"))
            d = ExtractorTexto().extraer(ruta)
        self.assertEqual(d.bloques[0]["filas"][2], ["TI", "Disponibilidad", "99"])

    def test_huellas_ignoran_el_bloqueo_de_excel(self):
        from corpus_org.conversion.publicacion import escribir_huellas
        from corpus_org.comun.estructura import archivos_de_huellas, rutas_publicadas
        with tempfile.TemporaryDirectory() as tmp:
            r = rutas_publicadas(Path(tmp))
            r.matriz.mkdir(parents=True)
            (r.matriz / "matriz_organizacional.xlsx").write_bytes(b"x")
            (r.matriz / "~$matriz_organizacional.xlsx").write_bytes(b"lock")
            nombres = [q.name for q in archivos_de_huellas(Path(tmp))]
            escribir_huellas(Path(tmp))
            huellas = (r.indice / "huellas.sha256").read_text(encoding="utf-8")
        self.assertEqual(nombres, ["matriz_organizacional.xlsx"])
        self.assertNotIn("~$", huellas)


class CopiasDelContextoTest(unittest.TestCase):
    def test_copia_con_sufijo_se_descarta_y_se_avisa_si_difiere(self):
        from corpus_org.conversion.inventario import quitar_copias_contexto
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            archivos = []
            for nombre, datos in (("Iniciativas 2026.csv", b"a;b\n1;2"), ("Iniciativas 2026 (1).csv", b"a;b\n1;3"),
                                  ("Mapa.pdf", b"x"), ("Mapa (1).pdf", b"x"), ("Datos.csv", b"1"), ("Datos.md", b"1")):
                (r / nombre).write_bytes(datos)
                archivos.append(r / nombre)
            usados, avisos = quitar_copias_contexto(archivos)
        self.assertEqual(sorted(p.name for p in usados), ["Datos.csv", "Datos.md", "Iniciativas 2026.csv", "Mapa.pdf"])
        self.assertEqual(len(avisos), 2)
        self.assertTrue(any("distinto" in a for a in avisos if "Iniciativas" in a))
        self.assertFalse(any("distinto" in a for a in avisos if "Mapa" in a))


class RepetidosTest(unittest.TestCase):
    def test_un_parrafo_que_vuelve_en_otra_pagina_no_es_un_duplicado_de_conversion(self):
        from corpus_org.conversion.analisis.estructura import avisos_de_estructura
        frase = "Este documento es confidencial y no puede reproducirse sin autorizacion."
        otras = [{"k": "p", "texto": f"Contenido distinto de la diapositiva numero {k} del documento.", "pagina": k}
                 for k in range(1, 6)]
        en_paginas = [{"k": "p", "texto": frase, "pagina": 0}] + otras + [{"k": "p", "texto": frase, "pagina": 7}]
        self.assertFalse(any("repetidos" in a for a in avisos_de_estructura(en_paginas, 0)))
        misma_pagina = [{"k": "p", "texto": frase, "pagina": 2}, {"k": "p", "texto": frase, "pagina": 2}]
        self.assertTrue(any("repetidos" in a for a in avisos_de_estructura(misma_pagina, 0)))
        seguidos = [{"k": "p", "texto": frase, "pagina": 2}, {"k": "p", "texto": frase, "pagina": 3}]
        self.assertTrue(any("repetidos" in a for a in avisos_de_estructura(seguidos, 0)))

    def test_el_segundo_motor_no_marca_fragmentos_de_palabras_enteras(self):
        from corpus_org.conversion.verificacion import _fragmentos
        partes = _fragmentos({"matriz", "comerciales"})
        self.assertIn("atriz", partes)
        self.assertIn("ciales", partes)
        self.assertNotIn("zzz", partes)


if __name__ == "__main__":
    unittest.main()
