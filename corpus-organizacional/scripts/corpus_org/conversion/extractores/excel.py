"""Extractor de libros de Excel (.xlsx, .xlsm) usados como material de contexto.

Cada hoja visible es una tabla (la primera fila no vacia es la cabecera; una hoja de una sola columna son
parrafos). Se leen los valores guardados, no las formulas. Las imagenes pegadas en una hoja (una captura de un
documento, un organigrama) se leen con OCR y quedan bajo una marca, igual que en un PDF.
"""

import collections
import datetime
import io
import zipfile
from pathlib import Path

from ...comun.esquema import RE_MARCAS
from ...comun.texto import numeros, tokens
from ..modelo import DocumentoExtraido, bloque_h
from .base import Extractor
from .imagenes import es_imagen_de_contenido, texto_de_imagen

MAX_IMAGENES_LIBRO = 20      # imagenes del libro cuyo texto se lee con OCR
FILAS_HOJA_GRANDE = 3000     # a partir de aqui se avisa en las notas que la hoja es grande


def valor_texto(celda):
    """Texto de una celda tal como se ve: fechas ISO, enteros sin ``.0``, porcentajes con %."""
    v = celda.value
    if v is None:
        return ""
    if isinstance(v, bool):
        return "VERDADERO" if v else "FALSO"
    if isinstance(v, datetime.datetime):
        return v.strftime("%Y-%m-%d") if (v.hour, v.minute, v.second) == (0, 0, 0) else v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, datetime.date):
        return v.isoformat()
    if isinstance(v, datetime.time):
        return v.strftime("%H:%M")
    if isinstance(v, (int, float)):
        if "%" in (celda.number_format or ""):
            return f"{v * 100:.6g}%"
        if isinstance(v, float):
            if v.is_integer():
                return str(int(v))
            return f"{v:.8f}".rstrip("0").rstrip(".")
        return str(v)
    return " ".join(str(v).split())


def _tabla_de_hoja(ws):
    """Filas (listas de texto) de la hoja sin filas ni columnas completamente vacias."""
    filas = [[valor_texto(c) for c in fila] for fila in ws.iter_rows()]
    filas = [f for f in filas if any(f)]
    if not filas:
        return []
    ancho = max(len(f) for f in filas)
    filas = [f + [""] * (ancho - len(f)) for f in filas]
    usadas = [j for j in range(ancho) if any(f[j] for f in filas)]
    return [[f[j] for j in usadas] for f in filas]


def abrir_libro(path, data_only=True):
    """Libro de openpyxl desde los bytes del archivo: openpyxl se niega a abrir por la extension (un Excel guardado
    como .csv), pero lee igual desde un flujo."""
    import openpyxl
    return openpyxl.load_workbook(io.BytesIO(Path(path).read_bytes()), data_only=data_only)


def _imagenes_de_hoja(ws):
    """[bytes] de las imagenes que hay en la hoja (openpyxl las conserva con Pillow instalado)."""
    res = []
    for im in getattr(ws, "_images", []):
        try:
            res.append(im._data())
        except Exception:
            continue
    return res


class ExtractorExcel(Extractor):
    extensiones = (".xlsx", ".xlsm")

    def extraer(self, path):
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError("Falta openpyxl para leer Excel: python -m pip install openpyxl")
        path = Path(path)
        try:
            wb = abrir_libro(path)
        except zipfile.BadZipFile:
            raise RuntimeError("El archivo no es un libro de Excel válido (¿protegido con contraseña o dañado?).")
        d = DocumentoExtraido()
        d.paginas = 0
        textos, bloques = [], []
        ocultas = [ws.title for ws in wb.worksheets if ws.sheet_state != "visible"]
        visibles = [ws for ws in wb.worksheets if ws.sheet_state == "visible"]
        imagenes_leidas = 0
        sin_valor = self._formulas_sin_valor(path, visibles)
        for n, ws in enumerate(visibles, 1):
            tabla = _tabla_de_hoja(ws)
            imagenes = _imagenes_de_hoja(ws)
            if not tabla and not imagenes:
                continue
            if len(visibles) > 1 or imagenes:
                bloques.append(bloque_h(1, ws.title))
                textos.append(ws.title)
            if tabla and len(tabla[0]) == 1:                          # una sola columna: texto corrido
                for fila in tabla:
                    bloques.append({"k": "p", "texto": fila[0]})
                    textos.append(fila[0])
            elif tabla:
                bloques.append({"k": "tabla", "filas": tabla})
                d.tablas += 1
                textos += [c for f in tabla for c in f]
                if len(tabla) > FILAS_HOJA_GRANDE:
                    d.notas.append(f"La hoja «{ws.title}» tiene {len(tabla)} filas: considere resumirla.")
            for datos in imagenes:
                if not es_imagen_de_contenido(datos):
                    continue
                if imagenes_leidas >= MAX_IMAGENES_LIBRO:
                    d.imagenes_omitidas += 1
                    continue
                imagenes_leidas += 1
                texto_de_imagen(d, bloques, f"LA HOJA «{ws.title}»", n, datos)
            charts = len(getattr(ws, "_charts", []))
            if charts:
                d.notas.append(f"La hoja «{ws.title}» tiene {charts} gráfico(s): no se leen.")
                bloques.append({"k": "marca", "texto": f"[DIAGRAMA O IMAGEN: gráfico en la hoja «{ws.title}»; "
                                                        "ver el Excel original]"})
        if ocultas:
            d.notas.append("Hojas ocultas que no se leyeron: " + ", ".join(ocultas) + ".")
        if sin_valor:
            d.avisos.append(f"{sin_valor} fórmulas sin valor guardado (celdas que salen vacías): abra el archivo en "
                            "Excel, guárdelo y vuelva a convertir")
        d.bloques = bloques
        crudo = " ".join(textos)
        d.crudo = collections.Counter(tokens(RE_MARCAS.sub(" ", crudo)))
        d.numeros = numeros(crudo)
        if path.suffix.lower() not in self.extensiones:
            d.notas.append(f"El archivo se llama «{path.name}» pero es un libro de Excel: se leyó como Excel.")
        return d

    @staticmethod
    def _formulas_sin_valor(path, visibles):
        """Cantidad de formulas de las hojas visibles que no tienen valor guardado (se leerian como vacias)."""
        try:
            wf = abrir_libro(path, data_only=False)
            wv = abrir_libro(path, data_only=True)
        except Exception:
            return 0
        total = 0
        for ws in visibles:
            if ws.title not in wf.sheetnames:
                continue
            for fila_f, fila_v in zip(wf[ws.title].iter_rows(), wv[ws.title].iter_rows()):
                for cf, cv in zip(fila_f, fila_v):
                    if isinstance(cf.value, str) and cf.value.startswith("=") and cv.value is None:
                        total += 1
        return total
