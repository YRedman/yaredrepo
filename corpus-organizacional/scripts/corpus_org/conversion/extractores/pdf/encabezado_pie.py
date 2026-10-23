"""Encabezado y pie de las paginas con texto: se detectan por repeticion, se guardan una vez y se quitan del contenido."""

import re

from ....comun.texto import tokens
from .encabezados import (ZONA_INFERIOR, ZONA_SUPERIOR, SEPARACION_VALOR_ENCABEZADO, clave_rep, corte_superior,
                          detectar_encabezados, encabezado_por_patron, es_clave)
from .lineas import texto_zona

SALTO_MAXIMO_ENCABEZADO = 14      # puntos: un salto mayor entre lineas repetidas termina la zona del encabezado
ALTO_MAXIMO_VALOR = 16            # puntos: una linea mas alta que esto no es el valor de una etiqueta del encabezado


class EncabezadoPie:
    """Separa en cada pagina las lineas de encabezado y pie del contenido."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.claves_sup, self.claves_inf = detectar_encabezados(ctx.paginas_lineas, ctx.alturas)
        self.claves_guardadas = set()

    def separar(self, i, page, lineas, h, w):
        """(corte superior, corte inferior, lineas de encabezado y pie) de la pagina ``i``."""
        ctx = self.ctx
        sup = [l for l in lineas if l["y1"] <= ZONA_SUPERIOR * h and es_clave(clave_rep(l["texto"]), self.claves_sup)]
        inf = [l for l in lineas if l["y0"] >= ZONA_INFERIOR * h and es_clave(clave_rep(l["texto"]), self.claves_inf)]
        if not self.claves_sup and not self.claves_inf:
            sup, inf = encabezado_por_patron(lineas, h)
        corte_sup, corte_inf = 0.0, h
        enc_lineas = []
        if sup:
            fondo = self._fondo(sup, lineas, h)
            corte_sup = corte_superior(page, fondo)
            enc_lineas += [l for l in lineas if l["y1"] <= fondo + 0.5]
        if inf:
            tope = self._tope_del_pie(inf)
            corte_inf = tope - 0.5
            enc_lineas += [l for l in lineas if l["y0"] >= tope - 0.5]
        if enc_lineas:
            if not ctx.encabezado_guardado:
                self._guardar(page, enc_lineas, corte_sup, corte_inf, w, h)
                self.claves_guardadas = {clave_rep(l["texto"]) for l in enc_lineas}
            else:
                enc_lineas = self._sin_texto_unico(i, enc_lineas)
            for l in enc_lineas:
                ctx.d.crudo_encabezado.update(tokens(l["texto"]))
        if sup or inf:
            ctx.cortes.append((corte_sup if sup else None, corte_inf if inf else None))
        return corte_sup, corte_inf, enc_lineas

    @staticmethod
    def _tope_del_pie(inf):
        """Altura donde empieza el pie: sube mientras las lineas repetidas no tengan un salto grande entre ellas."""
        inf = sorted(inf, key=lambda l: -l["y1"])
        tope = inf[0]["y0"]
        for l in inf[1:]:
            if l["y1"] < tope - SALTO_MAXIMO_ENCABEZADO:
                break
            tope = min(tope, l["y0"])
        return tope

    def _sin_texto_unico(self, i, enc_lineas):
        """Deja como contenido las lineas de la zona de encabezado o pie que no estan en el encabezado guardado.

        El encabezado se guarda una sola vez (el de la primera pagina) y en las demas paginas se descarta.
        Una linea que no se parece a ninguna de las guardadas no es un encabezado repetido: si se
        descartara, su texto desapareceria del corpus sin que la verificacion lo notara.
        """
        unicas = [l for l in enc_lineas if len(re.findall(r"[a-z]", clave_rep(l["texto"]))) >= 3
                  and clave_rep(l["texto"]) not in self.claves_guardadas]
        if unicas:
            ids = {id(l) for l in unicas}
            self.ctx.d.avisos.append(f"p.{i + 1}: {len(unicas)} líneas en la zona de encabezado o pie no coinciden "
                                     "con el encabezado de la primera página; se conservaron como contenido")
            return [l for l in enc_lineas if id(l) not in ids]
        return enc_lineas

    @staticmethod
    def _fondo(sup, lineas, h):
        """Zona continua desde arriba: se detiene en el primer salto grande entre lineas repetidas."""
        sup = sorted(sup, key=lambda l: l["y0"])
        fondo = sup[0]["y1"]
        for l in sup[1:]:
            if l["y0"] > fondo + SALTO_MAXIMO_ENCABEZADO:
                break
            fondo = max(fondo, l["y1"])
        # lineas sueltas pegadas al encabezado: el final de una linea partida o el valor numerico que esta
        # debajo de su etiqueta en la misma celda ("Vigencia:" / "01/02/2024", "Página:" / "1 de 3")
        for l in sorted(lineas, key=lambda l: l["y0"]):
            if l["y1"] <= fondo + 0.5:
                continue
            if l["y0"] > fondo + SEPARACION_VALOR_ENCABEZADO or l["y1"] > ZONA_SUPERIOR * h:
                break
            if len(re.findall(r"[A-Za-z]", l["texto"])) < 3 and l["y1"] - l["y0"] <= ALTO_MAXIMO_VALOR:
                fondo = l["y1"]       # el valor ocupa su propia linea (no importa lo alta que quede bajo la etiqueta)
        return fondo

    def _guardar(self, page, enc_lineas, corte_sup, corte_inf, w, h):
        ctx = self.ctx
        fitz = ctx.fitz
        zona_sup = [l for l in enc_lineas if l["y1"] <= corte_sup + 0.5]
        zona_inf = [l for l in enc_lineas if l["y1"] > corte_sup + 0.5]
        ctx.d.encabezado = (
            (texto_zona(page, fitz, zona_sup, fitz.Rect(0, 0, w, corte_sup)) if zona_sup else [])
            + (texto_zona(page, fitz, zona_inf, fitz.Rect(0, corte_inf, w, h)) if zona_inf else []))
        ctx.encabezado_guardado = True
