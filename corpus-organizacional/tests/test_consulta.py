"""Pruebas unitarias de la consulta (corpus en memoria)."""

import unittest

from tests import ayuda  # noqa: F401
from corpus_org.comun.errores import AreaAmbigua, AreaNoEncontrada
from corpus_org.comun.texto import empieza_palabra, oracion_con
from corpus_org.consulta.areas import ResolutorAreas, construir_alias
from corpus_org.consulta.comandos.ficha import resumen_desarrollo
from corpus_org.consulta.modelo import Area, DocumentoCorpus
from corpus_org.consulta.puestos import DetectorPuestos, Puesto
from corpus_org.consulta.roles import rol, verbo


def areas(*pares):
    return {cod: Area(cod, nombre) for cod, nombre in pares}


class AliasTest(unittest.TestCase):
    def test_solo_siglas_del_glosario(self):
        ar = areas(("COM", "Compras"), ("RHU", "Recursos Humanos"))
        glosario = DocumentoCorpus("GLO-GEN-01", "GLO_GEN.md", 0, 5, "Glosario", [
            "| Sigla | Significado |", "|---|---|", "| RRHH | Recursos Humanos |",
            "| Responsable | Compras |", "| Área | Compras |"])
        alias = construir_alias(ar, [glosario])
        self.assertIn("RRHH", alias["RHU"])
        self.assertNotIn("Responsable", alias["COM"])
        self.assertNotIn("Área", alias["COM"])


class ResolutorTest(unittest.TestCase):
    def setUp(self):
        ar = areas(("COM", "Compras"), ("CIN", "Compras Internacionales"), ("ALM", "Almacén"), ("XYZ", ""))
        self.r = ResolutorAreas(ar, construir_alias(ar, []))

    def test_exacto_y_por_codigo(self):
        self.assertEqual(self.r.resolver("almacen"), ("ALM", False))
        self.assertEqual(self.r.resolver("com"), ("COM", False))

    def test_parecido_se_informa(self):
        self.assertEqual(self.r.resolver("Almacenes"), ("ALM", True))

    def test_ambiguo(self):
        with self.assertRaises(AreaAmbigua) as e:
            self.r.resolver("compra")
        self.assertNotIn("XYZ", [c for c, _ in e.exception.candidatos])  # un area sin nombre no coincide con todo

    def test_no_encontrado(self):
        with self.assertRaises(AreaNoEncontrada):
            self.r.resolver("Seguridad")


class PuestosTest(unittest.TestCase):
    def setUp(self):
        self.det = DetectorPuestos([Puesto("DES-COM-01", "Gerente de Compras Nacionales"),
                                    Puesto("DES-COM-02", "Gerente de Compras Internacionales"),
                                    Puesto("DES-ALM-01", "Jefe de Almacén")])

    def test_exacta(self):
        m = self.det.detectar("El Jefe de Almacén recibe")
        self.assertEqual([(x.tipo, x.puesto.codigo) for x in m], [("exacta", "DES-ALM-01")])

    def test_empate_no_se_asigna(self):
        m = self.det.detectar("El Gerente de Compras aprueba")
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0].tipo, "ambigua")
        self.assertFalse(m[0].asignada)
        self.assertEqual({p.codigo for p in m[0].candidatos}, {"DES-COM-01", "DES-COM-02"})


class RolesTest(unittest.TestCase):
    def test_rol_por_oracion(self):
        linea = "El Gerente de Compras aprueba las órdenes. El Jefe de Almacén recibe el material."
        self.assertEqual(rol("", oracion_con(linea, "Jefe de Almacén"), "Responsabilidades"),
                         "Responsabilidad asignada")
        self.assertEqual(rol("", oracion_con(linea, "Gerente de Compras"), "Responsabilidades"), "Aprueba")

    def test_raices_al_inicio_de_palabra(self):
        self.assertEqual(rol("", "El analista confirma la recepción", ""), "Mencionado")
        self.assertEqual(verbo("Se confirma con el proveedor"), "Mención")
        self.assertEqual(rol("Responsable", "cualquier texto", ""), "Ejecuta (responsable del paso)")


class FichaTest(unittest.TestCase):
    def test_palabra_completa(self):
        self.assertTrue(empieza_palabra("mision", "mision del puesto"))
        self.assertFalse(empieza_palabra("mision", "comisiones"))

    def test_cada_tabla_tiene_su_cabecera(self):
        lineas = ["| Paso | Responsable |", "| 1 | Jefe |", "Texto intermedio",
                  "| Paso | Responsable |", "| 2 | Gerente |"]
        r = resumen_desarrollo(lineas)
        self.assertIn("general: 2", r)
        self.assertIn("Jefe; Gerente", r)
        self.assertNotIn("Responsable;", r)


if __name__ == "__main__":
    unittest.main()
