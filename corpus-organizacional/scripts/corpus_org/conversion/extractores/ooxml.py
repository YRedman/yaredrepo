"""Utilidades comunes a los formatos Office Open XML (Word, PowerPoint)."""


def nombre_local(el):
    """Nombre de un elemento XML sin su espacio de nombres ('{...}p' -> 'p'); los comentarios y las instrucciones de
    proceso de lxml no tienen un nombre de texto y se devuelven tal cual."""
    t = el.tag
    return t.split("}", 1)[1] if isinstance(t, str) and "}" in t else t
