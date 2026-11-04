"""Pruebas del vaciado del K4 a la plantilla metodologica, con archivos sinteticos (ver fixtures_vaciado)."""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests import ayuda  # noqa: F401
from tests import fixtures_vaciado as fx
from corpus_org.consulta import cli as consulta_cli
from corpus_org.consulta.vaciado import valores
from corpus_org.consulta.vaciado.hoja_xml import CeldaConFormula, HojaXml
from corpus_org.consulta.vaciado import checklist
from corpus_org.consulta.vaciado.checklist import alerta_de_carga, evaluar
from corpus_org.consulta.vaciado.k4 import K4, evaluar_aritmetica, leer_k4
from corpus_org.consulta.vaciado.metodologia import VerificacionFallida, vaciar_k4
from corpus_org.consulta.vaciado.estilos import verificar_estilos_agregados
from corpus_org.consulta.vaciado.verificacion import verificar
from corpus_org.consulta.vaciado.xlsx import Libro


def modificar(origen, destino, parte, cambio):
    """Copia un xlsx cambiando el texto de una de sus partes con ``cambio(texto) -> texto``."""
    with zipfile.ZipFile(origen) as zo, zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zd:
        for n in zo.namelist():
            datos = zo.read(n)
            if n == parte:
                datos = cambio(datos.decode("utf-8")).encode("utf-8")
            zd.writestr(n, datos)
    return destino


class ValoresTest(unittest.TestCase):
    def test_minutos(self):
        self.assertEqual(valores.minutos(480)[0], 480.0)
        self.assertEqual(valores.minutos("45 min")[0], 45)
        self.assertEqual(valores.minutos("2 h")[0], 120)
        self.assertEqual(valores.minutos("1:30")[0], 90)
        self.assertEqual(valores.minutos("1h30")[0], 90)
        self.assertEqual(valores.minutos("20-30")[0], 25)
        self.assertIn("promedio", valores.minutos("20-30")[1])

    def test_cero_y_textos_sin_dato_no_son_tiempo(self):
        self.assertEqual(valores.minutos(0), (None, "tiempo 0 (= sin dato)"))
        self.assertEqual(valores.minutos("N/D"), (None, None))
        self.assertIsNone(valores.minutos("mucho")[0])

    def test_una_fecha_de_excel_no_es_un_volumen(self):
        celda = type("C", (), {"valor": 45292.0, "es_fecha": True, "es_hora": False})()
        valor, nota = valores.volumen(celda)
        self.assertIsNone(valor)
        self.assertIn("fecha", nota)

    def test_retrabajo_solo_fracciones_o_porcentajes(self):
        self.assertEqual(valores.retrabajo(0.1), (0.1, None))
        self.assertEqual(valores.retrabajo("10%")[0], 0.1)
        valor, nota = valores.retrabajo(15)
        self.assertIsNone(valor)
        self.assertIn("mayor que 1", nota)

    def test_frecuencias(self):
        self.assertEqual(valores.frecuencia("Diario")[0], "Diaria")
        self.assertEqual(valores.frecuencia("A demanda")[0], "Eventual")
        self.assertIsNotNone(valores.frecuencia("A demanda")[1])
        self.assertEqual(valores.frecuencia("Bimestral")[0], "Bimestral")
        self.assertIsNone(valores.frecuencia("cuando llueve")[0])

    def test_bimestral_se_convierte_a_anual_por_seis_con_las_mismas_horas(self):
        from corpus_org.consulta.vaciado import calculo
        periodo, eventos, nota = valores.periodo_para_plantilla("Bimestral", 2)
        self.assertEqual((periodo, eventos), ("Anual", 12))
        self.assertIsNotNone(nota)
        antes = 2 * 6 / 12                       # 2 veces cada bimestre = 12 al año = 1 al mes
        self.assertAlmostEqual(calculo.horas_mes(60, 0, eventos, periodo, None, 1.0), antes)
        self.assertEqual(valores.periodo_para_plantilla("Mensual", 3), ("Mensual", 3, None))

    def test_listas_de_la_plantilla(self):
        self.assertEqual(valores.escolaridad("Licenciatura"), "Universitaria")
        self.assertEqual(valores.escolaridad("Diplomado"), "Especialización")
        self.assertIsNone(valores.escolaridad("10 años de experiencia"))
        self.assertEqual(valores.modalidad("Híbrido (3 días)"), "Híbrido")
        self.assertEqual(valores.nivel("avanzado"), "Avanzado")
        self.assertIsNone(valores.nivel("Alto"))
        self.assertEqual(valores.tipo_competencia("Técnica"), "Técnica")

    def test_aritmetica_segura(self):
        self.assertEqual(evaluar_aritmetica("=(8*60)"), 480.0)
        self.assertIsNone(evaluar_aritmetica("=A1+2"))
        self.assertIsNone(evaluar_aritmetica("=__import__('os')"))
        self.assertIsNone(evaluar_aritmetica("=1/0"))


class HojaXmlTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        ruta = fx.crear_plantilla(Path(self.tmp.name) / "p.xlsx")
        with zipfile.ZipFile(ruta) as z:
            self.texto = z.read("xl/worksheets/sheet6.xml").decode("utf-8")        # Actividades_Carga

    def test_no_escribe_sobre_formulas(self):
        h = HojaXml(self.texto)
        with self.assertRaises(CeldaConFormula):
            h.escribir("Q8", "x")
        self.assertFalse(h.modificada)

    def test_conserva_el_estilo_de_la_celda_y_quita_spans(self):
        h = HojaXml(self.texto)
        estilo = h.estilo("D8")
        h.escribir("D8", "Actividad")
        self.assertEqual(h.estilo("D8"), estilo)
        self.assertNotIn("spans", re.search(r'<row r="8"[^>]*>', h.texto()).group(0))

    def test_textos_especiales_y_numeros(self):
        h = HojaXml(self.texto)
        h.escribir("D8", "a < b & c\r\nlínea\x01")
        h.escribir("J8", 30.0)
        h.escribir("K8", 0.25)
        nuevo = h.texto()
        self.assertIn("a &lt; b &amp; c\nlínea", nuevo)
        self.assertIn('<v>30</v>', nuevo)
        self.assertIn('<v>0.25</v>', nuevo)

    def test_texto_largo_se_recorta_y_avisa(self):
        h = HojaXml(self.texto)
        self.assertTrue(h.escribir("D8", "x" * 40000))
        self.assertFalse(h.escribir("D9", "corto"))

    def test_celda_nueva_usa_el_estilo_indicado_y_amplia_la_dimension(self):
        h = HojaXml(self.texto)
        h.escribir("B40", "nuevo", estilo=str(fx.ENTRADA))
        self.assertEqual(h.estilo("B40"), str(fx.ENTRADA))
        self.assertIn('<dimension ref="B7:V40"/>', h.texto())

    def test_lista_desplegable_clasica_antes_de_los_margenes(self):
        h = HojaXml(self.texto)
        h.agregar_validacion_lista("E8:E30", ["A", "B & C"])
        t = h.texto()
        self.assertIn('<dataValidations count="1">', t)
        self.assertIn("A,B &amp; C", t)
        self.assertLess(t.index("<dataValidations"), t.index("<pageMargins"))


