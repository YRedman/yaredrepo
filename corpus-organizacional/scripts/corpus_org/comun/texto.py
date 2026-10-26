"""Normalizacion y manipulacion de texto (sin dependencias del dominio)."""

import collections
import re
import unicodedata


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


def sin_acentos(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c))


def norm(s):
    """Minusculas, sin acentos, espacios simples."""
    return re.sub(r"\s+", " ", sin_acentos(s).casefold()).strip()


def tokens(s):
    """Palabras de un texto (NFKC, minusculas) para comparar original y salida."""
    s = unicodedata.normalize("NFKC", s or "").casefold()
    return re.findall(r"\w+", s)


def porcentaje(texto):
    """Numero de un texto de CSV ('99,5 %', '100', '87.3%'). Lanza ValueError si no es un numero."""
    return float(str(texto if texto is not None else "").replace("%", "").replace(",", ".").strip())


RE_NUMERO = re.compile(r"(?<![\w.,])\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?(?!\w)|(?<![\w.,])\d+[.,]\d+(?!\w)")


def numeros(texto):
    """Numeros con separadores tal como aparecen (45.000,00 · 1.5 · 352,600,000).

    ``tokens`` los parte en pedazos ('45', '000', '00'), asi que un numero truncado pasaria la
    verificacion por palabras; se comparan aparte y completos.
    """
    return collections.Counter(RE_NUMERO.findall(texto or ""))


def recortar_palabras(s, n):
    pal = (s or "").split()
    if len(pal) <= n:
        return " ".join(pal)
    return " ".join(pal[:n]) + " …"


def recortar_en_palabra(s, n):
    """Corta ``s`` a lo mas ``n`` caracteres sin partir una palabra y agrega « …» si quito algo."""
    if len(s) <= n:
        return s
    corte = s[:n]
    if not s[n].isspace():                       # el corte cae dentro de una palabra: se vuelve al espacio anterior
        previo = corte.rfind(" ")
        corte = corte[:previo] if previo > n // 2 else corte
    return corte.rstrip() + " …"


def limitar_lineas(texto, n_palabras):
    """Corta un texto multilinea al completar la linea donde se alcanzan n palabras."""
    if len(texto.split()) <= n_palabras:
        return texto
    cuenta, salida = 0, []
    for linea in texto.splitlines():
        cuenta += len(linea.split())
        salida.append(linea)
        if cuenta >= n_palabras:
            break
    return "\n".join(salida) + "\n…"


def unir(a, b):
    """Une dos lineas de un parrafo, deshaciendo la separacion silabica (palabra-\\ncontinuacion)."""
    if not a:
        return b
    if not b:
        return a
    if a.endswith("-") and len(a) > 1 and a[-2].isalpha() and b[0].islower():
        return a[:-1] + b
    if a.endswith(("-", "/")):
        return a + b
    return a + " " + b


def limpiar_celda(s):
    s = (s or "").replace("\r", "\n")
    out = ""
    for parte in (p.strip() for p in s.split("\n")):
        if parte:
            out = unir(out, parte)
    return out.strip()


def patron_frase(frase, flags=0):
    """Regex que encuentra la frase completa (no dentro de otra palabra), tolerando espacios multiples."""
    palabras = [re.escape(p) for p in frase.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(palabras) + r"(?!\w)", flags)


def patron_termino(termino):
    """Termino de busqueda sobre texto normalizado; '*' = cualquier final de palabra; espacios flexibles."""
    partes = [re.escape(p).replace(r"\*", r"\w*") for p in norm(termino).split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(partes) + r"(?!\w)")


def empieza_palabra(clave, texto):
    """True si ``clave`` aparece en ``texto`` al inicio de una palabra ('mision' no coincide con 'comision')."""
    return re.search(r"(?<!\w)" + re.escape(clave), texto) is not None


RE_FIN_ORACION = re.compile(r"(?<=[.;!?])\s+")


def oracion_con(texto, fragmento):
    """Oracion normalizada de ``texto`` que contiene ``fragmento`` (o todo el texto si no se encuentra).

    Sirve para clasificar un verbo o rol con la oracion donde aparece la mencion y no con toda la
    linea: en "El Gerente aprueba. El Jefe recibe." el Jefe no aprueba.
    """
    n, f = norm(texto), norm(fragmento)
    for oracion in RE_FIN_ORACION.split(n):
        if f and f in oracion:
            return oracion
    return n
