"""Contrato de los modos de ``convertir.py`` y utilidades que comparten."""

from abc import ABC, abstractmethod
from pathlib import Path

from ..lote import OpcionesConversion, trabajadores_por_defecto

CARPETA_SALIDA_CONSTRUCCION = "salida_corpus"


class Modo(ABC):
    """Un modo de ``convertir.py``. Para agregar uno nuevo: subclase + registro en ``modos``."""

    nombre = ""

    def configurar(self, parser):
        """Declara los argumentos propios del modo (``--entrada`` y ``--salida`` ya estan)."""

    @abstractmethod
    def ejecutar(self, args):
        """Hace el trabajo del modo y muestra el resultado en la consola."""


def agregar_argumentos_de_lista(parser):
    """Argumentos de los modos que arman el inventario desde una lista de archivos."""
    parser.add_argument("--lista", default="lista.txt")
    parser.add_argument("--catalogo", default=None, help="catalogo.csv editado con los códigos de departamento.")
    parser.add_argument("--incluir-duplicados", action="store_true",
                        help="Conserva el mismo documento en .pdf y .docx o sus copias '(1)'.")


def agregar_argumentos_de_conversion(parser):
    """Argumentos de los modos que convierten documentos."""
    parser.add_argument("--sin-verificacion-cruzada", action="store_true")
    parser.add_argument("--tiempo-max", type=float, default=0,
                        help="Segundos máximos; lo que no alcance queda como pendiente.")
    parser.add_argument("--trabajadores", type=int, default=0,
                        help="Documentos que se convierten a la vez (0 = automático según los núcleos, 1 = uno a uno).")


def carpeta_salida(args):
    """Carpeta de salida del modo (se crea si no existe): ``--salida`` o ``<entrada>/salida``."""
    s = Path(args.salida) if args.salida else Path(args.entrada) / "salida"
    s.mkdir(parents=True, exist_ok=True)
    return s


def raiz_de_construccion(args):
    """Carpeta de una construccion completa: ``--salida`` o ``<entrada>/salida_corpus``."""
    if args.salida:
        return Path(args.salida).resolve()
    return Path(args.entrada).resolve() / CARPETA_SALIDA_CONSTRUCCION


def trabajadores(args):
    """--trabajadores N (0 o sin indicar = automatico, 1 = un documento a la vez)."""
    n = getattr(args, "trabajadores", 0) or 0
    return n if n >= 1 else trabajadores_por_defecto()


def opciones_de_conversion(args):
    return OpcionesConversion(verificacion_cruzada=not args.sin_verificacion_cruzada,
                              tiempo_max=args.tiempo_max or 0, raiz_entrada=getattr(args, "entrada", None),
                              raiz_contexto=getattr(args, "contexto", None), trabajadores=trabajadores(args))


def imprimir_archivos_generados(rutas):
    print()
    print("ARCHIVOS GENERADOS")
    for p in rutas:
        print(f"- {p}")
