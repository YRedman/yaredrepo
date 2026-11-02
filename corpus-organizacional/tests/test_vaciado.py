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
from corpus_org.consulta.vaciado.k4 import evaluar_aritmetica, leer_k4
from corpus_org.consulta.vaciado.metodologia import VerificacionFallida, vaciar_k4
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


def celdas_de(libro, hoja, columna):
    h = libro.hoja(hoja)
    return {n: h.valor(f"{columna}{n}") for n in range(8, 31)}


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
        self.assertIn('<dimension ref="B7:Q40"/>', h.texto())

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
        self.assertIsNone(fila(10, "Meses/año activos"))             # estacional: se pregunta
        self.assertEqual(fila(10, "% dedicación personal"), 0.5)      # 30 de 60 minutos
        self.assertEqual(fila(8, "% dedicación personal"), 1)
        self.assertIsNone(fila(10, "Automatización"))                # «Rara vez» no esta en la lista
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
        self.assertIsNone(comp.valor("E10"))                  # «Otra» no esta en la lista
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
            self.assertEqual(zo.namelist(), zs.namelist())
            cambiadas = {n for n in zo.namelist() if zo.read(n) != zs.read(n)}
            self.assertTrue(all(n.startswith(("xl/worksheets/sheet", "xl/tables/")) or n == "xl/workbook.xml" for n in cambiadas), cambiadas)
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
        self.assertIsNone(c.valor("C15"))                                  # K4 y reunión difieren: vacía
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


class VerificacionTest(VaciadoBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.resultado, _, _ = cls().vaciar("ok.xlsx")
        cls.ok = cls.dir / "ok.xlsx"

    def errores(self, salida, esperadas=None):
        return verificar(self.plantilla, salida, self.resultado.escritas if esperadas is None else esperadas)

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
        self.assertTrue(any("xl/styles.xml" in e for e in self.errores(s)))

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


if __name__ == "__main__":
    unittest.main()
