"""Construccion del inventario maestro a partir de las rutas de lista.txt."""

import collections
import difflib
import itertools
import os

from ...comun.esquema import INVENTARIO_ACTIVO, INVENTARIO_RETIRADO
from ...comun.texto import norm
from ...comun.tipos import TIPOS_AREA, tipo as tipo_documento
from ..configuracion import EXT_RECONOCIDAS
from .claves import clave_documento, nombre_de_tipo, orden_de_tipo, plural_de_tipo, quitar_duplicados
from .departamentos import ancho_numeracion, asignar_codigos, nombre_departamento
from .modelo import Inventario, InventarioBase

PARECIDO_DE_DEPARTAMENTOS = 0.85


def fila_de_inventario(codigo, codigo_tipo, cod_dep, departamento, f, obs):
    return {"codigo": codigo, "tipo": tipo_documento(codigo_tipo).nombre, "codigo_departamento": cod_dep,
            "departamento": departamento, "archivo": f["archivo"], "ruta_original": f["ruta"], "observaciones": obs,
            "estado_inventario": INVENTARIO_ACTIVO}


def _departamentos(filas):
    """{departamento normalizado: nombre} en orden alfabetico."""
    deps = collections.OrderedDict()
    for f in sorted(filas, key=lambda f: norm(f["departamento"])):
        deps.setdefault(norm(f["departamento"]), f["departamento"])
    return deps


def _codigos_de_departamento(deps, codigos_fijados, base):
    """Los codigos del catalogo mandan; despues los del inventario base; el resto se propone."""
    fijados = dict(codigos_fijados or {})
    for k, cod in base.departamentos.items():
        if k in deps and k not in fijados:
            fijados[k] = cod
    return asignar_codigos(deps, fijados, reservados=set(base.departamentos.values()))


def _numerar_documentos(inv, filas, deps, codigos, base):
    """Un codigo por documento: el del inventario base si ya estaba, o el siguiente de su grupo (tipo y departamento).

    Devuelve (documentos del base que siguen, codigos nuevos, {(tipo, documento): codigo})."""
    grupos = collections.defaultdict(list)
    for f in filas:
        grupos[(f["tipo"], norm(f["departamento"]))].append(f)
    nuevos, vistos, por_documento = [], set(), {}
    for (tipo, kdep), lista_f in sorted(grupos.items(), key=lambda kv: (orden_de_tipo(kv[0][0]), codigos[kv[0][1]])):
        lista_f.sort(key=lambda f: (norm(os.path.splitext(f["archivo"])[0]), f["archivo"]))
        for n, c in collections.Counter(norm(f["archivo"]) for f in lista_f).items():
            if c > 1:
                inv.avisos.append(f"Archivo repetido en {plural_de_tipo(tipo)}/{deps[kdep]}: {n}")
        cod_dep = codigos[kdep]
        siguiente = base.maximos[(tipo, cod_dep)]
        ancho = ancho_numeracion(max(len(lista_f), siguiente))
        for f in lista_f:
            obs = "Formato .doc antiguo: guardarlo como .docx o PDF antes de convertir" \
                if f["archivo"].lower().endswith(".doc") else ""
            clave = (tipo, kdep, clave_documento(f["archivo"]))
            if clave in base.documentos:
                codigo = base.documentos[clave]["codigo"]
                vistos.add(clave)
            else:
                siguiente += 1
                codigo = f"{tipo}-{cod_dep}-{siguiente:0{ancho}d}"
                if base.documentos:
                    nuevos.append(codigo)
                    obs = (obs + "; " if obs else "") + "NUEVO respecto del inventario base"
            inv.documentos.append(fila_de_inventario(codigo, tipo, cod_dep, deps[kdep], f, obs))
            por_documento[(tipo, clave_documento(f["archivo"]))] = codigo
    return vistos, nuevos, por_documento


