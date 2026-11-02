"""Un libro de Excel como paquete zip: se cambian solo las partes que hacen falta y el resto se copia igual."""

import os
import re
import tempfile
import zipfile
from pathlib import Path

from .hoja_xml import HojaXml
from .xlsx import Libro


RE_CELDA_CON_FORMULA = re.compile(r"<c\b[^>]*?>(?:(?!</c>).)*?<f\b.*?</c>", re.S)
RE_VALOR_GUARDADO = re.compile(r"<v>[^<]*</v>|<v/>")


def _sin_valor(m):
    celda = RE_VALOR_GUARDADO.sub("", m.group(0))
    return re.sub(r'(<c\b[^>]*?) t="(?:str|b|e|n)"', r"\1", celda, count=1)


class Paquete:
    def __init__(self, ruta):
        self.ruta = Path(ruta)
        with zipfile.ZipFile(self.ruta) as z:
            self.orden = z.namelist()
            self.partes = {n: z.read(n) for n in self.orden}
        self._libro = Libro(self.ruta)
        self._hojas_xml = {}
        self._cambios = {}               # parte -> bytes
        self._limpiar_calculados = True

    @property
    def libro(self):
        return self._libro

    def hoja_xml(self, nombre):
        h = self._libro.hoja(nombre)
        if h is None:
            raise KeyError(f"La plantilla no tiene la hoja «{nombre}»")
        if nombre not in self._hojas_xml:
            self._hojas_xml[nombre] = (h.parte, HojaXml(self.partes[h.parte].decode("utf-8")))
        return self._hojas_xml[nombre][1]

    # -- tablas ------------------------------------------------------------------------------------------------

    def parte_de_tabla(self, nombre_hoja):
        h = self._libro.hoja(nombre_hoja)
        for _id, (destino, tipo) in self._libro._relaciones(h.parte).items():
            if tipo.endswith("/table"):
                return destino
        return None

    def capacidad_de_tabla(self, nombre_hoja):
        """Ultima fila de la tabla de la hoja (la que dice su ref); 0 si la hoja no tiene tabla."""
        parte = self.parte_de_tabla(nombre_hoja)
        if parte is None:
            return 0
        m = re.search(r'<table\b[^>]*?\bref="[A-Z]+\d+:[A-Z]+(\d+)"', (self._cambios.get(parte) or self.partes[parte]).decode("utf-8"))
        return int(m.group(1))

    def ampliar_tabla(self, nombre_hoja, ultima_fila, nombre_nuevo=None):
        """Estira la tabla de la hoja hasta ``ultima_fila`` y, si se pide, la renombra (si nada mas usa el nombre)."""
        parte = self.parte_de_tabla(nombre_hoja)
        if parte is None:
            return
        xml = self.partes[parte].decode("utf-8")
        ref = re.search(r'<table\b[^>]*?\bref="([A-Z]+)(\d+):([A-Z]+)(\d+)"', xml)
        nuevo_ref = f"{ref.group(1)}{ref.group(2)}:{ref.group(3)}{max(int(ref.group(4)), ultima_fila)}"
        xml = xml.replace(ref.group(0), ref.group(0).replace(f"{ref.group(1)}{ref.group(2)}:{ref.group(3)}{ref.group(4)}", nuevo_ref), 1)
        xml = re.sub(r'(<autoFilter\b[^>]*?\bref=")[^"]*(")', rf"\g<1>{nuevo_ref}\g<2>", xml, count=1)
        if nombre_nuevo:
            viejo = re.search(r'<table\b[^>]*?\bname="([^"]+)"', xml).group(1)
            usos = sum(p.decode("utf-8", "ignore").count(viejo) for n, p in self.partes.items()
                       if n.endswith((".xml", ".rels")) and n != parte)
            if usos == 0:
                xml = xml.replace(f'name="{viejo}"', f'name="{nombre_nuevo}"').replace(f'displayName="{viejo}"', f'displayName="{nombre_nuevo}"')
        self._cambios[parte] = xml.encode("utf-8")

    # -- libro -------------------------------------------------------------------------------------------------

    def recalcular_al_abrir(self):
        xml = self.partes["xl/workbook.xml"].decode("utf-8")
        if "fullCalcOnLoad" not in xml:
            xml = re.sub(r"<calcPr\b", '<calcPr fullCalcOnLoad="1"', xml, count=1)
        self._cambios["xl/workbook.xml"] = xml.encode("utf-8")

    # -- guardar -----------------------------------------------------------------------------------------------

    def quitar_valores_calculados(self):
        """Borra el valor guardado de las celdas con formula (las formulas no se tocan).

        Lo guardado quedaria desactualizado respecto de los datos nuevos; sin el, Excel y LibreOffice recalculan al abrir."""
        for hoja in self._libro.hojas:
            parte = hoja.parte
            texto = self._cambios.get(parte, self.partes[parte]).decode("utf-8")
            self._cambios[parte] = RE_CELDA_CON_FORMULA.sub(_sin_valor, texto).encode("utf-8")

    def guardar(self, destino):
        destino = Path(destino)
        for _nombre, (parte, hoja) in self._hojas_xml.items():
            if hoja.modificada:
                self._cambios[parte] = hoja.texto().encode("utf-8")
        if self._limpiar_calculados:
            self._cambios_antes = dict(self._cambios)
            self.quitar_valores_calculados()
        destino.parent.mkdir(parents=True, exist_ok=True)
        fd, temporal = tempfile.mkstemp(suffix=".xlsx", dir=str(destino.parent))
        os.close(fd)
        try:
            with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as z:
                for n in self.orden:
                    z.writestr(n, self._cambios.get(n, self.partes[n]))
            os.replace(temporal, destino)
        finally:
            if os.path.exists(temporal):
                os.unlink(temporal)
        return destino

    @property
    def partes_cambiadas(self):
        return sorted(self._cambios)
