"""Tablas que siguen en la pagina siguiente: se unen en una sola."""

from ....comun.esquema import MARCA_COMBINADA
from ....comun.texto import norm, tokens, unir
from ...secciones import clave_titulo, es_seccion_conocida


MAX_SUELTAS_ENTRE_TABLAS = 3


def _es_suelta_entre_tablas(it):
    """Linea corta que puede quedar entre dos trozos de una tabla partida (fragmento de fila, no un titulo)."""
    if it["tipo"] != "fila":
        return False
    t = it["texto"].strip()
    # una linea en negrita es un titulo (p. ej. la banda «Características Especiales del Puesto» al pie de una
    # pagina): la tabla que sigue en la otra pagina es otra tabla, no su continuacion
    if not t or len(t.split()) > 15 or it.get("bold"):
        return False
    return not es_seccion_conocida(clave_titulo(t))


def _columnas_compatibles(a, b):
    na = len(a["filas"][0]) if a["filas"] else 0
    nb = len(b["filas"][0]) if b["filas"] else 0
    xs_ok = (not a["xs"] or not b["xs"] or len(a["xs"]) != len(b["xs"]) or
             all(abs(x - y) <= 6 for x, y in zip(a["xs"], b["xs"])))
    return na == nb and na > 0 and xs_ok


def _agregar_continuacion(a, b, d, pagina):
    """Agrega las filas de ``b`` a la tabla ``a`` (sin la cabecera repetida; uniendo una fila partida)."""
    filas_b = b["filas"]
    if filas_b and [norm(c) for c in filas_b[0]] == [norm(c) for c in a["filas"][0]]:
        for c in filas_b[0]:
            d.retirados.update(tokens(c))
        filas_b = filas_b[1:]
    if filas_b and not filas_b[0][0].strip() and any(c.strip() for c in filas_b[0][1:]):
        a["filas"][-1] = [
            (unir(x, y.replace(MARCA_COMBINADA, "")) if y.strip() and not y.endswith(MARCA_COMBINADA) else x)
            for x, y in zip(a["filas"][-1], filas_b[0])]
        filas_b = filas_b[1:]
        d.notas.append(f"Página {pagina + 1}: fila de tabla partida entre páginas; se unió con la anterior.")
    a["filas"].extend(filas_b)
    a["pagina_fin"] = pagina


def unir_tablas_continuas(items, d):
    """Une una tabla que continua en la pagina siguiente con la de la pagina anterior.

    Tambien si entre ambos trozos quedaron hasta 3 lineas sueltas cortas (fragmentos de una fila que
    no quedaron en celdas): la tabla se une, las lineas se conservan despues de ella y se emite un
    aviso de estructura para revisarla.
    """
    k = 1
    while k < len(items):
        pb, _, _, b = items[k]
        if b["tipo"] != "tabla":
            k += 1
            continue
        j, medio = k - 1, []
        while j >= 0 and len(medio) < MAX_SUELTAS_ENTRE_TABLAS and _es_suelta_entre_tablas(items[j][3]):
            medio.insert(0, j)
            j -= 1
        if j < 0 or items[j][3]["tipo"] != "tabla":
            k += 1
            continue
        a = items[j][3]
        pa = a.get("pagina_fin", items[j][0])
        if pb != pa + 1 or any(items[m][0] not in (pa, pb) for m in medio) or not _columnas_compatibles(a, b):
            k += 1
            continue
        if b.get("banda") and not b.get("continuacion") and [norm(c) for c in b["filas"][0]] != \
                [norm(c) for c in a["filas"][0]]:
            k += 1          # otra caja con su propia banda («Firma de Aprobación»), no la continuacion de la anterior
            continue
        _agregar_continuacion(a, b, d, pb)
        sueltas = [items[m] for m in medio]
        del items[k]
        for m in reversed(medio):
            del items[m]
        for desplazamiento, it in enumerate(sueltas):
            items.insert(j + 1 + desplazamiento, it)
        if sueltas:
            d.avisos.append(f"p.{pb + 1}: tabla partida entre páginas con {len(sueltas)} líneas sueltas en medio; "
                            "se unió la tabla y las líneas quedaron después de ella")
        k = j + 1 + len(sueltas)
