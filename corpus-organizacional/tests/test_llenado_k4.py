"""Pruebas de ``llenar-k4``: escribir los datos de la entrevista en el K4 en blanco sin tocar su estructura (archivos sinteticos)."""

import copy
import hashlib
import io
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
from corpus_org.consulta.vaciado.estilos import MORADO, NEGRO, Estilos
from corpus_org.consulta.vaciado.llenado_k4 import DatosInvalidos, LlenadoK4, estructura_de, llenar_k4
from corpus_org.consulta.vaciado.metodologia import VerificacionFallida
from corpus_org.consulta.vaciado.verificacion_k4 import verificar_k4
from corpus_org.consulta.vaciado.xlsx import Libro

ROJOS = ("FFFF0000", "FFC00000", "00FF0000")


def modificar(origen, destino, parte, cambio):
    with zipfile.ZipFile(origen) as zo, zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zd:
        for n in zo.namelist():
            datos = zo.read(n)
            if n == parte:
                datos = cambio(datos.decode("utf-8")).encode("utf-8")
            zd.writestr(n, datos)
    return destino


def sha(ruta):
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


DATOS = {
    "colaborador": {"nombre": "Ana", "apellido": "Prueba", "correo": "ana@ejemplo.test", "telefono": "555-0000"},
    "inventario": [{"proceso": "Compras", "actividad": "Emitir orden", "tipo": "Core"}, {"actividad": "Conciliar facturas"},
                   {"proceso": "Gestión", "actividad": "Reportar", "tipo": "Soporte"}, {"actividad": "Archivar"}, {"actividad": "Auditar"}],
    "actividades": [{"actividad": "Emitir orden", "descripcion": "Genera la orden", "recurrencia": "a demanda", "tiempo": 30, "volumen": 5,
                     "periodo": "mensual", "automatizacion": "manual"},
                    {"actividad": "Conciliar facturas", "tiempo": 90, "volumen": 2, "periodo": "Diaria"},
                    {"actividad": "Reportar", "tiempo": 20}, {"actividad": "Archivar", "tiempo": 5}, {"actividad": "Auditar", "tiempo": 60}],
    "herramientas": [{"nombre": "SAP", "tipo": "ERP", "uso": "Órdenes", "dominio": "Avanzado", "frecuencia": "Diaria", "requerido": "Requerido"},
                     {"nombre": "Excel"}],
    "general": [{"puesto": "Analista de Compras", "codigo": "CMP-001", "area": "Compras", "reporta": "Jefe de Compras", "personas": 0,
                 "puestos_cargo": "No aplica"}],
    "responsabilidades": [{"funcion": "Aprobar compras menores", "frecuencia": "Diaria"}],
    "competencias": [{"tipo": "Técnica", "competencia": "Negociación", "nivel": "Avanzado"}],
    "condiciones": [{"horario": "8 a 5", "modalidad": "Híbrido"}],
    "exposicion": ["Disponibilidad: viajes ocasionales"],
}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.base = fx.crear_k4_en_blanco(cls.dir / "base.xlsx")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def datos(self, **cambios):
        d = copy.deepcopy(DATOS)
        d.update(cambios)
        return d

    def llenar(self, nombre="salida.xlsx", **cambios):
        return llenar_k4(self.base, self.datos(**cambios), self.dir / nombre)


class EstilosTest(unittest.TestCase):
    def test_agrega_formatos_al_final_sin_cambiar_los_existentes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = fx.crear_k4_en_blanco(Path(tmp) / "b.xlsx")
            original = zipfile.ZipFile(ruta).read("xl/styles.xml").decode("utf-8")
        e = Estilos(original)
        n_formatos = len(e.formatos)
        self.assertTrue(e.es_rojo(fx.ROJO))
        negro = e.con_color(fx.ROJO, NEGRO)
        self.assertEqual(e.con_color(fx.ROJO, NEGRO), negro)                       # no se duplica
        self.assertFalse(e.es_rojo(negro))
        self.assertEqual(e.color_de_letra(negro), NEGRO)
        self.assertEqual(e.color_de_letra(e.con_color(fx.ROJO, MORADO)), MORADO)
        nuevo = e.texto()
        self.assertIn(f'<cellXfs count="{len(e.formatos)}"', nuevo)
        self.assertGreater(len(e.formatos), n_formatos)
        self.assertTrue(nuevo.startswith(original[:200]))                          # lo anterior queda igual
        self.assertEqual(Estilos(nuevo).formatos[:n_formatos], Estilos(original).formatos)


