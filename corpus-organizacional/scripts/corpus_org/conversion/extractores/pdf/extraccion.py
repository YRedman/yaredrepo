"""Extraccion de un PDF concreto: pagina por pagina, con texto o escaneada."""

import collections
import re

from ....comun.esquema import MARCA_COMBINADA
from ....comun.texto import numeros, tokens
from ..maquetacion import agrupar_filas, bloques_desde_items
from .bandas import FilasBanda, bandas_apiladas, cajas_con_texto, es_organigrama, formas_con_texto, rects_banda
from .contexto import ContextoPDF
from .continuas import unir_tablas_continuas
from .encabezado_pie import EncabezadoPie
from .encabezados import consenso_de_encabezados
from .escaneadas import PaginasEscaneadas
from .imagenes_pagina import ImagenesDePagina
from .lineas import dentro
from .tablas import bordes_horizontales_completos, tabla_desde_fitz, unir_celdas


class ExtraccionPDF:
    """Extrae un PDF concreto (una instancia por archivo). Las paginas escaneadas, el encabezado y las imagenes los
    resuelven sus propias clases; esta orquesta y se ocupa del texto, las tablas y los organigramas."""

    def __init__(self, fitz, doc_pdf):
        self.ctx = ContextoPDF(fitz, doc_pdf)
        self.encabezado = EncabezadoPie(self.ctx)
        self.imagenes = ImagenesDePagina(self.ctx)
        self.escaneadas = PaginasEscaneadas(self.ctx, self.imagenes.info_img)
        self.rects_organigrama = []    # (pagina, rect) de organigramas ya agregados como marca
        self.bandas_pagina = []

    def ejecutar(self):
        ctx = self.ctx
        for i, page in enumerate(ctx.pdf):
            if self.escaneadas.es_escaneada(i):
                self.escaneadas.leer(i, page)
            else:
                self._pagina_con_texto(i, page)
        self.escaneadas.aplicar_pendiente()
        d = ctx.d
        d.encabezado = consenso_de_encabezados(d.encabezado, self.escaneadas.encabezados_ocr, d.notas)
        d.crudo = +d.crudo
        d.numeros = +d.numeros
        ctx.items.sort(key=lambda t: (t[0], t[1], t[2]))
        unir_tablas_continuas(ctx.items, d)
        d.tablas = sum(1 for it in ctx.items if it[3]["tipo"] == "tabla")
        d.bloques = bloques_desde_items([it[3] for it in ctx.items])
        return d

    # -- paginas con texto ----------------------------------------------------

    def _pagina_con_texto(self, i, page):
        ctx = self.ctx
        lineas = ctx.paginas_lineas[i]
        h, w = ctx.alturas[i], ctx.anchos[i]
        corte_sup, corte_inf, enc_lineas = self.encabezado.separar(i, page, lineas, h, w)
        tablas = self._tablas(i, page, ctx.fitz.Rect(0, corte_sup, w, corte_inf))
        self.bandas_pagina = rects_banda(page, w, lineas)
        ids_enc_tab = {id(l) for l in enc_lineas}
        tablas += bandas_apiladas(ctx.fitz, page, [l for l in lineas if id(l) not in ids_enc_tab],
                                  [r for r, _, _ in tablas], w, corte_sup, self._termina_en_banda(i - 1))
        lineas = self._organigrama(i, page, lineas, enc_lineas, tablas, w, h)
        self._contenido(i, lineas, enc_lineas, tablas)
        ids_enc = {id(l) for l in enc_lineas}
        # las cajas que ya se leyeron como organigrama no son «un diagrama sin orden»
        sueltas = [l for l in lineas if id(l) not in ids_enc
                   and not any(p == i and dentro(l, r) for p, r in self.rects_organigrama)]
        en_formas = formas_con_texto(page, sueltas, [r for r, _, _ in tablas], w, h)
        if en_formas:
            ctx.d.avisos.append(f"p.{i + 1}: posible diagrama vectorial ({en_formas} líneas de texto dentro de "
                                "formas); su texto quedó como líneas sueltas")
        self.imagenes.agregar(i, corte_sup, corte_inf, w, h)
        self._texto_crudo(page, enc_lineas)

    def _texto_crudo(self, page, enc_lineas):
        """Texto de verificacion (motor principal, pagina completa, sin encabezado ni pie)."""
        d = self.ctx.d
        crudo = re.sub(r"(\w)-\n(?=[a-záéíóúüñ])", r"\1", page.get_text("text"))
        d.crudo.update(tokens(crudo))
        d.numeros.update(numeros(crudo))
        for l in enc_lineas:
            d.crudo.subtract(tokens(l["texto"]))
            d.numeros.subtract(numeros(l["texto"]))

    def _es_caja_con_banda(self, rect, filas):
        """Tabla de una columna cuya primera fila es una banda de color (caja con titulo)."""
        if isinstance(filas, FilasBanda) and not filas.continuacion:
            return True
        return (bool(filas) and all(len(f) == 1 for f in filas) and not getattr(filas, "continuacion", False)
                and any(abs(b.y0 - rect.y0) < 3 and abs(b.x0 - rect.x0) < 6 for b in self.bandas_pagina))

    def _termina_en_banda(self, pagina):
        """La ultima tabla de la pagina (la de mas abajo) es una caja de una columna con banda de titulo."""
        tablas = [it for it in self.ctx.items if it[0] == pagina and it[3]["tipo"] == "tabla"]
        return bool(tablas) and max(tablas, key=lambda it: it[3]["y1"])[3].get("banda", False)

    def _organigrama(self, i, page, lineas, enc_lineas, tablas, w, h):
        """Saca del texto corrido las lineas que estan dentro de cajas de un organigrama y las agrega
        como una marca seguida de las cajas en orden (de arriba hacia abajo). Devuelve las lineas restantes."""
        ids_enc = {id(l) for l in enc_lineas}
        # las cajas ya leidas como organigrama desde una tabla de una columna no se agregan otra vez
        ocupadas = [r for r, _, _ in tablas] + [r for p, r in self.rects_organigrama if p == i]
        libres = [l for l in lineas if id(l) not in ids_enc and not any(dentro(l, r) for r in ocupadas)]
        cajas = cajas_con_texto(page, libres, [r for r, _, _ in tablas], w, h)
        if not cajas:
            return lineas
        usadas = {id(l) for _, ls in cajas for l in ls}
        textos = [unir_celdas(l["texto"].strip() for l in sorted(ls, key=lambda l: (l["y0"], l["x0"])))
                  for _, ls in cajas]
        self._agregar_organigrama(i, cajas[0][0], textos)
        for _, ls in cajas:
            for l in ls:
                self.ctx.d.lineas_diag.append((i + 1, "organigrama", l["texto"]))
        return [l for l in lineas if id(l) not in usadas]

    def _agregar_organigrama(self, i, rect, cajas):
        """Marca de organigrama seguida de sus cajas en orden (de arriba hacia abajo)."""
        self.ctx.marca(i, rect.y0, rect.x0, f"[ORGANIGRAMA: cajas de arriba hacia abajo; ver página {i + 1} del original]")
        self.ctx.items.append((i, rect.y0 + 0.01, rect.x0, {"tipo": "marca", "texto": " → ".join(cajas), "pagina": i}))
        self.rects_organigrama.append((i, rect))

    def _tablas(self, i, page, clip):
        ctx = self.ctx
        tablas = []
        try:
            palabras = page.get_text("words")
            for t in page.find_tables(clip=clip).tables:
                rect = ctx.fitz.Rect(t.bbox)
                filas, xs, limites = tabla_desde_fitz(t, palabras, bordes_horizontales_completos(page, rect))
                if not filas or (len(filas) == 1 and len(filas[0]) == 1):
                    continue  # vacia o recuadro simple: se trata como texto
                if limites:
                    # lo que queda fuera de los bordes reales (organigrama, parrafo) se lee como texto
                    rect = ctx.fitz.Rect(rect.x0, limites[0], rect.x1, limites[1])
                if es_organigrama(t, filas, rect, page.rect.width):
                    self._agregar_organigrama(i, rect, [f[0] for f in filas])
                    continue
                tablas.append((rect, filas, xs))
        except Exception as e:
            ctx.d.notas.append(f"No se pudieron leer tablas en la página {i + 1}: {e}")
        return tablas

    def _contenido(self, i, lineas, enc_lineas, tablas):
        """Reparte las lineas entre tablas y texto. Nunca descarta una linea que no sea encabezado o pie."""
        d = self.ctx.d
        ids_enc = {id(l) for l in enc_lineas}
        contenido = []
        en_tabla = collections.defaultdict(list)
        for l in lineas:
            if id(l) in ids_enc:
                d.lineas_diag.append((i + 1, "encabezado o pie", l["texto"]))
                continue
            if any(p == i and dentro(l, r) for p, r in self.rects_organigrama):
                d.lineas_diag.append((i + 1, "organigrama", l["texto"]))
                continue
            k = next((k for k, (r, _, _) in enumerate(tablas) if dentro(l, r)), None)
            if k is not None:
                en_tabla[k].append(l)
            else:
                contenido.append(l)
                d.lineas_diag.append((i + 1, "texto", l["texto"]))
        # cada tabla debe contener el texto de las lineas que cubre; lo que no, se conserva como texto
        for k, (r, filas, xs) in enumerate(tablas):
            disponibles = collections.Counter(tokens(" ".join(" ".join(c.replace(MARCA_COMBINADA, "") for c in f)
                                                              for f in filas)))
            propias = sorted(en_tabla.get(k, []), key=lambda l: (l["y0"], l["x0"]))
            sueltas = []
            for l in propias:
                tk = collections.Counter(tokens(l["texto"]))
                if tk - disponibles:
                    sueltas.append(l)
                else:
                    disponibles -= tk
            total = sum(len(tokens(l["texto"])) for l in propias)
            perdidas = sum(len(tokens(l["texto"])) for l in sueltas)
            if total and perdidas > 0.3 * total:
                contenido.extend(propias)
                d.lineas_diag += [(i + 1, "posible tabla tratada como texto", l["texto"]) for l in propias]
                d.avisos.append(f"p.{i + 1}: posible tabla tratada como texto ({perdidas} de {total} palabras "
                                "fuera de celdas)")
                continue
            if sueltas:
                contenido.extend(sueltas)
                d.avisos.append(f"p.{i + 1}: {len(sueltas)} líneas de una tabla fuera de sus celdas; se agregaron "
                                "como texto junto a la tabla")
            d.lineas_diag += [(i + 1, "tabla", l["texto"]) for l in propias]
            self.ctx.items.append((i, r.y0, r.x0, {"tipo": "tabla", "filas": filas, "xs": xs, "y0": r.y0, "y1": r.y1,
                                                   "pagina": i, "banda": self._es_caja_con_banda(r, filas),
                                                   "continuacion": getattr(filas, "continuacion", False)}))
        for f in agrupar_filas(contenido):
            f["pagina"] = i
            self.ctx.items.append((i, f["y0"], f["x0"], f))
