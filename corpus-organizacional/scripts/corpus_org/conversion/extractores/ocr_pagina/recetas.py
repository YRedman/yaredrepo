"""Mejoras de la imagen antes de leerla de nuevo cuando la confianza es baja (nitidez, brillo, binarizado)."""

def receta_nitidez(img):
    from PIL import ImageFilter, ImageOps
    return ImageOps.autocontrast(img, cutoff=1).filter(ImageFilter.UnsharpMask(radius=2, percent=160, threshold=3))


def _receta_brillo(img):
    """Aclara una pagina oscura u oscurece una palida (gamma segun el gris medio) y estira el contraste."""
    from PIL import ImageOps
    import numpy as np
    media = float(np.asarray(img).mean())
    gamma = 1.0
    if media < 140:
        gamma = 0.6
    elif media > 225:
        gamma = 1.6
    tabla = [int(255 * ((v / 255.0) ** gamma)) for v in range(256)]
    return ImageOps.autocontrast(img.point(tabla), cutoff=1)


def _receta_binarizada(img):
    """Blanco y negro con el umbral de Otsu y sin motas (fondos con ruido o sellos de color)."""
    from PIL import Image, ImageFilter, ImageOps
    import numpy as np
    gris = np.asarray(ImageOps.autocontrast(img, cutoff=1))
    hist = np.bincount(gris.ravel(), minlength=256).astype(float)
    total, suma = hist.sum(), (hist * np.arange(256)).sum()
    mejor, w0, s0, umbral = -1.0, 0.0, 0.0, 128
    for t in range(256):
        w0 += hist[t]
        s0 += t * hist[t]
        if w0 == 0 or w0 == total:
            continue
        m0, m1 = s0 / w0, (suma - s0) / (total - w0)
        entre = w0 * (total - w0) * (m0 - m1) ** 2
        if entre > mejor:
            mejor, umbral = entre, t
    binaria = Image.fromarray(((gris > umbral) * 255).astype("uint8"))
    return binaria.filter(ImageFilter.MedianFilter(3))


RECETAS = (("original", None), ("contraste y nitidez", receta_nitidez), ("brillo y contraste", _receta_brillo),
           ("blanco y negro", _receta_binarizada))