def _retirar_documentos(inv, base, vistos, por_documento):
    """Los documentos del inventario base que ya no estan quedan RETIRADOS (su codigo se reserva). Si el mismo
    documento cambio de area, su codigo anterior se registra como equivalencia. Devuelve los codigos retirados."""
    retirados = []
    for clave, f in base.documentos.items():
        if clave in vistos:
            continue
        nuevo = por_documento.get((clave[0], clave[2]))
        if nuevo and nuevo != f["codigo"]:       # el mismo documento cambio de area: tiene otro codigo
            inv.equivalencias.append((f["codigo"], nuevo))
            motivo = f"RETIRADO: el documento pasó a {nuevo} (cambió de área); el código queda reservado"
        else:
            retirados.append(f["codigo"])
            motivo = "RETIRADO: no está en la lista actual; el código queda reservado"
        inv.documentos.append(dict(f, estado_inventario=INVENTARIO_RETIRADO, observaciones=motivo))
    return retirados


def _avisos_de_cambios(inv, nuevos, retirados):
    if nuevos:
        inv.avisos.append(f"Documentos nuevos (códigos agregados al final): {', '.join(nuevos)}")
    if retirados:
        inv.avisos.append(f"Documentos del inventario base que ya no están (códigos reservados): {', '.join(retirados)}")
    if inv.equivalencias:
        inv.avisos.append(f"Documentos que cambiaron de área ({len(inv.equivalencias)}): su código anterior queda "
                          "reservado y la equivalencia en equivalencias_codigos.csv")


def _avisar_departamentos_parecidos(inv, deps):
    for a, b in itertools.combinations(list(deps), 2):
        if difflib.SequenceMatcher(None, a, b).ratio() >= PARECIDO_DE_DEPARTAMENTOS:
            inv.avisos.append(f"Nombres de departamento muy parecidos (¿son el mismo?): '{deps[a]}' y '{deps[b]}'")


def _catalogo(filas, deps, codigos):
    """Una fila por departamento: su codigo y cuantos documentos tiene de cada tipo."""
    catalogo = []
    for k, nombre in deps.items():
        fila_cat = {"departamento": nombre, "codigo": codigos[k]}
        for t in TIPOS_AREA:
            fila_cat[t] = sum(1 for f in filas if norm(f["departamento"]) == k and f["tipo"] == t)
        catalogo.append(fila_cat)
    return sorted(catalogo, key=lambda r: r["codigo"])


def construir_inventario(filas, ignoradas, codigos_fijados=None, incluir_duplicados=False, base=None):
    """Inventario maestro a partir de las rutas de lista.txt.

    Con ``base`` (el inventario anterior) los codigos no cambian: cada documento conserva el suyo, los
    nuevos se numeran despues del mayor codigo de su grupo y los que ya no estan quedan RETIRADOS
    (su codigo queda reservado y no se reutiliza). Sin ``base`` se numera en orden alfabetico.
    """
    base = base or InventarioBase()
    inv = Inventario(ignoradas=ignoradas, rutas_validas=len(filas))
    filas = [dict(f, departamento=nombre_departamento(f["departamento"])) for f in filas]
    filas, inv.avisos = quitar_duplicados(filas, incluir_duplicados)
    deps = inv.departamentos = _departamentos(filas)
    codigos = _codigos_de_departamento(deps, codigos_fijados, base)
    vistos, nuevos, por_documento = _numerar_documentos(inv, filas, deps, codigos, base)
    retirados = _retirar_documentos(inv, base, vistos, por_documento)
    _avisos_de_cambios(inv, nuevos, retirados)
    inv.documentos.sort(key=lambda f: (orden_de_tipo(f["codigo"].split("-")[0]), f["codigo"]))
    _avisar_departamentos_parecidos(inv, deps)
    inv.catalogo = _catalogo(filas, deps, codigos)
    return inv


def inventario_provisional(entradas, tipo, codigo_dep, departamento):
    """Inventario con los archivos adjuntos de UN departamento (orden alfabetico), sin lista.txt."""
    filas = [{"tipo": tipo, "departamento": departamento, "archivo": p.name, "path": p}
             for p in entradas if p.suffix.lower() in EXT_RECONOCIDAS]
    filas, _avisos = quitar_duplicados(filas)
    docs = sorted((f["path"] for f in filas), key=lambda p: (norm(os.path.splitext(p.name)[0]), p.name))
    ancho = ancho_numeracion(len(docs))
    return [{"codigo": f"{tipo}-{codigo_dep}-{i:0{ancho}d}", "tipo": nombre_de_tipo(tipo), "codigo_departamento": codigo_dep,
             "departamento": departamento, "archivo": p.name} for i, p in enumerate(docs, 1)]