class LectorK4Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.k4 = leer_k4(fx.crear_k4(Path(cls.tmp.name) / "k4.xlsx"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_colaborador(self):
        self.assertEqual(self.k4.colaborador["nombre"], "Ana")
        self.assertEqual(self.k4.colaborador["apellido"], "Prueba")

    def test_actividades_sin_ejemplos_ni_filas_auxiliares(self):
        nombres = [f.texto("actividad") for f in self.k4.filas("actividades")]
        self.assertEqual(nombres, ["Emitir orden de compra", "Conciliar facturas", "Reportar al jefe"])
        avisos = " ".join(self.k4.avisos)
        self.assertIn("1 fila(s) de ejemplo en rojo", avisos)
        self.assertIn("sin actividad", avisos)

    def test_hereda_proceso_y_tipo_en_el_inventario(self):
        conciliar = next(f for f in self.k4.filas("inventario") if f.texto("actividad") == "Conciliar facturas")
        self.assertEqual((conciliar.texto("proceso"), conciliar.texto("tipo")), ("Compras", "Core"))

    def test_lee_la_hoja_oculta(self):
        self.assertEqual(self.k4.hojas_ocultas_leidas, ["9. Competencias"])
        self.assertEqual([f.texto("competencia") for f in self.k4.filas("competencias")], ["Negociación", "Orden", "Idiomas"])

    def test_formula_aritmetica_sin_valor_guardado(self):
        reportar = self.k4.filas("actividades")[2]
        self.assertEqual(reportar.valor("tiempo"), 60.0)

    def test_origen_por_comentario(self):
        conciliar = self.k4.filas("actividades")[1]
        self.assertEqual(conciliar.origen("volumen"), "entrevista")
        self.assertEqual(conciliar.origen("tiempo"), "k4")

    def test_exposicion_no_ensucia_las_condiciones(self):
        self.assertEqual(len(self.k4.filas("condiciones")), 1)
        self.assertEqual(self.k4.exposicion, ["Disponibilidad: viajes ocasionales", "Ruido moderado"])

    def test_hojas_que_faltan(self):
        self.assertEqual(sorted(self.k4.hojas_faltantes), ["2.1 actividades", "3. entregables", "4. relaciones"])


class VaciadoBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.k4 = fx.crear_k4(cls.dir / "k4.xlsx")
        cls.plantilla = fx.crear_plantilla(cls.dir / "plantilla.xlsx")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def vaciar(self, nombre="salida.xlsx", **kw):
        return vaciar_k4(self.k4, self.plantilla, self.dir / nombre, **kw)


class VaciadoTest(VaciadoBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.resultado, _, cls.celdas = cls().vaciar()
        cls.salida = Libro(cls.dir / "salida.xlsx")

    def test_identificacion_y_perfil(self):
        c = self.salida.hoja("Control")
        self.assertEqual([c.valor(f"C{n}") for n in range(9, 17)],
                         ["Compras", "Abastecimiento", "CMP-001", "Analista de Compras", "Ana Prueba", "Jefe de Compras", "Sede central", "Híbrido"])
        p = self.salida.hoja("Perfil_Puesto")
        etiquetas = {p.valor(f"B{9 + 3 * i}"): p.valor(f"B{10 + 3 * i}") for i in range(len(fx.ROTULOS_PERFIL))}
        self.assertEqual(etiquetas["Escolaridad mínima*"], "Universitaria")
        self.assertEqual(etiquetas["Disponibilidad / viajes / turnos"], "8 a 5\nDisponibilidad: viajes ocasionales")
        self.assertEqual(etiquetas["Riesgos SST / ergonómicos"], "Ruido moderado")
        self.assertEqual(etiquetas["Recursos requeridos"], "Computadora")
        self.assertEqual(etiquetas["Conocimientos técnicos*"], "Negociación")
        self.assertEqual(etiquetas["Puestos que supervisa"], "2 persona(s) a cargo\nAuxiliar")

    def test_el_correo_y_el_telefono_no_se_copian(self):
        todo = " ".join(str(c.valor) for h in self.salida.hojas for c in h.celdas.values() if c.valor is not None)
        self.assertNotIn("ana@ejemplo.test", todo)
        self.assertNotIn("555-0000", todo)

    def test_actividades_con_sus_conversiones(self):
        h = self.salida.hoja("Actividades_Carga")
        col = {h.valor(f"{c}7"): c for c in "BCDEFGHIJKLMNOPQ"}
        fila = lambda n, e: h.valor(f"{col[e]}{n}")          # noqa: E731
        self.assertEqual([fila(n, "Actividad") for n in (8, 9, 10)], ["Emitir orden de compra", "Conciliar facturas", "Reportar al jefe"])
        self.assertEqual((fila(8, "Frecuencia"), fila(8, "Eventos por frecuencia"), fila(8, "Retrabajo %")), ("Diaria", 5, 0.1))
        self.assertEqual((fila(9, "Frecuencia"), fila(9, "Eventos por frecuencia"), fila(9, "Tiempo unitario min")), ("Anual", 12, 90))
        self.assertIsNone(fila(9, "Retrabajo %"))                    # 15 podria ser minutos: no se escribe
        self.assertEqual(fila(9, "Fuente del dato"), "Entrevista")
        self.assertEqual(fila(8, "Fuente del dato"), "Estimación experta")
        self.assertEqual(fila(8, "Meses/año activos"), 12)
        self.assertEqual(fila(10, "Meses/año activos"), 12)          # estacional: valor provisional marcado «A validar» (ver la nota)
        self.assertEqual(fila(10, "% dedicación personal"), 0.5)      # 30 de 60 minutos
        self.assertEqual(fila(8, "% dedicación personal"), 1)
        self.assertEqual(fila(10, "Automatización"), "Manual")       # «Rara vez» no esta en la lista: se infiere «Manual»
        self.assertEqual(fila(8, "Proceso"), "Compras")
        self.assertEqual(fila(10, "Tipo proceso"), "Soporte")

    def test_horas_calculadas(self):
        esperado = 30 * 5 * 23.83 * 1.1 / 60 + 90 * 12 / 12 / 60 + 60 * 1 * 0.5 / 60
        self.assertAlmostEqual(self.resultado.horas_mes, esperado, places=6)
        self.assertEqual(self.resultado.sin_horas, [])

    def test_los_valores_fuera_de_lista_van_a_puntos_a_validar(self):
        tipos = {(p["hoja"], p["campo"]): p["tipo"] for p in self.resultado.puntos}
        self.assertEqual(tipos[("Competencias", "Tipo de «Idiomas»")], "Valor fuera de lista")
        self.assertEqual(tipos[("Actividades_Carga", "Retrabajo de «Conciliar facturas»")], "Valor fuera de lista")
        self.assertEqual(tipos[("Actividades_Carga", "Automatización de «Reportar al jefe»")], "Valor fuera de lista")
        self.assertEqual(tipos[("Perfil_Puesto", "Reporta matricialmente / regionalmente a")], "Dato sin destino")
        self.assertEqual(tipos[("Actividades_Carga", "Meses activos de «Reportar al jefe»")], "Dato faltante")
        self.assertEqual(tipos[("Capacidad", "Parámetros de capacidad")], "Dato faltante")

    def test_competencias_responsabilidades_y_optimizacion(self):
        comp = self.salida.hoja("Competencias")
        self.assertEqual([comp.valor(f"D{n}") for n in (8, 9, 10)], ["Negociación", "Orden", "Idiomas"])
        self.assertEqual(comp.valor("E10"), "Avanzado")       # «Alto» no esta en la lista: se infiere «Avanzado»
        self.assertTrue(comp.celda("E10").nota.startswith("Inferido: el K4 dice «Alto»"))
        resp = self.salida.hoja("Responsabilidades")
        self.assertEqual([resp.valor(f"E{n}") for n in (8, 9)], ["Eventual", "Mensual"])      # «A demanda» → Eventual
        riesgos = self.salida.hoja("Riesgos_Mejoras")
        self.assertEqual(riesgos.valor("D8"), "Error de proveedor")
        self.assertEqual(riesgos.valor("G9"), "Optimización de tiempo")

    def test_hoja_de_puntos(self):
        h = self.salida.hoja("Puntos_a_validar")
        self.assertEqual(h.valor("B8"), "PV-001")
        self.assertEqual(h.valor(f"B{8 + len(self.resultado.puntos) - 1}"), f"PV-{len(self.resultado.puntos):03d}")
        self.assertEqual({h.valor(f"J{n}") for n in range(8, 8 + len(self.resultado.puntos))}, {"Pendiente"})
        with zipfile.ZipFile(self.dir / "salida.xlsx") as z:
            tabla = z.read("xl/tables/table8.xml").decode("utf-8")
            hoja = z.read("xl/worksheets/sheet11.xml").decode("utf-8")
        self.assertIn('name="tblPuntosValidar"', tabla)
        self.assertIn('ref="B7:J107"', tabla)
        self.assertEqual(hoja.count('type="list"'), 2)         # Tipo y Estado

    def test_la_plantilla_conserva_formulas_listas_x14_y_recalcula_al_abrir(self):
        with zipfile.ZipFile(self.plantilla) as zo, zipfile.ZipFile(self.dir / "salida.xlsx") as zs:
            self.assertEqual(zs.namelist()[:len(zo.namelist())], zo.namelist())
            agregadas = zs.namelist()[len(zo.namelist()):]                       # solo las partes de las notas de celda
            self.assertTrue(agregadas and all(re.match(r"xl/(comments\d+\.xml|drawings/vmlDrawing\d+\.vml|worksheets/_rels/)", n) for n in agregadas), agregadas)
            cambiadas = {n for n in zo.namelist() if zo.read(n) != zs.read(n)}
            self.assertTrue(all(n.startswith(("xl/worksheets/sheet", "xl/worksheets/_rels/", "xl/tables/", "xl/comments", "xl/drawings/vmlDrawing"))
                                or n in ("xl/workbook.xml", "xl/styles.xml", "[Content_Types].xml") for n in cambiadas), cambiadas)
            self.assertIn("fullCalcOnLoad", zs.read("xl/workbook.xml").decode("utf-8"))
            origen, salida = zo.read("xl/worksheets/sheet6.xml").decode("utf-8"), zs.read("xl/worksheets/sheet6.xml").decode("utf-8")
            self.assertEqual(origen.count("<x14:dataValidation "), salida.count("<x14:dataValidation "))
            self.assertEqual(re.findall(r"<f>[^<]*</f>", origen), re.findall(r"<f>[^<]*</f>", salida))
            portada = zs.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertRegex(portada, r'<c r="B4"[^>]*><f>Control!C8</f></c>')       # sin el valor guardado (desactualizado)

    def test_resumen_de_celdas(self):
        self.assertEqual(self.celdas, len(self.resultado.escritas))
        self.assertGreater(self.resultado.por_hoja["Actividades_Carga"], 30)


class ComplementosTest(VaciadoBase):
    def test_diferencia_deja_la_celda_vacia_y_un_punto(self):
        complementos = {"campos": [{"hoja": "Control", "campo": "Ubicación", "valor": "Sucursal norte", "fuente": "Transcripción", "modo": "diferencia"},
                                   {"hoja": "Control", "campo": "Subárea", "valor": "Abastecimiento"},
                                   {"hoja": "Control", "campo": "Rótulo que no existe", "valor": "x"}]}
        r, _, _ = self.vaciar("c1.xlsx", complementos=complementos)
        c = Libro(self.dir / "c1.xlsx").hoja("Control")
        self.assertEqual(c.valor("C15"), "A validar: ubicación")           # K4 y reunión difieren: no se elige, queda para validar
        self.assertEqual(c.celda("C15").color_letra, "FF7030A0")
        self.assertEqual(c.valor("C10"), "Abastecimiento")
        punto = next(p for p in r.puntos if p["tipo"] == "Diferencia K4/Reunión")
        self.assertEqual((punto["valor_formato"], punto["valor_reunion"], punto["fuente_reunion"]), ("Sede central", "Sucursal norte", "Transcripción"))
        self.assertTrue(any(p["tipo"] == "Dato sin destino" and p["campo"] == "Rótulo que no existe" for p in r.puntos))

    def test_actividad_nueva_puntos_y_evidencias(self):
        complementos = {"actividades_nuevas": [{"actividad": "Visitar proveedores", "periodo": "Mensual", "volumen": 2, "tiempo_min": 120}],
                        "puntos": [{"hoja": "Perfil_Puesto", "campo": "Alcance", "tipo": "Recomendación", "que_validar": "Confirmar"},
                                   {"hoja": "X", "campo": "Y", "tipo": "Inventado"}],
                        "evidencias": [{"nombre": "Transcripción.docx", "tipo": "Entrevista"}]}
        r, _, _ = self.vaciar("c2.xlsx", complementos=complementos)
        a = Libro(self.dir / "c2.xlsx").hoja("Actividades_Carga")
        self.assertEqual((a.valor("D11"), a.valor("G11"), a.valor("H11")), ("Visitar proveedores", "Mensual", 2))
        self.assertEqual(a.valor("N11"), "Entrevista")
        tipos = [p["tipo"] for p in r.puntos]
        self.assertIn("Recomendación", tipos)
        self.assertEqual(next(p["tipo"] for p in r.puntos if p["hoja"] == "X"), "Interpretación")       # tipo inválido → Interpretación
        self.assertAlmostEqual(r.horas_mes, 30 * 5 * 23.83 * 1.1 / 60 + 1.5 + 0.5 + 120 * 2 / 60, places=6)

    def test_filas_que_no_caben_se_avisan(self):
        extra = [{"nombre": f"Doc {i}"} for i in range(3)]               # Evidencias solo tiene 2 filas libres
        r, _, _ = self.vaciar("c3.xlsx", complementos={"evidencias": extra})
        self.assertEqual(len(r.desbordes["Evidencias"]), 2)
        self.assertTrue(any(p["campo"] == "Filas que no cupieron" for p in r.puntos))


ACTIVIDADES = ("Emitir orden de compra", "Conciliar facturas")


class PropuestasEnMoradoTest(VaciadoBase):
    """Valor, subproceso, cliente y hallazgos que propone el agente: letra morada para que el consultor los valide a mano."""

    MORADO = "FF7030A0"
    COMPLEMENTOS = {
        "clasificacion": [
            {"actividad": ACTIVIDADES[0], "valor": "va", "subproceso": "Compras directas", "cliente": "interno", "responsabilidad": "Abastecer",
             "participantes": 2},
            {"actividad": ACTIVIDADES[1], "valor": "NVA-N", "cliente": "Quizás"},
            {"actividad": "Actividad que no existe", "valor": "VA"}],
        "hallazgos": [
            {"actividad": ACTIVIDADES[0], "hallazgo": "Reingreso manual de datos", "evidencia": "K4 hoja 2", "causa_raiz": "Sin integración",
             "impacto": "alto", "probabilidad": "Medio", "accion": "automatizar", "beneficio": "por medir", "esfuerzo": "medio", "prioridad": "alta"},
            {"actividad": ACTIVIDADES[0], "complementa_k4": True, "impacto": "Alto", "accion": "Estandarizar", "causa_raiz": "no debe pisar al K4"},
            {"actividad": "Otra", "evidencia": "sin hallazgo"},
            {"actividad": ACTIVIDADES[1], "hallazgo": "Esperas", "impacto": "Gigante"}]}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.resultado, _, _ = cls().vaciar("morado.xlsx", complementos=cls.COMPLEMENTOS)
        cls.salida = Libro(cls.dir / "morado.xlsx")

    def celda(self, hoja, ref):
        return self.salida.hoja(hoja).celda(ref)

    def col(self, hoja, encabezado, libro=None):
        h = (libro or self.salida).hoja(hoja)
        return next(c for c, x in h.fila(7).items() if isinstance(x.valor, str) and x.valor.replace("*", "").strip() == encabezado)

    def en(self, hoja, encabezado, fila):
        return self.celda(hoja, f"{self.col(hoja, encabezado)}{fila}")

    def test_clasificacion_en_morado_con_valores_de_la_lista(self):
        for encabezado, esperado in (("Subproceso", "Compras directas"), ("Cliente", "Interno"), ("Valor", "VA"),
                                     ("Responsabilidad vinculada", "Abastecer"), ("Participantes por evento", 2.0)):
            c = self.en("Actividades_Carga", encabezado, 8)
            self.assertEqual((c.valor, c.color_letra), (esperado, self.MORADO), encabezado)
        self.assertEqual(self.en("Actividades_Carga", "Valor", 9).valor, "NVA-N")
        cliente = self.en("Actividades_Carga", "Cliente", 9)
        self.assertEqual(cliente.valor, "Interno")                                       # «Quizás» no es un cliente de la lista: se infiere uno
        self.assertTrue(cliente.nota.startswith("Inferido: "), cliente.nota)

    def test_el_dato_del_k4_sigue_en_su_formato_y_solo_las_propuestas_cambian_de_color(self):
        base = Libro(self.plantilla)
        c = self.en("Actividades_Carga", "Actividad", 8)
        self.assertNotEqual(c.color_letra, self.MORADO)
        self.assertEqual(c.estilo, base.hoja("Actividades_Carga").celda(f"{self.col('Actividades_Carga', 'Actividad')}8").estilo)
        col = self.col("Actividades_Carga", "Valor")
        self.assertEqual(self.celda("Actividades_Carga", f"{col}8").color_relleno, base.hoja("Actividades_Carga").celda(f"{col}8").color_relleno)

    def test_hallazgo_nuevo_en_morado_y_codigo_del_puesto_en_negro(self):
        h = self.salida.hoja("Riesgos_Mejoras")
        d, e = self.col("Riesgos_Mejoras", "Actividad / proceso"), self.col("Riesgos_Mejoras", "Hallazgo / dolor")
        fila = next(n for n in range(8, 31) if h.valor(f"{d}{n}") == ACTIVIDADES[0] and h.valor(f"{e}{n}") == "Reingreso manual de datos")
        self.assertEqual(self.en("Riesgos_Mejoras", "Código puesto", fila).valor, "CMP-001")
        self.assertNotEqual(self.en("Riesgos_Mejoras", "Código puesto", fila).color_letra, self.MORADO)
        for encabezado, esperado in (("Actividad / proceso", ACTIVIDADES[0]), ("Hallazgo / dolor", "Reingreso manual de datos"), ("Evidencia", "K4 hoja 2"),
                                     ("Causa raíz", "Sin integración"), ("Impacto", "Alto"), ("Probabilidad", "Medio"), ("Acción sugerida", "Automatizar"),
                                     ("Beneficio esperado", "por medir"), ("Esfuerzo", "Medio"), ("Prioridad", "Alta")):
            c = self.en("Riesgos_Mejoras", encabezado, fila)
            self.assertEqual((c.valor, c.color_letra), (esperado, self.MORADO), encabezado)

    def test_complementa_la_fila_del_k4_sin_pisar_lo_que_escribio_el_ocupante(self):
        self.assertEqual(self.en("Riesgos_Mejoras", "Actividad / proceso", 8).valor, "Emitir orden de compra")
        causa = self.en("Riesgos_Mejoras", "Causa raíz", 8)
        self.assertEqual(self.en("Riesgos_Mejoras", "Hallazgo / dolor", 8).valor, "Error de proveedor")
        self.assertEqual(causa.valor, "Datos incompletos")                                # no la pisó «no debe pisar al K4»
        self.assertNotEqual(causa.color_letra, self.MORADO)
        for encabezado, esperado in (("Impacto", "Alto"), ("Acción sugerida", "Estandarizar")):
            c = self.en("Riesgos_Mejoras", encabezado, 8)
            self.assertEqual((c.valor, c.color_letra), (esperado, self.MORADO))

    def test_lo_que_no_cuadra_va_a_puntos_y_no_se_escribe(self):
        puntos = {(p["hoja"], p["campo"]): p for p in self.resultado.puntos}
        self.assertEqual(puntos[("Actividades_Carga", f"Cliente de «{ACTIVIDADES[1]}»")]["tipo"], "Valor fuera de lista")
        self.assertEqual(puntos[("Riesgos_Mejoras", f"Impacto de «{ACTIVIDADES[1]}»")]["valor_formato"], "Gigante")
        self.assertEqual(puntos[("Actividades_Carga", "Clasificación de «Actividad que no existe»")]["tipo"], "Dato sin destino")
        self.assertEqual(puntos[("Riesgos_Mejoras", "Hallazgo de «Otra»")]["tipo"], "Dato faltante")

    def test_resumen_de_propuestas_y_punto_global(self):
        self.assertGreater(self.resultado.propuestas["Actividades_Carga"], 6)            # las del agente y las inferidas por regla
        self.assertGreaterEqual(self.resultado.propuestas["Riesgos_Mejoras"], 12)
        tipos = {(p["hoja"], p["campo"]): p["tipo"] for p in self.resultado.puntos}
        self.assertEqual(tipos[("Actividades_Carga", "Propuestas en letra morada")], "Interpretación")

    def test_la_verificacion_pasa_y_detecta_morado_perdido_o_formato_cambiado(self):
        ok = self.dir / "morado.xlsx"
        args = (self.resultado.escritas, self.resultado.horas_mes, 23.83, self.resultado.colores, self.resultado.notas)
        self.assertEqual(verificar(self.plantilla, ok, *args), [])
        base = Libro(self.plantilla)
        parte = base.hoja("Actividades_Carga").parte
        ref = f"{self.col('Actividades_Carga', 'Valor')}8"
        gris = base.hoja("Actividades_Carga").celda(ref).estilo
        sin_morado = modificar(ok, self.dir / "m1.xlsx", parte, lambda t: re.sub(rf'(<c r="{ref}") s="\d+"', rf'\1 s="{gris}"', t, count=1))
        self.assertTrue(any("morada" in e for e in verificar(self.plantilla, sin_morado, *args)))
        otro_formato = modificar(ok, self.dir / "m2.xlsx", "xl/styles.xml", lambda t: t.replace('fgColor theme="0"', 'fgColor theme="3"', 1))
        self.assertTrue(any("styles.xml" in e for e in verificar(self.plantilla, otro_formato, *args)))

    def test_estilos_ya_existentes_no_se_tocan(self):
        with zipfile.ZipFile(self.plantilla) as zo, zipfile.ZipFile(self.dir / "morado.xlsx") as zs:
            self.assertEqual(verificar_estilos_agregados(zo.read("xl/styles.xml").decode(), zs.read("xl/styles.xml").decode()), [])


class CatalogoTest(unittest.TestCase):
    def test_lee_las_listas_de_la_hoja_catalogos_y_devuelve_vacio_si_no_esta(self):
        with tempfile.TemporaryDirectory() as tmp:
            conlista = fx.crear_plantilla(Path(tmp) / "p.xlsx")
            sinlista = fx.crear_xlsx(Path(tmp) / "q.xlsx", [h for h in fx.hojas_plantilla() if h["nombre"] != "Catálogos"])
            from corpus_org.consulta.vaciado.plantilla import Plantilla
            p, q = Plantilla(Libro(conlista)), Plantilla(Libro(sinlista))
            self.assertEqual(p.catalogo("Valor"), ["VA", "NVA-N", "NVA"])
            self.assertEqual(p.catalogo("Acción")[:2], ["Eliminar", "Simplificar"])
            self.assertEqual(p.catalogo("Inexistente"), [])
            self.assertEqual(q.catalogo("Valor"), [])


class NotasDeCeldaTest(VaciadoBase):
    """Cada celda en letra morada lleva una nota «Inferido: …» o «A validar: …» dentro del mismo archivo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.resultado, _, _ = cls().vaciar("notas.xlsx", complementos=PropuestasEnMoradoTest.COMPLEMENTOS)
        cls.salida = Libro(cls.dir / "notas.xlsx")

    def test_toda_celda_morada_tiene_su_nota(self):
        self.assertTrue(self.resultado.colores)
        for (hoja, ref), color in self.resultado.colores.items():
            celda = self.salida.hoja(hoja).celda(ref)
            self.assertEqual(color, "FF7030A0")
            self.assertRegex(celda.nota, r"^(Inferido|A validar)", (hoja, ref))
            self.assertEqual(celda.nota, self.resultado.notas[(hoja, ref)])
            self.assertTrue(celda.nota.endswith("Validar con el consultor."), celda.nota)

    def test_etiquetas_segun_haya_o_no_base(self):
        h = self.salida.hoja("Actividades_Carga")
        c = {x.valor.replace("*", ""): col for col, x in h.fila(7).items() if isinstance(x.valor, str)}
        self.assertTrue(h.celda(f"{c['Subproceso']}9").valor.startswith("A validar: subproceso de «Compras»"))
        self.assertTrue(h.celda(f"{c['Subproceso']}9").nota.startswith("A validar:"))
        self.assertTrue(h.celda(f"{c['Cliente']}10").nota.startswith("Inferido:"))
        self.assertTrue(self.salida.hoja("Actividades_Carga").celda(f"{c['Valor']}10").nota.startswith("Inferido:"))
        self.assertIn("VA = el cliente lo pagaría", self.resultado.notas[("Actividades_Carga", f"{c['Valor']}10")])

    def test_la_hoja_con_notas_conserva_la_suya_y_las_hojas_sin_notas_reciben_las_partes_nuevas(self):
        base = Libro(self.plantilla)
        self.assertEqual(self.salida.hoja("Actividades_Carga").celda("H7").nota, base.hoja("Actividades_Carga").celda("H7").nota)
        with zipfile.ZipFile(self.dir / "notas.xlsx") as z, zipfile.ZipFile(self.plantilla) as zo:
            nuevos = [n for n in z.namelist() if n not in zo.namelist()]
            self.assertTrue(any(n.startswith("xl/comments") for n in nuevos))                          # hojas sin comentarios: partes nuevas
            self.assertTrue(any(n.startswith("xl/drawings/vmlDrawing") for n in nuevos))
            comentarios_de_actividades = z.read("xl/comments6.xml").decode("utf-8")
            self.assertIn("Nota de la plantilla", comentarios_de_actividades)                           # la de la plantilla sigue en su parte
            self.assertIn("Claude (inferido)", comentarios_de_actividades)                              # y las nuevas se agregaron a la misma
            sheet_nuevo = z.read(Libro(self.plantilla).hoja("Responsabilidades").parte).decode("utf-8")
            self.assertRegex(sheet_nuevo, r'<legacyDrawing r:id="rId\d+"/>')
            self.assertLess(sheet_nuevo.index("<legacyDrawing"), sheet_nuevo.index("<tableParts"))      # orden que exige el esquema
            self.assertIn('Extension="vml"', z.read("[Content_Types].xml").decode("utf-8"))

    def test_todas_las_partes_nuevas_son_xml_valido_y_las_formas_cubren_las_notas(self):
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(self.dir / "notas.xlsx") as z:
            for n in z.namelist():
                if n.startswith(("xl/comments", "xl/drawings/vmlDrawing")) or n.endswith(".rels") or n == "[Content_Types].xml":
                    ET.fromstring(z.read(n))
            vml = z.read("xl/comments6.xml").decode("utf-8")
            forma_vml = z.read("xl/drawings/vmlDrawing6.vml").decode("utf-8")
            self.assertEqual(vml.count("<comment "), forma_vml.count("<v:shape id="))                  # una forma por nota
            ids = re.findall(r'id="_x0000_s(\d+)"', forma_vml)
            self.assertEqual(len(ids), len(set(ids)))

    def test_la_verificacion_detecta_una_nota_alterada_o_perdida(self):
        args = dict(esperadas=self.resultado.escritas, horas_esperadas=self.resultado.horas_mes, colores=self.resultado.colores, notas=self.resultado.notas)
        ok = self.dir / "notas.xlsx"
        self.assertEqual(verificar(self.plantilla, ok, **args), [])
        alterada = modificar(ok, self.dir / "n1.xlsx", "xl/comments6.xml", lambda x: x.replace("Inferido por el agente", "Otra cosa", 1))
        self.assertTrue(any("nota de la celda no es la esperada" in e for e in verificar(self.plantilla, alterada, **args)))
        perdida = modificar(ok, self.dir / "n2.xlsx", "xl/comments6.xml", lambda x: x.replace("Nota de la plantilla: eventos por frecuencia", "Cambiada"))
        errores = verificar(self.plantilla, perdida, **args)
        self.assertTrue(any("cambió una nota" in e or "se perdió o cambió" in e for e in errores), errores)


class SinCamposVaciosTest(VaciadoBase):
    """El vaciado no deja celdas de entrada sin valor en las filas que escribe: se infiere o queda «A validar»."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.resultado, _, _ = cls().vaciar("llenas.xlsx")
        cls.salida = Libro(cls.dir / "llenas.xlsx")

    def vacias(self, hoja, filas):
        h, base = self.salida.hoja(hoja), Libro(self.plantilla).hoja(hoja)
        encabezados = {c: x.valor.replace("*", "") for c, x in h.fila(7).items() if isinstance(x.valor, str)}
        return sorted({e for n in filas for c, e in encabezados.items()
                       if (h.celda(f"{c}{n}") is None or h.celda(f"{c}{n}").vacia) and not base.celda(f"{c}{n}").formula})

    def test_actividades(self):
        self.assertEqual(self.vacias("Actividades_Carga", (8, 9, 10)), ["Retrabajo %"])        # sin dato no se inventa un retrabajo

    def test_riesgos_responsabilidades_competencias_interacciones_y_sistemas(self):
        self.assertEqual(self.vacias("Riesgos_Mejoras", (8, 9)), [])
        self.assertEqual(self.vacias("Responsabilidades", (8, 9)), [])
        self.assertEqual(self.vacias("Competencias", (8, 9, 10)), [])
        self.assertEqual(self.vacias("Sistemas_Datos", (8,)), [])

    def test_control_y_perfil_completan_los_rotulos_de_texto(self):
        c = self.salida.hoja("Control")
        self.assertTrue(all(c.valor(f"C{n}") not in (None, "") for n in range(9, 17)))
        p = self.salida.hoja("Perfil_Puesto")
        vacios = [p.valor(f"B{9 + 3 * i}") for i in range(len(fx.ROTULOS_PERFIL)) if p.valor(f"B{10 + 3 * i}") in (None, "")]
        self.assertEqual(vacios, [])

    def test_valores_inferidos_por_regla(self):
        h = self.salida.hoja("Riesgos_Mejoras")
        e = {x.valor.replace("*", ""): c for c, x in h.fila(7).items() if isinstance(x.valor, str)}
        self.assertEqual(h.valor(f"{e['Evidencia']}8"), "K4: 2. Actividades Base!L6")                  # referencia al K4: dato, en negro
        self.assertNotEqual(h.celda(f"{e['Evidencia']}8").color_letra, "FF7030A0")
        self.assertIn(h.valor(f"{e['Impacto']}8"), ("Bajo", "Medio", "Alto"))
        self.assertIn(h.valor(f"{e['Prioridad']}8"), ("Baja", "Media", "Alta"))
        self.assertTrue(h.valor(f"{e['Causa raíz']}9").startswith("A validar: "))

    def test_sin_codigo_de_puesto_valido_la_columna_queda_a_validar(self):
        parte = Libro(self.k4).hoja("8. Información General").parte
        sin_codigo = modificar(self.k4, self.dir / "k4_sin_codigo.xlsx", parte, lambda t: t.replace("CMP-001", "sin codigo"))
        resultado, _, _ = vaciar_k4(sin_codigo, self.plantilla, self.dir / "sin_codigo.xlsx")
        salida = Libro(self.dir / "sin_codigo.xlsx")
        self.assertEqual(salida.hoja("Actividades_Carga").valor("B8"), "A validar: código del puesto")
        self.assertEqual(salida.hoja("Control").valor("C11"), "A validar: código puesto")
        self.assertEqual(salida.hoja("Actividades_Carga").celda("B8").color_letra, "FF7030A0")
        self.assertTrue(salida.hoja("Actividades_Carga").celda("B8").nota.startswith("A validar:"))

    def test_las_fechas_no_se_completan_y_van_a_puntos(self):
        puntos = {(p["hoja"], p["campo"]): p["tipo"] for p in self.resultado.puntos}
        self.assertEqual(puntos[("Control", "Fecha de entrevista y fecha de vigencia")], "Dato faltante")

    def test_el_resumen_cuenta_inferidos_y_a_validar(self):
        from corpus_org.consulta.vaciado.resumen import texto_resultado
        texto = "\n".join(texto_resultado(self.resultado, leer_k4(self.k4), "k4.xlsx", "p.xlsx", 1))
        self.assertRegex(texto, r"Celdas en letra morada con nota \(validar a mano\): .* — Inferido: \d+ · A validar: \d+")


class InferenciaTest(unittest.TestCase):
    def test_valor_de_la_actividad(self):
        from corpus_org.consulta.vaciado import inferencia as i
        self.assertEqual(i.valor_de_actividad("Reprocesar pedidos devueltos", "Core")[0], "NVA")
        self.assertEqual(i.valor_de_actividad("Preparar el informe de cumplimiento", "Core")[0], "NVA-N")
        self.assertEqual(i.valor_de_actividad("Negociar contratos", "Gobierno/Control")[0], "NVA-N")
        self.assertEqual(i.valor_de_actividad("Atender solicitudes", "Soporte")[0], "NVA-N")
        self.assertEqual(i.valor_de_actividad("Negociar contratos", "Core")[0], "VA")

    def test_tipo_y_cliente(self):
        from corpus_org.consulta.vaciado import inferencia as i
        self.assertEqual(i.tipo_de_proceso("Aprobar presupuestos")[0], "Gobierno/Control")
        self.assertEqual(i.tipo_de_proceso("Registrar facturas")[0], "Soporte")
        self.assertEqual(i.tipo_de_proceso("Vender productos")[0], "Core")
        self.assertEqual(i.cliente_de("Atender al cliente del hospital")[0], "Externo")
        self.assertEqual(i.cliente_de("Coordinar con el equipo de la gerencia")[0], "Interno")
        self.assertEqual(i.cliente_de("Reunir al equipo y al proveedor")[0], "Mixto")
        self.assertEqual(i.cliente_de("Hacer algo")[0], "Interno")

    def test_impacto_probabilidad_accion_esfuerzo_y_prioridad_usan_solo_valores_de_las_listas(self):
        from corpus_org.consulta.vaciado import inferencia as i, valores
        self.assertEqual(i.impacto_de(30, 100)[0], "Alto")
        self.assertEqual(i.impacto_de(8, 100)[0], "Medio")
        self.assertEqual(i.impacto_de(1, 100)[0], "Bajo")
        self.assertEqual(i.impacto_de(0, 100)[0], "Medio")
        self.assertEqual(i.probabilidad_de(0.1)[0], "Alto")
        self.assertEqual(i.probabilidad_de(None)[0], "Medio")
        combinaciones = [(v, a, h, r) for v in ("VA", "NVA-N", "NVA") for a in ("Manual", "Automatizada", None) for h in (0, 20) for r in (None, 0.2)]
        for v, a, h, r in combinaciones:
            accion = i.accion_de(v, a, h, r)[0]
            self.assertIn(accion, valores.ACCIONES)
            self.assertIn(i.esfuerzo_de(accion)[0], valores.ESCALA)
        for imp in valores.NIVELES_DE_RIESGO:
            for prob in valores.NIVELES_DE_RIESGO:
                self.assertIn(i.prioridad_de(imp, prob)[0], valores.PRIORIDADES)
        self.assertEqual(i.prioridad_de("Alto", "Alto")[0], "Alta")
        self.assertEqual(i.prioridad_de("Bajo", "Bajo")[0], "Baja")

    def test_coincidencia_de_palabras_y_nivel_del_cargo(self):
        from corpus_org.consulta.vaciado import inferencia as i
        funciones = ["Definir y dirigir la estrategia comercial institucional", "Revisar el presupuesto anual"]
        self.assertEqual(i.coincidencia("Actualizar la estrategia comercial", funciones)[0], funciones[0])
        self.assertIsNone(i.coincidencia("Archivar documentos", funciones))
        self.assertEqual(i.tipo_de_competencia("Liderazgo de equipos")[0], "Conductual")
        self.assertEqual(i.tipo_de_competencia("Legislación laboral")[0], "Regulatoria")
        self.assertEqual(i.tipo_de_competencia("Idiomas")[0], "Técnica")
        self.assertEqual(i.nivel_del_cargo("Director Comercial Institucional")[0], "Directivo")
        self.assertEqual(i.nivel_del_cargo("Analista de Compras")[0], "Profesional / operativo")
        self.assertIsNone(i.nivel_del_cargo("Cargo raro"))

    def test_frecuencia_y_nivel_aproximados(self):
        self.assertEqual(valores.frecuencia_aproximada("Mensual / a demanda"), "Mensual")
        self.assertEqual(valores.frecuencia_aproximada("Continua"), "Diaria")
        self.assertEqual(valores.frecuencia_aproximada("Por evento"), "Eventual")
        self.assertEqual(valores.frecuencia_aproximada("Anual / trimestral"), "Anual")
        self.assertIsNone(valores.frecuencia_aproximada("N/D"))
        self.assertEqual(valores.nivel_aproximado("Intermedio-avanzado"), "Avanzado")
        self.assertEqual(valores.nivel_aproximado("Alto"), "Avanzado")
        self.assertEqual(valores.nivel_aproximado("básico"), "Básico")
        self.assertIsNone(valores.nivel_aproximado("???"))


class VerificacionTest(VaciadoBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.resultado, _, _ = cls().vaciar("ok.xlsx")
        cls.ok = cls.dir / "ok.xlsx"

    def errores(self, salida, esperadas=None):
        return verificar(self.plantilla, salida, self.resultado.escritas if esperadas is None else esperadas,
                         colores=self.resultado.colores, notas=self.resultado.notas)

    def test_archivo_correcto(self):
        self.assertEqual(self.errores(self.ok), [])

    def test_detecta_una_formula_cambiada(self):
        s = modificar(self.ok, self.dir / "t1.xlsx", "xl/worksheets/sheet6.xml", lambda t: t.replace("<f>IFERROR(K8*0,0)</f>", "<f>IFERROR(K8*1,0)</f>", 1))
        self.assertTrue(any("fórmula" in e for e in self.errores(s)))

    def test_detecta_listas_desplegables_perdidas(self):
        s = modificar(self.ok, self.dir / "t2.xlsx", "xl/worksheets/sheet6.xml", lambda t: re.sub(r"<extLst>.*</extLst>", "", t, flags=re.S))
        self.assertTrue(any("listas desplegables" in e for e in self.errores(s)))

    def test_detecta_un_cambio_que_no_se_pidio(self):
        s = modificar(self.ok, self.dir / "t3.xlsx", "xl/worksheets/sheet2.xml", lambda t: t.replace("<v>", "<v>", 1).replace(
            '<c r="B9" t="inlineStr"><is><t xml:space="preserve">Área / unidad*', '<c r="B9" t="inlineStr"><is><t xml:space="preserve">Otra cosa', 1))
        self.assertTrue(any("cambió sin haberse pedido" in e for e in self.errores(s)))

    def test_detecta_un_valor_distinto_al_esperado(self):
        s = modificar(self.ok, self.dir / "t4.xlsx", "xl/worksheets/sheet2.xml", lambda t: t.replace("Analista de Compras", "Otro puesto", 1))
        self.assertTrue(any("se esperaba" in e for e in self.errores(s)))

    def test_detecta_escritura_en_una_celda_que_no_es_de_entrada(self):
        esperadas = dict(self.resultado.escritas)
        esperadas[("Control", "B9")] = "Área / unidad*"                # un rotulo (sin relleno gris)
        self.assertTrue(any("no es una celda de entrada" in e for e in self.errores(self.ok, esperadas)))

    def test_detecta_partes_que_no_debian_tocarse(self):
        s = modificar(self.ok, self.dir / "t5.xlsx", "xl/styles.xml", lambda t: t.replace('fgColor rgb="FFFFFF00"', 'fgColor rgb="FF00FF00"'))
        self.assertTrue(any("styles.xml" in e for e in self.errores(s)))

    def test_vaciar_k4_borra_la_salida_si_la_verificacion_falla(self):
        destino = self.dir / "fallida.xlsx"
        with mock.patch("corpus_org.consulta.vaciado.verificacion.verificar", return_value=["algo no coincide"]):
            with self.assertRaises(VerificacionFallida):
                vaciar_k4(self.k4, self.plantilla, destino)
        self.assertFalse(destino.exists())


class ComandoVaciarTest(VaciadoBase):
    def correr(self, *argv, datos=None):
        flujo = io.StringIO()
        with mock.patch.dict(os.environ, {"CORPUS_DATOS": str(datos or self.dir / "sin_corpus")}):
            codigo = consulta_cli.main(list(argv), uso="uso", flujo=flujo)
        return codigo, flujo.getvalue()

    def test_vaciar_funciona_sin_corpus(self):
        salida = self.dir / "cmd.xlsx"
        codigo, texto = self.correr("vaciar", "--k4", str(self.k4), "--plantilla", str(self.plantilla), "--salida", str(salida))
        self.assertEqual(codigo, 0, texto)
        self.assertTrue(salida.is_file())
        self.assertIn("Verificación: correcta", texto)
        self.assertIn("PV-001", texto)
        self.assertIn("preliminar", texto)

    def test_leer_no_genera_archivo(self):
        codigo, texto = self.correr("vaciar", "--k4", str(self.k4), "--leer")
        self.assertEqual(codigo, 0, texto)
        self.assertIn("Emitir orden de compra", texto)
        self.assertFalse((self.dir / f"Metodologia_{self.k4.stem}.xlsx").exists())

    def test_salida_no_puede_ser_el_k4_ni_la_plantilla(self):
        codigo, texto = self.correr("vaciar", "--k4", str(self.k4), "--plantilla", str(self.plantilla), "--salida", str(self.k4))
        self.assertNotEqual(codigo, 0)
        self.assertIn("no puede ser", texto)

    def test_plantilla_o_k4_inexistentes(self):
        codigo, texto = self.correr("vaciar", "--k4", str(self.dir / "no.xlsx"))
        self.assertNotEqual(codigo, 0)
        self.assertIn("No encuentro el K4", texto)
        codigo, texto = self.correr("vaciar", "--k4", str(self.k4), "--plantilla", str(self.dir / "no.xlsx"))
        self.assertNotEqual(codigo, 0)
        self.assertIn("No encuentro la plantilla", texto)

    def test_complementos_invalidos(self):
        malo = self.dir / "malo.json"
        malo.write_text("[1, 2]", encoding="utf-8")
        codigo, texto = self.correr("vaciar", "--k4", str(self.k4), "--plantilla", str(self.plantilla), "--complementos", str(malo),
                                    "--salida", str(self.dir / "x.xlsx"))
        self.assertNotEqual(codigo, 0)
        self.assertIn("objeto JSON", texto)

    def test_complementos_desde_archivo(self):
        ruta = self.dir / "comp.json"
        ruta.write_text(json.dumps({"evidencias": [{"nombre": "Minuta.docx"}]}), encoding="utf-8")
        codigo, texto = self.correr("vaciar", "--k4", str(self.k4), "--plantilla", str(self.plantilla), "--complementos", str(ruta),
                                    "--salida", str(self.dir / "comp.xlsx"))
        self.assertEqual(codigo, 0, texto)
        self.assertEqual(Libro(self.dir / "comp.xlsx").hoja("Evidencias").valor("D9"), "Minuta.docx")

    def test_donde_sigue_funcionando_sin_corpus(self):
        codigo, texto = self.correr("donde")
        self.assertEqual(codigo, 0, texto)


class PublicacionTest(VaciadoBase):
    def test_las_plantillas_se_copian_al_skill_y_el_vaciado_corre_desde_los_scripts_publicados(self):
        from corpus_org.conversion.publicacion import copiar_formularios
        from corpus_org.conversion.skills import copiar_scripts
        origen = self.dir / "formularios"
        origen.mkdir(exist_ok=True)
        shutil.copy(self.plantilla, origen / "Plantilla_PwC_Levantamiento.xlsx")
        (origen / "~$Plantilla_PwC_Levantamiento.xlsx").write_bytes(b"bloqueo")            # bloqueo de Excel: no se copia
        skill = self.dir / "publicado" / "fuente-corpus"
        copiar_scripts(skill / "scripts")
        copiados = copiar_formularios(skill / "formularios", origen)
        self.assertEqual([Path(c).name for c in copiados], ["Plantilla_PwC_Levantamiento.xlsx"])
        self.assertEqual(copiar_formularios(self.dir / "otro" / "formularios", self.dir / "no_existe"), [])
        entorno = {k: v for k, v in os.environ.items() if not k.startswith("CORPUS_")}
        salida = self.dir / "desde_scripts.xlsx"
        r = subprocess.run([sys.executable, "-I", "-S", str(skill / "scripts" / "corpus.py"), "vaciar", "--k4", str(self.k4),
                            "--salida", str(salida)], capture_output=True, text=True, encoding="utf-8", env=entorno)
        self.assertEqual(r.returncode, 0, r.stdout[-600:] + r.stderr[-600:])
        self.assertIn("Verificación: correcta", r.stdout)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(Libro(salida).hoja("Control").valor("C11"), "CMP-001")


class ChecklistTest(VaciadoBase):
    """Checklist de completitud (Sí / Parcial / No / N/A), carga laboral y calidad 1–5 de un K4 antes de pasarlo a la plantilla."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.k4_leido = leer_k4(cls.k4)
        cls.cl = evaluar(cls.k4_leido, "k4.xlsx")

    def estado(self, prefijo):
        return self.cl.criterio(prefijo).estado

    def test_los_nueve_criterios_con_su_estado(self):
        self.assertEqual([c.estado for c in self.cl.criterios], ["Sí", "Sí", "Parcial", "Sí", "Sí", "N/A", "Parcial", "Parcial", "Parcial"])
        self.assertEqual(self.cl.criterio("Funciones").detalle, "2 funciones y 3 actividades (se esperan al menos 3 funciones)")
        self.assertEqual(self.cl.criterio("Frecuencia y tiempo").detalle, "3 de 3 actividades con tiempo, volumen y período")
        self.assertIn("experiencia", self.cl.criterio("Formación").detalle)
        self.assertEqual(self.cl.criterio("Competencias").detalle, "1 sin nivel")
        self.assertEqual(self.cl.criterio("Indicadores").detalle, "un solo indicador")

    def test_porcentaje_ignora_los_na_y_el_veredicto_marca_las_reservas(self):
        self.assertAlmostEqual(self.cl.porcentaje, (4 + 4 * 0.5) / 8)
        self.assertEqual(self.cl.veredicto, "Con reservas")
        self.assertIn("parcial: Funciones principales", self.cl.motivo_veredicto)

    def test_las_horas_son_las_mismas_que_calcula_el_vaciado_y_la_alerta_usa_la_capacidad(self):
        resultado, _, _ = self.vaciar("chk.xlsx")
        self.assertAlmostEqual(self.cl.horas_mes, resultado.horas_mes, places=6)
        self.assertAlmostEqual(resultado.checklist.horas_mes, resultado.horas_mes)
        self.assertTrue(self.cl.alerta.startswith("Baja: subutilización"), self.cl.alerta)
        self.assertEqual(alerta_de_carga(250, 190.64)[:5], "Alta:")
        self.assertEqual(alerta_de_carga(200, 190.64)[:5], "Media")
        self.assertEqual(alerta_de_carga(150, 190.64), "Sin alerta (79% de la capacidad)")
        self.assertEqual(alerta_de_carga(0, 190.64), "Sin datos")

    def test_calidad_estimada_con_sus_razones(self):
        self.assertEqual((self.cl.coherencia, self.cl.especificidad, self.cl.promedio), (1, 1, 1.0))
        self.assertIn("cargo operativo con 100% de funciones estratégicas", self.cl.detalle_calidad[0])
        self.assertIn("0 de 5 funciones o actividades con detalle concreto", self.cl.detalle_calidad[1])

    def test_pendientes_validar_y_na_no_cuentan_como_dato(self):
        from types import SimpleNamespace
        fila = SimpleNamespace(texto=lambda campo: {"a": "VALIDAR: nombre", "b": "N/D", "c": "Jefe", "d": "0"}.get(campo))
        self.assertIsNone(checklist._dato(fila, "a"))
        self.assertIsNone(checklist._dato(fila, "b"))
        self.assertEqual((checklist._dato(fila, "c"), checklist._dato(fila, "d")), ("Jefe", "0"))

    def test_un_formulario_vacio_no_esta_listo(self):
        vacio = evaluar(K4(), "vacio.xlsx")
        self.assertEqual((vacio.criterio("Datos generales").estado, vacio.criterio("Funciones").estado), ("No", "No"))
        self.assertEqual(vacio.veredicto, "No listo")
        self.assertIn("falta lo esencial", vacio.motivo_veredicto)

    def test_cargo_directivo_con_funciones_operativas_baja_la_coherencia(self):
        from corpus_org.consulta.vaciado.k4 import Fila
        from corpus_org.consulta.vaciado.xlsx import Celda
        def fila(h, **campos):
            return Fila(h, 1, {k: Celda("A1", v) for k, v in campos.items()})
        k4 = K4(tablas={"general": [fila("g", puesto="Director de Compras")],
                        "responsabilidades": [fila("r", funcion="Digitar facturas", nivel="Bajo"), fila("r", funcion="Archivar documentos", nivel="Bajo"),
                                              fila("r", funcion="Definir la estrategia anual", nivel="Alto")]})
        nota, razones = checklist.coherencia(k4)
        self.assertEqual(nota, 1)                      # 5 - 3 (cargo directivo con 67 % operativas) - 1 (responsabilidad baja en 67 %)
        self.assertIn("directivo", razones[0])

    def test_hoja_de_puntos_incluye_el_checklist(self):
        resultado, _, _ = self.vaciar("chk2.xlsx")
        campos = {(p["hoja"], p["campo"]): p for p in resultado.puntos}
        self.assertEqual(campos[("Checklist", "Funciones principales")]["tipo"], "Dato faltante")
        self.assertEqual(campos[("Checklist", "Completitud y calidad del formulario")]["tipo"], "Interpretación")
        self.assertIn("Con reservas", campos[("Checklist", "Completitud y calidad del formulario")]["valor_formato"])
        self.assertNotIn(("Checklist", "Datos generales (reporta a, área, supervisados)"), campos)          # los «Sí» no generan puntos


class ComandoChecklistTest(VaciadoBase):
    def correr(self, *argv):
        flujo = io.StringIO()
        with mock.patch.dict(os.environ, {"CORPUS_DATOS": str(self.dir / "sin_corpus")}):
            codigo = consulta_cli.main(list(argv), uso="uso", flujo=flujo)
        return codigo, flujo.getvalue()

    def test_checklist_de_varios_formularios_en_una_tabla(self):
        vacio = fx.crear_xlsx(self.dir / "vacio.xlsx", [{"nombre": "Instrucciones", "celdas": {"B3": "Nada"}}])
        codigo, texto = self.correr("checklist", "--k4", str(self.k4), str(vacio))
        self.assertEqual(codigo, 0, texto)
        self.assertIn("| Formulario | Datos generales | Propósito | Funciones | Frecuencia y tiempo | Resp. y nivel de decisión | Relaciones |", texto)
        self.assertIn("Veredicto |", texto)
        self.assertIn("k4.xlsx | Sí | Sí | Parcial | Sí | Sí | N/A | Parcial | Parcial | Parcial | 75% |", texto)
        self.assertIn("vacio.xlsx", texto)
        self.assertIn("**Con reservas**", texto)
        self.assertIn("**No listo**", texto)

    def test_vaciar_leer_muestra_el_checklist(self):
        codigo, texto = self.correr("vaciar", "--k4", str(self.k4), "--leer")
        self.assertEqual(codigo, 0, texto)
        self.assertIn("Calidad (estimación heurística)", texto)

    def test_vaciar_incluye_el_checklist_y_exigir_listo_detiene_un_formulario_incompleto(self):
        codigo, texto = self.correr("vaciar", "--k4", str(self.k4), "--plantilla", str(self.plantilla), "--salida", str(self.dir / "v.xlsx"), "--exigir-listo")
        self.assertEqual(codigo, 0, texto)                         # «Con reservas» pasa; solo «No listo» se detiene
        self.assertIn("Checklist del formulario: Con reservas", texto)
        vacio = fx.crear_xlsx(self.dir / "vacio2.xlsx", [{"nombre": "Instrucciones", "celdas": {"B3": "Nada"}}])
        destino = self.dir / "no_debe_existir.xlsx"
        codigo, texto = self.correr("vaciar", "--k4", str(vacio), "--plantilla", str(self.plantilla), "--salida", str(destino), "--exigir-listo")
        self.assertNotEqual(codigo, 0)
        self.assertIn("no está listo", texto)
        self.assertFalse(destino.exists())

    def test_falta_el_archivo(self):
        codigo, texto = self.correr("checklist", "--k4", str(self.dir / "no.xlsx"))
        self.assertNotEqual(codigo, 0)
        self.assertIn("No encuentro el K4", texto)


class SkillMdTest(unittest.TestCase):
    """Copilot rechaza un SKILL.md de más de 30 000 caracteres («Skill instructions must not exceed 30000 characters»)."""

    def test_el_skill_md_del_repositorio_deja_margen_bajo_el_limite(self):
        from corpus_org.comun.estructura import MAX_CARACTERES_SKILL_MD
        texto = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text(encoding="utf-8")
        crlf = len(texto) + texto.count("\n")                       # Windows guarda cada salto de línea como dos caracteres
        self.assertLess(crlf, MAX_CARACTERES_SKILL_MD - 1500, f"SKILL.md tiene {len(texto)} caracteres ({crlf} con CRLF)")

    def test_la_construccion_avisa_si_el_skill_md_es_demasiado_largo(self):
        from types import SimpleNamespace

        from corpus_org.comun.estructura import MAX_CARACTERES_SKILL_MD
        from corpus_org.conversion.modos.construir import _copiar_skill_md
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "fuente-corpus"
            skill.mkdir()
            largo = Path(tmp) / "largo.md"
            largo.write_text("x" * (MAX_CARACTERES_SKILL_MD + 1), encoding="utf-8")
            validacion = SimpleNamespace(avisos=[])
            _copiar_skill_md(SimpleNamespace(skill_md=str(largo)), SimpleNamespace(skill=skill), Path("nota.md"), validacion)
        self.assertTrue(any("30000 characters" in a for a in validacion.avisos), validacion.avisos)


if __name__ == "__main__":
    unittest.main()
