"""Cadena documental (que documento cita a cual) y lectura de Word: cuadros con tablas, ecuaciones y filas partidas."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from tests import ayuda  # noqa: F401

from corpus_org.consulta.cadena import calcular_enlaces, faltantes, tipo_de_codigo_cliente, vecinos

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _meta():
    return {
        "POL-ALM-01": {"codigo_interno": "XYZ-ALMA-RD-POL-001",
                       "codigos_citados": "ALMA-RD-PRO-011, DIST-RD-FOR-036, XYZ-ALMA-RD-POL-001"},
        "PRD-ALM-03": {"codigo_interno": "XYZ-ALMA-RD-PRO-011", "codigos_citados": "ALM-FOR-012, XYZ-ALMA-RD-POL-001"},
        "PRD-LOG-01": {"codigo_interno": "XYZ-LOGI-PRO-001", "codigos_citados": "XYZ-ALMA-RD-PRO-011, ALM-FOR-012"},
        "DES-GCO-01": {"codigo_interno": "", "codigos_citados": ""},
    }


class CadenaTest(unittest.TestCase):
    def test_un_codigo_se_une_si_es_igual_o_es_el_final_del_codigo_interno(self):
        enlaces = calcular_enlaces(_meta())
        unidos = {(e.origen, e.destino, e.via) for e in enlaces if e.resuelto}
        self.assertEqual(unidos, {("POL-ALM-01", "PRD-ALM-03", "final del código"),
                                  ("PRD-ALM-03", "POL-ALM-01", "exacto"),
                                  ("PRD-LOG-01", "PRD-ALM-03", "exacto")})
        # el documento no se cita a si mismo (su propio codigo en el pie de pagina)
        self.assertFalse(any(e.origen == "POL-ALM-01" and e.citado == "XYZ-ALMA-RD-POL-001" for e in enlaces))

    def test_vecinos_hacia_delante_y_hacia_atras_con_profundidad(self):
        enlaces = calcular_enlaces(_meta())
        self.assertEqual(vecinos(enlaces, "PRD-LOG-01", "sale", 1), {"PRD-ALM-03": 1})
        self.assertEqual(vecinos(enlaces, "PRD-LOG-01", "sale", 2), {"PRD-ALM-03": 1, "POL-ALM-01": 2})
        self.assertEqual(vecinos(enlaces, "PRD-ALM-03", "entra", 1), {"POL-ALM-01": 1, "PRD-LOG-01": 1})

    def test_los_codigos_sin_documento_son_los_que_faltan_en_el_corpus(self):
        falta = faltantes(calcular_enlaces(_meta()))
        self.assertEqual(list(falta), ["ALM-FOR-012", "DIST-RD-FOR-036"])
        self.assertEqual(falta["ALM-FOR-012"], {"PRD-ALM-03", "PRD-LOG-01"})
        self.assertEqual([tipo_de_codigo_cliente(c) for c in ("COM-FOR-001", "ALM-PRO-002", "BIOM-RD-PRT-007", "X-Y-1")],
                         ["Formato", "Procedimiento", "Protocolo", ""])

    def test_un_final_ambiguo_no_se_une(self):
        meta = {"A": {"codigo_interno": "AA-ALMA-PRO-001", "codigos_citados": ""},
                "B": {"codigo_interno": "BB-ALMA-PRO-001", "codigos_citados": ""},
                "C": {"codigo_interno": "", "codigos_citados": "ALMA-PRO-001"}}
        self.assertEqual([(e.destino, e.resuelto) for e in calcular_enlaces(meta)], [("", False)])


def _docx(ruta, cuerpo):
    contenido = (f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}" '
                 'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
                 'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
                 f'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"><w:body>{cuerpo}</w:body></w:document>')
    tipos = ('<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="xml" ContentType="application/xml"/><Default Extension="rels" '
             'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.'
             'wordprocessingml.document.main+xml"/></Types>')
    rels = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'officeDocument" Target="word/document.xml"/></Relationships>')
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("[Content_Types].xml", tipos)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", contenido)


def _p(texto):
    return f'<w:p><w:r><w:t xml:space="preserve">{texto}</w:t></w:r></w:p>'


def _tabla(filas):
    return "<w:tbl>" + "".join("<w:tr>" + "".join(f"<w:tc>{_p(c) if c else '<w:p/>'}</w:tc>" for c in f) + "</w:tr>"
                               for f in filas) + "</w:tbl>"


class WordTest(unittest.TestCase):
    def _leer(self, cuerpo):
        from corpus_org.conversion.extractores import extractor_para
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "doc.docx"
            _docx(ruta, cuerpo)
            return extractor_para(ruta).extraer(ruta)

    def test_el_texto_de_un_cuadro_con_tabla_y_el_de_una_ecuacion_se_leen_y_se_verifican(self):
        caja = ('<w:p><w:r><mc:AlternateContent><mc:Choice><w:drawing><wps:wsp><wps:txbx><w:txbxContent>'
                + _tabla([["No cumple", "Entonces elaborar el protocolo"]]) + _p("Si aplica validación")
                + '</w:txbxContent></wps:txbx></wps:wsp></w:drawing></mc:Choice></mc:AlternateContent></w:r></w:p>')
        ecuacion = ('<w:p><m:oMath><m:r><m:t>Bolsas Facturadas menos Bolsas Prescritas</m:t></m:r></m:oMath></w:p>')
        d = self._leer(_p("Inicio del flujo") + caja + ecuacion)
        textos = " ".join(b.get("texto", "") + " ".join(c for f in b.get("filas", []) for c in f) for b in d.bloques)
        for esperado in ("No cumple", "Entonces elaborar el protocolo", "Si aplica validación", "Bolsas Facturadas"):
            self.assertIn(esperado, textos)
        for palabra in ("cumple", "protocolo", "facturadas", "prescritas"):
            self.assertIn(palabra, d.crudo)           # la lectura independiente tambien ve el texto de la ecuacion

    def test_una_frase_partida_en_dos_filas_se_une_pero_una_fila_nueva_no(self):
        filas = [["Secciones", "Requisitos"], ["Título", "Debe ser claro."], ["Procedimiento", "Describir los pasos y los"],
                 ["", "resultados obtenidos."], ["Fin del proceso", ""], ["", "Nueva fila que empieza en mayúscula"]]
        d = self._leer(_tabla(filas))
        tabla = next(b["filas"] for b in d.bloques if b["k"] == "tabla")
        self.assertIn(["Procedimiento", "Describir los pasos y los resultados obtenidos."], tabla)
        self.assertIn(["", "Nueva fila que empieza en mayúscula"], tabla)
        self.assertEqual(len(tabla), 5)


class AvisosRepetidosTest(unittest.TestCase):
    def test_la_misma_funcion_bajo_dos_roles_no_es_un_duplicado_pero_dos_parrafos_seguidos_si(self):
        from corpus_org.conversion.analisis import avisos_de_estructura
        frase = "Aprobar la documentación requerida para las licitaciones externas."
        dos_roles = [{"k": "p", "texto": "Director General:"}, {"k": "li", "texto": frase},
                     {"k": "p", "texto": "Director Comercial"}, {"k": "li", "texto": frase}]
        self.assertEqual(avisos_de_estructura(dos_roles, 0), [])
        seguidos = [{"k": "p", "texto": frase}, {"k": "p", "texto": "Otro párrafo sin relación alguna."},
                    {"k": "p", "texto": frase}]
        self.assertTrue(any("repetidos" in a for a in avisos_de_estructura(seguidos, 0)))

    def test_fin_del_proceso_no_es_una_fila_partida(self):
        from corpus_org.conversion.analisis import avisos_de_estructura
        filas = [["N.º", "Actividad"]] + [[str(k), f"Paso {k}"] for k in range(1, 8)] + [["", "Fin del proceso"]]
        self.assertEqual(avisos_de_estructura([{"k": "tabla", "filas": filas}], 0), [])


if __name__ == "__main__":
    unittest.main()


class ParaleloTest(unittest.TestCase):
    def test_convertir_en_paralelo_da_lo_mismo_que_uno_a_uno(self):
        from corpus_org.conversion.lote import Grupo, OpcionesConversion, procesar_grupo
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            archivos, filas = {}, []
            for k in range(1, 6):
                ruta = tmp / f"Procedimiento {k}.docx"
                _docx(ruta, _p(f"Objetivo del procedimiento número {k}") + _p("Alcance general de la operación diaria."))
                filas.append({"codigo": f"PRD-GEN-0{k}", "archivo": ruta.name})
                archivos[f"PRD-GEN-0{k}"] = ruta
            resultados = []
            for n in (1, 3):
                salida = tmp / f"salida{n}"
                salida.mkdir()
                grupo = Grupo("PRD", "GEN", "General", filas, archivos, "PRD_GEN")
                opciones = OpcionesConversion(verificacion_cruzada=False, trabajadores=n)
                opciones.lanzar([grupo])
                self.assertEqual(bool(opciones._futuros), n > 1)
                try:
                    r = procesar_grupo(grupo, salida, opciones)
                finally:
                    opciones.cerrar()
                resultados.append(([d.codigo for d in r.documentos], [d.estado for d in r.documentos],
                                   [d.palabras for d in r.documentos],
                                   (salida / "PRD_GEN.md").read_text(encoding="utf-8")))
        self.assertEqual(resultados[0][:3], resultados[1][:3])
        self.assertEqual(resultados[0][3].split("\n", 3)[0], resultados[1][3].split("\n", 3)[0])
        self.assertEqual(resultados[0][1], ["OK"] * 5)

    def test_un_error_en_un_documento_no_detiene_a_los_demas(self):
        from corpus_org.conversion.lote import Grupo, OpcionesConversion, procesar_grupo
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            archivos, filas = {}, []
            for k in range(1, 5):
                ruta = tmp / f"Doc {k}.docx"
                if k == 2:
                    ruta.write_bytes(b"no es un zip")
                else:
                    _docx(ruta, _p(f"Objetivo número {k}") + _p("Alcance general de la operación."))
                filas.append({"codigo": f"PRD-GEN-0{k}", "archivo": ruta.name})
                archivos[f"PRD-GEN-0{k}"] = ruta
            grupo = Grupo("PRD", "GEN", "General", filas, archivos, "PRD_GEN")
            opciones = OpcionesConversion(verificacion_cruzada=False, trabajadores=2)
            opciones.lanzar([grupo])
            try:
                r = procesar_grupo(grupo, tmp, opciones)
            finally:
                opciones.cerrar()
        self.assertEqual([d.estado for d in r.documentos], ["OK", "ERROR", "OK", "OK"])


class NombresYDuplicadosTest(unittest.TestCase):
    def test_una_sigla_del_archivo_explicada_por_el_puesto_leido_no_es_un_aviso(self):
        from corpus_org.conversion.analisis import _siglas_explicadas
        self.assertTrue(_siglas_explicadas("3. ENFERMERO-A TSMO GGH-FOR-040", "Enfermero Terapia de Soporte Multiorgánica"))
        self.assertTrue(_siglas_explicadas("3. Analista GDC GECA-ATTA-FOR-034_DESCRIPCIÓN DE PUESTO",
                                           "Analista de Gestión del Conocimiento"))
        self.assertFalse(_siglas_explicadas("3. ENFERMERO-A TSMO GGH-FOR-040", "Gerente de Compras"))

    def test_las_capturas_con_numero_son_imagenes_distintas_y_solo_se_unen_las_identicas(self):
        from corpus_org.conversion.inventario import quitar_copias_contexto
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "a").mkdir()
            (raiz / "b").mkdir()
            rutas = [raiz / "a" / "captura (1).png", raiz / "a" / "captura (2).png", raiz / "b" / "captura (1).png"]
            for r, contenido in zip(rutas, (b"uno", b"dos", b"uno")):
                r.write_bytes(contenido)
            otras = [raiz / "Datos.csv", raiz / "Datos (1).csv"]
            otras[0].write_text("a;b\n1;2\n")
            otras[1].write_text("a;b\n1;3\n")
            usados, avisos = quitar_copias_contexto(rutas + otras, raiz)
        self.assertEqual(sorted(p.name for p in usados), ["Datos.csv", "captura (1).png", "captura (2).png"])
        self.assertTrue(any("a/captura (1).png" in a and "b/captura (1).png" in a for a in avisos), avisos)
        self.assertTrue(any("Datos (1).csv" in a and "es distinto" in a for a in avisos), avisos)


class EncabezadoPorVotoTest(unittest.TestCase):
    def test_el_valor_mal_leido_en_una_pagina_se_corrige_con_el_de_las_demas(self):
        from corpus_org.conversion.extractores.pdf.encabezados import consenso_de_encabezados
        pagina = ["Descripción de Puesto", "Código: GECA-ATTA-FOR-034", "Versión: 05", "Vigente a partir de: 10/09/2025"]
        malas = ["Descripción de Puesto", "Código: SECA-ATTA-FOR-034", "Versión: p.", "Vigente a partir de: 10J09/2025"]
        notas = []
        res = consenso_de_encabezados(malas, [malas, pagina, pagina, pagina, pagina], notas)
        self.assertEqual(res, pagina)
        self.assertEqual(len(notas), 3)
        # con menos de tres paginas, o sin acuerdo entre dos, no se toca
        self.assertEqual(consenso_de_encabezados(malas, [malas, pagina]), malas)
        distintas = [["Código: AAA-BBB-001"], ["Código: CCC-DDD-002"], ["Código: EEE-FFF-003"]]
        self.assertEqual(consenso_de_encabezados(distintas[0], distintas), distintas[0])


class CodigosDeContextoUnicosTest(unittest.TestCase):
    def test_archivos_con_el_mismo_nombre_base_nunca_comparten_codigo(self):
        from corpus_org.conversion.inventario import inventario_contexto
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "a").mkdir()
            (raiz / "b").mkdir()
            archivos = [raiz / "a" / "captura (1).png", raiz / "a" / "captura (2).png", raiz / "b" / "captura (3).png",
                        raiz / "Plan.xlsx"]
            # inventario anterior con un codigo repetido (el error de una corrida previa) y otro material
            base = [{"codigo": "CTX-GEN-01", "tipo": "Contexto general", "archivo": "captura (1).png", "estado_inventario": "ACTIVO"},
                    {"codigo": "CTX-GEN-01", "tipo": "Contexto general", "archivo": "captura (3).png", "estado_inventario": "ACTIVO"},
                    {"codigo": "CTX-GEN-02", "tipo": "Contexto general", "archivo": "Plan.csv", "estado_inventario": "ACTIVO"},
                    {"codigo": "CTX-GEN-03", "tipo": "Contexto general", "archivo": "Viejo.csv", "estado_inventario": "ACTIVO"}]
            filas, _ = inventario_contexto(archivos, raiz, base)
        activos = {f["archivo"]: f["codigo"] for f in filas if f["estado_inventario"] == "ACTIVO"}
        self.assertEqual(len(set(activos.values())), len(activos), activos)
        self.assertEqual(activos["captura (1).png"], "CTX-GEN-01")          # el mismo nombre conserva su codigo
        self.assertEqual(activos["Plan.xlsx"], "CTX-GEN-02")                # el mismo documento con otra extension
        codigos = [f["codigo"] for f in filas]
        self.assertEqual(len(codigos), len(set(codigos)), codigos)           # ni siquiera entre activos y retirados
        retirados = {f["codigo"] for f in filas if f["estado_inventario"] == "RETIRADO"}
        self.assertIn("CTX-GEN-03", retirados)


class RutaOriginalDeContextoTest(unittest.TestCase):
    def test_un_documento_de_area_que_vino_del_contexto_se_muestra_como_contexto(self):
        from corpus_org.conversion.lote import Grupo, OpcionesConversion, ruta_original
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "contexto" / "Plan").mkdir(parents=True)
            (raiz / "entrada").mkdir()
            archivo = raiz / "contexto" / "Plan" / "Proc.pdf"
            archivo.write_bytes(b"x")
            grupo = Grupo("PRD", "PES", "Planificación", [], {}, "PRD_PES")
            opciones = OpcionesConversion(raiz_entrada=raiz / "entrada", raiz_contexto=raiz / "contexto")
            self.assertEqual(ruta_original({"archivo": "Proc.pdf", "desde_contexto": True}, grupo, opciones, archivo),
                             "contexto/Plan/Proc.pdf")
            otro = raiz / "entrada" / "Descriptivos" / "A.pdf"
            otro.parent.mkdir()
            otro.write_bytes(b"x")
            self.assertEqual(ruta_original({"archivo": "A.pdf"}, grupo, opciones, otro), "entrada/Descriptivos/A.pdf")
