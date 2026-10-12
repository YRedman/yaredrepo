"""Paquete del corpus para el conocimiento de Copilot (limite de archivos)."""

import tempfile
import unittest
from pathlib import Path

from tests import ayuda  # noqa: F401
from corpus_org.comun.archivos import escribir_csv
from corpus_org.comun.esquema import AVISO_ESCANEADO, COLUMNAS_INDICE
from corpus_org.conversion.copilot import ARCHIVO_INSTRUCCIONES, exportar_copilot


def _publicado(raiz, areas=26, por_area=7):
    pub = raiz / "publicado"
    pub.mkdir(parents=True)
    filas = []
    for a in range(areas):
        sigla = f"A{a:02d}"
        docs = []
        for n in range(1, por_area + 1):
            codigo = f"D-{sigla}-{n:02d}"
            docs.append(f"## [{codigo}] Puesto {n}\n\n" + f"Funciones del puesto {n} del área {sigla}. " * 3)
            filas.append({"codigo": codigo, "departamento": f"Área {sigla}", "nombre_puesto": f"Puesto {n}",
                          "palabras": "0" if (a, n) == (0, 1) else "120",
                          "detalle_avisos": AVISO_ESCANEADO + ": 1" if (a, n) == (0, 1) else ""})
        (pub / f"D_{sigla}.md").write_text("\n\n".join(docs), encoding="utf-8")
    escribir_csv(pub / "indice_corpus.csv", COLUMNAS_INDICE, filas)
    (pub / "contexto.md").write_text("## [C-CTX-01] Organigrama\n", encoding="utf-8")
    (pub / "kpis.csv").write_text("id;indicador;meta\nK-01;Tiempo de entrega;5\n", encoding="utf-8")
    (raiz / "RESUMEN_CONSTRUCCION.md").write_text("- Resultado: **LISTO PARA PUBLICAR**\n", encoding="utf-8")
    return filas


class CopilotTest(unittest.TestCase):
    def test_paquete_dentro_del_limite(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            filas = _publicado(raiz)
            carpeta = exportar_copilot(raiz, 20)
            archivos = sorted(p.name for p in carpeta.iterdir())
            indice = (carpeta / "00_indice_corpus.md").read_text(encoding="utf-8")
            todo = "".join((carpeta / n).read_text(encoding="utf-8") for n in archivos if "descriptivos" in n)
            instrucciones = (raiz / ARCHIVO_INSTRUCCIONES).read_text(encoding="utf-8")
        self.assertEqual(len(archivos), 20)
        self.assertIn("01_contexto.md", archivos)
        self.assertIn("02_indicadores.md", archivos)
        for f in filas:   # cada documento esta una vez, y el indice dice en que archivo
            self.assertEqual(todo.count(f"## [{f['codigo']}]"), 1)
            self.assertRegex(indice, rf"\| {f['codigo']} \|.*\| \d\d_descriptivos_[A-Z0-9-]+\.md \|")
        self.assertIn("SIN TEXTO (escaneado)", indice)
        self.assertIn("LISTO PARA PUBLICAR", instrucciones)

    def test_pocas_areas_un_archivo_por_area(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            _publicado(raiz, areas=3, por_area=2)
            archivos = sorted(p.name for p in exportar_copilot(raiz, 20).iterdir())
        self.assertEqual(len(archivos), 6)
        self.assertIn("03_descriptivos_A00.md", archivos)


if __name__ == "__main__":
    unittest.main()