class LlenadoTest(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.resultado = llenar_k4(cls.base, copy.deepcopy(DATOS), cls.dir / "salida.xlsx")
        cls.libro = Libro(cls.dir / "salida.xlsx")
        cls.base_libro = Libro(cls.base)

    def test_los_encabezados_quedan_iguales_y_las_respuestas_debajo(self):
        for nombre in ("5. Herramientas Tecnológicas", "8. Información General", "2. Actividades Base"):
            antes, despues = self.base_libro.hoja(nombre), self.libro.hoja(nombre)
            fila = 9 if nombre.startswith("5.") else (7 if nombre.startswith("8.") else 8)
            self.assertEqual({c: (x.valor, x.estilo) for c, x in antes.fila(fila).items()},
                             {c: (x.valor, x.estilo) for c, x in despues.fila(fila).items()})
        h5 = self.libro.hoja("5. Herramientas Tecnológicas")
        self.assertEqual([h5.valor(f"{c}9") for c in "BCDEFG"][0], "Nombre de la herramienta o sistema")
        self.assertEqual([h5.valor(f"{c}10") for c in "BCDEFG"], ["SAP", "ERP", "Órdenes", "Avanzado", "Diaria", "Requerido"])

    def test_informacion_general_es_un_solo_registro_horizontal_sin_blancos(self):
        h = self.libro.hoja("8. Información General")
        fila = [h.valor(f"{c}8") for c in "BCDEFGHIJ"]
        self.assertEqual(fila[:6], ["Analista de Compras", "CMP-001", "Compras", "VALIDAR: departamento", "Jefe de Compras",
                                    "VALIDAR: confirmar si existe reporte matricial o regional"])
        self.assertEqual(fila[6:], [0.0, "No aplica", "VALIDAR: ubicación o sucursal"])
        self.assertIsNone(h.valor("B9"))
        self.assertNotIn("Nombre del puesto", [h.valor(f"{c}8") for c in "BCDEFGHIJ"])

    def test_pendientes_en_morado_datos_en_negro_y_nada_en_rojo(self):
        h = self.libro.hoja("8. Información General")
        self.assertEqual(h.celda("E8").color_letra, MORADO)
        self.assertNotIn(h.celda("B8").color_letra, ROJOS)
        self.assertEqual(h.celda("B8").color_letra, NEGRO)
        for hoja in self.libro.hojas:
            rojos = [r for r, c in hoja.celdas.items() if not c.vacia and c.color_letra in ROJOS]
            self.assertEqual(rojos, [], hoja.nombre)
        self.assertEqual(len(self.resultado.borradas), 7 + 8 + 1)               # 7 notas de hoja + 8 ejemplos de competencias + su nota final

    def test_el_texto_rojo_se_borra_incluidas_las_notas_y_los_ejemplos(self):
        self.assertIsNone(self.libro.hoja("1. Inventario de Procesos").valor("B6"))        # «Nota: la información en rojo…»
        comp = self.libro.hoja("9. Competencias")
        self.assertEqual([comp.valor(f"{c}9") for c in "BCD"], ["Técnica", "Negociación", "Avanzado"])   # el ejemplo se reemplazó
        self.assertIsNone(comp.valor("C10"))                                                # el otro ejemplo se borró
        self.assertIsNone(comp.valor("B13"))                                                # y la nota de la hoja
        self.assertIn(("9. Competencias", "B13"), self.resultado.borradas)

    def test_colaborador_exposicion_y_condiciones(self):
        i = self.libro.hoja("Instrucciones")
        self.assertEqual([i.valor(f"E{n}") for n in range(7, 11)], ["Ana", "Prueba", "ana@ejemplo.test", "555-0000"])
        c = self.libro.hoja("10. Condiciones de Trabajo")
        self.assertEqual((c.valor("B9"), c.valor("C9")), ("8 a 5", "Híbrido"))
        self.assertEqual(c.valor("B13"), "Disponibilidad: viajes ocasionales")
        self.assertEqual(c.valor("B12"), "Exposición del puesto a riesgos laborales y disponibilidad")     # el rotulo no se toca

    def test_listas_desplegables_corregidas_y_ampliadas_a_las_filas_nuevas(self):
        h = self.libro.hoja("2. Actividades Base")
        self.assertEqual([h.valor(f"D{n}") for n in (9, 10)], ["A demanda", None])         # «a demanda» → valor de la lista
        self.assertEqual(h.valor("G9"), "Mensual")
        self.assertEqual(h.valor("I9"), "Manual")
        with zipfile.ZipFile(self.dir / "salida.xlsx") as z:
            texto = z.read(self.libro.hoja("2. Actividades Base").parte).decode("utf-8")
        self.assertEqual(sorted(re.findall(r'sqref="([^"]+)"', texto)), ["D9:D13", "G9:G13", "I9:I13"])     # 5 actividades, el marco tenia 3

    def test_filas_nuevas_conservan_el_formato_del_cuerpo(self):
        h = self.libro.hoja("2. Actividades Base")
        self.assertEqual([h.valor(f"B{n}") for n in range(9, 14)], ["Emitir orden", "Conciliar facturas", "Reportar", "Archivar", "Auditar"])
        for n in range(9, 14):
            self.assertNotIn(h.celda(f"B{n}").color_letra, ROJOS)
            self.assertIsNotNone(h.celda(f"E{n}"))
        with zipfile.ZipFile(self.dir / "salida.xlsx") as z:
            texto = z.read(self.libro.hoja("2. Actividades Base").parte).decode("utf-8")
        self.assertNotIn("customHeight", re.search(r'<row r="9"[^>]*>', texto).group(0))      # el alto vuelve a ajustarse al texto

    def test_inventario_agrupa_los_procesos_con_celdas_combinadas(self):
        h = self.libro.hoja("1. Inventario de Procesos")
        self.assertEqual([h.valor(f"C{n}") for n in range(9, 14)], ["Emitir orden", "Conciliar facturas", "Reportar", "Archivar", "Auditar"])
        self.assertEqual((h.valor("B9"), h.valor("B10"), h.valor("B11"), h.valor("B12")), ("Compras", None, "Gestión", None))
        self.assertEqual((h.valor("D9"), h.valor("D11")), ("Core", "Soporte"))
        self.assertEqual(set(h.combinadas), {"B9:B10", "D9:D10", "B11:B13", "D11:D13"})
        self.assertEqual(set(self.resultado.combinadas_quitadas["1. Inventario de Procesos"]), {"B9:B13", "D9:D13"})

    def test_resumen_del_resultado(self):
        self.assertEqual(self.resultado.filas["actividades"], 5)
        self.assertEqual(len(self.resultado.validar), 8)          # Excel sin 5 datos + departamento, reporte matricial y ubicación

    def test_el_archivo_base_no_se_modifica_y_la_verificacion_pasa(self):
        self.assertEqual(verificar_k4(self.base, self.dir / "salida.xlsx", self.resultado), [])
        self.assertEqual(Libro(self.base).hoja("9. Competencias").valor("B9"), "Técnica")           # el base conserva sus ejemplos


class DatosInvalidosTest(Base):
    def errores(self, **cambios):
        with self.assertRaises(DatosInvalidos) as cm:
            self.llenar("x.xlsx", **cambios)
        self.assertFalse((self.dir / "x.xlsx").exists())
        return " | ".join(cm.exception.errores)

    def test_valor_fuera_de_la_lista(self):
        malo = copy.deepcopy(DATOS["actividades"])
        malo[0]["periodo"] = "Cada rato"
        self.assertIn("no está en la lista de «Período del volumen»", self.errores(actividades=malo))

    def test_actividad_que_no_esta_en_el_inventario(self):
        malo = copy.deepcopy(DATOS["actividades"])
        malo[0]["actividad"] = "Algo inventado"
        self.assertIn("no está en el inventario", self.errores(actividades=malo))

    def test_informacion_general_admite_un_solo_registro(self):
        self.assertIn("un solo registro", self.errores(general=DATOS["general"] * 2))

    def test_campos_y_claves_desconocidos(self):
        self.assertIn("el campo «inventado» no existe", self.errores(herramientas=[{"inventado": "x"}]))
        self.assertIn("Claves desconocidas", self.errores(otra_hoja=[]))

    def test_mas_filas_de_las_que_caben_sin_pasar_sobre_otro_contenido(self):
        self.assertIn("admite 3 fila(s)", self.errores(condiciones=[{"horario": str(i)} for i in range(4)]))

    def test_exposicion_con_mas_textos_que_filas(self):
        self.assertIn("admite 2 texto(s)", self.errores(exposicion=["a", "b", "c"]))

    def test_valores_que_no_son_texto_ni_numero(self):
        self.assertIn("debe ser texto o número", self.errores(responsabilidades=[{"funcion": ["lista"]}]))

    def test_base_sin_la_fila_de_encabezados_no_se_llena(self):
        sin = fx.crear_k4_en_blanco(self.dir / "sin_encabezados.xlsx", sin_encabezados_de="5. Herramientas Tecnológicas")
        with self.assertRaises(DatosInvalidos) as cm:
            llenar_k4(sin, self.datos(), self.dir / "y.xlsx")
        self.assertIn("no encuentro la fila de encabezados", cm.exception.errores[0])
        self.assertFalse((self.dir / "y.xlsx").exists())

    def test_base_que_ya_trae_datos_bajo_los_encabezados(self):
        lleno = modificar(self.base, self.dir / "lleno.xlsx", "xl/worksheets/sheet4.xml",
                          lambda t: t.replace('<c r="B10" s="2"/>', '<c r="B10" t="inlineStr"><is><t>Ya escrito</t></is></c>', 1))
        with self.assertRaises(DatosInvalidos):
            llenar_k4(lleno, self.datos(), self.dir / "z.xlsx")


class VerificacionK4Test(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.resultado = llenar_k4(cls.base, copy.deepcopy(DATOS), cls.dir / "ok.xlsx")
        cls.ok = cls.dir / "ok.xlsx"
        cls.hojas = {h.nombre: h.parte for h in Libro(cls.base).hojas}

    def errores(self, salida):
        return verificar_k4(self.base, salida, self.resultado)

    def cambiar(self, nombre, hoja, cambio):
        return modificar(self.ok, self.dir / nombre, self.hojas[hoja], cambio)

    def test_detecta_que_se_borro_el_encabezado(self):
        s = self.cambiar("t1.xlsx", "5. Herramientas Tecnológicas", lambda t: re.sub(r'<row r="9".*?</row>', '<row r="9"/>', t, count=1, flags=re.S))
        errores = self.errores(s)
        self.assertTrue(any("encabezado" in e for e in errores), errores)

    def test_detecta_una_combinada_del_encabezado_que_cambia(self):
        s = self.cambiar("t2.xlsx", "2. Actividades Base", lambda t: t.replace("</sheetData>", '</sheetData><mergeCells count="1"><mergeCell ref="B8:C8"/></mergeCells>', 1))
        self.assertTrue(any("combinadas" in e for e in self.errores(s)))

    def test_detecta_texto_en_rojo(self):
        rojo = fx.ROJO
        s = self.cambiar("t3.xlsx", "6. Responsabilidades del Puesto", lambda t: re.sub(r'(<c r="B9") s="\d+"', rf'\1 s="{rojo}"', t, count=1))
        errores = self.errores(s)
        self.assertTrue(any("roja" in e for e in errores), errores)

    def test_detecta_un_cambio_en_una_celda_que_no_se_pidio(self):
        s = self.cambiar("t4.xlsx", "Instrucciones", lambda t: t.replace("Nombre: ", "Otro: ", 1))
        self.assertTrue(any("cambió sin haberse pedido" in e for e in self.errores(s)))

    def test_detecta_un_pendiente_que_no_esta_en_morado(self):
        parte = self.hojas["8. Información General"]
        con_morado = zipfile.ZipFile(self.ok).read(parte).decode("utf-8")
        celda = re.search(r'<c r="E8" s="(\d+)"', con_morado).group(1)
        s = self.cambiar("t5.xlsx", "8. Información General", lambda t: t.replace(f'<c r="E8" s="{celda}"', f'<c r="E8" s="{fx.NORMAL}"', 1))
        self.assertTrue(any("morado" in e or "formato" in e for e in self.errores(s)))

    def test_detecta_listas_desplegables_perdidas(self):
        s = self.cambiar("t6.xlsx", "2. Actividades Base", lambda t: re.sub(r"<dataValidations.*?</dataValidations>", "", t, flags=re.S))
        self.assertTrue(any("listas" in e for e in self.errores(s)))

    def test_detecta_xml_que_excel_no_abriria(self):
        s = self.cambiar("t7.xlsx", "2. Actividades Base", lambda t: t.replace("</worksheet>", "<roto></worksheet>", 1).replace("<roto>", "<roto", 1))
        self.assertTrue(any("XML" in e or "no es válido" in e for e in self.errores(s)))

    def test_detecta_formatos_existentes_modificados(self):
        s = modificar(self.ok, self.dir / "t8.xlsx", "xl/styles.xml", lambda t: t.replace('<font><b/><sz val="11"/>', '<font><i/><sz val="11"/>', 1))
        self.assertTrue(any("fuentes o formatos" in e for e in self.errores(s)))

    def test_llenar_k4_borra_la_salida_si_la_verificacion_falla(self):
        destino = self.dir / "falla.xlsx"
        with mock.patch("corpus_org.consulta.vaciado.verificacion_k4.verificar_k4", return_value=["algo no coincide"]):
            with self.assertRaises(VerificacionFallida):
                llenar_k4(self.base, self.datos(), destino)
        self.assertFalse(destino.exists())


class ComandoLlenarK4Test(Base):
    def correr(self, *argv):
        flujo = io.StringIO()
        with mock.patch.dict(os.environ, {"CORPUS_DATOS": str(self.dir / "sin_corpus")}):
            codigo = consulta_cli.main(list(argv), uso="uso", flujo=flujo)
        return codigo, flujo.getvalue()

    def test_estructura_describe_donde_se_escribe(self):
        codigo, texto = self.correr("llenar-k4", "--base", str(self.base), "--estructura")
        self.assertEqual(codigo, 0, texto)
        self.assertIn("general · hoja «8. Información General» · encabezados en la fila 7, respuestas desde la fila 8 · un solo registro", texto)
        self.assertIn("valores de periodo: Diaria, Semanal", texto)
        self.assertIn("condiciones · hoja «10. Condiciones de Trabajo»", texto)

    def test_llena_desde_un_json_y_no_toca_la_base(self):
        import json
        datos = self.dir / "datos.json"
        datos.write_text(json.dumps(DATOS, ensure_ascii=False), encoding="utf-8")
        antes, salida = sha(self.base), self.dir / "cmd.xlsx"
        codigo, texto = self.correr("llenar-k4", "--base", str(self.base), "--datos", str(datos), "--salida", str(salida))
        self.assertEqual(codigo, 0, texto)
        self.assertIn("Verificación: correcta", texto)
        self.assertIn("Texto rojo borrado:", texto)
        self.assertIn("VALIDAR: ubicación o sucursal", texto)
        self.assertEqual(sha(self.base), antes)
        self.assertEqual(Libro(salida).hoja("8. Información General").valor("B8"), "Analista de Compras")

    def test_la_salida_no_puede_ser_la_base(self):
        import json
        datos = self.dir / "d2.json"
        datos.write_text(json.dumps(DATOS), encoding="utf-8")
        codigo, texto = self.correr("llenar-k4", "--base", str(self.base), "--datos", str(datos), "--salida", str(self.base))
        self.assertNotEqual(codigo, 0)
        self.assertIn("siempre sobre una copia", texto)

    def test_errores_de_los_datos_no_dejan_archivo(self):
        import json
        datos = self.dir / "d3.json"
        datos.write_text(json.dumps({"general": DATOS["general"] * 2}), encoding="utf-8")
        salida = self.dir / "no.xlsx"
        codigo, texto = self.correr("llenar-k4", "--base", str(self.base), "--datos", str(datos), "--salida", str(salida))
        self.assertNotEqual(codigo, 0)
        self.assertIn("No se escribió el archivo", texto)
        self.assertFalse(salida.exists())

    def test_falta_la_base_o_los_datos(self):
        codigo, texto = self.correr("llenar-k4", "--base", str(self.dir / "no.xlsx"), "--estructura")
        self.assertNotEqual(codigo, 0)
        self.assertIn("No encuentro el K4 base", texto)
        codigo, texto = self.correr("llenar-k4", "--base", str(self.base))
        self.assertNotEqual(codigo, 0)
        self.assertIn("Falta --datos", texto)

    def test_corre_desde_los_scripts_publicados_solo_con_la_biblioteca_estandar(self):
        from corpus_org.conversion.skills import copiar_scripts
        skill = self.dir / "publicado" / "fuente-corpus"
        copiar_scripts(skill / "scripts")
        entorno = {k: v for k, v in os.environ.items() if not k.startswith("CORPUS_")}
        r = subprocess.run([sys.executable, "-I", "-S", str(skill / "scripts" / "corpus.py"), "llenar-k4", "--base", str(self.base),
                            "--estructura"], capture_output=True, text=True, encoding="utf-8", env=entorno)
        self.assertEqual(r.returncode, 0, r.stdout[-500:] + r.stderr[-500:])
        self.assertIn("respuestas desde la fila 8", r.stdout)
        self.assertNotIn("Traceback", r.stderr)


class AnalisisTest(Base):
    def test_estructura_de_reporta_hojas_ausentes(self):
        lineas = estructura_de(self.base)
        self.assertTrue(any("«2.1 actividades…» no está en el archivo" in ln for ln in lineas))

    def test_el_marco_y_el_tope_de_cada_tabla(self):
        llenado = LlenadoK4(self.base, {})
        t = llenado.analizar("actividades")
        self.assertEqual((t.fila_encabezado, t.inicio, t.fin_marco, t.tope), (8, 9, 11, 0))
        c = llenado.analizar("condiciones")
        self.assertEqual((c.inicio, c.tope, c.capacidad), (9, 11, 3))              # el rotulo de exposicion esta en la fila 12
        comp = llenado.analizar("competencias")
        self.assertEqual(comp.tope, 0)                                              # la nota roja del final no es contenido

    def test_copia_de_la_base_intacta_tras_analizar(self):
        antes = sha(self.base)
        LlenadoK4(self.base, {}).analizar("general")
        shutil.copy(self.base, self.dir / "copia.xlsx")
        self.assertEqual(sha(self.base), antes)


if __name__ == "__main__":
    unittest.main()
