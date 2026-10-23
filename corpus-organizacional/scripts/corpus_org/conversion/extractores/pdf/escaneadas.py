"""Paginas escaneadas (sin texto digital): se leen con OCR y se agregan al documento una vez conocido el encabezado."""

import statistics

from ....comun.texto import tokens
from ..maquetacion import agrupar_filas
from ..ocr import configurar_pytesseract
from ..ocr_pagina import CONFIANZA_OBJETIVO, MIN_PALABRAS_TEXTO, leer_pagina
from .lineas import palabras_ocr

MIN_PALABRAS_OCR = MIN_PALABRAS_TEXTO
MAX_CARACTERES_ESCANEADA = 25       # una pagina con menos texto digital que esto y una imagen grande esta escaneada
COBERTURA_IMAGEN_ESCANEADA = 0.4    # fraccion de la pagina que cubre la imagen del escaneo


def _giro(res):
    """'girada 90° y reflejada (espejo)' segun lo que hubo que corregir en la pagina."""
    return " y ".join(([f"girada {res.orientacion}°"] if res.orientacion else []) + (["reflejada (espejo)"] if res.espejo else []))


class PaginasEscaneadas:
    """Lee las paginas escaneadas con OCR. El texto se agrega al final (``aplicar_pendiente``), cuando ya se conocen los
    cortes de encabezado y pie de las paginas digitales."""

    def __init__(self, ctx, info_img):
        self.ctx = ctx
        self.info_img = info_img
        self.pendientes = []          # (pagina, resultado del OCR, altura)
        self.encabezados_ocr = []     # encabezado de cada pagina leida con OCR: se repite, y el voto corrige sus errores

    def es_escaneada(self, i):
        """Casi sin texto y con una imagen que cubre la pagina."""
        ctx = self.ctx
        chars = sum(l["chars"] for l in ctx.paginas_lineas[i])
        area_img = sum(abs(ctx.fitz.Rect(im["bbox"])) for im in self.info_img[i])
        return chars < MAX_CARACTERES_ESCANEADA and area_img > COBERTURA_IMAGEN_ESCANEADA * ctx.anchos[i] * ctx.alturas[i]

    def leer(self, i, page):
        ctx, d = self.ctx, self.ctx.d
        if not ctx.idioma_ocr():
            d.paginas_escaneadas_sin_ocr.append(i + 1)
            ctx.marca(i, 0, 0, f"[PÁGINA ESCANEADA SIN TEXTO: página {i + 1}; no se pudo aplicar OCR]")
            return
        try:
            res = leer_pagina(page, ctx.idioma_ocr(), configurar_pytesseract())
        except Exception as e:
            res = None
            d.notas.append(f"OCR falló en la página {i + 1}: {e}")
        if res is not None and res.palabras_utiles < MIN_PALABRAS_OCR:
            # una foto o ilustracion de pagina completa: el OCR solo saca ruido; se deja como imagen
            d.diagramas.append(i + 1)
            ctx.marca(i, 0, 0, f"[DIAGRAMA O IMAGEN: ver página {i + 1} del documento original]")
            return
        d.paginas_ocr.append(i + 1)
        d.idioma_ocr = ctx.idioma_ocr()
        ctx.marca(i, -1, 0, f"[TEXTO OCR: página {i + 1} escaneada; revisar contra el original]")
        if res is None:
            return
        self._avisar(i, res)
        d.crudo_ocr |= palabras_ocr(res.textos)
        d.confianzas_ocr += res.confianzas
        self._encabezado(res)
        self.pendientes.append((i, res, ctx.alturas[i]))

    def _avisar(self, i, res):
        d = self.ctx.d
        if res.orientacion or res.espejo:
            d.notas.append(f"Página {i + 1} (OCR): estaba {_giro(res)}; se enderezó antes de leerla.")
        if res.firmas:
            d.notas.append(f"Página {i + 1} (OCR): {res.firmas} campo(s) de firma manuscrita ignorados "
                           "(su lectura es ruido, no texto).")
        if res.mejora and res.mejora != "original":
            d.notas.append(f"Página {i + 1} (OCR): imagen mejorada con {res.mejora}; confianza {res.confianza:.0f} %.")
        if res.confianza < CONFIANZA_OBJETIVO:
            d.avisos.append(f"p.{i + 1}: página poco legible (OCR {res.confianza:.0f} % < {CONFIANZA_OBJETIVO:.0f} % "
                            "aun mejorando la imagen): use una versión digital o un escaneo mejor")

    def _encabezado(self, res):
        ctx = self.ctx
        if res.encabezado:
            self.encabezados_ocr.append(list(res.encabezado))
        if res.encabezado and not ctx.encabezado_guardado:
            ctx.d.encabezado = list(res.encabezado)
            ctx.encabezado_guardado = True
        for t in res.encabezado:
            ctx.d.crudo_encabezado.update(tokens(t))

    def aplicar_pendiente(self):
        """Agrega el texto OCR quitando el encabezado y pie, ubicados con la mediana de las otras paginas."""
        ctx = self.ctx
        sups = [c[0] for c in ctx.cortes if c[0] is not None]
        infs = [c[1] for c in ctx.cortes if c[1] is not None]
        lim_sup = statistics.median(sups) if sups else None
        lim_inf = statistics.median(infs) if infs else None
        for i, res, _h in self.pendientes:
            ocr = res.lineas
            if not res.encabezado:   # sin la tabla del formato: se usa el corte de las paginas digitales
                quitadas = [l for l in ocr if (lim_sup is not None and l["y1"] <= lim_sup + 2) or
                            (lim_inf is not None and l["y0"] >= lim_inf - 2)]
                if quitadas:
                    ctx.d.notas.append(f"Página {i + 1} (OCR): se quitaron {len(quitadas)} líneas de encabezado o pie.")
                ocr = [l for l in ocr if l not in quitadas]
            self._agregar_pagina(i, res, ocr)

    def _agregar_pagina(self, i, res, ocr):
        ctx = self.ctx
        for y0, x0, y1, _x1, filas, xs in res.tablas:
            ctx.items.append((i, y0, x0, {"tipo": "tabla", "filas": filas, "xs": xs, "y0": y0, "y1": y1,
                                          "pagina": i, "ocr": True}))
        if res.cajas:
            cajas = sorted(res.cajas)
            ctx.marca(i, cajas[0][0], cajas[0][1],
                      f"[ORGANIGRAMA: cajas de arriba hacia abajo; ver página {i + 1} del original]")
            ctx.items.append((i, cajas[0][0] + 0.01, cajas[0][1],
                              {"tipo": "marca", "texto": " → ".join(c[2] for c in cajas), "pagina": i}))
        for f in agrupar_filas(ocr):
            f["pagina"] = i
            f["ocr"] = True
            ctx.items.append((i, f["y0"], f["x0"], f))
